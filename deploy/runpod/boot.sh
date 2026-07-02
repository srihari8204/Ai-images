#!/usr/bin/env bash
# RunPod auto-start entrypoint.
#
# Set this as the pod's "Container Start Command":
#     bash /workspace/Ai-images/deploy/runpod/boot.sh
#
# and put the 5 secrets in the pod's Environment Variables (they persist across
# stop/start), so the worker comes back automatically every time you start the
# GPU — no manual steps:
#     REDIS_URL, DATABASE_URL, S3_ACCESS_KEY, S3_SECRET_KEY, SECRET_KEY
#
# Logs go to /workspace/boot.log. The container is held open even if the worker
# exits, so the web terminal stays usable for debugging.
exec > /workspace/boot.log 2>&1
echo ">>> boot $(date 2>/dev/null || true)"

cd /workspace/Ai-images 2>/dev/null || { echo "repo missing at /workspace/Ai-images"; sleep infinity; }
git pull -q || true

# start-worker-instantid.sh installs deps, ensures models, then execs the worker
# (foreground). If it ever exits, fall through and keep the container alive.
bash deploy/runpod/start-worker-instantid.sh || echo ">>> worker exited with an error"

echo ">>> worker process ended; holding container open for the web terminal"
sleep infinity
