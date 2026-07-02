#!/usr/bin/env bash
# Generate a preview thumbnail for every style (one-time GPU job).
#
# Renders each style once with a stock face and uploads to R2 previews/<slug>.png.
# Idempotent — re-run to fill any that failed. Stop the queue worker first (or run
# alongside; they share the GPU, just slower).
#
# Usage (export the 3 secrets first, like the worker):
#   export DATABASE_URL='postgresql://...'
#   export S3_ACCESS_KEY='...'
#   export S3_SECRET_KEY='...'
#   export SECRET_KEY='...'
#   bash deploy/runpod/generate-previews.sh
set -uo pipefail

REPO=/workspace/Ai-images
cd "$REPO"

: "${DATABASE_URL:?set DATABASE_URL before running}"
: "${S3_ACCESS_KEY:?set S3_ACCESS_KEY before running}"
: "${S3_SECRET_KEY:?set S3_SECRET_KEY before running}"
: "${SECRET_KEY:?set SECRET_KEY before running}"

export GENERATION_BACKEND=instantid
export TORCH_DEVICE=cuda
export S3_REGION=auto
export HF_HOME=/workspace/hf
export HF_HUB_DISABLE_XET=1
export HF_HUB_ENABLE_HF_TRANSFER=0
export INSIGHTFACE_ROOT=/workspace/insightface
export INSTANTID_BASE_MODEL="${INSTANTID_BASE_MODEL:-wangqixun/YamerMIX_v8}"
export INSTANTID_REPO=InstantX/InstantID
export S3_ENDPOINT_URL=https://7fd1208c57579b53f47307ade895aa3c.r2.cloudflarestorage.com
export S3_PUBLIC_ENDPOINT_URL=https://7fd1208c57579b53f47307ade895aa3c.r2.cloudflarestorage.com
export PYTHONPATH="$REPO/backend:$REPO/ai-engine:/workspace/InstantID"

git pull -q || true
echo ">>> generating style previews (this can take ~1-2 hours for the full catalog)"
exec python -m ai_engine.preview_gen
