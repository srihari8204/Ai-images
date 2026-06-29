"""Worker Prometheus metrics, served on a dedicated port for scraping.

Covers per-stage durations, GPU/VRAM utilisation, and job outcomes — the
worker-side counterparts to the API metrics.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, start_http_server

stage_duration_seconds = Histogram(
    "worker_stage_duration_seconds",
    "Duration of each pipeline stage",
    ["stage"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 20, 30, 60, 120),
)
jobs_processed_total = Counter(
    "worker_jobs_processed_total", "Jobs processed by the worker", ["status"]
)
stage_failures_total = Counter(
    "worker_stage_failures_total", "Stage failures", ["stage", "transient"]
)
gpu_utilization = Gauge("worker_gpu_utilization_percent", "GPU utilization", ["device"])
gpu_memory_used_mb = Gauge("worker_gpu_memory_used_mb", "GPU VRAM used (MB)", ["device"])
model_load_seconds = Histogram(
    "worker_model_load_seconds", "Model load/warm time", ["model"]
)
inflight_jobs = Gauge("worker_inflight_jobs", "Jobs currently being processed")


def start_metrics_server(port: int = 9100) -> None:
    start_http_server(port)
