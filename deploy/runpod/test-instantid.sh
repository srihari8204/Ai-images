#!/usr/bin/env bash
# Loads the InstantID stack DIRECTLY and prints the real error.
#
# The normal job pipeline silently falls back to a placeholder gradient when
# InstantID can't load, which hides the actual cause. This calls the raw loader
# so the true exception/traceback is printed.
#
# Usage:  bash deploy/runpod/test-instantid.sh
set -uo pipefail
REPO=/workspace/Ai-images
cd "$REPO"

export TORCH_DEVICE=cuda
export SECRET_KEY="${SECRET_KEY:-x}"
export HF_HOME=/workspace/hf
export HF_HUB_DISABLE_XET=1
export HF_HUB_ENABLE_HF_TRANSFER=0
export INSIGHTFACE_ROOT=/workspace/insightface
export INSTANTID_BASE_MODEL="${INSTANTID_BASE_MODEL:-SG161222/RealVisXL_V5.0}"
export INSTANTID_REPO=InstantX/InstantID
export PYTHONPATH="$REPO/backend:$REPO/ai-engine:/workspace/InstantID"

echo ">>> python: $(python --version)"
echo ">>> testing imports + InstantID load (base=$INSTANTID_BASE_MODEL)"
python - <<'PY'
import traceback

print("\n[1/4] import onnxruntime ...")
try:
    import onnxruntime as ort
    print("    ok:", ort.__version__, ort.get_available_providers())
except Exception:
    traceback.print_exc()

print("\n[2/4] import insightface ...")
try:
    import insightface
    from insightface.app import FaceAnalysis
    print("    ok:", insightface.__version__)
except Exception:
    traceback.print_exc()

print("\n[3/4] import InstantID custom pipeline ...")
try:
    from pipeline_stable_diffusion_xl_instantid import (
        StableDiffusionXLInstantIDPipeline, draw_kps,
    )
    print("    ok")
except Exception:
    traceback.print_exc()

print("\n[4/4] full _load_instantid() (downloads base model on first run) ...")
try:
    from ai_engine.models.loader import _load_instantid
    m = _load_instantid()
    print("\n>>> INSTANTID_OK:", type(m))
except Exception:
    print("\n>>> INSTANTID_FAILED — real error:\n")
    traceback.print_exc()
PY
