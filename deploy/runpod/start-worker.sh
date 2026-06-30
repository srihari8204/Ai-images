#!/usr/bin/env bash
# RunPod GPU worker bootstrap.
#
# The RunPod web terminal truncates very long pasted lines, so instead of one
# giant env-prefixed command, set the five secrets (one short line each) and run
# this script. Non-secret config (model, paths, R2 endpoint) lives here.
#
# Usage:
#   tmux new -s worker            # (skip if already in a tmux session)
#   export REDIS_URL='rediss://...'
#   export DATABASE_URL='postgresql://...'
#   export S3_ACCESS_KEY='...'
#   export S3_SECRET_KEY='...'
#   export SECRET_KEY='...'
#   bash deploy/runpod/start-worker.sh
#
# Leave it running: press Ctrl+B then D to DETACH. Never Ctrl+C (that kills it).
# Reattach later with:  tmux attach -t worker
set -euo pipefail

REPO=/workspace/Ai-images
cd "$REPO"

# ---- required secrets (export these before running) ----
: "${REDIS_URL:?set REDIS_URL before running}"
: "${DATABASE_URL:?set DATABASE_URL before running}"
: "${S3_ACCESS_KEY:?set S3_ACCESS_KEY before running}"
: "${S3_SECRET_KEY:?set S3_SECRET_KEY before running}"
: "${SECRET_KEY:?set SECRET_KEY before running}"

# ---- non-secret config ----
export GENERATION_BACKEND=sdturbo
export SDTURBO_MODEL=segmind/tiny-sd
export SDTURBO_STEPS=20
export SDTURBO_GUIDANCE=7.5
export TORCH_DEVICE=cuda
export S3_REGION=auto
export HF_HOME=/workspace/hf
export HF_HUB_DISABLE_XET=1
export HF_HUB_ENABLE_HF_TRANSFER=0
export PYTHONPATH="$REPO/backend:$REPO/ai-engine"
export S3_ENDPOINT_URL=https://7fd1208c57579b53f47307ade895aa3c.r2.cloudflarestorage.com
export S3_PUBLIC_ENDPOINT_URL=https://7fd1208c57579b53f47307ade895aa3c.r2.cloudflarestorage.com

# ---- deps (idempotent; model weights stay cached under HF_HOME on /workspace) ----
git pull -q || true
pip install -r backend/requirements.txt --ignore-installed -q
pip install diffusers==0.32.1 transformers==4.48.0 accelerate safetensors sentencepiece protobuf -q

echo ">>> deps ready — starting worker (detach with Ctrl+B then D)"
exec python -m ai_engine.worker
