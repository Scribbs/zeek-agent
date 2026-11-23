# NemoClaw + OpenShell Multi-Node (2× GB10)

Docker Compose layout for running NemoClaw / OpenShell with multi-node vLLM across two clustered Dell Pro Max GB10 systems.

This mirrors the pattern used for the vulnerability analysis pipeline: head node runs the control plane + vLLM head, worker node joins the tensor-parallel group.

## Prerequisites

- Two GB10s with passwordless SSH and a high-bandwidth interconnect (QSFP RoCE preferred)
- Docker + NVIDIA Container Toolkit on both nodes
- `cgroupns=host` already configured (from `nemoclaw setup-spark` or manual `daemon.json`)
- Hugging Face token if the model is gated (`export HF_TOKEN=hf_...`)

## Environment

Create `.env` on both nodes (or export):

```bash
HEAD_IP=10.0.0.1          # head node IP on the cluster fabric
PEER_IP=10.0.0.2          # worker node IP
NCCL_IF=eth0              # or the RoCE interface (e.g. rocep1s0f0)
VLLM_MODEL=nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4
VLLM_PORT=8000
OPENSHELL_PORT=9090
HF_TOKEN=hf_xxx
```

## Start the cluster

**On the head node (promaxgb10-1):**

```bash
docker compose -f docker-compose.nemoclaw-cluster.yml --profile head up -d
```

**On the worker node (promaxgb10-2):**

```bash
docker compose -f docker-compose.nemoclaw-cluster.yml --profile worker up -d
```

Wait for vLLM to report ready:

```bash
curl http://$HEAD_IP:8000/v1/models
```

## Onboard NemoClaw (on the head node)

```bash
export NEMOCLAW_GATEWAY_PORT=9090
export NEMOCLAW_VLLM_PORT=8000
export NEMOCLAW_PROVIDER=install-vllm
# Optional dual-node preset if using NemoClaw's managed dual profile instead of this compose:
# export NEMOCLAW_MANAGED_CLUSTER_PEERS=$PEER_IP
# export NEMOCLAW_SERVING_PRESET=vllm.dgx-spark-gb10.dual.deepseek-v4-flash-0731

nemoclaw onboard --name OpenClaw
```

Point the Zeek summarizer (or any other client) at `http://$HEAD_IP:8000/v1`.

## Alternative: NemoClaw managed dual-Spark profile

If you prefer NemoClaw to manage the dual-node vLLM itself (experimental):

```bash
export NEMOCLAW_MANAGED_CLUSTER_PEERS=<peer-ip-or-hostname>
export NEMOCLAW_SERVING_PRESET=vllm.dgx-spark-gb10.dual.deepseek-v4-flash-0731
export NEMOCLAW_PROVIDER=install-vllm
curl -fsSL https://www.nvidia.com/nemoclaw.sh | bash
```

See official docs: https://docs.nvidia.com/nemoclaw/user-guide/deepagents/inference/local-inference/set-up-vllm-on-two-dgx-sparks

## Stop everything

```bash
# On both nodes
docker compose -f docker-compose.nemoclaw-cluster.yml down

# Plus NemoClaw cleanup
nemoclaw stop --all
openshell gateway stop
```
