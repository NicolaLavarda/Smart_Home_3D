from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
import logging
import os
from pathlib import Path
import sys
import time
from typing import Optional

logger = logging.getLogger("spatial_server.telemetry.gpu")


@dataclass(frozen=True)
class GpuSample:
    """Point-in-time GPU load and memory utilization snapshot."""

    gpu_percent: Optional[float] = None
    gpu_memory_mb: Optional[float] = None
    gpu_3d_percent: Optional[float] = None
    gpu_video_decode_percent: Optional[float] = None
    gpu_compute_percent: Optional[float] = None
    backend_name: str = "unavailable"
    adapter_name: Optional[str] = None


class IGpuMetricsProbe(ABC):
    """Strategy interface for low-overhead OS GPU load sampling."""

    @abstractmethod
    def sample(self) -> GpuSample:
        """Return the latest GPU load & memory snapshot (non-blocking)."""

    def close(self) -> None:
        """Release any native OS handles."""


class NoOpGpuProbe(IGpuMetricsProbe):
    """Fallback probe when no GPU telemetry interface is available."""

    def __init__(self, reason: str = "unavailable") -> None:
        self.reason = reason

    def sample(self) -> GpuSample:
        return GpuSample(backend_name=self.reason)


class WindowsGpuProbe(IGpuMetricsProbe):
    """
    Zero-subprocess Windows 10/11 GPU telemetry probe for Intel HD Graphics 530 & WDDM 2.x GPUs.

    Strategy cascade:
    1. Win32 PDH (`pdh.dll`, English counters `\\GPU Engine(*)\\Utilization Percentage` and
       `\\GPU Adapter Memory(*)\\...`), which gives per-engine-type breakdown (3D / VideoDecode / Compute).
    2. Direct WDDM kernel query (`gdi32.dll` `D3DKMTEnumAdapters2` + `D3DKMTQueryAdapterInfo`
       + `D3DKMTQueryStatistics`), which skips software WARP adapters and computes exact node busy %
       over `RunningTime` deltas even inside restricted service or sandboxed sessions.
    """

    _PDH_FMT_DOUBLE = 0x00000200
    _PDH_MORE_DATA = 0x800007D2
    _KMTQAITYPE_ADAPTERTYPE = 15
    _D3DKMT_QUERY_ADAPTER = 0
    _D3DKMT_QUERY_SEGMENT = 3
    _D3DKMT_QUERY_NODE = 5

    def __init__(self) -> None:
        self._mode: str = "init"
        self._pdh = None
        self._pdh_query = None
        self._pdh_eng_counter = None
        self._pdh_mem_shared_counter = None
        self._pdh_mem_ded_counter = None
        self._pdh_primed = False

        self._gdi32 = None
        self._prev_node_times: dict[tuple[int, int, int], int] = {}
        self._prev_sample_mono: float = 0.0
        self._last_d3dkmt_sample: Optional[GpuSample] = None

        self._init_backends()

    def _init_backends(self) -> None:
        if sys.platform != "win32":
            self._mode = "unsupported_os"
            return

        if self._try_init_pdh():
            self._mode = "pdh"
            return

        if self._try_init_d3dkmt():
            self._mode = "d3dkmt"
            return

        self._mode = "unavailable"

    def _try_init_pdh(self) -> bool:
        try:
            import ctypes
            import ctypes.wintypes as wt

            pdh = ctypes.windll.pdh
            h_query = wt.HANDLE()
            if pdh.PdhOpenQueryW(None, 0, ctypes.byref(h_query)) != 0:
                return False

            h_eng = wt.HANDLE()
            res_eng = pdh.PdhAddEnglishCounterW(
                h_query,
                r"\GPU Engine(*)\Utilization Percentage",
                0,
                ctypes.byref(h_eng),
            )
            if res_eng != 0:
                pdh.PdhCloseQuery(h_query)
                return False

            h_shared = wt.HANDLE()
            if (
                pdh.PdhAddEnglishCounterW(
                    h_query,
                    r"\GPU Adapter Memory(*)\Shared Usage",
                    0,
                    ctypes.byref(h_shared),
                )
                != 0
            ):
                h_shared = None

            h_ded = wt.HANDLE()
            if (
                pdh.PdhAddEnglishCounterW(
                    h_query,
                    r"\GPU Adapter Memory(*)\Dedicated Usage",
                    0,
                    ctypes.byref(h_ded),
                )
                != 0
            ):
                h_ded = None

            # Prime initial PDH delta sample
            pdh.PdhCollectQueryData(h_query)
            self._pdh = pdh
            self._pdh_query = h_query
            self._pdh_eng_counter = h_eng
            self._pdh_mem_shared_counter = h_shared
            self._pdh_mem_ded_counter = h_ded
            self._pdh_primed = True
            return True
        except Exception as exc:
            logger.debug("PDH GPU init skipped: %s", exc)
            return False

    def _read_pdh_array(self, h_counter) -> list[tuple[str, float]]:
        import ctypes
        import ctypes.wintypes as wt

        if self._pdh is None or h_counter is None:
            return []

        class _PDH_FMT_COUNTERVALUE(ctypes.Structure):
            _fields_ = [("CStatus", wt.DWORD), ("doubleValue", ctypes.c_double)]

        class _PDH_FMT_COUNTERVALUE_ITEM_W(ctypes.Structure):
            _fields_ = [("szName", wt.LPWSTR), ("FmtValue", _PDH_FMT_COUNTERVALUE)]

        buf_size = wt.DWORD(0)
        item_count = wt.DWORD(0)
        status = self._pdh.PdhGetFormattedCounterArrayW(
            h_counter,
            self._PDH_FMT_DOUBLE,
            ctypes.byref(buf_size),
            ctypes.byref(item_count),
            None,
        )
        if (status & 0xFFFFFFFF) != self._PDH_MORE_DATA or buf_size.value == 0:
            return []

        buf = (ctypes.c_uint8 * buf_size.value)()
        status2 = self._pdh.PdhGetFormattedCounterArrayW(
            h_counter,
            self._PDH_FMT_DOUBLE,
            ctypes.byref(buf_size),
            ctypes.byref(item_count),
            buf,
        )
        if status2 != 0:
            return []

        items = ctypes.cast(buf, ctypes.POINTER(_PDH_FMT_COUNTERVALUE_ITEM_W))
        out: list[tuple[str, float]] = []
        for idx in range(int(item_count.value)):
            entry = items[idx]
            if entry.FmtValue.CStatus == 0:
                out.append((str(entry.szName or ""), float(entry.FmtValue.doubleValue)))
        return out

    def _sample_pdh(self) -> Optional[GpuSample]:
        if self._pdh is None or self._pdh_query is None:
            return None
        try:
            if self._pdh.PdhCollectQueryData(self._pdh_query) != 0:
                return None

            eng_rows = self._read_pdh_array(self._pdh_eng_counter)
            if not eng_rows and not self._pdh_primed:
                return None

            by_engtype: dict[str, float] = defaultdict(float)
            for name, val in eng_rows:
                low = name.lower()
                if "engtype_" in low:
                    eng_type = low.split("engtype_", 1)[1]
                else:
                    eng_type = "other"
                by_engtype[eng_type] += max(0.0, val)

            total_pct = max(by_engtype.values(), default=0.0)
            total_pct = round(max(0.0, min(100.0, total_pct)), 1)

            pct_3d = round(min(100.0, by_engtype.get("3d", 0.0)), 1) if eng_rows else None
            pct_vdec = round(min(100.0, by_engtype.get("videodecode", 0.0)), 1) if eng_rows else None
            pct_comp = round(min(100.0, by_engtype.get("compute", 0.0)), 1) if eng_rows else None

            mem_bytes = 0.0
            has_mem = False
            for h_mem in (self._pdh_mem_ded_counter, self._pdh_mem_shared_counter):
                if h_mem is None:
                    continue
                rows = self._read_pdh_array(h_mem)
                if rows:
                    has_mem = True
                    mem_bytes += sum(max(0.0, v) for _, v in rows)

            mem_mb = round(mem_bytes / (1024.0 * 1024.0), 1) if has_mem else None
            return GpuSample(
                gpu_percent=total_pct,
                gpu_memory_mb=mem_mb,
                gpu_3d_percent=pct_3d,
                gpu_video_decode_percent=pct_vdec,
                gpu_compute_percent=pct_comp,
                backend_name="win_pdh",
            )
        except Exception as exc:
            logger.debug("PDH GPU sample failed: %s", exc)
            return None

    def _try_init_d3dkmt(self) -> bool:
        try:
            import ctypes

            gdi32 = ctypes.windll.gdi32
            if not hasattr(gdi32, "D3DKMTEnumAdapters2") or not hasattr(gdi32, "D3DKMTQueryStatistics"):
                return False
            self._gdi32 = gdi32
            # Perform initial baseline capture
            self._sample_d3dkmt()
            return True
        except Exception as exc:
            logger.debug("D3DKMT GPU init skipped: %s", exc)
            return False

    def _sample_d3dkmt(self) -> Optional[GpuSample]:
        if self._gdi32 is None:
            return None
        try:
            import ctypes
            import ctypes.wintypes as wt

            class _LUID(ctypes.Structure):
                _fields_ = [("LowPart", wt.DWORD), ("HighPart", wt.LONG)]

            class _D3DKMT_ADAPTERINFO(ctypes.Structure):
                _fields_ = [
                    ("hAdapter", wt.UINT),
                    ("AdapterLuid", _LUID),
                    ("NumOfSources", wt.UINT),
                    ("bPresentMoveRegionsPreferred", wt.BOOL),
                ]

            class _D3DKMT_ENUMADAPTERS2(ctypes.Structure):
                _fields_ = [
                    ("NumAdapters", wt.ULONG),
                    ("pAdapters", ctypes.POINTER(_D3DKMT_ADAPTERINFO)),
                ]

            class _D3DKMT_CLOSEADAPTER(ctypes.Structure):
                _fields_ = [("hAdapter", wt.UINT)]

            class _D3DKMT_QUERYADAPTERINFO(ctypes.Structure):
                _fields_ = [
                    ("hAdapter", wt.UINT),
                    ("Type", wt.UINT),
                    ("pPrivateDriverData", ctypes.c_void_p),
                    ("PrivateDriverDataSize", wt.UINT),
                ]

            class _D3DKMT_QUERYSTATISTICS_RAW(ctypes.Structure):
                _fields_ = [
                    ("Type", wt.UINT),
                    ("AdapterLuid", _LUID),
                    ("hProcess", wt.HANDLE),
                    ("QueryResult", ctypes.c_uint8 * 776),
                    ("InputParam", ctypes.c_uint32),
                    ("_pad", ctypes.c_uint8 * 256),
                ]

            ea = _D3DKMT_ENUMADAPTERS2()
            if self._gdi32.D3DKMTEnumAdapters2(ctypes.byref(ea)) != 0 or ea.NumAdapters == 0:
                return None

            adapters = (_D3DKMT_ADAPTERINFO * ea.NumAdapters)()
            ea.pAdapters = adapters
            if self._gdi32.D3DKMTEnumAdapters2(ctypes.byref(ea)) != 0:
                return None

            now_mono = time.monotonic()
            dt_s = now_mono - self._prev_sample_mono if self._prev_sample_mono > 0.0 else 0.0
            next_node_times: dict[tuple[int, int, int], int] = {}
            max_node_pct: Optional[float] = None
            total_committed_bytes = 0
            has_hw_adapter = False

            for ad in adapters:
                if not ad.hAdapter:
                    continue
                try:
                    atype = wt.UINT(0)
                    qai = _D3DKMT_QUERYADAPTERINFO(
                        ad.hAdapter,
                        self._KMTQAITYPE_ADAPTERTYPE,
                        ctypes.addressof(atype),
                        4,
                    )
                    if self._gdi32.D3DKMTQueryAdapterInfo(ctypes.byref(qai)) == 0:
                        is_software = bool(atype.value & 0x4)
                        if is_software:
                            continue
                    elif ad.NumOfSources == 0:
                        continue

                    has_hw_adapter = True
                    q0 = _D3DKMT_QUERYSTATISTICS_RAW(Type=self._D3DKMT_QUERY_ADAPTER, AdapterLuid=ad.AdapterLuid)
                    if self._gdi32.D3DKMTQueryStatistics(ctypes.byref(q0)) != 0:
                        continue

                    nb_seg, node_cnt = (ctypes.c_uint32 * 2).from_buffer_copy(bytes(q0.QueryResult[:8]))
                    luid_hi = int(ad.AdapterLuid.HighPart)
                    luid_lo = int(ad.AdapterLuid.LowPart)

                    for nid in range(min(int(node_cnt), 32)):
                        qn = _D3DKMT_QUERYSTATISTICS_RAW(
                            Type=self._D3DKMT_QUERY_NODE,
                            AdapterLuid=ad.AdapterLuid,
                            InputParam=nid,
                        )
                        if self._gdi32.D3DKMTQueryStatistics(ctypes.byref(qn)) != 0:
                            continue
                        running_100ns = ctypes.c_int64.from_buffer_copy(bytes(qn.QueryResult[:8])).value
                        key = (luid_hi, luid_lo, nid)
                        next_node_times[key] = running_100ns
                        if dt_s >= 0.05 and key in self._prev_node_times:
                            delta = running_100ns - self._prev_node_times[key]
                            if delta >= 0:
                                pct = max(0.0, min(100.0, 100.0 * delta / (dt_s * 1e7)))
                                if max_node_pct is None or pct > max_node_pct:
                                    max_node_pct = pct

                    for sid in range(min(int(nb_seg), 16)):
                        qs = _D3DKMT_QUERYSTATISTICS_RAW(
                            Type=self._D3DKMT_QUERY_SEGMENT,
                            AdapterLuid=ad.AdapterLuid,
                            InputParam=sid,
                        )
                        if self._gdi32.D3DKMTQueryStatistics(ctypes.byref(qs)) != 0:
                            continue
                        u64 = (ctypes.c_uint64 * 3).from_buffer_copy(bytes(qs.QueryResult[:24]))
                        bytes_committed = int(u64[1])
                        if 0 <= bytes_committed < (128 * 1024 * 1024 * 1024):
                            total_committed_bytes += bytes_committed
                finally:
                    ca = _D3DKMT_CLOSEADAPTER(ad.hAdapter)
                    self._gdi32.D3DKMTCloseAdapter(ctypes.byref(ca))

            if not has_hw_adapter:
                return None

            self._prev_node_times = next_node_times
            self._prev_sample_mono = now_mono

            if max_node_pct is None and self._last_d3dkmt_sample is not None:
                return self._last_d3dkmt_sample

            sample = GpuSample(
                gpu_percent=round(max_node_pct, 1) if max_node_pct is not None else 0.0,
                gpu_memory_mb=round(total_committed_bytes / (1024.0 * 1024.0), 1),
                backend_name="win_d3dkmt",
            )
            self._last_d3dkmt_sample = sample
            return sample
        except Exception as exc:
            logger.debug("D3DKMT GPU sample failed: %s", exc)
            return None

    def sample(self) -> GpuSample:
        if self._mode == "pdh":
            res = self._sample_pdh()
            if res is not None:
                return res
            if self._try_init_d3dkmt():
                self._mode = "d3dkmt"
        if self._mode == "d3dkmt":
            res = self._sample_d3dkmt()
            if res is not None:
                return res
        return GpuSample(backend_name=self._mode)

    def close(self) -> None:
        if self._pdh is not None and self._pdh_query is not None:
            try:
                self._pdh.PdhCloseQuery(self._pdh_query)
            except Exception:
                pass
        self._pdh_query = None
        self._pdh_eng_counter = None
        self._pdh_mem_shared_counter = None
        self._pdh_mem_ded_counter = None


class LinuxDrmGpuProbe(IGpuMetricsProbe):
    """Best-effort Linux DRM sysfs (`gpu_busy_percent`) probe for non-Windows hosts."""

    def __init__(self) -> None:
        self._busy_paths = sorted(Path("/sys/class/drm").glob("card*/device/gpu_busy_percent"))

    def is_available(self) -> bool:
        return bool(self._busy_paths)

    def sample(self) -> GpuSample:
        for p in self._busy_paths:
            try:
                val = float(p.read_text(encoding="utf-8").strip())
                return GpuSample(
                    gpu_percent=round(max(0.0, min(100.0, val)), 1),
                    backend_name="linux_drm",
                )
            except Exception:
                continue
        return GpuSample(backend_name="unavailable")


def create_default_gpu_probe() -> IGpuMetricsProbe:
    """Create the appropriate zero-subprocess GPU metrics probe for the current host OS."""
    if sys.platform == "win32":
        probe = WindowsGpuProbe()
        if probe._mode in ("pdh", "d3dkmt"):
            return probe
        return NoOpGpuProbe(reason=probe._mode)
    if os.name == "posix":
        drm = LinuxDrmGpuProbe()
        if drm.is_available():
            return drm
    return NoOpGpuProbe(reason="unavailable")
