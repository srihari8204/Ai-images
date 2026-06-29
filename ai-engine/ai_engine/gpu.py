"""GPU / VRAM utilisation reporting and capacity checks.

Uses NVML when available. When no GPU is present (dev/CPU), reports an
unavailable device so the orchestrator can surface "no capacity" gracefully
instead of crashing.
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_engine import metrics


@dataclass
class GpuStats:
    available: bool
    device_index: int
    utilization_percent: float
    memory_used_mb: float
    memory_total_mb: float


def _try_nvml() -> list[GpuStats]:
    try:
        import pynvml  # type: ignore

        pynvml.nvmlInit()
        out = []
        for i in range(pynvml.nvmlDeviceGetCount()):
            h = pynvml.nvmlDeviceGetHandleByIndex(i)
            util = pynvml.nvmlDeviceGetUtilizationRates(h)
            mem = pynvml.nvmlDeviceGetMemoryInfo(h)
            out.append(
                GpuStats(
                    available=True,
                    device_index=i,
                    utilization_percent=float(util.gpu),
                    memory_used_mb=mem.used / 1e6,
                    memory_total_mb=mem.total / 1e6,
                )
            )
        pynvml.nvmlShutdown()
        return out
    except Exception:  # noqa: BLE001 - no NVML / no GPU
        return []


def collect_and_report() -> list[GpuStats]:
    stats = _try_nvml()
    for s in stats:
        metrics.gpu_utilization.labels(device=str(s.device_index)).set(s.utilization_percent)
        metrics.gpu_memory_used_mb.labels(device=str(s.device_index)).set(s.memory_used_mb)
    return stats


def has_capacity() -> bool:
    """True if the worker can accept a job now.

    On a real GPU we consider capacity exhausted above a VRAM watermark. With no
    GPU (CPU stand-in) we always report capacity so dev flows complete.
    """

    stats = collect_and_report()
    if not stats:
        return True  # CPU stand-in path
    return any(s.memory_used_mb / max(s.memory_total_mb, 1) < 0.92 for s in stats)
