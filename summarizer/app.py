import streamlit as st
import pandas as pd
import time
import os
import re
from openai import OpenAI
from pathlib import Path
from datetime import datetime, timedelta

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
    """Keep only the final bullet summary; drop reasoning traces."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)

    # Prefer content after an explicit summary marker
    for marker in ("**Summary**", "Summary:", "## Summary", "Final summary:", "Here is the summary"):
        idx = text.lower().find(marker.lower())
        if idx != -1:
            text = text[idx:]
            break

    # If still looks like reasoning, keep from the first bullet onward
    lines = text.splitlines()
    bullet_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(("-", "*", "•")) or re.match(r"^\d+[.)]\s", stripped):
            bullet_idx = i
            break
    if bullet_idx is not None and bullet_idx > 2:
        text = "\n".join(lines[bullet_idx:])

    # Drop any remaining leading prose that is clearly reasoning
    text = re.sub(
        r"^(The user wants|Let me|I need to|Looking at|Analyzing|Here'?s my|Okay,).*?(?=\n[-*•]|\n\d+[.)])",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return text.strip()

def summarize(text):
    if not text.strip():
        return "No recent data."
    prompt = f"""Summarize these Zeek logs as a network security analyst.
Output ONLY a short bullet list. No preamble, no reasoning, no "The user wants", no "Let me analyze".
Start with the first bullet.

Focus on: top talkers, unusual volumes, beaconing, odd ports/protocols, notices.

{text[:8000]}"""
    try:
        r = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "Reply with only a bullet list. No reasoning. No preamble. First character must be a dash or asterisk."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=400
        )
        raw = r.choices[0].message.content or ""
        cleaned = strip_reasoning(raw)
        return cleaned if cleaned else raw
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
            blob += "CONN:\n" + conn.head(60).to_string() + "\n"
        if not notice.empty:
            blob += "NOTICES:\n" + notice.to_string() + "\n"

        st.subheader("LLM Summary")
        with st.spinner("Summarizing..."):
            st.markdown(summarize(blob))

        st.caption(f"Updated {datetime.now().strftime('%H:%M:%S')}  |  Window: last {WINDOW_MIN} min  |  Model: {MODEL}")

    time.sleep(REFRESH)
