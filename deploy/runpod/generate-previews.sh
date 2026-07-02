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

# InstantID source (also provides the stock example faces used for previews).
if [ ! -f /workspace/InstantID/pipeline_stable_diffusion_xl_instantid.py ]; then
  rm -rf /workspace/InstantID
  git clone --depth 1 https://github.com/instantX-research/InstantID /workspace/InstantID
fi

# Deps (idempotent). A fresh pod loses pip packages, so ensure them here too.
pip install -r backend/requirements.txt --ignore-installed -q
pip install diffusers==0.32.1 transformers==4.48.0 accelerate safetensors sentencepiece protobuf -q
pip install insightface==0.7.3 opencv-python-headless -q
pip uninstall -y onnxruntime-gpu >/dev/null 2>&1 || true
pip install "onnxruntime>=1.17" -q

# Face models (antelopev2 + inswapper) if missing.
[ -f "$INSIGHTFACE_ROOT/models/antelopev2/scrfd_10g_bnkps.onnx" ] || bash deploy/runpod/setup-antelopev2.sh || true
if [ ! -f "$INSIGHTFACE_ROOT/models/inswapper_128.onnx" ]; then
  mkdir -p "$INSIGHTFACE_ROOT/models"
  python - <<PY || echo ">>> WARN: inswapper download failed"
from huggingface_hub import hf_hub_download
import shutil, os
p = hf_hub_download("ezioruan/inswapper_128.onnx", "inswapper_128.onnx")
shutil.copy(p, os.path.join("$INSIGHTFACE_ROOT", "models", "inswapper_128.onnx"))
print(">>> inswapper ready")
PY
fi

echo ">>> generating style previews (first one downloads the base model; full catalog ~1 hour)"
exec python -m ai_engine.preview_gen
