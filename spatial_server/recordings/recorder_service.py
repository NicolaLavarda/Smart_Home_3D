from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from spatial_server.config import SpatialServerConfig
from spatial_server.recordings.filesystem_nvr import FilesystemNvrArchiveRepository
from spatial_server.recordings.interfaces import (
    EncodedPacket,
    IDualTierRecorderCoordinator,
    IMediaPacketSource,
    IMediaSegmentWriter,
    RecordingSegmentRecord,
    SegmentWriteResult,
    StreamMetadata,
)
from spatial_server.recordings.media_backend import (
    PyAvMp4SegmentWriter,
    PyAvRtspPacketSource,
    is_pyav_available,
)
from spatial_server.recordings.retention import DiskRetentionManager, RetentionSweepReport
from spatial_server.recordings.ring_buffer import CompressedGopRingBuffer

logger = logging.getLogger("spatial_server.recordings.recorder")

PacketSourceFactory = Callable[[str], IMediaPacketSource]
SegmentWriterFactory = Callable[[], IMediaSegmentWriter]


@dataclass(frozen=True)
class CameraRecordingProfile:
    """Profilo di registrazione per singola telecamera (scalabile ad N camere)."""

    camera_id: str
    sub_rtsp_url: str
    main_rtsp_url: str
    sub_clock_offset_ms: float = 0.0
    main_clock_offset_ms: float = 0.0
    enabled: bool = True


class MainEventStateMachine:
    """Macchina a stati per la registrazione su evento del Main Stream con pre-roll e inerzia."""

    STATE_IDLE = "idle"
    STATE_BUFFERING = "buffering"
    STATE_RECORDING = "recording"

    def __init__(
        self,
        *,
        pre_roll_sec: float = 10.0,
        inertia_sec: float = 15.0,
        max_clip_sec: float = 300.0,
        trigger_classes: tuple[str, ...] = ("person", "car", "truck", "motorbike"),
        min_confidence: float = 0.55,
    ) -> None:
        self.pre_roll_sec = max(0.0, float(pre_roll_sec))
        self.inertia_sec = max(1.0, float(inertia_sec))
        self.max_clip_sec = max(10.0, float(max_clip_sec))
        self.trigger_classes = frozenset(c.strip().lower() for c in trigger_classes if c.strip())
        self.min_confidence = max(0.0, float(min_confidence))

        self._lock = threading.Lock()
        self._state: str = self.STATE_IDLE
        self._trigger_requested: bool = False
        self._trigger_started_unix: float = 0.0
        self._inertia_deadline_unix: float = 0.0
        self._active_classes: set[str] = set()
        self._active_track_ids: set[int] = set()
        self._trigger_count: int = 0

    def set_buffering(self) -> None:
        with self._lock:
            if self._state == self.STATE_IDLE:
                self._state = self.STATE_BUFFERING

    def set_idle(self) -> None:
        with self._lock:
            self._state = self.STATE_IDLE
            self._trigger_requested = False
            self._active_classes.clear()
            self._active_track_ids.clear()

    def on_detection(
        self,
        now_unix: float,
        class_label: str,
        confidence: float,
        track_id: Optional[int] = None,
    ) -> bool:
        norm_cls = (class_label or "").strip().lower()
        if self.trigger_classes and norm_cls not in self.trigger_classes:
            return False
        if float(confidence) < self.min_confidence:
            return False

        now = float(now_unix)
        with self._lock:
            self._trigger_requested = True
            if self._state != self.STATE_RECORDING:
                self._trigger_started_unix = now
                self._state = self.STATE_RECORDING
            self._inertia_deadline_unix = max(self._inertia_deadline_unix, now + self.inertia_sec)
            if norm_cls:
                self._active_classes.add(norm_cls)
            if track_id is not None:
                self._active_track_ids.add(int(track_id))
            self._trigger_count += 1
            return True

    def on_manual_trigger(self, now_unix: float, duration_sec: Optional[float] = None) -> bool:
        now = float(now_unix)
        dur = max(2.0, float(duration_sec if duration_sec is not None else self.inertia_sec))
        with self._lock:
            self._trigger_requested = True
            if self._state != self.STATE_RECORDING:
                self._trigger_started_unix = now
                self._state = self.STATE_RECORDING
            self._inertia_deadline_unix = max(self._inertia_deadline_unix, now + dur)
            self._active_classes.add("manual")
            self._trigger_count += 1
            return True

    def is_recording_requested(self) -> bool:
        with self._lock:
            return self._trigger_requested

    def get_trigger_context(self) -> dict[str, Any]:
        with self._lock:
            return {
                "trigger_started_unix": self._trigger_started_unix,
                "inertia_deadline_unix": self._inertia_deadline_unix,
                "trigger_classes": sorted(self._active_classes),
                "track_ids": sorted(self._active_track_ids),
            }

    def evaluate_finalize(self, now_unix: float, clip_start_unix: float, is_keyframe: bool) -> Optional[str]:
        now = float(now_unix)
        with self._lock:
            if not self._trigger_requested:
                return None
            if (now - float(clip_start_unix)) >= self.max_clip_sec and is_keyframe:
                return "max_duration_rollover"
            if now >= self._inertia_deadline_unix:
                if is_keyframe or now >= (self._inertia_deadline_unix + 4.0):
                    return "inertia_expired"
            return None

    def mark_rollover(self, now_unix: float) -> dict[str, Any]:
        with self._lock:
            ctx = {
                "trigger_classes": sorted(self._active_classes),
                "track_ids": sorted(self._active_track_ids),
            }
            self._trigger_started_unix = float(now_unix)
            return ctx

    def mark_finalized(self) -> dict[str, Any]:
        with self._lock:
            ctx = {
                "trigger_classes": sorted(self._active_classes),
                "track_ids": sorted(self._active_track_ids),
            }
            self._trigger_requested = False
            self._state = self.STATE_BUFFERING
            self._active_classes.clear()
            self._active_track_ids.clear()
            return ctx

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "state": self._state,
                "trigger_requested": self._trigger_requested,
                "inertia_deadline_unix": round(self._inertia_deadline_unix, 3) if self._inertia_deadline_unix else None,
                "trigger_count": self._trigger_count,
                "active_classes": sorted(self._active_classes),
                "active_track_ids": sorted(self._active_track_ids),
            }


def _build_segment_target_path(
    storage_dir: Path,
    camera_id: str,
    tier: str,
    start_unix: float,
    nominal_dur_sec: float = 0.0,
) -> Path:
    day_str = datetime.fromtimestamp(start_unix, tz=timezone.utc).astimezone().strftime("%Y-%m-%d")
    day_dir = storage_dir / camera_id / day_str
    day_dir.mkdir(parents=True, exist_ok=True)
    dur_part = f"{max(0.1, nominal_dur_sec):.3f}" if nominal_dur_sec > 0 else "live"
    return day_dir / f"{tier}_{start_unix:.3f}_{dur_part}.mp4"


def _finalize_and_register_segment(
    archive: FilesystemNvrArchiveRepository,
    *,
    camera_id: str,
    tier: str,
    write_result: SegmentWriteResult,
    clock_offset_sec: float,
    has_motion: bool,
    metadata: Optional[dict[str, Any]] = None,
) -> Optional[RecordingSegmentRecord]:
    adj_start = max(0.0, float(write_result.start_wall_ts) + float(clock_offset_sec))
    adj_end = max(adj_start + 0.1, float(write_result.end_wall_ts) + float(clock_offset_sec))
    duration_sec = max(0.1, adj_end - adj_start)
    final_path = write_result.file_path
    canonical_name = f"{tier}_{adj_start:.3f}_{duration_sec:.3f}.mp4"
    if final_path.exists() and final_path.name != canonical_name:
        canonical_path = final_path.with_name(canonical_name)
        try:
            final_path.replace(canonical_path)
            final_path = canonical_path
        except OSError:
            pass

    size_bytes = write_result.size_bytes
    if final_path.exists():
        try:
            size_bytes = final_path.stat().st_size
        except OSError:
            pass

    rel_path = ""
    if archive.storage_dir is not None:
        try:
            rel_path = str(final_path.resolve().relative_to(archive.storage_dir.resolve())).replace("\\", "/")
        except Exception:
            rel_path = f"{camera_id}/{final_path.name}"

    record = RecordingSegmentRecord(
        id=f"{camera_id}:{final_path.name}",
        camera_id=camera_id,
        start_unix=adj_start,
        end_unix=adj_end,
        stream_url=f"/api/v1/recordings/{camera_id}/file/{final_path.name}",
        format="mp4",
        storage_type=archive.storage_type,
        has_motion=has_motion,
        size_bytes=size_bytes,
        file_path=final_path,
        metadata=metadata or {},
        stream_tier=tier,
        codec=write_result.codec_name or "h264",
        width=write_result.width,
        height=write_result.height,
        relative_path=rel_path,
    )
    archive.register_recorded_segment(record)
    return record


class SubStreamContinuousWorker:
    """Worker daemon per registrazione continua H24 del Sub Stream con taglio pulito sui keyframe."""

    def __init__(
        self,
        profile: CameraRecordingProfile,
        archive: FilesystemNvrArchiveRepository,
        *,
        segment_sec: float = 60.0,
        packet_source_factory: Optional[PacketSourceFactory] = None,
        segment_writer_factory: Optional[SegmentWriterFactory] = None,
        reconnect_initial_sec: float = 1.0,
        reconnect_max_sec: float = 30.0,
    ) -> None:
        self.profile = profile
        self.archive = archive
        self.segment_sec = max(5.0, float(segment_sec))
        self._packet_source_factory = packet_source_factory or (lambda url: PyAvRtspPacketSource(url))
        self._segment_writer_factory = segment_writer_factory or PyAvMp4SegmentWriter
        self._reconnect_initial_sec = reconnect_initial_sec
        self._reconnect_max_sec = reconnect_max_sec

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._connected: bool = False
        self._segments_written: int = 0
        self._last_error: Optional[str] = None
        self._last_packet_ts: float = 0.0

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name=f"nvr-sub-{self.profile.camera_id}",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout_sec: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout_sec)
            self._thread = None

    def _run_loop(self) -> None:
        backoff = self._reconnect_initial_sec
        while not self._stop_event.is_set():
            source: Optional[IMediaPacketSource] = None
            writer: Optional[IMediaSegmentWriter] = None
            seg_start_wall: float = 0.0
            last_wall: float = 0.0
            segment_open = False

            try:
                if not self.archive.is_configured or self.archive.storage_dir is None:
                    self._stop_event.wait(1.0)
                    continue

                source = self._packet_source_factory(self.profile.sub_rtsp_url)
                meta: StreamMetadata = source.open()
                with self._lock:
                    self._connected = True
                    self._last_error = None
                backoff = self._reconnect_initial_sec

                for pkt in source.iter_packets():
                    if self._stop_event.is_set():
                        break
                    with self._lock:
                        self._last_packet_ts = pkt.wall_ts
                    last_wall = pkt.wall_ts

                    if not segment_open:
                        if pkt.stream_kind != "video" or not pkt.is_keyframe:
                            continue
                        seg_start_wall = pkt.wall_ts
                        writer = self._segment_writer_factory()
                        target = _build_segment_target_path(
                            self.archive.storage_dir,
                            self.profile.camera_id,
                            "sub",
                            seg_start_wall + (self.profile.sub_clock_offset_ms / 1000.0),
                            self.segment_sec,
                        )
                        writer.open_segment(target, meta, seg_start_wall)
                        writer.write_packet(pkt)
                        segment_open = True
                        continue

                    # Taglio pulito esattamente sul keyframe dopo segment_sec -> zero gap tra segmenti!
                    if (
                        pkt.stream_kind == "video"
                        and pkt.is_keyframe
                        and (pkt.wall_ts - seg_start_wall) >= self.segment_sec
                    ):
                        assert writer is not None
                        res = writer.close_segment(pkt.wall_ts)
                        if res is not None:
                            _finalize_and_register_segment(
                                self.archive,
                                camera_id=self.profile.camera_id,
                                tier="sub",
                                write_result=res,
                                clock_offset_sec=self.profile.sub_clock_offset_ms / 1000.0,
                                has_motion=False,
                            )
                            with self._lock:
                                self._segments_written += 1

                        seg_start_wall = pkt.wall_ts
                        writer = self._segment_writer_factory()
                        target = _build_segment_target_path(
                            self.archive.storage_dir,
                            self.profile.camera_id,
                            "sub",
                            seg_start_wall + (self.profile.sub_clock_offset_ms / 1000.0),
                            self.segment_sec,
                        )
                        writer.open_segment(target, meta, seg_start_wall)
                        writer.write_packet(pkt)
                        continue

                    assert writer is not None
                    writer.write_packet(pkt)

                if segment_open and writer is not None:
                    res = writer.close_segment(max(seg_start_wall + 0.1, last_wall))
                    if res is not None:
                        _finalize_and_register_segment(
                            self.archive,
                            camera_id=self.profile.camera_id,
                            tier="sub",
                            write_result=res,
                            clock_offset_sec=self.profile.sub_clock_offset_ms / 1000.0,
                            has_motion=False,
                        )
                        with self._lock:
                            self._segments_written += 1

            except Exception as exc:
                if writer is not None:
                    writer.abort_segment()
                with self._lock:
                    self._connected = False
                    self._last_error = str(exc)
                logger.warning(
                    "SubStreamContinuousWorker [%s] errore stream: %s (riprovo tra %.1fs)",
                    self.profile.camera_id,
                    exc,
                    backoff,
                )
            finally:
                with self._lock:
                    self._connected = False
                if source is not None:
                    try:
                        source.close()
                    except Exception:
                        pass

            if not self._stop_event.is_set():
                self._stop_event.wait(backoff)
                backoff = min(self._reconnect_max_sec, backoff * 2.0)

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "connected": self._connected,
                "segments_written": self._segments_written,
                "last_error": self._last_error,
                "last_packet_ts": self._last_packet_ts,
            }


class MainStreamEventWorker:
    """Worker daemon per ring-buffer compresso in RAM sul Main Stream e scrittura su evento con pre-roll."""

    def __init__(
        self,
        profile: CameraRecordingProfile,
        archive: FilesystemNvrArchiveRepository,
        state_machine: MainEventStateMachine,
        ring_buffer: CompressedGopRingBuffer,
        *,
        packet_source_factory: Optional[PacketSourceFactory] = None,
        segment_writer_factory: Optional[SegmentWriterFactory] = None,
        reconnect_initial_sec: float = 1.0,
        reconnect_max_sec: float = 30.0,
    ) -> None:
        self.profile = profile
        self.archive = archive
        self.state_machine = state_machine
        self.ring_buffer = ring_buffer
        self._packet_source_factory = packet_source_factory or (lambda url: PyAvRtspPacketSource(url))
        self._segment_writer_factory = segment_writer_factory or PyAvMp4SegmentWriter
        self._reconnect_initial_sec = reconnect_initial_sec
        self._reconnect_max_sec = reconnect_max_sec

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._connected: bool = False
        self._clips_written: int = 0
        self._last_error: Optional[str] = None
        self._last_packet_ts: float = 0.0

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self.state_machine.set_buffering()
        self._thread = threading.Thread(
            target=self._run_loop,
            name=f"nvr-main-{self.profile.camera_id}",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout_sec: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout_sec)
            self._thread = None
        self.state_machine.set_idle()
        self.ring_buffer.clear()

    def _open_with_preroll(
        self,
        meta: StreamMetadata,
        current_pkt: EncodedPacket,
        trigger_started_unix: float,
    ) -> tuple[Optional[IMediaSegmentWriter], float, Optional[EncodedPacket]]:
        if self.archive.storage_dir is None:
            return None, 0.0, None
        target_start = trigger_started_unix - self.state_machine.pre_roll_sec
        preroll_gops = self.ring_buffer.snapshot_pre_roll(target_start)
        if not preroll_gops:
            if current_pkt.stream_kind != "video" or not current_pkt.is_keyframe:
                return None, 0.0, None
            clip_start = current_pkt.wall_ts
            writer = self._segment_writer_factory()
            target = _build_segment_target_path(
                self.archive.storage_dir,
                self.profile.camera_id,
                "main",
                clip_start + (self.profile.main_clock_offset_ms / 1000.0),
            )
            writer.open_segment(target, meta, clip_start)
            writer.write_packet(current_pkt)
            return writer, clip_start, current_pkt

        clip_start = preroll_gops[0].start_wall_ts
        writer = self._segment_writer_factory()
        target = _build_segment_target_path(
            self.archive.storage_dir,
            self.profile.camera_id,
            "main",
            clip_start + (self.profile.main_clock_offset_ms / 1000.0),
        )
        writer.open_segment(target, meta, clip_start)
        last_written: Optional[EncodedPacket] = None
        for gop in preroll_gops:
            for gop_pkt in gop.packets:
                writer.write_packet(gop_pkt)
                last_written = gop_pkt
        return writer, clip_start, last_written

    def _run_loop(self) -> None:
        backoff = self._reconnect_initial_sec
        while not self._stop_event.is_set():
            source: Optional[IMediaPacketSource] = None
            writer: Optional[IMediaSegmentWriter] = None
            clip_start_wall: float = 0.0
            last_wall: float = 0.0

            try:
                if not self.archive.is_configured or self.archive.storage_dir is None:
                    self._stop_event.wait(1.0)
                    continue

                source = self._packet_source_factory(self.profile.main_rtsp_url)
                meta: StreamMetadata = source.open()
                with self._lock:
                    self._connected = True
                    self._last_error = None
                backoff = self._reconnect_initial_sec

                for pkt in source.iter_packets():
                    if self._stop_event.is_set():
                        break
                    with self._lock:
                        self._last_packet_ts = pkt.wall_ts
                    last_wall = pkt.wall_ts
                    self.ring_buffer.push_packet(pkt)

                    if writer is None:
                        if not self.state_machine.is_recording_requested():
                            continue
                        ctx = self.state_machine.get_trigger_context()
                        writer, clip_start_wall, last_written = self._open_with_preroll(
                            meta,
                            pkt,
                            float(ctx["trigger_started_unix"]),
                        )
                        if writer is not None and last_written is not pkt:
                            # `pkt` è già nel GOP corrente pushato sopra in ring_buffer -> non duplicarlo
                            pass
                        continue

                    finalize_reason = (
                        self.state_machine.evaluate_finalize(pkt.wall_ts, clip_start_wall, pkt.is_keyframe)
                        if pkt.stream_kind == "video"
                        else None
                    )
                    if finalize_reason == "max_duration_rollover":
                        ctx = self.state_machine.mark_rollover(pkt.wall_ts)
                        res = writer.close_segment(pkt.wall_ts)
                        if res is not None:
                            _finalize_and_register_segment(
                                self.archive,
                                camera_id=self.profile.camera_id,
                                tier="main",
                                write_result=res,
                                clock_offset_sec=self.profile.main_clock_offset_ms / 1000.0,
                                has_motion=True,
                                metadata={
                                    "pre_roll_sec": self.state_machine.pre_roll_sec,
                                    "inertia_sec": self.state_machine.inertia_sec,
                                    "rollover": True,
                                    **ctx,
                                },
                            )
                            with self._lock:
                                self._clips_written += 1

                        clip_start_wall = pkt.wall_ts
                        writer = self._segment_writer_factory()
                        target = _build_segment_target_path(
                            self.archive.storage_dir,
                            self.profile.camera_id,
                            "main",
                            clip_start_wall + (self.profile.main_clock_offset_ms / 1000.0),
                        )
                        writer.open_segment(target, meta, clip_start_wall)
                        writer.write_packet(pkt)
                        continue

                    if finalize_reason == "inertia_expired":
                        if not pkt.is_keyframe:
                            writer.write_packet(pkt)
                        end_ts = pkt.wall_ts
                        ctx = self.state_machine.mark_finalized()
                        res = writer.close_segment(end_ts)
                        writer = None
                        if res is not None:
                            _finalize_and_register_segment(
                                self.archive,
                                camera_id=self.profile.camera_id,
                                tier="main",
                                write_result=res,
                                clock_offset_sec=self.profile.main_clock_offset_ms / 1000.0,
                                has_motion=True,
                                metadata={
                                    "pre_roll_sec": self.state_machine.pre_roll_sec,
                                    "inertia_sec": self.state_machine.inertia_sec,
                                    **ctx,
                                },
                            )
                            with self._lock:
                                self._clips_written += 1
                        continue

                    writer.write_packet(pkt)

                if writer is not None:
                    ctx = self.state_machine.mark_finalized()
                    res = writer.close_segment(max(clip_start_wall + 0.1, last_wall))
                    writer = None
                    if res is not None:
                        _finalize_and_register_segment(
                            self.archive,
                            camera_id=self.profile.camera_id,
                            tier="main",
                            write_result=res,
                            clock_offset_sec=self.profile.main_clock_offset_ms / 1000.0,
                            has_motion=True,
                            metadata={
                                "pre_roll_sec": self.state_machine.pre_roll_sec,
                                "inertia_sec": self.state_machine.inertia_sec,
                                **ctx,
                            },
                        )
                        with self._lock:
                            self._clips_written += 1

            except Exception as exc:
                if writer is not None:
                    writer.abort_segment()
                    writer = None
                with self._lock:
                    self._connected = False
                    self._last_error = str(exc)
                logger.warning(
                    "MainStreamEventWorker [%s] errore stream: %s (riprovo tra %.1fs)",
                    self.profile.camera_id,
                    exc,
                    backoff,
                )
            finally:
                with self._lock:
                    self._connected = False
                if source is not None:
                    try:
                        source.close()
                    except Exception:
                        pass

            if not self._stop_event.is_set():
                self._stop_event.wait(backoff)
                backoff = min(self._reconnect_max_sec, backoff * 2.0)

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "connected": self._connected,
                "clips_written": self._clips_written,
                "last_error": self._last_error,
                "last_packet_ts": self._last_packet_ts,
                "ring_buffer": self.ring_buffer.get_stats(),
                "event_state": self.state_machine.get_status(),
            }


class CameraDualTierRecorder:
    """Composizione OOP per singola telecamera: Sub H24 continuo + Main su evento con pre-roll RAM."""

    def __init__(
        self,
        profile: CameraRecordingProfile,
        archive: FilesystemNvrArchiveRepository,
        config: SpatialServerConfig,
        *,
        packet_source_factory: Optional[PacketSourceFactory] = None,
        segment_writer_factory: Optional[SegmentWriterFactory] = None,
    ) -> None:
        self.profile = profile
        self.state_machine = MainEventStateMachine(
            pre_roll_sec=config.nvr_main_pre_roll_sec,
            inertia_sec=config.nvr_main_inertia_sec,
            max_clip_sec=config.nvr_main_max_clip_sec,
            trigger_classes=config.nvr_trigger_classes,
            min_confidence=config.nvr_min_confidence,
        )
        self.ring_buffer = CompressedGopRingBuffer(
            max_duration_sec=config.nvr_main_pre_roll_sec + 4.0,
            max_bytes=int(config.nvr_ram_buffer_max_mb_per_cam * 1024 * 1024),
        )
        self.sub_worker = SubStreamContinuousWorker(
            profile=profile,
            archive=archive,
            segment_sec=config.nvr_sub_segment_sec,
            packet_source_factory=packet_source_factory,
            segment_writer_factory=segment_writer_factory,
        )
        self.main_worker = MainStreamEventWorker(
            profile=profile,
            archive=archive,
            state_machine=self.state_machine,
            ring_buffer=self.ring_buffer,
            packet_source_factory=packet_source_factory,
            segment_writer_factory=segment_writer_factory,
        )

    def start(self) -> None:
        if not self.profile.enabled:
            return
        self.sub_worker.start()
        self.main_worker.start()

    def stop(self) -> None:
        self.sub_worker.stop()
        self.main_worker.stop()

    def get_diagnostics(self) -> dict[str, Any]:
        return {
            "camera_id": self.profile.camera_id,
            "enabled": self.profile.enabled,
            "sub": self.sub_worker.get_status(),
            "main": self.main_worker.get_status(),
        }


class DualTierNvrRecorderCoordinator(IDualTierRecorderCoordinator):
    """Coordinatore scalabile per tutte le camere del manifesto (Sub H24 + Main Event + Retention)."""

    def __init__(
        self,
        config: SpatialServerConfig,
        archive: FilesystemNvrArchiveRepository,
        camera_manifest_meta: Optional[dict[str, dict[str, Any]]] = None,
        *,
        packet_source_factory: Optional[PacketSourceFactory] = None,
        segment_writer_factory: Optional[SegmentWriterFactory] = None,
    ) -> None:
        self.config = config
        self.archive = archive
        self.camera_manifest_meta = dict(camera_manifest_meta or {})
        self._packet_source_factory = packet_source_factory
        self._segment_writer_factory = segment_writer_factory

        self.retention_manager = DiskRetentionManager(
            archive=archive,
            sub_retention_days=config.nvr_sub_retention_days,
            main_retention_days=config.nvr_main_retention_days,
            min_free_gb=config.nvr_min_free_gb,
            max_storage_gb=config.nvr_max_storage_gb,
        )
        self.profiles: dict[str, CameraRecordingProfile] = self._build_profiles()
        self.recorders: dict[str, CameraDualTierRecorder] = {
            cam_id: CameraDualTierRecorder(
                profile=prof,
                archive=archive,
                config=config,
                packet_source_factory=packet_source_factory,
                segment_writer_factory=segment_writer_factory,
            )
            for cam_id, prof in self.profiles.items()
        }
        self._state: str = "stopped"
        self._state_reason: str = "not_started"
        self._pyav_version: Optional[str] = None
        self._prune_task: Optional[asyncio.Task[None]] = None
        self._last_prune_report: Optional[RetentionSweepReport] = None

    def _build_profiles(self) -> dict[str, CameraRecordingProfile]:
        offsets_map: dict[tuple[str, str], float] = {
            (cam_id, tier): offset_ms
            for cam_id, tier, offset_ms in self.config.nvr_camera_clock_offsets
        }
        stream_overrides: dict[str, tuple[str, str]] = {
            cam_id: (sub_url, main_url)
            for cam_id, sub_url, main_url in self.config.nvr_camera_streams
        }

        base_rtsp = (self.config.go2rtc_rtsp_base_url or "rtsp://127.0.0.1:8554").rstrip("/")
        cam_ids = list(self.camera_manifest_meta.keys()) or list(stream_overrides.keys()) or ["Cam_Carraio"]
        for cam_id in stream_overrides:
            if cam_id not in cam_ids:
                cam_ids.append(cam_id)

        profiles: dict[str, CameraRecordingProfile] = {}
        for cam_id in cam_ids:
            if cam_id in stream_overrides:
                sub_url, main_url = stream_overrides[cam_id]
                if not sub_url:
                    sub_url = main_url
                if not main_url:
                    main_url = sub_url
            else:
                meta = self.camera_manifest_meta.get(cam_id) or {}
                slug = re.sub(r"^cam_", "", cam_id, flags=re.IGNORECASE).lower()
                main_id = str(meta.get("stream_id") or "").strip() or f"{slug}_main"
                sub_id = str(meta.get("sub_stream_id") or "").strip() or f"{slug}_sub"
                sub_url = f"{base_rtsp}/{sub_id}"
                main_url = f"{base_rtsp}/{main_id}"

            profiles[cam_id] = CameraRecordingProfile(
                camera_id=cam_id,
                sub_rtsp_url=sub_url,
                main_rtsp_url=main_url,
                sub_clock_offset_ms=offsets_map.get((cam_id, "sub"), 0.0),
                main_clock_offset_ms=offsets_map.get((cam_id, "main"), 0.0),
                enabled=True,
            )
        return profiles

    async def start(self) -> None:
        if not self.config.nvr_recorder_enabled:
            self._state = "disabled"
            self._state_reason = "SPATIAL_NVR_RECORDER_ENABLED=false"
            return

        if not self.archive.is_configured:
            self._state = "storage_not_configured"
            self._state_reason = "SPATIAL_NVR_STORAGE_DIR non configurato o directory non trovata"
            logger.warning("NVR dual-tier abilitato ma disco non configurato (%s)", self.archive.storage_dir)
            return

        if self._packet_source_factory is None or self._segment_writer_factory is None:
            ok_av, info = is_pyav_available()
            if not ok_av:
                self._state = "missing_pyav"
                self._state_reason = f"Pacchetto PyAV ('av') non installato: {info}"
                logger.warning("NVR dual-tier in standby: %s", self._state_reason)
                return
            self._pyav_version = info

        self.archive.reconcile_with_filesystem(force=False)
        for rec in self.recorders.values():
            rec.start()

        self._state = "running"
        self._state_reason = "ok"
        self._prune_task = asyncio.create_task(self._retention_loop())
        logger.info(
            "DualTierNvrRecorderCoordinator avviato su %d telecamere (pre_roll=%.1fs, inertia=%.1fs, sub_seg=%.0fs)",
            len(self.recorders),
            self.config.nvr_main_pre_roll_sec,
            self.config.nvr_main_inertia_sec,
            self.config.nvr_sub_segment_sec,
        )

    async def stop(self) -> None:
        if self._prune_task is not None:
            self._prune_task.cancel()
            try:
                await self._prune_task
            except asyncio.CancelledError:
                pass
            self._prune_task = None

        for rec in self.recorders.values():
            rec.stop()

        if self._state == "running":
            self._state = "stopped"
            self._state_reason = "stopped"

    async def _retention_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.config.nvr_prune_interval_sec)
                self._last_prune_report = await asyncio.to_thread(self.retention_manager.sweep)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Errore nel ciclo retention NVR: %s", exc)

    def notify_detection_activity(
        self,
        *,
        camera_id: str,
        timestamp: float,
        class_label: str,
        confidence: float,
        track_id: Optional[int] = None,
    ) -> bool:
        if self._state != "running":
            return False
        rec = self.recorders.get(camera_id)
        if rec is None:
            return False
        return rec.state_machine.on_detection(
            now_unix=timestamp,
            class_label=class_label,
            confidence=confidence,
            track_id=track_id,
        )

    def trigger_manual_event(self, camera_id: str, duration_sec: Optional[float] = None) -> dict[str, Any]:
        rec = self.recorders.get(camera_id)
        if rec is None:
            raise KeyError(f"Camera '{camera_id}' non registrata nel coordinatore NVR")
        now_ts = time.time()
        triggered = rec.state_machine.on_manual_trigger(now_ts, duration_sec=duration_sec)
        return {
            "camera_id": camera_id,
            "triggered": triggered,
            "recorder_state": self._state,
            "event_state": rec.state_machine.get_status(),
        }

    def run_maintenance_prune(self) -> RetentionSweepReport:
        self._last_prune_report = self.retention_manager.sweep()
        return self._last_prune_report

    def get_diagnostics(self) -> dict[str, Any]:
        per_cam = {cam_id: rec.get_diagnostics() for cam_id, rec in self.recorders.items()}
        ram_total_mb = round(
            sum(float(d["main"]["ring_buffer"]["buffered_mb"]) for d in per_cam.values()),
            2,
        )
        active_main_clips = sum(
            1 for d in per_cam.values() if d["main"]["event_state"]["state"] == "recording"
        )
        return {
            "enabled": self.config.nvr_recorder_enabled,
            "state": self._state,
            "reason": self._state_reason,
            "pyav_version": self._pyav_version,
            "pre_roll_sec": self.config.nvr_main_pre_roll_sec,
            "inertia_sec": self.config.nvr_main_inertia_sec,
            "sub_segment_sec": self.config.nvr_sub_segment_sec,
            "ram_buffer_total_mb": ram_total_mb,
            "active_main_recordings": active_main_clips,
            "cameras": per_cam,
            "last_prune": (
                {
                    "deleted_sub_count": self._last_prune_report.deleted_sub_count,
                    "deleted_main_count": self._last_prune_report.deleted_main_count,
                    "reclaimed_bytes": self._last_prune_report.reclaimed_bytes,
                    "disk_free_gb": self._last_prune_report.disk_free_gb,
                    "disk_total_gb": self._last_prune_report.disk_total_gb,
                    "ran_at_unix": self._last_prune_report.ran_at_unix,
                }
                if self._last_prune_report is not None
                else None
            ),
        }
