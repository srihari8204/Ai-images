"""End-to-end local smoke test (no GPU required).

Drives the running stack through a full happy path and asserts each step:
login -> balance -> submit job -> poll to completion -> result in gallery ->
credits debited. Proves the async pipeline works on the CPU stand-in.

Prereqs:
  1. Stack running (docker compose up) — api, worker, postgres, redis, minio.
  2. A verified user with credits:
        docker compose exec api python -m app.db.bootstrap --email dev@local \
            --password Str0ngPassw0rd --credits 100

Usage:
  python scripts/smoke_e2e.py --base http://localhost:8080 \
      --email dev@local --password Str0ngPassw0rd
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid

import httpx


def fail(msg: str) -> "NoReturn":  # type: ignore[name-defined]
    print(f"FAIL: {msg}")
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8080")
    ap.add_argument("--email", default="dev@local")
    ap.add_argument("--password", default="Str0ngPassw0rd")
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args()

    c = httpx.Client(base_url=args.base, timeout=30)

    # 0) liveness / readiness
    assert c.get("/healthz").status_code == 200, "healthz not ok"
    ready = c.get("/readyz").json()
    print(f"[ok] readyz: {ready}")
    if not ready.get("ready"):
        # Don't hard-fail: the minio probe can be false (R2 object tokens can't
        # ListBuckets) while object read/write still works. Postgres+Redis are
        # what submission needs; the worker stores output with its own creds.
        print(f"WARNING: readyz not fully ready ({ready}) — continuing anyway")

    # 1) login
    r = c.post("/api/v1/auth/login", json={"email": args.email, "password": args.password})
    if r.status_code != 200:
        fail(f"login failed ({r.status_code}): {r.text}. "
             f"Run the bootstrap step first.")
    tok = r.json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    print("[ok] logged in")

    # 2) balance
    bal0 = c.get("/api/v1/credits/balance", headers=h).json()
    print(f"[ok] balance before: {bal0}")
    if bal0["available"] < 1:
        fail("no credits — re-run bootstrap with --credits 100")

    # 3) styles catalog (cached, public)
    styles = c.get("/api/v1/styles").json()
    print(f"[ok] styles: {[s['slug'] for s in styles]}")

    # 4) submit a generation job (generate stage only — CPU stand-in)
    r = c.post(
        "/api/v1/jobs",
        headers={**h, "Idempotency-Key": uuid.uuid4().hex},
        json={
            "prompt": "a serene mountain lake at sunrise",
            "style_slug": "cinematic",
            "stages": ["generate", "gfpgan", "realesrgan"],
            "params": {"width": 512, "height": 512, "steps": 8},
        },
    )
    if r.status_code != 202:
        fail(f"submit failed ({r.status_code}): {r.text}")
    job_id = r.json()["job_id"]
    cost = r.json()["cost_credits"]
    print(f"[ok] job submitted: {job_id} cost={cost}")

    # 5) poll to completion
    deadline = time.time() + args.timeout
    status = "queued"
    while time.time() < deadline:
        job = c.get(f"/api/v1/jobs/{job_id}", headers=h).json()
        status = job["status"]
        if status in ("completed", "failed", "cancelled"):
            break
        print(f"    ... {status} {job['progress']}%")
        time.sleep(2)
    if status != "completed":
        fail(f"job did not complete (status={status}). Is the worker running?")
    print(f"[ok] job completed with {len(job['result_image_ids'])} output(s)")

    # 6) result visible in gallery with a presigned URL
    gallery = c.get("/api/v1/gallery", headers=h).json()
    if not gallery["items"]:
        fail("gallery empty after completion")
    print(f"[ok] gallery has {len(gallery['items'])} image(s); "
          f"first url: {gallery['items'][0]['url'][:60]}...")

    # 7) credits debited exactly by the job cost
    bal1 = c.get("/api/v1/credits/balance", headers=h).json()
    spent = bal0["balance"] - bal1["balance"]
    print(f"[ok] balance after: {bal1} (spent {spent})")
    if spent != cost:
        fail(f"expected to debit {cost}, debited {spent}")

    print("\nPASS — full local generation path works (no GPU).")


if __name__ == "__main__":
    main()
