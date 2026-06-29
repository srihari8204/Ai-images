"""Wait for the worker to finish loading the model, then generate a real image.

Polls until a submitted generate-only job completes (the job sits queued until the
worker warms the model), then prints the result image URL. Hands-off: run it and
wait for the final PASS line.
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid

import httpx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:18080")
    ap.add_argument("--email", default="dev@example.com")
    ap.add_argument("--password", default="Str0ngPassw0rd")
    ap.add_argument("--timeout", type=int, default=1800)  # up to 30 min
    args = ap.parse_args()

    c = httpx.Client(base_url=args.base, timeout=30)
    r = c.post("/api/v1/auth/login", json={"email": args.email, "password": args.password})
    r.raise_for_status()
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # Clean real image: generate stage only (no stand-in post-processing artifacts).
    r = c.post(
        "/api/v1/jobs",
        headers={**h, "Idempotency-Key": uuid.uuid4().hex},
        json={
            "prompt": "a golden retriever puppy sitting in a sunny meadow, photo",
            "stages": ["generate"],
            "params": {"width": 512, "height": 512, "steps": 20},
        },
    )
    if r.status_code != 202:
        print(f"submit failed {r.status_code}: {r.text}")
        return 1
    job_id = r.json()["job_id"]
    print(f"[submitted] job {job_id} — waiting for the worker to load the model and run it...")

    deadline = time.time() + args.timeout
    last = None
    while time.time() < deadline:
        job = c.get(f"/api/v1/jobs/{job_id}", headers=h).json()
        st = job.get("status")
        if st != last:
            print(f"  status={st} progress={job.get('progress')}")
            last = st
        if st in ("completed", "failed", "cancelled"):
            break
        time.sleep(5)

    if st != "completed":
        print(f"FAILED: status={st} err={job.get('error_message')}")
        return 1

    detail = c.get(f"/api/v1/gallery/{job['result_image_ids'][0]}", headers=h).json()
    print("\nPASS — real image generated.")
    print(f"Open it here: {detail['url']}")
    print("Or just refresh the Gallery at http://localhost:3000/gallery")
    return 0


if __name__ == "__main__":
    sys.exit(main())
