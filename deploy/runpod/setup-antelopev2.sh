#!/usr/bin/env bash
# Download the antelopev2 insightface model that InstantID needs.
#
# insightface cannot auto-download antelopev2, so FaceAnalysis(name="antelopev2")
# finds an empty model dir and fails with:
#   AssertionError: assert 'detection' in self.models
# This fetches the 5 .onnx files into the location FaceAnalysis expects:
#   $INSIGHTFACE_ROOT/models/antelopev2/
set -euo pipefail

DEST="${INSIGHTFACE_ROOT:-/workspace/insightface}/models/antelopev2"
mkdir -p "$DEST"
echo ">>> downloading antelopev2 into $DEST"

HF_HUB_DISABLE_XET=1 python - <<PY
from huggingface_hub import hf_hub_download
import shutil, os
dest = "$DEST"
# antelopev2 model pack (detection + landmarks + recognition + genderage)
files = ["scrfd_10g_bnkps.onnx", "glintr100.onnx", "genderage.onnx",
         "1k3d68.onnx", "2d106det.onnx"]
for f in files:
    p = hf_hub_download("DIAMONIK7777/antelopev2", f)
    shutil.copy(p, os.path.join(dest, f))
    print("  ok", f)
print(">>> antelopev2 ready")
PY

echo ">>> contents:"
ls -lh "$DEST"
