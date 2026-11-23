# Zeek Near-Real-Time Summarizer

Containerized Zeek log summarizer with Streamlit UI.  
**Inference is provided by NemoClaw + OpenShell + vLLM** (no local Ollama).  
Designed for Dell Pro Max GB10 / DGX Spark clusters (including 2-node setups).

## Architecture

```
NemoClaw / OpenShell (host)
  └── vLLM (OpenAI-compatible :8000)
         ▲
         │
zeek-summarizer (Streamlit :8501)  ── reads ──►  Zeek logs (host volume or NFS)
```

The summarizer never runs its own LLM. It talks to the vLLM instance that NemoClaw manages.

## Prerequisites

1. **NemoClaw + OpenShell** installed and onboarded on at least one GB10.
2. **vLLM** running (via NemoClaw onboarding option “Install vLLM (DGX Spark)” or a managed multi-node profile).
3. Docker + NVIDIA Container Toolkit on the node that will run this Compose stack.
4. Zeek logs available on the host (or via NFS shared across the cluster).

### Recommended NemoClaw onboarding notes

```bash
# Avoid port conflicts (8080 is often taken)
export NEMOCLAW_GATEWAY_PORT=9090

# Optional: pin vLLM port
export NEMOCLAW_VLLM_PORT=8000

nemoclaw onboard --name OpenClaw
# Choose: 8) Install vLLM (DGX Spark)
# or a dual-node profile if available
```

Confirm vLLM is ready:

```bash
curl http://localhost:8000/v1/models
```

## Quick Start

```bash
git clone https://github.com/Scribbs/zeek-agent.git
cd zeek-agent
cp .env.example .env
# Edit .env if needed (especially VLLM_BASE_URL and VLLM_MODEL)

docker compose up -d --build

# UI
# http://<gb10-ip>:8501
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ZEEK_LOG_DIR` | `/opt/zeek/logs` | Host path (or NFS mount) to Zeek logs |
| `VLLM_BASE_URL` | `http://host.docker.internal:8000/v1` | NemoClaw vLLM OpenAI endpoint |
| `VLLM_MODEL` | `nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4` | Model ID registered by vLLM |
| `REFRESH_SECONDS` | `60` | UI auto-refresh interval |
| `LOG_WINDOW_MINUTES` | `15` | Look-back window for logs |
| `VLLM_API_KEY` | `not-needed` | Usually unused for local vLLM |

## 2-Node GB10 Cluster

### Shared logs
- Prefer an NFS export (or the QSFP fabric) for the Zeek log directory so both nodes see the same data.
- Set `ZEEK_LOG_DIR` to that mount on the node running this Compose stack.

### Multi-node vLLM
NemoClaw has experimental dual-DGX-Spark vLLM profiles (tensor-parallel across two nodes). See the official docs:

- [Set Up vLLM on Two DGX Sparks](https://docs.nvidia.com/nemoclaw/user-guide/deepagents/inference/local-inference/set-up-vllm-on-two-dgx-sparks)

Typical pattern:

1. Onboard NemoClaw on the primary node with a dual-node serving preset (if available) or run multi-node vLLM manually with Ray + `--tensor-parallel-size 2`.
2. Point this stack’s `VLLM_BASE_URL` at the head node’s vLLM endpoint (e.g. `http://10.0.0.1:8000/v1`).
3. Run the Zeek summarizer Compose stack on either node (or both, behind a load balancer if desired).

### Port notes
- OpenShell gateway: default 8080 (override with `NEMOCLAW_GATEWAY_PORT`)
- vLLM: default 8000 (override with `NEMOCLAW_VLLM_PORT`)
- Streamlit UI: 8501

## NemoClaw / Agent Integration

- The Streamlit UI is the primary interface.
- For agent use, you can later add a small JSON endpoint to `app.py` or have the NemoClaw sandbox call the summarizer over the network.
- Pre-computed summaries written to a shared volume also work well inside the OpenShell sandbox.

## Files

- `docker-compose.yml` — Zeek (optional) + summarizer
- `summarizer/app.py` — Streamlit app (vLLM client)
- `summarizer/Dockerfile` — Python 3.12 + Streamlit + OpenAI client
- `.env.example` — configuration template

## Troubleshooting

- **“LLM error: connection refused”** → vLLM not ready or wrong `VLLM_BASE_URL`. Check `curl http://<host>:8000/v1/models`.
- **Empty logs** → confirm `ZEEK_LOG_DIR` is correct and the volume is mounted (`docker exec zeek-summarizer ls /zeek/logs`).
- **Port 8080 conflict** → set `NEMOCLAW_GATEWAY_PORT` before onboarding.
- **Hugging Face cache permission errors** → `sudo chown -R $(id -u):$(id -g) ~/.cache/huggingface`.

## License

Internal / lab use. Adjust as needed.
