#!/usr/bin/env bash
# RunPod GPU worker — InstantID (AI-Mirror-style face personalization on SDXL).
#
# Turns an uploaded selfie into stylized portraits that preserve the person's
# identity. Needs a GPU with >=16 GB VRAM (L4 24 GB is fine). All models and
# caches go to /workspace (the persistent network volume), NOT the 30 GB
# container disk.
#
# Usage (inside a tmux session):
#   tmux new -s worker
#   export REDIS_URL='rediss://...'
#   export DATABASE_URL='postgresql://...'
#   export S3_ACCESS_KEY='...'
#   export S3_SECRET_KEY='...'
#   export SECRET_KEY='...'
#   bash deploy/runpod/start-worker-instantid.sh
#
# Leave it running: Ctrl+B then D to DETACH. Never Ctrl+C.
# First run downloads SDXL + InstantID + antelopev2 (~10 GB) — be patient.
set -euo pipefail

REPO=/workspace/Ai-images
cd "$REPO"

# ---- required secrets ----
: "${REDIS_URL:?set REDIS_URL before running}"
: "${DATABASE_URL:?set DATABASE_URL before running}"
: "${S3_ACCESS_KEY:?set S3_ACCESS_KEY before running}"
: "${S3_SECRET_KEY:?set S3_SECRET_KEY before running}"
: "${SECRET_KEY:?set SECRET_KEY before running}"

# ---- InstantID backend config (everything cached on /workspace) ----
export GENERATION_BACKEND=instantid
export TORCH_DEVICE=cuda
export S3_REGION=auto
export HF_HOME=/workspace/hf
export HF_HUB_DISABLE_XET=1
export HF_HUB_ENABLE_HF_TRANSFER=0
export INSIGHTFACE_ROOT=/workspace/insightface
# YamerMIX_v8 is the base model from the official InstantID demo — it preserves
# the input identity far better than "beautify" checkpoints like RealVisXL
# (which tend to westernize/age faces). This is the key to faithful likeness.
export INSTANTID_BASE_MODEL="${INSTANTID_BASE_MODEL:-wangqixun/YamerMIX_v8}"
export INSTANTID_REPO=InstantX/InstantID
export S3_ENDPOINT_URL=https://7fd1208c57579b53f47307ade895aa3c.r2.cloudflarestorage.com
export S3_PUBLIC_ENDPOINT_URL=https://7fd1208c57579b53f47307ade895aa3c.r2.cloudflarestorage.com

# ---- InstantID custom pipeline code (pipeline file + ip_adapter/ package) ----
# Cloned once into /workspace and added to PYTHONPATH so the worker can import
# `pipeline_stable_diffusion_xl_instantid` and its ip_adapter helpers.
INSTANTID_SRC=/workspace/InstantID
if [ ! -f "$INSTANTID_SRC/pipeline_stable_diffusion_xl_instantid.py" ]; then
  echo ">>> cloning InstantID source"
  rm -rf "$INSTANTID_SRC"
  git clone --depth 1 https://github.com/instantX-research/InstantID "$INSTANTID_SRC"
fi
export PYTHONPATH="$REPO/backend:$REPO/ai-engine:$INSTANTID_SRC"

# ---- python deps ----
git pull -q || true
pip install -r backend/requirements.txt --ignore-installed -q
pip install diffusers==0.32.1 transformers==4.48.0 accelerate safetensors sentencepiece protobuf -q
pip install insightface==0.7.3 opencv-python-headless -q
# insightface needs onnxruntime importable. onnxruntime-gpu frequently fails to
# load on RunPod (cuDNN/CUDA version mismatch) which makes InstantID silently
# unavailable. CPU onnxruntime always imports and face detection is light; the
# heavy SDXL diffusion still runs on the GPU via torch.
pip uninstall -y onnxruntime-gpu >/dev/null 2>&1 || true
pip install "onnxruntime>=1.17" -q

# ---- optional enhancers: face restore (GFPGAN), upscale (RealESRGAN), bg removal (rembg) ----
# Weights auto-download from URLs on first use. basicsr imports a torchvision
# module removed in tv>=0.17, so we patch it in place after install.
pip install gfpgan realesrgan rembg -q || true
# basicsr's degradations.py imports torchvision.transforms.functional_tensor,
# removed in tv>=0.17. Locate the file WITHOUT importing it (the import itself is
# what fails), then rewrite the import in place.
BASICSR_DEG=$(python -c "import importlib.util, os; d=importlib.util.find_spec('basicsr').submodule_search_locations[0]; print(os.path.join(d,'data','degradations.py'))" 2>/dev/null || true)
if [ -n "$BASICSR_DEG" ] && [ -f "$BASICSR_DEG" ]; then
  sed -i 's/torchvision\.transforms\.functional_tensor/torchvision.transforms.functional/g' "$BASICSR_DEG" || true
  echo ">>> patched basicsr for modern torchvision: $BASICSR_DEG"
fi

echo ">>> InstantID worker starting (first run downloads ~10 GB to /workspace; detach with Ctrl+B then D)"
exec python -m ai_engine.worker
