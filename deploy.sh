#!/usr/bin/env bash
# deploy.sh — Bring up Ray cluster, start vLLM inside ray-head, onboard NemoClaw, start analysis
#
# Run on the HEAD node after the worker has joined (or start worker first).
#
# Usage:
#   ./deploy.sh
#   ./deploy.sh --skip-onboard
#   ./deploy.sh --worker-only          # on the second node

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

HEAD_IP="${HEAD_IP:-$(hostname -I | awk '{print $1}')}"
VLLM_PORT="${VLLM_PORT:-8000}"
VLLM_MODEL="${VLLM_MODEL:-nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4}"
SANDBOX_NAME="${SANDBOX_NAME:-OpenClaw}"
GATEWAY_PORT="${NEMOCLAW_GATEWAY_PORT:-9090}"

export HEAD_IP VLLM_PORT VLLM_MODEL

SKIP_ONBOARD=false
WORKER_ONLY=false
for arg in "$@"; do
  case "$arg" in
    --skip-onboard) SKIP_ONBOARD=true ;;
    --worker-only)  WORKER_ONLY=true ;;
  esac
done

echo "=== Zeek-Agent Cluster Deploy ==="
echo "HEAD_IP=$HEAD_IP  VLLM_PORT=$VLLM_PORT  MODEL=$VLLM_MODEL"

if [[ "$WORKER_ONLY" == true ]]; then
  echo "Starting Ray worker..."
  docker compose -f docker-compose.vllm.yml --profile worker up -d --build
  echo "Worker started. Confirm on head: docker exec ray-head ray status"
  exit 0
fi

# 1. Start Ray head
echo "[1/5] Starting Ray head..."
docker compose -f docker-compose.vllm.yml --profile head up -d --build

echo "Waiting for Ray head..."
for i in $(seq 1 30); do
  if docker exec ray-head ray status >/dev/null 2>&1; then
    echo "Ray head is up."
    break
  fi
  if [[ $i -eq 30 ]]; then
    echo "ERROR: Ray head did not become ready."
    docker logs ray-head --tail 30 || true
    exit 1
  fi
  sleep 2
done

# 2. Wait for worker to join (user starts it separately, or it may already be up)
echo "[2/5] Waiting for 2 GPUs in Ray cluster (start worker if not already running)..."
for i in $(seq 1 60); do
  GPUS=$(docker exec ray-head python3 -c "import ray; ray.init(address='auto'); print(int(ray.cluster_resources().get('GPU', 0)))" 2>/dev/null || echo 0)
  if [[ "$GPUS" -ge 2 ]]; then
    echo "Ray cluster ready: $GPUS GPUs."
    break
  fi
  if [[ $i -eq 60 ]]; then
    echo "ERROR: Ray cluster did not reach 2 GPUs. Current: $GPUS"
    echo "On the worker node run: ./deploy.sh --worker-only"
    docker exec ray-head ray status || true
    exit 1
  fi
  sleep 5
done

# 3. Start vLLM inside ray-head
echo "[3/5] Starting vLLM inside ray-head..."
chmod +x start-vllm.sh
./start-vllm.sh

echo "Waiting for vLLM at http://localhost:${VLLM_PORT}/v1/models ..."
for i in $(seq 1 120); do
  if curl -sf "http://localhost:${VLLM_PORT}/v1/models" >/dev/null 2>&1; then
    echo "vLLM is ready."
    break
  fi
  if [[ $i -eq 120 ]]; then
    echo "ERROR: vLLM did not become ready within 10 minutes."
    docker logs ray-head --tail 40 || true
    exit 1
  fi
  sleep 5
done

MODEL_ID=$(curl -sf "http://localhost:${VLLM_PORT}/v1/models" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data'][0]['id'] if d.get('data') else '')" 2>/dev/null || echo "$VLLM_MODEL")
echo "Detected model: $MODEL_ID"

# 4. Onboard NemoClaw
if [[ "$SKIP_ONBOARD" == false ]]; then
  echo "[4/5] Onboarding NemoClaw/OpenShell to vLLM..."
  export NEMOCLAW_GATEWAY_PORT="$GATEWAY_PORT"
  export NEMOCLAW_VLLM_PORT="$VLLM_PORT"
  export NEMOCLAW_PROVIDER=custom
  export NEMOCLAW_ENDPOINT_URL="http://localhost:${VLLM_PORT}/v1"
  export NEMOCLAW_MODEL="$MODEL_ID"
  export NEMOCLAW_COMPATIBLE_AUTH_MODE=none
  export COMPATIBLE_API_KEY=dummy
  export NEMOCLAW_NON_INTERACTIVE=1
  export NEMOCLAW_YES=1
  export NEMOCLAW_SANDBOX_NAME="$SANDBOX_NAME"
  export PATH="$HOME/.local/bin:$PATH"

  if ! command -v nemoclaw >/dev/null 2>&1; then
    echo "nemoclaw not found. Installing..."
    curl -fsSL https://www.nvidia.com/nemoclaw.sh | bash || true
    export PATH="$HOME/.local/bin:$PATH"
  fi

  if command -v nemoclaw >/dev/null 2>&1; then
    nemoclaw onboard --name "$SANDBOX_NAME" --non-interactive || \
      nemoclaw onboard --name "$SANDBOX_NAME" --resume || \
      echo "WARNING: onboard returned non-zero (may already be onboarded). Continuing."
  else
    echo "WARNING: nemoclaw CLI still not available. Skip onboard and continue."
  fi
else
  echo "[4/5] Skipping NemoClaw onboard (--skip-onboard)."
fi

# 5. Start analysis stack
echo "[5/5] Starting Zeek analysis stack..."
export VLLM_BASE_URL="http://host.docker.internal:${VLLM_PORT}/v1"
export MODEL="$MODEL_ID"
docker compose -f docker-compose.analysis.yml up -d --build

echo ""
echo "=== Deploy complete ==="
echo "vLLM:        http://localhost:${VLLM_PORT}/v1"
echo "Summarizer:  http://localhost:8501"
echo "NemoClaw:    nemoclaw list  /  openshell status"
echo ""
echo "On the worker node run:  ./deploy.sh --worker-only"
