#!/usr/bin/env bash
# Start vLLM inside the existing ray-head container.
# Requires the Ray cluster to already show 2 nodes / 2 GPUs.
#
# Usage (on head):
#   ./start-vllm.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

VLLM_MODEL="${VLLM_MODEL:-nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4}"
VLLM_PORT="${VLLM_PORT:-8000}"

echo "Checking Ray cluster..."
GPUS=$(docker exec ray-head python3 -c "import ray; ray.init(address='auto'); print(int(ray.cluster_resources().get('GPU', 0)))" 2>/dev/null || echo 0)
echo "GPUs visible to Ray: $GPUS"

if [[ "$GPUS" -lt 2 ]]; then
  echo "ERROR: Need 2 GPUs in the Ray cluster before starting vLLM."
  echo "Check: docker exec ray-head ray status"
  exit 1
fi

echo "Starting vLLM inside ray-head..."
docker exec -d ray-head bash -c "
  vllm serve '${VLLM_MODEL}' \\
    --host 0.0.0.0 \\
    --port ${VLLM_PORT} \\
    --tensor-parallel-size 2 \\
    --distributed-executor-backend ray \\
    --gpu-memory-utilization 0.80 \\
    --max-model-len 32768 \\
    --trust-remote-code
"

echo "vLLM starting. Watch with: docker logs -f ray-head"
