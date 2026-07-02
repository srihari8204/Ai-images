#!/usr/bin/env bash
# RunPod auto-start entrypoint.
#
# Set this as the pod's "Container Start Command":
#     bash /workspace/Ai-images/deploy/runpod/boot.sh
#
# and put the 5 secrets in the pod's Environment Variables (they persist across
# stop/start) so the worker returns automatically every time you start the GPU:
#     REDIS_URL, DATABASE_URL, S3_ACCESS_KEY, S3_SECRET_KEY, SECRET_KEY
#
# It starts our worker in the BACKGROUND, then hands control to RunPod's own
# startup (/start.sh: Jupyter/SSH/web terminal) so the pod behaves normally and
# RunPod's service/port responds. Worker logs -> /workspace/worker.log.

# Launch the GPU worker in the background (installs deps, loads models, listens).
if [ -d /workspace/Ai-images ]; then
  ( cd /workspace/Ai-images && git pull -q || true
    nohup bash deploy/runpod/start-worker-instantid.sh > /workspace/worker.log 2>&1 & ) \
    >> /workspace/boot.log 2>&1
fi

# Hand off to RunPod's default startup so Jupyter/terminal/port come up.
if [ -x /start.sh ]; then exec /start.sh; fi
if [ -f /start.sh ]; then exec bash /start.sh; fi
# No RunPod start script found — just keep the container alive.
sleep infinity
