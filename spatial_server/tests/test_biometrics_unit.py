from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Optional

import cv2
import httpx
import numpy as np
import pytest

from spatial_server.biometrics import (
    BiometricCropStore,
    BiometricEligibilityGate,
    BiometricJob,
    BiometricWorkerService,
    FaceEvaluation,
    FaceGalleryIndex,
    FaceQualityMetrics,
    Go2RtcSnapshotProvider,
    IFaceRecognizer,
    IPlateRecognizer,
    OnnxAlprRecognizer,
    OnnxInsightFaceRecognizer,
    PlateEvaluation,
    PlateQualityMetrics,
    PlateWhitelistMatcher,
    TrackBiometricConsensusManager,
    TrackBiometricUpdate,
    TrackCoalescingQueue,
    decode_and_crop_jpeg,
    levenshtein_distance,
    normalize_and_validate_plate,
    parse_jpeg_dimensions,
)
from spatial_server.config import REPO_ROOT
from spatial_server.domain.models import BoundingBox2D


def _make_jpeg_bytes(width: int, height: int, color: tuple[int, int, int] = (80, 120, 160)) -> bytes:
    img = np.full((height, width, 3), color, dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    assert ok
    return buf.tobytes()


def _make_synthetic_car_crop(plate_text: str = "AB123CD") -> np.ndarray:
    scene = np.full((480, 640, 3), (65, 72, 78), dtype=np.uint8)
    cv2.rectangle(scene, (90, 90), (550, 410), (42, 48, 56), -1)
    cv2.rectangle(scene, (120, 120), (520, 210), (30, 34, 38), -1)
    px1, py1, px2, py2 = 200, 265, 440, 321
    cv2.rectangle(scene, (px1, py1), (px2, py2), (242, 244, 246), -1)
    cv2.rectangle(scene, (px1, py1), (px1 + 24, py2), (165, 65, 18), -1)
    cv2.putText(scene, "I", (px1 + 6, py2 - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(scene, plate_text, (px1 + 34, py2 - 14), cv2.FONT_HERSHEY_SIMPLEX, 1.05, (15, 15, 18), 3, cv2.LINE_AA)
    cv2.rectangle(scene, (px1, py1), (px2, py2), (20, 20, 20), 2)
    return scene


# ---------------------------------------------------------------------------
# 1. Plate Post-Processing & Whitelist
# ---------------------------------------------------------------------------


def test_italian_plate_postprocessor_repairs_and_formats() -> None:
    exact = normalize_and_validate_plate("ab 123 cd_")
    assert exact.is_valid is True
    assert exact.plate == "AB123CD"
    assert exact.plate_format == "IT_STD"
    assert exact.repairs_applied == 0

    # Positional ambiguity fixes: '8'->'B' at letter pos, '0'->'D' at letter pos, 'Z'->'2' at digit pos
    repaired = normalize_and_validate_plate("A81Z3CD")
    assert repaired.is_valid is True
    assert repaired.plate == "AB123CD"
    assert repaired.plate_format == "IT_STD"
    assert repaired.repairs_applied == 2

    # Disallowed Italian letters (I, O, Q, U) repaired deterministically
    iou_fix = normalize_and_validate_plate("AO123CI")
    assert iou_fix.is_valid is True
    assert iou_fix.plate == "AD123CL"

    # Strip leading EU blue-band 'I' artifact and trailing sticker chars
    eu_band = normalize_and_validate_plate("IAB123CD")
    assert eu_band.is_valid is True
    assert eu_band.plate == "AB123CD"
    assert eu_band.plate_format == "IT_STD"

    trailing = normalize_and_validate_plate("AB123CDRM")
    assert trailing.is_valid is True
    assert trailing.plate == "AB123CD"

    # Too many corrupted chars -> rejected rather than hallucinated
    corrupted = normalize_and_validate_plate("00AAA00")
    assert corrupted.plate_format != "IT_STD"

    # Italian motorcycle plate (LLNNNNN)
    moto = normalize_and_validate_plate("EF12345")
    assert moto.is_valid is True
    assert moto.plate == "EF12345"
    assert moto.plate_format == "IT_MOTO"

    # Foreign / generic European plates preserved safely
    foreign = normalize_and_validate_plate("ZH987654")
    assert foreign.is_valid is True
    assert foreign.plate == "ZH987654"
    assert foreign.plate_format == "EU_GENERIC"


def test_plate_whitelist_levenshtein_and_tie_rejection(tmp_path: Path) -> None:
    assert levenshtein_distance("AB123CD", "AB123CE") == 1
    wl_path = tmp_path / "whitelist.json"
    matcher = PlateWhitelistMatcher(wl_path)
    matcher.upsert("AB123CD", "Auto Nicola", vehicle_label="Golf")

    hit, dist = matcher.match("AB123CD", max_distance=1)
    assert hit is not None and hit.owner_name == "Auto Nicola" and dist == 0

    fuzzy_hit, fuzzy_dist = matcher.match("AB123CE", max_distance=1)
    assert fuzzy_hit is not None and fuzzy_hit.plate == "AB123CD" and fuzzy_dist == 1

    # Ambiguous tie at distance 1 must NOT guess blindly
    matcher.upsert("AB123CF", "Auto Ospite")
    tie_hit, _ = matcher.match("AB123CE", max_distance=1)
    assert tie_hit is None

    # Short plates (<6) do not fuzzy match
    matcher.upsert("AB12", "Mini")
    short_hit, _ = matcher.match("AB13", max_distance=1)
    assert short_hit is None

    # Persistence reload check
    reloaded = PlateWhitelistMatcher(wl_path)
    assert len(reloaded.list_entries()) == 3
    assert reloaded.delete("AB12") is True
    assert len(reloaded.list_entries()) == 2


# ---------------------------------------------------------------------------
# 2. Face Gallery Index
# ---------------------------------------------------------------------------


def test_face_gallery_matching_margin_and_incremental_updates(tmp_path: Path) -> None:
    npz_path = tmp_path / "gallery.npz"
    gallery = FaceGalleryIndex(npz_path, max_reps_per_person=4)

    v_nicola = np.zeros(512, dtype=np.float32)
    v_nicola[0] = 1.0
    v_anna = np.zeros(512, dtype=np.float32)
    v_anna[1] = 1.0

    gallery.add_embedding("Nicola", v_nicola, quality=0.9)
    gallery.add_embedding("Anna", v_anna, quality=0.9)

    # Clear match
    probe_n = np.zeros(512, dtype=np.float32)
    probe_n[0] = 0.92
    probe_n[2] = 0.39
    res = gallery.match(probe_n, match_threshold=0.45, margin_threshold=0.08)
    assert res.passed is True and res.identity == "Nicola"

    # Ambiguous tie between two family members -> fails margin check
    probe_tie = np.zeros(512, dtype=np.float32)
    probe_tie[0] = 0.70
    probe_tie[1] = 0.68
    tie_res = gallery.match(probe_tie, match_threshold=0.45, margin_threshold=0.08)
    assert tie_res.passed is False and tie_res.identity is None

    # Below threshold -> unknown
    probe_stranger = np.zeros(512, dtype=np.float32)
    probe_stranger[10] = 1.0
    stranger_res = gallery.match(probe_stranger, match_threshold=0.45, margin_threshold=0.08)
    assert stranger_res.passed is False and stranger_res.identity is None

    # Persistence reload + person removal
    reloaded = FaceGalleryIndex(npz_path)
    assert reloaded.person_count == 2
    assert reloaded.remove_person("Anna") is True
    assert reloaded.person_count == 1
    assert reloaded.list_identities()[0]["name"] == "Nicola"


# ---------------------------------------------------------------------------
# 3. Consensus & Crop Store
# ---------------------------------------------------------------------------


def test_consensus_locking_whitelist_and_crop_store(tmp_path: Path) -> None:
    store = BiometricCropStore(tmp_path / "bio", jpeg_quality=80, max_side_px=320)
    wl = PlateWhitelistMatcher()
    wl.upsert("AB123CD", "Auto Nicola")

    consensus = TrackBiometricConsensusManager(
        crop_store=store,
        whitelist_matcher=wl,
        face_consensus_k=2,
        alpr_consensus_k=2,
        min_eval_interval_s=0.5,
        max_fast_attempts=3,
        unknown_backoff_s=4.0,
    )

    crop_low = np.full((600, 400, 3), 50, dtype=np.uint8)
    crop_high = np.full((600, 400, 3), 200, dtype=np.uint8)

    # First face evaluation -> pending, saves crop
    upd1 = consensus.record_face_evaluation(
        101,
        FaceEvaluation(
            identity="Nicola",
            similarity=0.72,
            quality_score=0.40,
            metrics=FaceQualityMetrics(det_score=0.85, face_width_px=70, blur_laplacian=80, yaw_ratio=0.1, passed=True),
            crop_bgr=crop_low,
        ),
        camera_id="Cam_Carraio",
        timestamp=1000.0,
    )
    assert upd1 is not None and upd1.biometric_locked is False and upd1.biometric_status == "pending"
    first_crop_rel = upd1.best_crop_relpath
    assert first_crop_rel and (store.crops_dir / first_crop_rel).is_file()

    # Cooldown prevents immediate second dispatch
    assert consensus.can_attempt(101, "face", now_ts=1000.2) is False
    assert consensus.can_attempt(101, "face", now_ts=1000.6) is True

    # Second concordant face evaluation with better quality -> LOCK + replaces crop on disk
    upd2 = consensus.record_face_evaluation(
        101,
        FaceEvaluation(
            identity="Nicola",
            similarity=0.81,
            quality_score=0.90,
            metrics=FaceQualityMetrics(det_score=0.95, face_width_px=110, blur_laplacian=150, yaw_ratio=0.05, passed=True),
            crop_bgr=crop_high,
        ),
        camera_id="Cam_Carraio",
        timestamp=1000.7,
    )
    assert upd2 is not None and upd2.biometric_locked is True and upd2.identity == "Nicola"
    assert upd2.best_crop_relpath != first_crop_rel
    assert not (store.crops_dir / first_crop_rel).exists()
    assert store.resolve_crop_path(upd2.best_crop_id, upd2.best_crop_relpath) is not None
    assert consensus.is_locked(101, "face") is True

    # Subsequent calls after lock return None
    assert (
        consensus.record_face_evaluation(
            101,
            None,
            camera_id="Cam_Portico",
            timestamp=1002.0,
        )
        is None
    )

    # ALPR consensus applies whitelist only on lock
    p_eval = PlateEvaluation(
        plate="AB123CE",  # 1-char OCR drift from AB123CD
        plate_raw="AB123CE",
        plate_format="IT_STD",
        confidence=0.91,
        quality_score=0.82,
        metrics=PlateQualityMetrics(det_score=0.9, plate_width_px=95, blur_laplacian=120, glare_ratio=0.0, mean_luma=130, passed=True),
        crop_bgr=crop_high,
    )
    a1 = consensus.record_plate_evaluation(202, p_eval, camera_id="Cam_Carraio", timestamp=2000.0)
    assert a1 is not None and a1.biometric_locked is False and a1.plate_whitelisted is None
    a2 = consensus.record_plate_evaluation(202, p_eval, camera_id="Cam_Carraio", timestamp=2000.8)
    assert a2 is not None and a2.biometric_locked is True
    assert a2.plate == "AB123CD"
    assert a2.plate_whitelisted is True
    assert a2.plate_owner == "Auto Nicola"
    assert a2.identity == "Auto Nicola"

    # Unknown backoff after max_fast_attempts failed reads
    for attempt in range(3):
        u = consensus.record_face_evaluation(303, None, camera_id="Cam_Portico", timestamp=3000.0 + attempt)
    assert u is not None and u.biometric_status == "unknown"
    assert consensus.can_attempt(303, "face", now_ts=3003.0) is False  # < 4s backoff
    assert consensus.can_attempt(303, "face", now_ts=3006.5) is True


def test_crop_store_security_and_quota_pruning(tmp_path: Path) -> None:
    store = BiometricCropStore(tmp_path / "bio", jpeg_quality=85, max_side_px=320)
    assert store.resolve_crop_path("../secret") is None
    assert store.resolve_crop_path("valid_id_1234", "../../outside.jpg") is None

    now = time.time()
    img_big = np.random.default_rng(7).integers(0, 255, size=(600, 800, 3), dtype=np.uint8)
    cid1, rel1 = store.save_best_crop("crop_old_0001", img_big, timestamp=now - 2 * 86400)
    cid2, rel2 = store.save_best_crop("crop_new_0002", img_big, timestamp=now)
    p1 = store.resolve_crop_path(cid1, rel1)
    p2 = store.resolve_crop_path(cid2, rel2)
    assert p1 is not None and p2 is not None

    # Resized down to <= 320px
    saved_im = cv2.imread(str(p2))
    assert saved_im is not None and max(saved_im.shape[:2]) == 320

    # Force old mtime on crop1 and enforce tiny disk quota -> oldest deleted first
    os.utime(p1, (now - 1000, now - 1000))
    os.utime(p2, (now, now))
    size_kb_2 = p2.stat().st_size / 1024.0
    removed = store.prune(retention_days=14, max_disk_mb=(size_kb_2 + 2.0) / 1024.0)
    assert removed >= 1
    assert not p1.exists()
    assert p2.exists()


# ---------------------------------------------------------------------------
# 4. Snapshot Provider (JPEG Header, Panoramic Half-Decode, Circuit Breaker)
# ---------------------------------------------------------------------------


def test_snapshot_provider_panoramic_decode_and_circuit_breaker() -> None:
    pano_jpeg = _make_jpeg_bytes(4096, 1152, (40, 180, 90))
    assert parse_jpeg_dimensions(pano_jpeg) == (4096, 1152)

    crop = decode_and_crop_jpeg(
        pano_jpeg,
        "Cam_Ingresso",
        1000.0,
        BoundingBox2D(x_min=0.40, y_min=0.30, x_max=0.60, y_max=0.80),
        max_decode_width=3840,
        is_panoramic_180=True,
    )
    assert crop is not None
    # Reduced 2x decode avoids full 4096x1152 allocation
    assert crop.full_width == 2048 and crop.full_height == 576

    pinhole_jpeg = _make_jpeg_bytes(1280, 720, (90, 90, 200))
    calls: list[str] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        src = request.url.params.get("src", "")
        calls.append(src)
        if src == "carraio_snap":
            return httpx.Response(404)
        if src == "carraio_main":
            return httpx.Response(200, headers={"Content-Type": "image/jpeg"}, content=pinhole_jpeg)
        if src.startswith("portico"):
            return httpx.Response(503)
        return httpx.Response(404)

    async def _run() -> None:
        provider = Go2RtcSnapshotProvider(
            "http://127.0.0.1:1984",
            breaker_failure_threshold=2,
            breaker_cooldown_s=10.0,
            http_transport=httpx.MockTransport(_handler),
        )
        try:
            # Falls back cleanly from carraio_snap (404) -> carraio_main (200)
            res = await provider.fetch_crop(
                "Cam_Carraio",
                BoundingBox2D(x_min=0.4, y_min=0.4, x_max=0.6, y_max=0.8),
                prefer_upper_fraction=0.6,
            )
            assert res is not None and res.source_variant == "carraio_main"
            assert calls == ["carraio_snap", "carraio_main"]

            # Cam_Portico trips breaker after 2 failed fetches; 3rd fetch skips HTTP immediately
            calls.clear()
            for _ in range(3):
                miss = await provider.fetch_crop(
                    "Cam_Portico",
                    BoundingBox2D(x_min=0.4, y_min=0.4, x_max=0.6, y_max=0.8),
                )
                assert miss is None
            assert len(calls) == 4  # 2 tries * (portico_snap + portico_main), 3rd skipped by breaker
            assert provider.get_diagnostics()["Cam_Portico"]["circuit_open"] is True
        finally:
            await provider.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 5. Coalescing Queue, Eligibility Gate & Async Worker
# ---------------------------------------------------------------------------


def test_coalescing_queue_and_eligibility_gate() -> None:
    q = TrackCoalescingQueue(maxsize=2)
    j1 = BiometricJob(
        track_id=1,
        camera_id="Cam_Carraio",
        class_label="person",
        timestamp=10.0,
        bbox=BoundingBox2D(x_min=0.4, y_min=0.4, x_max=0.5, y_max=0.8),
        obs_range_m=4.0,
        world_xyz=(0.0, 0.0, 4.0),
    )
    j1_newer = j1.model_copy(update={"timestamp": 10.5})
    j2 = j1.model_copy(update={"track_id": 2})
    j3 = j1.model_copy(update={"track_id": 3})

    q.put_nowait(j1)
    q.put_nowait(j1_newer)  # Coalesced in-place
    assert len(q) == 1 and q.coalesced_count == 1
    q.put_nowait(j2)
    q.put_nowait(j3)  # Drops track 1 (oldest)
    assert len(q) == 2 and q.dropped_count == 1

    async def _drain() -> list[int]:
        out = []
        while len(q):
            out.append((await q.get()).track_id)
        return out

    assert asyncio.run(_drain()) == [2, 3]

    gate = BiometricEligibilityGate(
        face_max_range_m=8.0,
        alpr_max_range_m=13.0,
        panoramic_edge_margin_u=0.15,
        camera_rules={"Cam_Carraio": {"face": 9.0, "alpr": 15.0}},
    )
    cons = TrackBiometricConsensusManager()

    # Panoramic edge rejected
    ok_edge, _ = gate.evaluate(
        j1.model_copy(update={"camera_id": "Cam_Ingresso", "is_panoramic_180": True, "bbox": BoundingBox2D(x_min=0.02, y_min=0.4, x_max=0.08, y_max=0.8)}),
        cons,
    )
    assert ok_edge is False

    # Panoramic center accepted with reduced weight 0.75
    ok_center, weight = gate.evaluate(
        j1.model_copy(update={"camera_id": "Cam_Ingresso", "is_panoramic_180": True}),
        cons,
    )
    assert ok_center is True and weight == 0.75

    # Dog ignored
    ok_dog, _ = gate.evaluate(j1.model_copy(update={"class_label": "dog"}), cons)
    assert ok_dog is False


def test_biometric_worker_end_to_end_locks_person_and_car(tmp_path: Path) -> None:
    jpeg_bytes = _make_jpeg_bytes(640, 480)

    class _FakeFace(IFaceRecognizer):
        def is_ready(self) -> bool:
            return True

        def recognize_crop(self, person_crop_bgr: np.ndarray) -> Optional[FaceEvaluation]:
            return FaceEvaluation(
                identity="Nicola",
                similarity=0.80,
                quality_score=0.88,
                metrics=FaceQualityMetrics(det_score=0.95, face_width_px=80, blur_laplacian=120, yaw_ratio=0.1, passed=True),
                crop_bgr=person_crop_bgr,
            )

    class _FakePlate(IPlateRecognizer):
        def is_ready(self) -> bool:
            return True

        def recognize_crop(self, vehicle_crop_bgr: np.ndarray) -> Optional[PlateEvaluation]:
            return PlateEvaluation(
                plate="AB123CD",
                plate_raw="AB123CD",
                plate_format="IT_STD",
                confidence=0.94,
                quality_score=0.86,
                metrics=PlateQualityMetrics(det_score=0.9, plate_width_px=90, blur_laplacian=100, glare_ratio=0.0, mean_luma=128, passed=True),
                crop_bgr=vehicle_crop_bgr,
            )

    async def _run() -> list[TrackBiometricUpdate]:
        updates: list[TrackBiometricUpdate] = []
        store = BiometricCropStore(tmp_path / "bio")
        wl = PlateWhitelistMatcher()
        wl.upsert("AB123CD", "Auto Nicola")
        cons = TrackBiometricConsensusManager(
            crop_store=store,
            whitelist_matcher=wl,
            face_consensus_k=2,
            alpr_consensus_k=2,
            min_eval_interval_s=0.05,
        )
        gate = BiometricEligibilityGate()
        provider = Go2RtcSnapshotProvider(
            "http://127.0.0.1:1984",
            http_transport=httpx.MockTransport(
                lambda _req: httpx.Response(200, headers={"Content-Type": "image/jpeg"}, content=jpeg_bytes)
            ),
        )

        async def _on_res(upd: TrackBiometricUpdate) -> None:
            updates.append(upd)

        worker = BiometricWorkerService(
            snapshot_provider=provider,
            consensus=cons,
            gate=gate,
            face_recognizer=_FakeFace(),
            plate_recognizer=_FakePlate(),
            on_result=_on_res,
        )
        await worker.start()
        try:
            for step in range(2):
                ts = 1000.0 + step * 0.2
                assert worker.enqueue_candidate(
                    BiometricJob(
                        track_id=10,
                        camera_id="Cam_Carraio",
                        class_label="person",
                        timestamp=ts,
                        bbox=BoundingBox2D(x_min=0.4, y_min=0.4, x_max=0.5, y_max=0.8),
                        obs_range_m=4.0,
                        world_xyz=(0.0, 0.0, 4.0),
                    )
                )
                assert worker.enqueue_candidate(
                    BiometricJob(
                        track_id=20,
                        camera_id="Cam_Carraio",
                        class_label="car",
                        timestamp=ts,
                        bbox=BoundingBox2D(x_min=0.2, y_min=0.4, x_max=0.5, y_max=0.8),
                        obs_range_m=7.0,
                        world_xyz=(0.0, 0.0, 7.0),
                    )
                )
                await asyncio.sleep(0.08)

            # Locked tracks must stop enqueuing new work
            assert worker.enqueue_candidate(
                BiometricJob(
                    track_id=10,
                    camera_id="Cam_Carraio",
                    class_label="person",
                    timestamp=1001.0,
                    bbox=BoundingBox2D(x_min=0.4, y_min=0.4, x_max=0.5, y_max=0.8),
                    obs_range_m=4.0,
                    world_xyz=(0.0, 0.0, 4.0),
                )
            ) is False
            diag = worker.get_diagnostics()
            assert diag["locked_total"] == 2
            return updates
        finally:
            await worker.stop()

    updates = asyncio.run(_run())
    person_locked = [u for u in updates if u.track_id == 10 and u.biometric_locked]
    car_locked = [u for u in updates if u.track_id == 20 and u.biometric_locked]
    assert len(person_locked) == 1 and person_locked[0].identity == "Nicola"
    assert len(car_locked) == 1 and car_locked[0].plate == "AB123CD" and car_locked[0].plate_whitelisted is True


# ---------------------------------------------------------------------------
# 6. Offline Real-Model ONNX Smoke Test (if Fase 0 models are cached locally)
# ---------------------------------------------------------------------------


def test_real_local_onnx_models_smoke_if_present() -> None:
    models_root = REPO_ROOT / "spatial_server" / "models" / "biometrics"
    det_face = models_root / "face" / "det_500m.onnx"
    rec_face = models_root / "face" / "w600k_mbf.onnx"
    det_plate = models_root / "alpr" / "yolo-v9-t-384-license-plate-end2end" / "yolo-v9-t-384-license-plates-end2end.onnx"
    ocr_plate = models_root / "alpr" / "cct-xs-v2-global-model" / "cct_xs_v2_global.onnx"
    ocr_cfg = models_root / "alpr" / "cct-xs-v2-global-model" / "cct_xs_v2_global_plate_config.yaml"

    if not (det_face.is_file() and rec_face.is_file() and det_plate.is_file() and ocr_plate.is_file() and ocr_cfg.is_file()):
        pytest.skip("Downloaded Fase 0 ONNX models not present in spatial_server/models/biometrics/")

    gallery_path = REPO_ROOT / "spatial_server" / "data" / "biometrics" / "face_gallery_mbf.npz"
    gallery = FaceGalleryIndex(gallery_path if gallery_path.is_file() else None)
    face_rec = OnnxInsightFaceRecognizer(det_face, rec_face, gallery, intra_threads=2)
    assert face_rec.is_ready() is True
    assert face_rec.recognize_crop(np.zeros((200, 200, 3), dtype=np.uint8)) is None

    alpr_rec = OnnxAlprRecognizer(det_plate, ocr_plate, ocr_cfg, intra_threads=2)
    assert alpr_rec.is_ready() is True
    car_crop = _make_synthetic_car_crop("AB123CD")
    plate_eval = alpr_rec.recognize_crop(car_crop)
    assert plate_eval is not None
    assert plate_eval.plate == "AB123CD"
    assert plate_eval.plate_format == "IT_STD"
    assert plate_eval.confidence > 0.5
