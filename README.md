# Zeek Agent on 2× GB10 Cluster

Consolidated deployment: multi-node vLLM (Ray) + NemoClaw/OpenShell + Zeek summarizer UI.

## Files

| File | Purpose |
|------|---------|
| `docker-compose.vllm.yml` | Ray head + worker containers (profiles) |
| `Dockerfile.vllm-ray` | Thin image that adds Ray to `vllm/vllm-openai` |
| `start-vllm.sh` | Starts vLLM **inside** the ray-head container |
| `deploy.sh` | One-shot: Ray cluster → vLLM → NemoClaw → analysis |
| `docker-compose.analysis.yml` | Zeek + Streamlit summarizer |
| `.env.example` | Template for cluster IPs, model, ports |

## Why vLLM runs inside ray-head

Running vLLM as a separate container fails to join the Ray session (`No node info found matching attributes`). The working pattern is:

1. Start `ray-head` on the head node and `ray-worker` on the worker node.
2. Confirm `docker exec ray-head ray status` shows **2 nodes / 2 GPUs**.
3. Start vLLM with `docker exec` into `ray-head` (see `start-vllm.sh`).

## Quick start

**Head node**
```bash
cp .env.example .env
# set HEAD_IP, WORKER_IP, NCCL_IF (ConnectX interface), HF_TOKEN, ZEEK_IFACE

chmod +x deploy.sh start-vllm.sh
./deploy.sh
```

**Worker node** (in another terminal or after head is up)
```bash
cp .env.example .env
# set HEAD_IP to the head's ConnectX IP, WORKER_IP to this node's ConnectX IP, NCCL_IF

./deploy.sh --worker-only
```

## Manual steps

**Head**
```bash
docker compose -f docker-compose.vllm.yml --profile head up -d --build
# wait until ray status is healthy
docker exec ray-head ray status

# only after 2 GPUs are visible:
./start-vllm.sh
docker logs -f ray-head
```

**Worker**
```bash
docker compose -f docker-compose.vllm.yml --profile worker up -d --build
```

## Important

- Run **only** the `head` profile on the head and **only** the `worker` profile on the worker. Running both on one node registers duplicate nodes.
- `NCCL_IF` must be the ConnectX / high-speed interface (e.g. `enp1s0f1np1`), not the management NIC.
- `HEAD_IP` and `WORKER_IP` must be the IPs on that ConnectX interface.
- First model load can take several minutes.

## URLs

- Summarizer UI: http://localhost:8501
- vLLM OpenAI API: http://localhost:8000/v1
- Ray dashboard: http://<HEAD_IP>:8265
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
