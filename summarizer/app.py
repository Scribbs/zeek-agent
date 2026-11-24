import streamlit as st
import pandas as pd
import time
import os
import re
from openai import OpenAI
from pathlib import Path
from datetime import datetime, timedelta
from io import StringIO

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
    """Load a Zeek log using the #fields header for column names."""
    p = ZEEK_DIR / f"{name}.log"
    if not p.exists():
        return pd.DataFrame(), f"{name}.log not found"
    try:
        text = p.read_text(errors="replace")
        fields = None
        data_lines = []
        for line in text.splitlines():
            if line.startswith("#fields"):
                fields = line.split("\t")[1:]  # drop the #fields token
            elif line.startswith("#"):
                continue
            elif line.strip():
                data_lines.append(line)

        if not data_lines:
            return pd.DataFrame(), f"{name}.log has no data rows"

        df = pd.read_csv(
            StringIO("\n".join(data_lines)),
            sep="\t",
            names=fields,
            header=None,
            low_memory=False,
            on_bad_lines="skip",
        )

        if df.empty:
            return df, f"{name}.log parsed empty"

        if "ts" in df.columns:
            df["ts"] = pd.to_datetime(df["ts"], unit="s", errors="coerce")
            cutoff = datetime.utcnow() - timedelta(minutes=WINDOW_MIN)
            recent = df[df["ts"] >= cutoff]
            if recent.empty:
                return df.tail(200), f"No rows in last {WINDOW_MIN} min; showing last 200"
            return recent, None
        return df, None
    except Exception as e:
        return pd.DataFrame(), f"Parse error on {name}.log: {e}"

def strip_reasoning(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    for marker in ("**Summary**", "Summary:", "## Summary", "Final summary:"):
        idx = text.lower().find(marker.lower())
        if idx != -1:
            text = text[idx:]
            break
    lines = text.splitlines()
    bullet_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(("-", "*", "•")) or re.match(r"^\d+[.)]\s", stripped):
            bullet_idx = i
            break
    if bullet_idx is not None and bullet_idx > 1:
        text = "\n".join(lines[bullet_idx:])
    return text.strip()

def summarize(text):
    if not text.strip():
        return "No recent data."
    prompt = f"""Summarize these Zeek logs for a security analyst.
Return ONLY a short bullet list of findings. No preamble.

{text[:8000]}"""
    try:
        r = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "Output only a bullet list of security findings. No reasoning, no instructions, no preamble."},
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
        conn, conn_err = load_log("conn")
        notice, notice_err = load_log("notice")

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Recent Connections")
            if conn_err:
                st.warning(conn_err)
            if not conn.empty:
                prefer = ["ts", "id.orig_h", "id.resp_h", "id.resp_p", "proto", "service", "orig_bytes", "resp_bytes", "conn_state"]
                cols = [c for c in prefer if c in conn.columns]
                if not cols:
                    cols = list(conn.columns)[:8]
                st.dataframe(conn[cols].head(40), height=280)
                if "id.orig_h" in conn.columns:
                    st.write("Top sources:", conn.groupby("id.orig_h").size().nlargest(8).to_dict())
            else:
                st.info("No connection data")

        with c2:
            st.subheader("Notices")
            if notice_err:
                st.warning(notice_err)
            if not notice.empty:
                prefer = ["ts", "note", "msg", "src", "dst", "p"]
                cols = [c for c in prefer if c in notice.columns]
                if not cols:
                    cols = list(notice.columns)[:6]
                st.dataframe(notice[cols].head(20), height=280)
            else:
                st.info("No notice data")

        blob = ""
        if not conn.empty:
            blob += "CONN:\n" + conn.head(40).to_string() + "\n"
        if not notice.empty:
            blob += "NOTICES:\n" + notice.head(10).to_string() + "\n"

        st.subheader("LLM Summary")
        with st.spinner("Summarizing..."):
            st.markdown(summarize(blob))

        st.caption(f"Updated {datetime.now().strftime('%H:%M:%S')}  |  Window: last {WINDOW_MIN} min  |  Model: {MODEL}")

    time.sleep(REFRESH)
