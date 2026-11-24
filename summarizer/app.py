import streamlit as st
import pandas as pd
import time
import os
import re
from openai import OpenAI
from pathlib import Path
from datetime import datetime, timedelta

# OpenAI-compatible client pointed at NemoClaw / vLLM
client = OpenAI(
    base_url=os.getenv("VLLM_BASE_URL", "http://host.docker.internal:8000/v1"),
    api_key=os.getenv("VLLM_API_KEY", "not-needed")
)
MODEL = os.getenv("MODEL", "nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4")
ZEEK_DIR = Path("/zeek/logs")
REFRESH = int(os.getenv("REFRESH_SECONDS", "60"))
WINDOW_MIN = int(os.getenv("LOG_WINDOW_MINUTES", "15"))

st.set_page_config(page_title="Zeek Summary", layout="wide")
st.title("Zeek Near-Real-Time Summary")
st.caption("Powered by NemoClaw / OpenShell + vLLM")

def load_log(name):
    p = ZEEK_DIR / f"{name}.log"
    if not p.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(p, sep="\t", comment="#", low_memory=False)
        if "ts" in df.columns:
            df["ts"] = pd.to_datetime(df["ts"], unit="s", errors="coerce")
            cutoff = datetime.utcnow() - timedelta(minutes=WINDOW_MIN)
            df = df[df["ts"] >= cutoff]
        return df
    except Exception:
        return pd.DataFrame()

def strip_reasoning(text: str) -> str:
    """Remove common reasoning-model traces so only the final summary remains."""
    # Drop <think>...</think> blocks if present
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Drop leading "The user wants..." style preambles up to the first real summary marker
    for marker in ("**Summary**", "Summary:", "## Summary", "Final summary:", "Here is the summary"):
        idx = text.lower().find(marker.lower())
        if idx != -1:
            text = text[idx:]
            break
    return text.strip()

def summarize(text):
    if not text.strip():
        return "No recent data."
    prompt = f"""You are a network security analyst. Summarize these recent Zeek logs.
Focus on top talkers, notices, unusual volumes, beaconing signs, odd ports/protocols.
Be concise with bullets.

IMPORTANT: Output ONLY the final summary. Do not include your reasoning, chain-of-thought, or any preamble like "The user wants" or "Let me parse". Start directly with the summary.

{text[:12000]}"""
    try:
        r = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are a concise network security analyst. Reply with only the final bullet summary. No reasoning, no preamble."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=600
        )
        raw = r.choices[0].message.content or ""
        return strip_reasoning(raw)
    except Exception as e:
        return f"LLM error: {e}"

placeholder = st.empty()
while True:
    with placeholder.container():
        conn = load_log("conn")
        notice = load_log("notice")

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Recent Connections")
            if not conn.empty:
                cols = [c for c in ["ts","id.orig_h","id.resp_h","id.resp_p","proto","service","orig_bytes","resp_bytes"] if c in conn.columns]
                st.dataframe(conn[cols].head(40), height=280)
                if "id.orig_h" in conn.columns:
                    st.write("Top sources:", conn.groupby("id.orig_h").size().nlargest(8).to_dict())
            else:
                st.info("No recent conn.log")

        with c2:
            st.subheader("Notices")
            if not notice.empty:
                st.dataframe(notice.head(20), height=280)
            else:
                st.info("No recent notices")

        blob = ""
        if not conn.empty:
            blob += "CONN:\n" + conn.head(80).to_string() + "\n"
        if not notice.empty:
            blob += "NOTICES:\n" + notice.to_string() + "\n"

        st.subheader("LLM Summary")
        with st.spinner("Summarizing..."):
            st.markdown(summarize(blob))

        st.caption(f"Updated {datetime.now().strftime('%H:%M:%S')}  |  Window: last {WINDOW_MIN} min  |  Model: {MODEL}")

    time.sleep(REFRESH)
