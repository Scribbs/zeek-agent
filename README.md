# Zeek Near-Real-Time Summarizer (NemoClaw / OpenShell compatible)

Containerized Zeek log summarizer with local Ollama inference and Streamlit UI.  
Designed for Dell Pro Max GB10 / DGX Spark clusters.

## Quick Start

```bash
# Optional: point at your Zeek current logs (or NFS mount)
export ZEEK_LOG_DIR=/opt/zeek/logs/current

docker compose up -d

# Pull a model (first time only)
docker exec -it ollama ollama pull qwen3.6:35b
# Alternatives: llama3.1:8b, qwen2.5:32b, gemma3:27b, etc.

# UI
# http://<host>:8501
```

## Layout

- `docker-compose.yml` — Ollama + summarizer
- `summarizer/` — Streamlit app + Dockerfile
- Bind-mount your Zeek logs via `ZEEK_LOG_DIR`

## NemoClaw Integration

1. Install NemoClaw / OpenShell on the host (see previous guidance).
2. The agent can call the summarizer at `http://<host>:8501` or you can extend `app.py` with a JSON API endpoint.
3. Shared volume of pre-computed summaries also works well for the sandbox.

## Cluster Notes (2× GB10)

- Prefer NFS (or the QSFP fabric) for the Zeek log directory so both nodes can see it.
- Run this Compose stack on the primary node.
- Optional: second Ollama on node B for extra capacity.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ZEEK_LOG_DIR` | `/opt/zeek/logs/current` | Host path to Zeek current logs |
| `MODEL` | `qwen3.6:35b` | Ollama model name |
| `REFRESH_SECONDS` | `60` | UI refresh interval |
| `LOG_WINDOW_MINUTES` | `15` | How far back to look |
| `OLLAMA_BASE_URL` | `http://ollama:11434/v1` | Inference endpoint |
