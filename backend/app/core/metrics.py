"""Prometheus metrics registry shared across the API process.

The worker maintains its own equivalents (see ``ai_engine/metrics.py``); together
they cover request latency, error rate, queue depth, per-stage durations, GPU
utilisation, and credit/payment counters.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# ---- HTTP ----
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
http_errors_total = Counter(
    "http_errors_total", "HTTP 5xx responses", ["path"]
)

# ---- Queue / jobs ----
jobs_submitted_total = Counter("jobs_submitted_total", "Jobs submitted")
jobs_completed_total = Counter("jobs_completed_total", "Jobs completed", ["status"])
queue_depth_gauge = Gauge("queue_depth", "Pending jobs per queue", ["queue"])
job_duration_seconds = Histogram(
    "job_duration_seconds",
    "End-to-end job duration",
    buckets=(1, 5, 10, 20, 30, 60, 120, 300),
)

# ---- Credits / payments ----
credit_txn_total = Counter("credit_transactions_total", "Credit ledger writes", ["type"])
payments_total = Counter("payments_total", "Payment events", ["kind", "status"])
revenue_cents_total = Counter("revenue_cents_total", "Gross revenue in cents")
