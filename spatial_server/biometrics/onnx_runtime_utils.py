from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import onnxruntime as ort

logger = logging.getLogger("spatial_server.biometrics.ort")


def build_ort_session_options(
    intra_threads: int = 2,
    inter_threads: int = 1,
) -> ort.SessionOptions:
    """Create bounded ONNX Runtime SessionOptions tuned for low-RAM 4-core hosts."""
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = max(1, int(intra_threads))
    opts.inter_op_num_threads = max(1, int(inter_threads))
    opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    opts.enable_cpu_mem_arena = True
    opts.log_severity_level = 3  # Suppress benign shape-merge warnings in production logs
    try:
        opts.add_session_config_entry("session.set_denormal_as_zero", "1")
    except Exception:
        pass
    return opts


def resolve_ort_providers(provider_name: str = "cpu") -> list[Any]:
    """Return ordered ORT ExecutionProvider list with memory-conservative CPU options."""
    available = set(ort.get_available_providers())
    norm = (provider_name or "cpu").strip().lower()
    cpu_provider: tuple[str, dict[str, str]] = (
        "CPUExecutionProvider",
        {"arena_extend_strategy": "kSameAsRequested"},
    )

    if norm == "openvino" and "OpenVINOExecutionProvider" in available:
        return ["OpenVINOExecutionProvider", cpu_provider]
    if norm in ("dml", "directml") and "DmlExecutionProvider" in available:
        return ["DmlExecutionProvider", cpu_provider]
    if norm != "cpu":
        logger.info("Requested ORT provider %r unavailable (%s); using CPUExecutionProvider", norm, sorted(available))
    return [cpu_provider]


def create_ort_session(
    onnx_path: Path,
    *,
    provider_name: str = "cpu",
    intra_threads: int = 2,
    inter_threads: int = 1,
) -> ort.InferenceSession:
    """Instantiate an ONNX Runtime InferenceSession with safe fallback to bare CPUExecutionProvider."""
    opts = build_ort_session_options(intra_threads=intra_threads, inter_threads=inter_threads)
    providers = resolve_ort_providers(provider_name)
    try:
        return ort.InferenceSession(str(onnx_path), sess_options=opts, providers=providers)
    except Exception as exc:
        logger.warning("Falling back to default CPUExecutionProvider for %s (%s)", onnx_path.name, exc)
        return ort.InferenceSession(str(onnx_path), sess_options=opts, providers=["CPUExecutionProvider"])
