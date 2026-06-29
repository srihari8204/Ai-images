#!/usr/bin/env bash
# =============================================================================
# AI Mirror — one-shot GPU host setup (Ubuntu 22.04 cloud GPU instance).
# Installs the host software that is NOT preinstalled, builds the GPU worker,
# and launches the full stack. Run as a sudo-capable user.
#
#   curl -fsSL <repo>/deploy/gpu-host-setup.sh | bash      (or copy & run)
# =============================================================================
set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/AI-Mirror-Starter/AI-Mirror-Starter}"

echo "==> 1/6 NVIDIA driver check"
if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "    NVIDIA driver not found. On most cloud GPU images it's preinstalled."
  echo "    Install it (Ubuntu):  sudo ubuntu-drivers autoinstall && sudo reboot"
  echo "    Then re-run this script."
  exit 1
fi
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

echo "==> 2/6 Docker Engine"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER" || true
fi

echo "==> 3/6 NVIDIA Container Toolkit (lets containers use the GPU)"
if ! docker info 2>/dev/null | grep -qi nvidia; then
  distribution=$(. /etc/os-release; echo "$ID$VERSION_ID")
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
    sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null
  sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
  sudo nvidia-ctk runtime configure --runtime=docker
  sudo systemctl restart docker
fi

echo "==> 4/6 Verify GPU is visible to Docker"
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi >/dev/null \
  && echo "    GPU visible to Docker: OK"

echo "==> 5/6 Build the GPU worker image"
cd "$REPO_DIR"
docker build -f docker/Dockerfile.worker.gpu -t aimirror-worker:gpu .

echo "==> 6/6 Launch the stack (worker uses the GPU image + real FLUX)"
# Provide secrets via docker/.env.prod (see docs/production-config.md). At minimum:
#   SECRET_KEY, HF_TOKEN, S3 creds, STRIPE_* (optional), SMTP_* (optional)
cat > docker/docker-compose.gpu.yml <<'YAML'
name: ai-mirror
services:
  worker:
    image: aimirror-worker:gpu
    environment:
      GENERATION_BACKEND: flux
      TORCH_DEVICE: cuda
      ENABLE_NSFW_MODEL: "true"
      HF_HOME: /models/hf
      HF_TOKEN: ${HF_TOKEN}
    volumes:
      - models:/models
    deploy:
      resources:
        reservations:
          devices:
            - { driver: nvidia, count: 1, capabilities: [gpu] }
volumes:
  models:
YAML

cd docker
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
echo
echo "Done. API: http://<host>:8000  | edge: http://<host>:8080"
echo "First generation downloads weights into the 'models' volume (~30GB) — be patient."
echo "Pre-warm:  docker compose exec worker python -c \"from ai_engine.models import loader; loader.warm(['flux.1'])\""
