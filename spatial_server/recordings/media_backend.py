from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Iterator, Optional

from spatial_server.recordings.interfaces import (
    EncodedPacket,
    IMediaPacketSource,
    IMediaSegmentWriter,
    SegmentWriteResult,
    StreamMetadata,
)

logger = logging.getLogger("spatial_server.recordings.media")

MP4_COMPATIBLE_AUDIO_CODECS = frozenset({"aac", "mp3", "mp2", "opus", "ac3"})


def is_pyav_available() -> tuple[bool, str]:
    try:
        import av  # type: ignore

        return True, str(getattr(av, "__version__", "available"))
    except Exception as exc:
        return False, str(exc)


def _normalize_video_codec(raw_name: str) -> str:
    lower = (raw_name or "").strip().lower()
    if lower in ("hevc", "h265", "hvc1", "hev1"):
        return "hevc"
    if lower in ("h264", "avc", "avc1"):
        return "h264"
    return lower or "unknown"


class PyAvRtspPacketSource(IMediaPacketSource):
    """Lettore RTSP TCP zero-transcode basato su PyAV (demux pacchetti H.264/HEVC senza decodifica)."""

    def __init__(self, rtsp_url: str, *, timeout_sec: float = 5.0) -> None:
        self.rtsp_url = rtsp_url
        self.timeout_sec = max(1.0, float(timeout_sec))
        self._container: Any = None
        self._video_stream: Any = None
        self._audio_stream: Any = None
        self._metadata: Optional[StreamMetadata] = None

    def open(self) -> StreamMetadata:
        import av  # type: ignore

        stimeout_us = str(int(self.timeout_sec * 1_000_000))
        options = {
            "rtsp_transport": "tcp",
            "stimeout": stimeout_us,
            "fflags": "nobuffer",
            "flags": "low_delay",
            "max_delay": "500000",
        }
        self._container = av.open(self.rtsp_url, options=options)
        video_streams = [s for s in self._container.streams if s.type == "video"]
        if not video_streams:
            self.close()
            raise RuntimeError(f"Nessuno stream video trovato su {self.rtsp_url}")

        self._video_stream = video_streams[0]
        video_codec = _normalize_video_codec(getattr(self._video_stream.codec_context, "name", "h264"))
        width = int(getattr(self._video_stream.codec_context, "width", 0) or 0)
        height = int(getattr(self._video_stream.codec_context, "height", 0) or 0)
        tb = getattr(self._video_stream, "time_base", None)
        tb_tuple = (int(tb.numerator), int(tb.denominator)) if tb is not None else (1, 90000)

        audio_streams = [s for s in self._container.streams if s.type == "audio"]
        chosen_audio = None
        audio_codec: Optional[str] = None
        for a_stream in audio_streams:
            a_name = str(getattr(a_stream.codec_context, "name", "") or "").lower()
            if a_name in MP4_COMPATIBLE_AUDIO_CODECS:
                chosen_audio = a_stream
                audio_codec = a_name
                break

        self._audio_stream = chosen_audio
        self._metadata = StreamMetadata(
            video_codec=video_codec,
            width=width,
            height=height,
            video_time_base=tb_tuple,
            has_audio=chosen_audio is not None,
            audio_codec=audio_codec,
            raw_video_stream=self._video_stream,
            raw_audio_stream=chosen_audio,
        )
        return self._metadata

    def iter_packets(self) -> Iterator[EncodedPacket]:
        if self._container is None or self._video_stream is None or self._metadata is None:
            raise RuntimeError("PyAvRtspPacketSource non aperto")

        demux_streams = [self._video_stream]
        if self._audio_stream is not None:
            demux_streams.append(self._audio_stream)

        for pkt in self._container.demux(demux_streams):
            if pkt is None or pkt.size <= 0 or pkt.dts is None:
                continue
            stream_kind = "video" if pkt.stream == self._video_stream else "audio"
            tb = getattr(pkt, "time_base", None) or getattr(pkt.stream, "time_base", None)
            tb_num = int(tb.numerator) if tb is not None else 1
            tb_den = int(tb.denominator) if tb is not None else 90000
            yield EncodedPacket(
                stream_kind=stream_kind,
                data=bytes(pkt),
                pts=pkt.pts,
                dts=pkt.dts,
                duration=pkt.duration,
                time_base_num=tb_num,
                time_base_den=tb_den,
                is_keyframe=bool(pkt.is_keyframe) if stream_kind == "video" else False,
                wall_ts=time.time(),
                codec_name=self._metadata.video_codec if stream_kind == "video" else (self._metadata.audio_codec or "aac"),
                width=self._metadata.width if stream_kind == "video" else 0,
                height=self._metadata.height if stream_kind == "video" else 0,
                raw_packet=pkt,
                raw_stream=pkt.stream,
            )

    def close(self) -> None:
        if self._container is not None:
            try:
                self._container.close()
            except Exception:
                pass
            self._container = None
        self._video_stream = None
        self._audio_stream = None


class PyAvMp4SegmentWriter(IMediaSegmentWriter):
    """Muxer MP4 atomico zero-transcode (`-c copy` equivalente) con `movflags=+faststart`."""

    def __init__(self) -> None:
        self._container: Any = None
        self._out_video: Any = None
        self._out_audio: Any = None
        self._final_path: Optional[Path] = None
        self._tmp_path: Optional[Path] = None
        self._metadata: Optional[StreamMetadata] = None
        self._start_wall_ts: float = 0.0
        self._first_dts_by_kind: dict[str, int] = {}
        self._last_dts_by_kind: dict[str, int] = {}
        self._packet_count: int = 0
        self._video_frame_count: int = 0

    def _add_template_stream(self, container: Any, template_stream: Any) -> Any:
        if hasattr(container, "add_stream_from_template"):
            return container.add_stream_from_template(template_stream)
        return container.add_stream(template=template_stream)

    def open_segment(self, target_path: Path, metadata: StreamMetadata, start_wall_ts: float) -> None:
        import av  # type: ignore

        target_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target_path.with_name(f".{target_path.stem}.tmp.mp4")
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass

        container = av.open(str(tmp_path), mode="w", format="mp4", options={"movflags": "+faststart"})
        out_video = self._add_template_stream(container, metadata.raw_video_stream)
        out_audio = None
        if metadata.has_audio and metadata.raw_audio_stream is not None:
            try:
                out_audio = self._add_template_stream(container, metadata.raw_audio_stream)
            except Exception as exc:
                logger.debug("Audio stream omesso nel mux MP4 (%s): %s", metadata.audio_codec, exc)
                out_audio = None

        self._container = container
        self._out_video = out_video
        self._out_audio = out_audio
        self._final_path = target_path
        self._tmp_path = tmp_path
        self._metadata = metadata
        self._start_wall_ts = float(start_wall_ts)
        self._first_dts_by_kind.clear()
        self._last_dts_by_kind.clear()
        self._packet_count = 0
        self._video_frame_count = 0

    def write_packet(self, packet: EncodedPacket) -> None:
        if self._container is None:
            return
        import av  # type: ignore

        kind = packet.stream_kind
        out_stream = self._out_video if kind == "video" else self._out_audio
        if out_stream is None:
            return

        pkt = av.Packet(packet.data)
        pkt.stream = out_stream
        if packet.time_base_den > 0:
            from fractions import Fraction

            pkt.time_base = Fraction(packet.time_base_num, packet.time_base_den)

        raw_dts = int(packet.dts if packet.dts is not None else (packet.pts or 0))
        raw_pts = int(packet.pts if packet.pts is not None else raw_dts)
        if kind not in self._first_dts_by_kind:
            self._first_dts_by_kind[kind] = raw_dts

        base_dts = self._first_dts_by_kind[kind]
        rebased_dts = max(0, raw_dts - base_dts)
        prev_dts = self._last_dts_by_kind.get(kind)
        if prev_dts is not None and rebased_dts <= prev_dts:
            rebased_dts = prev_dts + 1
        self._last_dts_by_kind[kind] = rebased_dts

        rebased_pts = max(rebased_dts, raw_pts - base_dts)
        pkt.dts = rebased_dts
        pkt.pts = rebased_pts
        if packet.duration is not None and packet.duration > 0:
            pkt.duration = int(packet.duration)
        if kind == "video":
            pkt.is_keyframe = packet.is_keyframe
            self._video_frame_count += 1

        self._container.mux(pkt)
        self._packet_count += 1

    def close_segment(self, end_wall_ts: float) -> Optional[SegmentWriteResult]:
        if self._container is None or self._final_path is None or self._tmp_path is None:
            return None
        final_path = self._final_path
        tmp_path = self._tmp_path
        meta = self._metadata or StreamMetadata()
        pkt_count = self._packet_count
        frame_count = self._video_frame_count
        start_ts = self._start_wall_ts

        try:
            self._container.close()
        except Exception as exc:
            logger.warning("Errore chiusura container MP4 %s: %s", tmp_path.name, exc)
            self._reset_handles()
            self._unlink_quiet(tmp_path)
            return None

        self._reset_handles()
        if frame_count <= 0 or not tmp_path.exists():
            self._unlink_quiet(tmp_path)
            return None

        try:
            tmp_path.replace(final_path)
            size_bytes = final_path.stat().st_size
        except OSError as exc:
            logger.warning("Errore rename atomico %s -> %s: %s", tmp_path, final_path, exc)
            self._unlink_quiet(tmp_path)
            return None

        return SegmentWriteResult(
            file_path=final_path,
            size_bytes=size_bytes,
            packet_count=pkt_count,
            video_frame_count=frame_count,
            start_wall_ts=start_ts,
            end_wall_ts=max(start_ts + 0.1, float(end_wall_ts)),
            duration_sec=max(0.1, float(end_wall_ts) - start_ts),
            codec_name=meta.video_codec,
            width=meta.width,
            height=meta.height,
        )

    def abort_segment(self) -> None:
        tmp_path = self._tmp_path
        if self._container is not None:
            try:
                self._container.close()
            except Exception:
                pass
        self._reset_handles()
        if tmp_path is not None:
            self._unlink_quiet(tmp_path)

    def _reset_handles(self) -> None:
        self._container = None
        self._out_video = None
        self._out_audio = None
        self._final_path = None
        self._tmp_path = None

    @staticmethod
    def _unlink_quiet(path: Path) -> None:
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass
