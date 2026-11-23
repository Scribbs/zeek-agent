#!/usr/bin/env bash
# deploy.sh — Bring up vLLM cluster, onboard NemoClaw/OpenShell, start analysis stack
#
# Run this on the HEAD node after the worker is already joined.
#
# Usage:
#   ./deploy.sh
#   ./deploy.sh --skip-onboard
#   ./deploy.sh --worker-only          # on the second node

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env if present
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

# Defaults
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
  echo "Starting vLLM worker..."
  docker compose -f docker-compose.vllm.yml --profile worker up -d
  echo "Worker started. Exit."
  exit 0
fi

# 1. Start vLLM head
echo "[1/4] Starting vLLM head..."
docker compose -f docker-compose.vllm.yml --profile head up -d

# 2. Wait for vLLM to be ready
echo "[2/4] Waiting for vLLM at http://localhost:${VLLM_PORT}/v1/models ..."
for i in $(seq 1 60); do
  if curl -sf "http://localhost:${VLLM_PORT}/v1/models" >/dev/null 2>&1; then
    echo "vLLM is ready."
    break
  fi
  if [[ $i -eq 60 ]]; then
    echo "ERROR: vLLM did not become ready within 5 minutes."
    docker logs vllm-head --tail 50 || true
    exit 1
  fi
  sleep 5
done

# Discover model id
MODEL_ID=$(curl -sf "http://localhost:${VLLM_PORT}/v1/models" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data'][0]['id'] if d.get('data') else '')" 2>/dev/null || echo "$VLLM_MODEL")
echo "Detected model: $MODEL_ID"

# 3. Onboard NemoClaw (non-interactive) to the running vLLM
if [[ "$SKIP_ONBOARD" == false ]]; then
  echo "[3/4] Onboarding NemoClaw/OpenShell to vLLM..."
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

  # Ensure PATH includes local bins
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
  echo "[3/4] Skipping NemoClaw onboard (--skip-onboard)."
fi

# 4. Start analysis stack
echo "[4/4] Starting Zeek analysis stack..."
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
