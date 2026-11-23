# Zeek Agent on 2× GB10 Cluster

Consolidated deployment: multi-node vLLM + NemoClaw/OpenShell + Zeek summarizer UI.

## Files

| File | Purpose |
|------|---------|
| `docker-compose.vllm.yml` | Multi-node vLLM (head + worker profiles) |
| `docker-compose.analysis.yml` | Zeek + Streamlit summarizer |
| `deploy.sh` | One-shot: start vLLM, onboard NemoClaw, start analysis |
| `.env.example` | Template for cluster IPs, model, ports |

## Quick start (head node)

```bash
cp .env.example .env
# edit HEAD_IP, NCCL_IF, HF_TOKEN, ZEEK_IFACE, etc.

chmod +x deploy.sh
./deploy.sh
```

## Worker node

```bash
cp .env.example .env
# set HEAD_IP to the head node's cluster IP

./deploy.sh --worker-only
```

## Manual steps (if you prefer)

**Head**
```bash
docker compose -f docker-compose.vllm.yml --profile head up -d
# wait for http://localhost:8000/v1/models
NEMOCLAW_PROVIDER=custom \
NEMOCLAW_ENDPOINT_URL=http://localhost:8000/v1 \
NEMOCLAW_MODEL=<model-id-from-vllm> \
NEMOCLAW_COMPATIBLE_AUTH_MODE=none \
COMPATIBLE_API_KEY=dummy \
NEMOCLAW_NON_INTERACTIVE=1 \
nemoclaw onboard --name OpenClaw

docker compose -f docker-compose.analysis.yml up -d --build
```

**Worker**
```bash
docker compose -f docker-compose.vllm.yml --profile worker up -d
```

## URLs

- Summarizer UI: http://localhost:8501
- vLLM OpenAI API: http://localhost:8000/v1
- OpenShell gateway: port 9090 (default)

## Stop

```bash
docker compose -f docker-compose.analysis.yml down
docker compose -f docker-compose.vllm.yml down
nemoclaw stop --all || true
openshell gateway stop || true
```

## Notes

- Zeek runs with host networking so it can see the real capture interface (`ZEEK_IFACE`).
- The summarizer reaches vLLM via `host.docker.internal`.
- NemoClaw is onboarded non-interactively to the already-running vLLM endpoint.
- Adjust `NCCL_IF` to your RoCE or management interface for multi-node tensor parallel.
