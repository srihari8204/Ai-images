"""Async load test for the generation path.

Spawns N concurrent virtual users that each register, log in, and submit jobs,
then reports submission throughput and latency percentiles. Use it to tune queue
concurrency and the priority tiers (high/normal/low) under load.

Usage:
    python scripts/loadtest.py --base http://localhost:8080 --users 50 --jobs 5
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time
import uuid

import httpx


async def _verify_in_dev(client: httpx.AsyncClient, base: str, email: str) -> None:
    # In dev the verification token is only in logs; this helper is a no-op unless
    # a test-only endpoint is exposed. Most load tests run against seeded users.
    return None


async def virtual_user(base: str, jobs: int, latencies: list[float], errors: list[int]):
    async with httpx.AsyncClient(base_url=base, timeout=30) as client:
        email = f"load_{uuid.uuid4().hex[:12]}@load.local"
        pw = "Str0ngPassw0rd"
        await client.post("/api/v1/auth/register",
                          json={"email": email, "password": pw})
        # Assumes a pre-seeded, verified load-test account in non-dev runs.
        r = await client.post("/api/v1/auth/login", json={"email": email, "password": pw})
        if r.status_code != 200:
            errors.append(r.status_code)
            return
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        for _ in range(jobs):
            start = time.perf_counter()
            resp = await client.post(
                "/api/v1/jobs",
                headers={**headers, "Idempotency-Key": uuid.uuid4().hex},
                json={"prompt": "load test image", "stages": ["generate"],
                      "params": {"width": 512, "height": 512, "steps": 10}},
            )
            latencies.append(time.perf_counter() - start)
            if resp.status_code not in (202, 402):
                errors.append(resp.status_code)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8080")
    ap.add_argument("--users", type=int, default=20)
    ap.add_argument("--jobs", type=int, default=5)
    args = ap.parse_args()

    latencies: list[float] = []
    errors: list[int] = []
    started = time.perf_counter()
    await asyncio.gather(
        *(virtual_user(args.base, args.jobs, latencies, errors) for _ in range(args.users))
    )
    elapsed = time.perf_counter() - started

    total = len(latencies)
    if total:
        latencies.sort()
        p50 = statistics.median(latencies)
        p95 = latencies[int(len(latencies) * 0.95) - 1]
        p99 = latencies[int(len(latencies) * 0.99) - 1]
        print(f"submitted={total} elapsed={elapsed:.1f}s "
              f"throughput={total / elapsed:.1f}/s "
              f"p50={p50*1000:.0f}ms p95={p95*1000:.0f}ms p99={p99*1000:.0f}ms "
              f"errors={len(errors)}")
    else:
        print(f"no successful submissions; errors={errors[:10]}")


if __name__ == "__main__":
    asyncio.run(main())
