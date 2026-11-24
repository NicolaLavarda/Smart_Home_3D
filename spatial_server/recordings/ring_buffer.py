from __future__ import annotations

import threading
from collections import deque
from typing import Any, Optional

from spatial_server.recordings.interfaces import EncodedPacket, GopChunk


class CompressedGopRingBuffer:
    """Ring-buffer thread-safe in RAM per pacchetti video/audio compressi allineati ai GOP (IDR keyframe).

    Consente di mantenere continuamente gli ultimi N secondi del Main Stream in RAM con consumo CPU quasi nullo
    (nessuna decodifica pixel) e di scaricarli su disco appena scatta un evento.
    """

    def __init__(
        self,
        max_duration_sec: float = 14.0,
        max_bytes: int = 48 * 1024 * 1024,
    ) -> None:
        self._max_duration_sec = max(1.0, float(max_duration_sec))
        self._max_bytes = max(1024 * 1024, int(max_bytes))
        self._lock = threading.RLock()
        self._gops: deque[GopChunk] = deque()
        self._current_gop: Optional[GopChunk] = None
        self._sealed_bytes: int = 0
        self._dropped_for_budget_count: int = 0
        self._last_codec: str = "h264"
        self._last_width: int = 0
        self._last_height: int = 0

    def push_packet(self, packet: EncodedPacket) -> Optional[GopChunk]:
        """Inserisce un pacchetto compresso; restituisce un eventuale GOP appena sigillato."""
        pkt_bytes = len(packet.data) if packet.data else 0
        sealed_out: Optional[GopChunk] = None

        with self._lock:
            if packet.stream_kind == "video":
                if packet.codec_name:
                    self._last_codec = packet.codec_name
                if packet.width > 0:
                    self._last_width = packet.width
                if packet.height > 0:
                    self._last_height = packet.height

                if packet.is_keyframe:
                    if self._current_gop is not None and self._current_gop.packets:
                        sealed_out = self._current_gop
                        self._gops.append(sealed_out)
                        self._sealed_bytes += sealed_out.size_bytes
                    self._current_gop = GopChunk(
                        packets=[packet],
                        start_wall_ts=packet.wall_ts,
                        end_wall_ts=packet.wall_ts,
                        size_bytes=pkt_bytes,
                        codec_name=packet.codec_name or self._last_codec,
                        width=packet.width or self._last_width,
                        height=packet.height or self._last_height,
                    )
                    self._evict_if_needed()
                    return sealed_out

                # Ignora pacchetti video P/B iniziali finché non arriva il primo keyframe
                if self._current_gop is None:
                    return None

                self._current_gop.packets.append(packet)
                if packet.wall_ts > self._current_gop.end_wall_ts:
                    self._current_gop.end_wall_ts = packet.wall_ts
                self._current_gop.size_bytes += pkt_bytes
                self._evict_if_needed()
                return None

            # Pacchetti audio: aggregati solo se esiste già un GOP video avviato da keyframe
            if self._current_gop is None:
                return None
            self._current_gop.packets.append(packet)
            if packet.wall_ts > self._current_gop.end_wall_ts:
                self._current_gop.end_wall_ts = packet.wall_ts
            self._current_gop.size_bytes += pkt_bytes
            self._evict_if_needed()
            return None

    def _total_bytes_locked(self) -> int:
        cur_bytes = self._current_gop.size_bytes if self._current_gop is not None else 0
        return self._sealed_bytes + cur_bytes

    def _oldest_ts_locked(self) -> Optional[float]:
        if self._gops:
            return self._gops[0].start_wall_ts
        if self._current_gop is not None:
            return self._current_gop.start_wall_ts
        return None

    def _newest_ts_locked(self) -> Optional[float]:
        if self._current_gop is not None:
            return self._current_gop.end_wall_ts
        if self._gops:
            return self._gops[-1].end_wall_ts
        return None

    def _evict_if_needed(self) -> None:
        # Mantiene almeno 1 GOP sigillato se sta nel budget di memoria, altrimenti evita OOM
        while self._gops:
            newest_ts = self._newest_ts_locked()
            oldest_ts = self._gops[0].start_wall_ts
            span_sec = (newest_ts - oldest_ts) if newest_ts is not None else 0.0
            over_bytes = self._total_bytes_locked() > self._max_bytes
            over_time = span_sec > self._max_duration_sec and len(self._gops) > 1
            if not over_bytes and not over_time:
                break
            removed = self._gops.popleft()
            self._sealed_bytes = max(0, self._sealed_bytes - removed.size_bytes)
            if over_bytes:
                self._dropped_for_budget_count += 1

    def snapshot_pre_roll(self, target_start_unix: float) -> list[GopChunk]:
        """Restituisce una copia ordinata dei GOP a partire dall'ultimo keyframe <= target_start_unix."""
        with self._lock:
            candidates: list[GopChunk] = list(self._gops)
            if self._current_gop is not None and self._current_gop.packets:
                candidates.append(self._current_gop)
            if not candidates:
                return []

            start_idx = 0
            for idx, gop in enumerate(candidates):
                if gop.start_wall_ts <= target_start_unix:
                    start_idx = idx
                else:
                    break

            selected = candidates[start_idx:]
            return [
                GopChunk(
                    packets=list(gop.packets),
                    start_wall_ts=gop.start_wall_ts,
                    end_wall_ts=gop.end_wall_ts,
                    size_bytes=gop.size_bytes,
                    codec_name=gop.codec_name,
                    width=gop.width,
                    height=gop.height,
                )
                for gop in selected
            ]

    def clear(self) -> None:
        with self._lock:
            self._gops.clear()
            self._current_gop = None
            self._sealed_bytes = 0

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            oldest_ts = self._oldest_ts_locked()
            newest_ts = self._newest_ts_locked()
            buffered_sec = max(0.0, newest_ts - oldest_ts) if (oldest_ts is not None and newest_ts is not None) else 0.0
            total_bytes = self._total_bytes_locked()
            gop_count = len(self._gops) + (1 if self._current_gop is not None else 0)
            return {
                "gop_count": gop_count,
                "buffered_sec": round(buffered_sec, 2),
                "buffered_bytes": total_bytes,
                "buffered_mb": round(total_bytes / (1024 * 1024), 2),
                "max_bytes": self._max_bytes,
                "max_duration_sec": self._max_duration_sec,
                "dropped_for_budget_count": self._dropped_for_budget_count,
                "codec": self._last_codec,
                "width": self._last_width,
                "height": self._last_height,
            }
