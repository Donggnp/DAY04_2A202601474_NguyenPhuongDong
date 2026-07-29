from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

from env_loader import load_lab_env
from providers import make_provider
from tools import TOOL_FUNCTIONS, load_tool_declarations, to_openai_tools
from versioning import artifact_version_dict, build_artifact_version
from chat import run_model_tool_loop, trim_history, write_transcript, safe_slug, now_iso

ROOT = Path(__file__).parent
ARTIFACTS_DIR = ROOT / "artifacts"
TRANSCRIPTS_DIR = ROOT / "transcripts"

load_lab_env(ROOT)

# 7 Tools specified for the Research Paper Agent
RESEARCH_TOOLS_7 = [
    "clarify",
    "lookup",
    "fetch",
    "format",
    "papers",
    "paper_text",
    "download_figure",
]

# Page Configuration
st.set_page_config(
    page_title="Research Paper AI Agent — Streamlit UI",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for rich aesthetics
st.markdown(
    """
    <style>
    /* Main Layout Aesthetics */
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        background: linear-gradient(135deg, #1E88E5 0%, #42A5F5 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #64748B;
        margin-bottom: 1.5rem;
    }
    
    /* Tool Badge Styling */
    .tool-badge {
        display: inline-block;
        background-color: #EFF6FF;
        color: #1D4ED8;
        border: 1px solid #BFDBFE;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 0.82rem;
        font-weight: 600;
        margin-right: 6px;
        margin-bottom: 6px;
    }
    .version-badge {
        display: inline-block;
        background-color: #ECFDF5;
        color: #047857;
        border: 1px solid #A7F3D0;
        padding: 4px 12px;
        border-radius: 8px;
        font-weight: 700;
        font-size: 0.9rem;
    }
    
    /* Trace Accordion Box */
    .trace-box {
        background-color: #F8FAFC;
        border-left: 4px solid #3B82F6;
        padding: 10px 14px;
        margin: 8px 0;
        border-radius: 4px;
        font-family: monospace;
        font-size: 0.88rem;
    }
    
    /* Quick Prompt Button Styling */
    div.stButton > button {
        border-radius: 8px;
        border: 1px solid #E2E8F0;
        transition: all 0.2s ease-in-out;
    }
    div.stButton > button:hover {
        border-color: #3B82F6;
        color: #2563EB;
        background-color: #EFF6FF;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def get_filtered_tools(tools_path: Path, target_tools: list[str]) -> list[dict[str, Any]]:
    all_declarations = load_tool_declarations(tools_path)
    filtered = [t for t in all_declarations if t["name"] in target_tools]
    return filtered


def initialize_session():
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "history" not in st.session_state:
        st.session_state.history = []
    if "transcript" not in st.session_state:
        st.session_state.transcript = None
    if "transcript_path" not in st.session_state:
        st.session_state.transcript_path = None
    if "turn_index" not in st.session_state:
        st.session_state.turn_index = 0


initialize_session()

# Sidebar Configuration
st.sidebar.markdown("## ⚙️ Configuration & Model")

# Available Providers & Defaults
provider_option = st.sidebar.selectbox(
    "Provider",
    options=["openai", "gemini", "openrouter", "anthropic"],
    index=0,
    help="Select LLM provider configured in .env",
)

model_override = st.sidebar.text_input(
    "Model (Optional Override)",
    value="",
    placeholder="e.g. gpt-4o-mini, gemini-2.0-flash",
    help="Leave blank to use provider default model",
)

version_option = st.sidebar.selectbox(
    "Artifact Version",
    options=["v3", "v2", "v1", "v0"],
    index=0,
    help="Version of system prompt and tool declarations",
)

max_tool_rounds = st.sidebar.slider("Max Tool Rounds", min_value=1, max_value=10, value=5)
history_window = st.sidebar.slider("History Window (Pairs)", min_value=1, max_value=10, value=5)

st.sidebar.markdown("---")
st.sidebar.markdown("### 🛠️ Active 7 Tools")

tool_declarations = get_filtered_tools(ARTIFACTS_DIR / "tools.yaml", RESEARCH_TOOLS_7)
openai_tools = to_openai_tools(tool_declarations)

for tool_info in tool_declarations:
    st.sidebar.markdown(f'<span class="tool-badge">🔧 {tool_info["name"]}</span>', unsafe_allow_html=True)

st.sidebar.markdown("---")

# Inspect Artifacts Collapsible
with st.sidebar.expander("📄 View System Prompt"):
    system_prompt_content = (ARTIFACTS_DIR / "system_prompt.md").read_text(encoding="utf-8")
    st.code(system_prompt_content, language="markdown")

with st.sidebar.expander("📋 View 7 Tools YAML"):
    st.code(json.dumps(tool_declarations, ensure_ascii=False, indent=2), language="json")

if st.sidebar.button("🗑️ Reset Chat & Transcript", use_container_width=True):
    st.session_state.messages = []
    st.session_state.history = []
    st.session_state.transcript = None
    st.session_state.transcript_path = None
    st.session_state.turn_index = 0
    st.rerun()

# Main Area Header
col_header, col_ver = st.columns([4, 1])
with col_header:
    st.markdown('<div class="main-header">🔬 Research Paper AI Agent</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Giao diện AI đọc & phân tích bài báo arXiv, tra cứu tin tức web, và trích xuất bảng biểu hình ảnh với 7 Tools chuẩn lab</div>',
        unsafe_allow_html=True,
    )
with col_ver:
    st.markdown(f'<div style="text-align: right; margin-top: 10px;"><span class="version-badge">Version: {version_option}</span></div>', unsafe_allow_html=True)

# Quick Demo Prompts
st.markdown("##### 🚀 Quick Demo Scenarios:")
demo_cols = st.columns(3)

prompt_to_submit = None

with demo_cols[0]:
    if st.button("🔎 1. Tìm paper RAG trên arXiv", use_container_width=True):
        prompt_to_submit = "Tìm giúp mình 5 bài báo arXiv mới nhất về Retrieval Augmented Generation."
with demo_cols[1]:
    if st.button("📖 2. Đọc arXiv paper 1706.03762", use_container_width=True):
        prompt_to_submit = "Đọc nội dung bài báo arXiv 1706.03762, lấy 3 trang đầu."
with demo_cols[2]:
    if st.button("📊 3. Trích hình ảnh paper 2303.08774", use_container_width=True):
        prompt_to_submit = "Trích xuất hình ảnh kết quả từ paper arXiv 2303.08774."

demo_cols2 = st.columns(2)
with demo_cols2[0]:
    if st.button("🌐 4. Tìm tin web Gemini 2.0 & fetch URL", use_container_width=True):
        prompt_to_submit = "Tìm tin tức web hôm nay về model Gemini 2.0 và tóm tắt link này: https://deepmind.google/technologies/gemini/"
with demo_cols2[1]:
    if st.button("📝 5. Tạo Digest brief bài báo", use_container_width=True):
        prompt_to_submit = "Tổng hợp các bài báo vừa tìm thành digest, dùng template brief."

st.markdown("---")

# Render Existing Chat Messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        
        # If assistant message has rounds / tool trace attached, render it nicely
        if msg["role"] == "assistant" and "rounds" in msg:
            rounds = msg.get("rounds", [])
            tool_events = msg.get("tool_events", [])
            
            if rounds:
                with st.expander(f"🔍 Tool Call Trace ({len(tool_events)} tool calls across {len(rounds)} rounds)"):
                    for r in rounds:
                        st.markdown(f"**Round {r.get('round')}**")
                        for tc in r.get("tool_calls", []):
                            st.code(f"🔧 Tool: {tc['name']}\nArgs: {json.dumps(tc['args'], ensure_ascii=False)}", language="json")
                        
                        for tr in r.get("tool_results", []):
                            st.caption(f"Result for `{tr.get('tool')}`:")
                            res = tr.get("result", {})
                            st.json(res)
                            
                            # Render extracted figures if tool was download_figure
                            if tr.get("tool") == "download_figure" and isinstance(res, dict) and "items" in res:
                                st.markdown("##### 🖼️ Extracted Figures & Tables:")
                                fig_cols = st.columns(2)
                                for idx, fig_item in enumerate(res.get("items", [])):
                                    img_path = fig_item.get("image_path")
                                    if img_path and os.path.exists(img_path):
                                        with fig_cols[idx % 2]:
                                            st.image(
                                                img_path,
                                                caption=f"Page {fig_item.get('page')}: {fig_item.get('caption', '')}",
                                                use_container_width=True,
                                            )

# Handle Chat Input
chat_input_val = st.chat_input("Nhập câu hỏi hoặc yêu cầu nghiên cứu của bạn...")
if prompt_to_submit is None and chat_input_val:
    prompt_to_submit = chat_input_val

if prompt_to_submit:
    # 1. Display user message
    st.session_state.messages.append({"role": "user", "content": prompt_to_submit})
    with st.chat_message("user"):
        st.markdown(prompt_to_submit)

    # 2. Setup agent provider and history
    system_prompt = (ARTIFACTS_DIR / "system_prompt.md").read_text(encoding="utf-8")
    provider = make_provider(provider_option)
    selected_model = model_override.strip() or getattr(provider, "default_model", None)
    artifact_version = build_artifact_version(version_option, ARTIFACTS_DIR / "system_prompt.md", ARTIFACTS_DIR / "tools.yaml")

    # Initialize transcript logging if not already created
    if st.session_state.transcript is None:
        timestamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
        transcript_id = "_".join([
            safe_slug(version_option),
            safe_slug(provider_option),
            timestamp,
        ])
        st.session_state.transcript_path = TRANSCRIPTS_DIR / f"{transcript_id}.transcript.json"
        st.session_state.transcript = {
            "transcript_id": transcript_id,
            **artifact_version_dict(artifact_version),
            "provider": provider_option,
            "model": selected_model,
            "system_prompt": str(ARTIFACTS_DIR / "system_prompt.md"),
            "tools": str(ARTIFACTS_DIR / "tools.yaml"),
            "history_window": history_window,
            "max_tool_rounds": max_tool_rounds,
            "active_tools": RESEARCH_TOOLS_7,
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "turns": [],
        }

    st.session_state.turn_index += 1
    messages_payload = [
        {"role": "system", "content": system_prompt},
        *trim_history(st.session_state.history, history_window),
        {"role": "user", "content": prompt_to_submit},
    ]

    turn_record = {
        "turn_index": st.session_state.turn_index,
        "started_at": now_iso(),
        "user": prompt_to_submit,
        "status": "started",
        "assistant_text": None,
        "rounds": [],
        "tool_events": [],
    }

    # 3. Execute model tool loop with spinner
    with st.chat_message("assistant"):
        with st.spinner("🤖 Agent đang suy nghĩ và gọi tools..."):
            try:
                result = run_model_tool_loop(
                    provider=provider,
                    messages=messages_payload,
                    tools=openai_tools,
                    model=selected_model,
                    max_tool_rounds=max_tool_rounds,
                )
                turn_record.update(result)
                assistant_text = result["assistant_text"]
                
                st.markdown(assistant_text)
                
                # Render tool trace
                rounds = result.get("rounds", [])
                tool_events = result.get("tool_events", [])
                if rounds:
                    with st.expander(f"🔍 Tool Call Trace ({len(tool_events)} tool calls across {len(rounds)} rounds)", expanded=True):
                        for r in rounds:
                            st.markdown(f"**Round {r.get('round')}**")
                            for tc in r.get("tool_calls", []):
                                st.code(f"🔧 Tool: {tc['name']}\nArgs: {json.dumps(tc['args'], ensure_ascii=False)}", language="json")
                            
                            for tr in r.get("tool_results", []):
                                st.caption(f"Result for `{tr.get('tool')}`:")
                                res = tr.get("result", {})
                                st.json(res)
                                
                                # Render figures if download_figure was executed
                                if tr.get("tool") == "download_figure" and isinstance(res, dict) and "items" in res:
                                    st.markdown("##### 🖼️ Extracted Figures & Tables:")
                                    fig_cols = st.columns(2)
                                    for idx, fig_item in enumerate(res.get("items", [])):
                                        img_path = fig_item.get("image_path")
                                        if img_path and os.path.exists(img_path):
                                            with fig_cols[idx % 2]:
                                                st.image(
                                                    img_path,
                                                    caption=f"Page {fig_item.get('page')}: {fig_item.get('caption', '')}",
                                                    use_container_width=True,
                                                )

                # Save assistant response to state
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": assistant_text,
                    "rounds": rounds,
                    "tool_events": tool_events,
                })
                st.session_state.history.append({"role": "user", "content": prompt_to_submit})
                st.session_state.history.append({"role": "assistant", "content": assistant_text})

            except Exception as exc:
                error_msg = f"ERROR ({type(exc).__name__}): {str(exc)}"
                turn_record.update({
                    "status": "provider_error",
                    "error": error_msg,
                })
                st.error(f"⚠️ {error_msg}")
                st.session_state.messages.append({"role": "assistant", "content": f"⚠️ {error_msg}"})

    # Save transcript log to file
    turn_record["ended_at"] = now_iso()
    st.session_state.transcript["turns"].append(turn_record)
    write_transcript(st.session_state.transcript_path, st.session_state.transcript)
    st.toast(f"💾 Transcript updated: {st.session_state.transcript_path.name}")
