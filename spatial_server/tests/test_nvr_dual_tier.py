from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator, Optional

import pytest
from fastapi import HTTPException

from spatial_server.config import SpatialServerConfig
from spatial_server.main import create_app
from spatial_server.recordings import (
    CameraRecordingProfile,
    CompressedGopRingBuffer,
    DiskRetentionManager,
    DualTierNvrRecorderCoordinator,
    EncodedPacket,
    FilesystemNvrArchiveRepository,
    IMediaPacketSource,
    IMediaSegmentWriter,
    MainEventStateMachine,
    RecordingSegmentRecord,
    SQLiteNvrIndexStore,
    SegmentWriteResult,
    StreamMetadata,
)
from spatial_server.security import HAUserPrincipal
from tests.e2e.helpers.artifacts import run_js_scenario


# ---------------------------------------------------------------------------
# Helpers deterministi per testare il registratore senza hardware / PyAV
# ---------------------------------------------------------------------------


def _make_pkt(
    wall_ts: float,
    *,
    is_keyframe: bool = False,
    stream_kind: str = "video",
    size: int = 1024,
    codec: str = "h264",
    width: int = 1920,
    height: int = 1080,
    pts: Optional[int] = None,
) -> EncodedPacket:
    p_val = pts if pts is not None else int(wall_ts * 90000)
    return EncodedPacket(
        stream_kind=stream_kind,
        data=b"x" * size,
        pts=p_val,
        dts=p_val,
        duration=3000,
        time_base_num=1,
        time_base_den=90000,
        is_keyframe=is_keyframe,
        wall_ts=wall_ts,
        codec_name=codec,
        width=width,
        height=height,
    )


class _InMemoryPacketSource(IMediaPacketSource):
    def __init__(self, packets: list[EncodedPacket], meta: StreamMetadata) -> None:
        self._packets = packets
        self._meta = meta
        self.closed = False

    def open(self) -> StreamMetadata:
        return self._meta

    def iter_packets(self) -> Iterator[EncodedPacket]:
        for pkt in self._packets:
            yield pkt

    def close(self) -> None:
        self.closed = True


class _StubMp4SegmentWriter(IMediaSegmentWriter):
    def __init__(self) -> None:
        self.target_path: Optional[Path] = None
        self.meta: Optional[StreamMetadata] = None
        self.start_wall_ts: float = 0.0
        self.packets: list[EncodedPacket] = []

    def open_segment(self, target_path: Path, metadata: StreamMetadata, start_wall_ts: float) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        self.target_path = target_path
        self.meta = metadata
        self.start_wall_ts = start_wall_ts
        self.packets = []

    def write_packet(self, packet: EncodedPacket) -> None:
        self.packets.append(packet)

    def close_segment(self, end_wall_ts: float) -> Optional[SegmentWriteResult]:
        if self.target_path is None:
            return None
        video_frames = sum(1 for p in self.packets if p.stream_kind == "video")
        if video_frames == 0:
            return None
        payload = json.dumps(
            {
                "start": self.start_wall_ts,
                "end": end_wall_ts,
                "frames": video_frames,
                "first_pkt_ts": self.packets[0].wall_ts,
                "last_pkt_ts": self.packets[-1].wall_ts,
            }
        ).encode("utf-8")
        self.target_path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + payload)
        return SegmentWriteResult(
            file_path=self.target_path,
            size_bytes=self.target_path.stat().st_size,
            packet_count=len(self.packets),
            video_frame_count=video_frames,
            start_wall_ts=self.start_wall_ts,
            end_wall_ts=max(self.start_wall_ts + 0.1, end_wall_ts),
            duration_sec=max(0.1, end_wall_ts - self.start_wall_ts),
            codec_name=self.meta.video_codec if self.meta else "h264",
            width=self.meta.width if self.meta else 0,
            height=self.meta.height if self.meta else 0,
        )

    def abort_segment(self) -> None:
        self.target_path = None
        self.packets = []


def _make_nvr_config(
    tmp_path: Path,
    nvr_dir: Optional[Path],
    *,
    recorder_enabled: bool = False,
    sub_segment_sec: float = 10.0,
    pre_roll_sec: float = 6.0,
    inertia_sec: float = 8.0,
    max_clip_sec: float = 60.0,
    clock_offsets: tuple[tuple[str, str, float], ...] = (),
) -> SpatialServerConfig:
    base = SpatialServerConfig.from_env()
    return SpatialServerConfig(
        host=base.host,
        port=base.port,
        manifest_path=base.manifest_path,
        glb_path=base.glb_path,
        sqlite_db_path=tmp_path / "tracks.db",
        calibration_override_path=tmp_path / "calibs.json",
        data_dir=tmp_path,
        models_dir=base.models_dir,
        default_ingestion_mode="synthetic",
        go2rtc_rtsp_url=base.go2rtc_rtsp_url,
        mqtt_host=base.mqtt_host,
        mqtt_port=base.mqtt_port,
        mqtt_user="",
        mqtt_password="",
        mqtt_topic_prefix=base.mqtt_topic_prefix,
        openvino_device=base.openvino_device,
        openvino_model_path=base.openvino_model_path,
        db_retention_days=7,
        face_webhook_url="",
        auth_required=False,
        nvr_storage_dir=nvr_dir,
        nvr_recorder_enabled=recorder_enabled,
        nvr_sub_segment_sec=sub_segment_sec,
        nvr_main_pre_roll_sec=pre_roll_sec,
        nvr_main_inertia_sec=inertia_sec,
        nvr_main_max_clip_sec=max_clip_sec,
        nvr_ram_buffer_max_mb_per_cam=16.0,
        nvr_camera_clock_offsets=clock_offsets,
    )


def _invoke_zero_await(coro):
    try:
        coro.send(None)
    except StopIteration as stop:
        return stop.value
    finally:
        coro.close()
    raise RuntimeError("Coroutine unexpectedly yielded")


def _get_route_endpoint(app, path: str, method: str = "GET"):
    for route in app.routes:
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
            return route.endpoint
    raise AssertionError(f"Route not registered: {method} {path}")


# ---------------------------------------------------------------------------
# 1. CompressedGopRingBuffer Unit Tests
# ---------------------------------------------------------------------------


def test_ring_buffer_drops_pre_keyframe_seals_gops_and_respects_ram_budget():
    rb = CompressedGopRingBuffer(max_duration_sec=30.0, max_bytes=2 * 1024 * 1024)

    # Pacchetti iniziali senza keyframe devono essere scartati
    assert rb.push_packet(_make_pkt(1000.0, is_keyframe=False, size=50_000)) is None
    assert rb.push_packet(_make_pkt(1000.5, is_keyframe=False, stream_kind="audio", size=5_000)) is None
    assert rb.get_stats()["gop_count"] == 0

    # Inserisce 8 GOP da 2 secondi ciascuno (~300 KB per GOP, tot ~2.4 MB > 2.0 MB budget)
    for g in range(8):
        t0 = 1002.0 + g * 2.0
        rb.push_packet(_make_pkt(t0, is_keyframe=True, size=200_000, width=3840, height=2160))
        rb.push_packet(_make_pkt(t0 + 1.0, is_keyframe=False, size=100_000, width=3840, height=2160))
        rb.push_packet(_make_pkt(t0 + 1.2, is_keyframe=False, stream_kind="audio", size=2_000))

    stats = rb.get_stats()
    assert stats["buffered_bytes"] <= 2 * 1024 * 1024
    assert stats["dropped_for_budget_count"] >= 1
    assert stats["width"] == 3840
    assert stats["height"] == 2160

    # Snapshot pre-roll da target_start_unix = 1011.0 -> deve partire dal keyframe 1010.0 (<= 1011.0) e includere GOP corrente
    gops = rb.snapshot_pre_roll(1011.0)
    assert len(gops) >= 3
    assert gops[0].start_wall_ts == 1010.0
    assert gops[0].packets[0].is_keyframe is True
    assert gops[-1].start_wall_ts == 1016.0


# ---------------------------------------------------------------------------
# 2. MainEventStateMachine Unit Tests
# ---------------------------------------------------------------------------


def test_main_event_state_machine_inertia_rollover_and_manual_trigger():
    sm = MainEventStateMachine(
        pre_roll_sec=10.0,
        inertia_sec=12.0,
        max_clip_sec=30.0,
        trigger_classes=("person", "car"),
        min_confidence=0.6,
    )
    sm.set_buffering()

    # Ignora classe non abilitata e confidenza bassa
    assert sm.on_detection(1000.0, "dog", 0.95) is False
    assert sm.on_detection(1000.0, "person", 0.40) is False
    assert sm.is_recording_requested() is False

    # Rilevazione valida attiva la registrazione con deadline a 1012.0
    assert sm.on_detection(1000.0, "person", 0.85, track_id=7) is True
    assert sm.is_recording_requested() is True
    assert sm.get_trigger_context()["inertia_deadline_unix"] == 1012.0

    # Altra rilevazione a 1008.0 estende continuamente l'inerzia a 1020.0 (niente stacchi!)
    assert sm.on_detection(1008.0, "person", 0.90, track_id=7) is True
    assert sm.evaluate_finalize(1013.0, clip_start_unix=990.0, is_keyframe=True) is None

    # Superata max_clip_sec (30s) su keyframe mentre siamo ancora dentro inerzia -> rollover continuo
    assert sm.evaluate_finalize(1020.0 - 0.5, clip_start_unix=989.0, is_keyframe=True) == "max_duration_rollover"
    ctx_roll = sm.mark_rollover(1019.5)
    assert ctx_roll["track_ids"] == [7]

    # Dopo scadenza inerzia (1020.0): attende il primo keyframe utile
    assert sm.evaluate_finalize(1021.0, clip_start_unix=1019.5, is_keyframe=False) is None
    assert sm.evaluate_finalize(1021.5, clip_start_unix=1019.5, is_keyframe=True) == "inertia_expired"
    ctx_fin = sm.mark_finalized()
    assert ctx_fin["trigger_classes"] == ["person"]
    assert sm.is_recording_requested() is False

    # Trigger manuale
    assert sm.on_manual_trigger(1050.0, duration_sec=15.0) is True
    assert sm.get_trigger_context()["inertia_deadline_unix"] == 1065.0


# ---------------------------------------------------------------------------
# 3. SQLiteNvrIndexStore & Dual-Tier Resolution + HEVC Fallback Tests
# ---------------------------------------------------------------------------


def test_sqlite_nvr_dual_tier_resolution_lookahead_and_hevc_fallback(tmp_path: Path):
    nvr_root = tmp_path / "Surveillance"
    cam_dir = nvr_root / "Cam_Ingresso" / "2026-11-24"
    cam_dir.mkdir(parents=True)

    sub1 = cam_dir / "sub_1000.000_60.000.mp4"
    sub2 = cam_dir / "sub_1060.000_60.000.mp4"
    main1 = cam_dir / "main_1012.500_25.750.mp4"
    for f in (sub1, sub2, main1):
        f.write_bytes(b"\x00\x00\x00\x18ftypmp42")

    repo = FilesystemNvrArchiveRepository(storage_dir=nvr_root)
    repo.register_recorded_segment(
        RecordingSegmentRecord(
            id="Cam_Ingresso:sub1",
            camera_id="Cam_Ingresso",
            start_unix=1000.0,
            end_unix=1060.0,
            stream_url="/api/v1/recordings/Cam_Ingresso/file/sub_1000.000_60.000.mp4",
            file_path=sub1,
            stream_tier="sub",
            codec="h264",
            size_bytes=sub1.stat().st_size,
        )
    )
    repo.register_recorded_segment(
        RecordingSegmentRecord(
            id="Cam_Ingresso:sub2",
            camera_id="Cam_Ingresso",
            start_unix=1060.0,
            end_unix=1120.0,
            stream_url="/api/v1/recordings/Cam_Ingresso/file/sub_1060.000_60.000.mp4",
            file_path=sub2,
            stream_tier="sub",
            codec="h264",
            size_bytes=sub2.stat().st_size,
        )
    )
    repo.register_recorded_segment(
        RecordingSegmentRecord(
            id="Cam_Ingresso:main1",
            camera_id="Cam_Ingresso",
            start_unix=1012.5,
            end_unix=1038.25,
            stream_url="/api/v1/recordings/Cam_Ingresso/file/main_1012.500_25.750.mp4",
            file_path=main1,
            has_motion=True,
            stream_tier="main",
            codec="hevc",
            width=7680,
            height=2160,
            size_bytes=main1.stat().st_size,
        )
    )

    # 1) Prima dell'evento (t=1005.0): seleziona sub1 ma annuncia switch anticipato a main1 a 1012.5!
    res_before = repo.resolve_timestamp("Cam_Ingresso", 1005.0, allow_hevc=True)
    assert res_before.available is True
    assert res_before.segment.stream_tier == "sub"
    assert res_before.effective_end_unix == 1012.5
    assert res_before.switch_at_unix == 1012.5
    assert res_before.next_segment is not None
    assert res_before.next_segment.stream_tier == "main"
    assert res_before.next_seek_offset_sec == 0.0

    # 2) Durante l'evento (t=1020.0): seleziona main1 e precarica ritorno a sub1 a offset 38.25!
    res_during = repo.resolve_timestamp("Cam_Ingresso", 1020.0, allow_hevc=True)
    assert res_during.available is True
    assert res_during.segment.stream_tier == "main"
    assert res_during.seek_offset_sec == 7.5
    assert res_during.effective_end_unix == 1038.25
    assert res_during.next_segment is not None
    assert res_during.next_segment.stream_tier == "sub"
    assert res_during.next_seek_offset_sec == pytest.approx(38.25, abs=0.01)

    # 3) Dopo l'evento (t=1045.0): seleziona sub1 e precarica sub2 a 0.0!
    res_after = repo.resolve_timestamp("Cam_Ingresso", 1045.0, allow_hevc=True)
    assert res_after.available is True
    assert res_after.segment.stream_tier == "sub"
    assert res_after.next_segment is not None
    assert res_after.next_segment.id == "Cam_Ingresso:sub2"
    assert res_after.next_seek_offset_sec == 0.0

    # 4) Fallback automatico su Sub H.264 se il client non supporta HEVC (Duo 3 PoE 16MP)
    res_no_hevc = repo.resolve_timestamp("Cam_Ingresso", 1020.0, allow_hevc=False)
    assert res_no_hevc.available is True
    assert res_no_hevc.segment.stream_tier == "sub"
    assert res_no_hevc.fallback_reason == "hevc_unsupported_fallback_sub"

    # 5) Sicurezza path traversal
    assert repo.resolve_segment_file("Cam_Ingresso", "../secret.mp4") is None
    assert repo.resolve_segment_file("Cam_Ingresso", "main_1012.500_25.750.mp4") == main1.resolve()
    repo.close()


# ---------------------------------------------------------------------------
# 4. End-to-End Dual-Tier Recorder Integration Test (Deterministic Stubs)
# ---------------------------------------------------------------------------


def test_dual_tier_recorder_end_to_end_preroll_inertia_and_clock_offset(tmp_path: Path):
    nvr_root = tmp_path / "Surveillance"
    nvr_root.mkdir(parents=True)

    # Sub stream: 16s di pacchetti (keyframe ogni 2s -> segment_sec=6s produce >= 2 segmenti continui)
    sub_packets = []
    for i in range(16):
        t = 1795092000.0 + i * 1.0
        sub_packets.append(_make_pkt(t, is_keyframe=(i % 2 == 0), size=2048, width=640, height=360))

    # Main stream: pacchetti ogni 1s con keyframe ogni 2s (t=0..15). Trigger a t=8.0 -> pre-roll 4s (t=4.0!)
    main_packets = []
    for i in range(16):
        t = 1795092000.0 + i * 1.0
        main_packets.append(_make_pkt(t, is_keyframe=(i % 2 == 0), size=16384, codec="hevc", width=3840, height=2160))

    cfg = _make_nvr_config(
        tmp_path,
        nvr_root,
        recorder_enabled=True,
        sub_segment_sec=6.0,
        pre_roll_sec=4.0,
        inertia_sec=3.0,
        max_clip_sec=60.0,
        clock_offsets=(("Cam_Carraio", "main", -250.0),),
    )
    archive = FilesystemNvrArchiveRepository(storage_dir=nvr_root, default_segment_duration_s=6.0)

    trigger_done = threading.Event()

    class _ControlledMainSource(_InMemoryPacketSource):
        def iter_packets(self):
            for idx, pkt in enumerate(self._packets):
                yield pkt
                # Simula rilevazione AI esattamente al pacchetto idx=8 (t=1795092008.0),
                # quando il ring-buffer RAM contiene già t=0..8!
                if idx == 8:
                    coordinator.notify_detection_activity(
                        camera_id="Cam_Carraio",
                        timestamp=pkt.wall_ts,
                        class_label="person",
                        confidence=0.92,
                        track_id=42,
                    )
                    trigger_done.set()

    def source_factory(url: str) -> IMediaPacketSource:
        if "sub" in url:
            return _InMemoryPacketSource(
                sub_packets,
                StreamMetadata(video_codec="h264", width=640, height=360),
            )
        return _ControlledMainSource(
            main_packets,
            StreamMetadata(video_codec="hevc", width=3840, height=2160),
        )

    coordinator = DualTierNvrRecorderCoordinator(
        config=cfg,
        archive=archive,
        camera_manifest_meta={
            "Cam_Carraio": {"stream_id": "carraio_main", "sub_stream_id": "carraio_sub"}
        },
        packet_source_factory=source_factory,
        segment_writer_factory=_StubMp4SegmentWriter,
    )

    rec = coordinator.recorders["Cam_Carraio"]
    # Prima di qualsiasi evento il Main Stream NON deve aver scritto nulla su disco
    assert archive.query_segments("Cam_Carraio", 0.0, 9999999999.0) == []

    # Avvia il coordinatore completo e attendi l'ingestione dello stream finito + scrittura clip
    async def _run_recorder_lifecycle():
        await coordinator.start()
        assert trigger_done.wait(timeout=5.0)
        deadline = time.time() + 3.0
        while time.time() < deadline:
            m_list = archive.query_segments("Cam_Carraio", 1795091990.0, 1795092100.0, stream_tier="main")
            s_list = archive.query_segments("Cam_Carraio", 1795091990.0, 1795092100.0, stream_tier="sub")
            if len(m_list) >= 1 and len(s_list) >= 2:
                break
            await asyncio.sleep(0.05)
        await coordinator.stop()

    asyncio.run(_run_recorder_lifecycle())

    sub_segs = archive.query_segments("Cam_Carraio", 1795091990.0, 1795092100.0, stream_tier="sub")
    main_segs = archive.query_segments("Cam_Carraio", 1795091990.0, 1795092100.0, stream_tier="main")

    assert len(sub_segs) >= 2
    assert len(main_segs) == 1
    m = main_segs[0]
    assert m.has_motion is True
    assert m.codec == "hevc"
    # Pre-roll di 4s prima del trigger (1795092008.0 - 4.0 = 1795092004.0) + clock_offset (-0.25s) = 1795092003.75!
    assert m.start_unix == pytest.approx(1795092003.75, abs=0.05)
    # Inerzia di 3s dopo 1795092008.0 -> chiude sul keyframe >= 1795092011.0 (t=1795092012.0 - 0.25 = 1795092011.75)
    assert m.end_unix >= 1795092011.5
    assert m.metadata.get("track_ids") == [42]
    assert "person" in (m.metadata.get("trigger_classes") or [])

    # Verifica che il replay al momento 2s PRIMA del trigger (t=1795092006.0) risolva già il Main!
    res_preroll = archive.resolve_timestamp("Cam_Carraio", 1795092006.0, allow_hevc=True)
    assert res_preroll.available is True
    assert res_preroll.segment.stream_tier == "main"
    archive.close()


# ---------------------------------------------------------------------------
# 5. DiskRetentionManager Tests (Age + Quota prioritizing Sub before Main)
# ---------------------------------------------------------------------------


def test_disk_retention_manager_expires_old_and_sacrifices_sub_before_main(tmp_path: Path):
    nvr_root = tmp_path / "Surveillance"
    day_dir = nvr_root / "Cam_Portico" / "2026-10-01"
    day_dir.mkdir(parents=True)
    archive = FilesystemNvrArchiveRepository(storage_dir=nvr_root)

    now_ts = 2_000_000_000.0
    sub_expired = day_dir / "sub_expired.mp4"
    sub_recent = day_dir / "sub_recent.mp4"
    main_recent = day_dir / "main_recent.mp4"

    sub_expired.write_bytes(b"a" * 2048)
    sub_recent.write_bytes(b"b" * 1024 * 600)  # 600 KB
    main_recent.write_bytes(b"c" * 1024 * 600)  # 600 KB

    archive.register_recorded_segment(
        RecordingSegmentRecord(
            id="Cam_Portico:sub_expired.mp4",
            camera_id="Cam_Portico",
            start_unix=now_ts - 40 * 86400,
            end_unix=now_ts - 40 * 86400 + 60.0,
            stream_url="/api/v1/recordings/Cam_Portico/file/sub_expired.mp4",
            file_path=sub_expired,
            stream_tier="sub",
            size_bytes=sub_expired.stat().st_size,
        )
    )
    archive.register_recorded_segment(
        RecordingSegmentRecord(
            id="Cam_Portico:sub_recent.mp4",
            camera_id="Cam_Portico",
            start_unix=now_ts - 2 * 86400,
            end_unix=now_ts - 2 * 86400 + 60.0,
            stream_url="/api/v1/recordings/Cam_Portico/file/sub_recent.mp4",
            file_path=sub_recent,
            stream_tier="sub",
            size_bytes=sub_recent.stat().st_size,
        )
    )
    archive.register_recorded_segment(
        RecordingSegmentRecord(
            id="Cam_Portico:main_recent.mp4",
            camera_id="Cam_Portico",
            start_unix=now_ts - 5 * 86400,
            end_unix=now_ts - 5 * 86400 + 30.0,
            stream_url="/api/v1/recordings/Cam_Portico/file/main_recent.mp4",
            file_path=main_recent,
            has_motion=True,
            stream_tier="main",
            size_bytes=main_recent.stat().st_size,
        )
    )

    # Quota max_storage_gb ~ 800 KB -> deve eliminare sub_expired (età) E sub_recent (quota),
    # ma PRESERVARE main_recent (600 KB < 800 KB)!
    mgr = DiskRetentionManager(
        archive,
        sub_retention_days=30,
        main_retention_days=60,
        min_free_gb=1.0,
        max_storage_gb=(800 * 1024) / (1024**3),
    )
    report = mgr.sweep(now_unix=now_ts)
    assert report.deleted_sub_count == 2
    assert report.deleted_main_count == 0
    assert not sub_expired.exists()
    assert not sub_recent.exists()
    assert main_recent.exists()
    archive.close()


# ---------------------------------------------------------------------------
# 6. FastAPI Routes & Admin RBAC Tests
# ---------------------------------------------------------------------------


def test_nvr_fastapi_diagnostics_trigger_and_prune_rbac(tmp_path: Path):
    nvr_root = tmp_path / "Surveillance"
    nvr_root.mkdir(parents=True)
    cfg = _make_nvr_config(tmp_path, nvr_root, recorder_enabled=False)
    app = create_app(cfg)
    req = SimpleNamespace(app=app)

    admin_user = HAUserPrincipal("u-admin", "Nicola", True, False, 1000.0, 2000.0)
    status_ep = _get_route_endpoint(app, "/api/v1/recordings/status", "GET")
    trigger_ep = _get_route_endpoint(app, "/api/v1/recordings/{camera_id}/trigger", "POST")
    prune_ep = _get_route_endpoint(app, "/api/v1/recordings/maintenance/prune", "POST")
    app_status_ep = _get_route_endpoint(app, "/api/v1/status", "GET")

    st = _invoke_zero_await(status_ep(request=req, _user=admin_user))
    assert st["configured"] is True
    assert st["recorder"] is not None
    assert st["recorder"]["state"] == "stopped"
    assert st["storage_stats"]["configured"] is True

    app_st = _invoke_zero_await(app_status_ep(_user=admin_user))
    assert "nvr" in app_st
    assert app_st["nvr"]["configured"] is True

    trig = _invoke_zero_await(
        trigger_ep(request=req, camera_id="Cam_Carraio", payload=None, _admin=admin_user)
    )
    assert trig["status"] == "ok"
    assert trig["triggered"] is True

    with pytest.raises(HTTPException) as exc_404:
        _invoke_zero_await(
            trigger_ep(request=req, camera_id="Cam_Inesistente", payload=None, _admin=admin_user)
        )
    assert exc_404.value.status_code == 404

    pruned = _invoke_zero_await(prune_ep(request=req, _admin=admin_user))
    assert pruned["status"] == "ok"
    assert pruned["prune_report"] is not None
    app.state.recording_archive.close()


# ---------------------------------------------------------------------------
# 7. Frontend Dual-Buffer Zero-Gap Playback JS Scenario
# ---------------------------------------------------------------------------


def test_frontend_dual_buffer_zero_gap_sub_to_main_to_sub_switch():
    code = """
      const { CameraCatalog } = await loadModule('/src/video/CameraCatalog.js');
      const {
        CameraRecordingManager,
        SpatialServerNvrProvider,
        RecordingPlaybackStatus,
      } = await loadModule('/src/video/recordings/index.js');
      const { SecurityFabHub } = await loadModule('/src/ui/SecurityFabHub.js');

      const catalog = new CameraCatalog();

      const sub1 = {
        id: 'Cam_Carraio:sub_1000',
        camera_id: 'Cam_Carraio',
        start_unix: 1000,
        end_unix: 1060,
        stream_url: '/api/v1/recordings/Cam_Carraio/file/sub_1000_60.mp4',
        stream_tier: 'sub',
        codec: 'h264',
        has_motion: false,
      };
      const main1 = {
        id: 'Cam_Carraio:main_1010',
        camera_id: 'Cam_Carraio',
        start_unix: 1010,
        end_unix: 1025,
        stream_url: '/api/v1/recordings/Cam_Carraio/file/main_1010_15.mp4',
        stream_tier: 'main',
        codec: 'h264',
        has_motion: true,
      };

      const provider = new SpatialServerNvrProvider({
        spatialStreamClient: {
          baseUrl: 'https://pc-fisso.tail123.ts.net',
          requestJson: async (path) => {
            if (path.includes('/segments')) {
              return { status: 'ok', segments: [sub1, main1] };
            }
            if (path.includes('/resolve')) {
              const qIdx = path.indexOf('?');
              const params = new URLSearchParams(qIdx >= 0 ? path.slice(qIdx + 1) : '');
              const t = Number(params.get('t') || 0);
              if (t < 1010) {
                return {
                  status: 'ok',
                  available: true,
                  camera_id: 'Cam_Carraio',
                  seek_offset_sec: t - 1000,
                  reason: 'ok',
                  segment: sub1,
                  effective_end_unix: 1010,
                  switch_at_unix: 1010,
                  next_segment: main1,
                  next_seek_offset_sec: 0,
                };
              }
              if (t < 1025) {
                return {
                  status: 'ok',
                  available: true,
                  camera_id: 'Cam_Carraio',
                  seek_offset_sec: t - 1010,
                  reason: 'ok',
                  segment: main1,
                  effective_end_unix: 1025,
                  switch_at_unix: 1025,
                  next_segment: sub1,
                  next_seek_offset_sec: 25,
                };
              }
              return {
                status: 'ok',
                available: true,
                camera_id: 'Cam_Carraio',
                seek_offset_sec: t - 1000,
                reason: 'ok',
                segment: sub1,
                effective_end_unix: 1060,
                switch_at_unix: null,
                next_segment: null,
                next_seek_offset_sec: 0,
              };
            }
            return { status: 'ok', configured: true, recorder: { state: 'running', ram_buffer_total_mb: 12.5 } };
          },
        },
      });

      const recMgr = new CameraRecordingManager({ cameraCatalog: catalog, providers: [provider] });
      const root = ctx.document.createElement('div');
      ctx.document.body.appendChild(root);

      const hub = new SecurityFabHub(root, {
        cameraCatalog: catalog,
        videoStreamManager: { attachToVideoElement: async () => ({ mode: 'webrtc', getStatus: () => ({}), onStatusChange: () => () => {} }), detachFromVideoElement: () => {} },
        recordingManager: recMgr,
        trajectoryRenderer: { setLiveMode: () => {}, setEntitiesVisible: () => {}, loadDetections: () => {}, clearHistorical: () => {}, updateAtTime: () => 0, interpolateLive: () => {} },
        spatialStreamClient: { connected: false, onStatusChange: () => () => {}, onFrame: () => () => {} },
        cameraController: { flyToPreset: () => {}, flyToCameraPOV: () => {} },
        assetLoader: { cameras: new Map() },
        deviceModals: { open: () => {} },
      });

      root.querySelector('#btn-security-fab').click();
      for (let i = 0; i < 6; i++) await Promise.resolve();

      await hub.setMode('replay', { skipInitialLoad: true });
      hub.currentUnix = 1005;
      await hub.bindAllHistoricalSlotsAndSeek(true);
      hub.setPlaying(true);

      const tile = root.querySelector('.m3-cam-tile');
      const primaryVideo = tile.querySelector('.m3-cam-video');
      const bufferVideo = tile.querySelector('.m3-cam-video-buffer');
      const slot = recMgr.slots.get('Cam_Carraio');

      const seenStatuses = [];
      const seenTiers = [];
      const origOnState = slot.onStateChange;
      slot.onStateChange = (st) => {
        seenStatuses.push(st.status);
        if (st.streamTier) seenTiers.push(st.streamTier);
        origOnState?.(st);
      };

      // Avanza a t=1008 (dentro lookahead 3s prima di 1010) -> precarica main1 sul buffer standby
      recMgr.syncPlaybackTick(1008.0);
      const preloadingMainSrc = bufferVideo.src;
      bufferVideo.dispatchEvent({ type: 'loadedmetadata' });
      const readyForMain = slot.bufferController.isStandbyReadyFor('Cam_Carraio:main_1010', 'https://pc-fisso.tail123.ts.net/api/v1/recordings/Cam_Carraio/file/main_1010_15.mp4');

      // Avanza al confine t=1010.05 -> swap istantaneo zero-gap su bufferVideo (nessun LOADING/NO_RECORDING!)
      recMgr.syncPlaybackTick(1010.05);
      for (let i = 0; i < 6; i++) await Promise.resolve();

      const activeAfterSwitch1 = slot.bufferController.getActiveVideo() === bufferVideo;
      const bufferVisibleClass = bufferVideo.classList.contains('is-buffer-visible');
      const primaryHiddenClass = primaryVideo.classList.contains('is-buffer-hidden');
      const tierDuringMain = seenTiers[seenTiers.length - 1] || null;
      const tileReplayInfoDuringMain = hub.getReplayTileInfo('Cam_Carraio')?.videoEl === bufferVideo;

      // Ora il lookahead successivo deve puntare a sub1 a t=1025: precarica su primaryVideo e swappa al volo!
      recMgr.syncPlaybackTick(1023.0);
      primaryVideo.dispatchEvent({ type: 'loadedmetadata' });
      recMgr.syncPlaybackTick(1025.05);
      for (let i = 0; i < 6; i++) await Promise.resolve();

      const activeBackToPrimary = slot.bufferController.getActiveVideo() === primaryVideo;
      const tierBackToSub = seenTiers[seenTiers.length - 1] || null;

      // Ritorno a Live resetta sempre il buffer primario
      await hub.setMode('live');
      const resetPrimaryVisible = !primaryVideo.classList.contains('is-buffer-hidden') && !bufferVideo.classList.contains('is-buffer-visible');

      hub.dispose();
      return {
        preloadingMainSrc,
        readyForMain,
        seenStatuses,
        seenTiers,
        activeAfterSwitch1,
        bufferVisibleClass,
        primaryHiddenClass,
        tierDuringMain,
        tileReplayInfoDuringMain,
        activeBackToPrimary,
        tierBackToSub,
        resetPrimaryVisible,
      };
    """
    res = run_js_scenario({"code": code})
    assert res["ok"] is True, res
    d = res["data"]
    assert d["preloadingMainSrc"].endswith("/main_1010_15.mp4")
    assert d["readyForMain"] is True
    assert "loading" not in d["seenStatuses"]
    assert "no_recording" not in d["seenStatuses"]
    assert d["activeAfterSwitch1"] is True
    assert d["bufferVisibleClass"] is True
    assert d["primaryHiddenClass"] is True
    assert d["tierDuringMain"] == "main"
    assert d["tileReplayInfoDuringMain"] is True
    assert d["activeBackToPrimary"] is True
    assert d["tierBackToSub"] == "sub"
    assert d["resetPrimaryVisible"] is True
