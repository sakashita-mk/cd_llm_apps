# app.py
import os, json
import streamlit as st
from openai import OpenAI
from tab1_usecase import render_tab as tab1_render
from tab2_gap import render_tab as tab2_render
from tab3_plan import render_tab as tab3_render

st.set_page_config(page_title="CDPユースケース構成アシスタント", layout="wide")
st.title("🌍 CDPユースケース構成アシスタント（Groq / Llama3.1）")

with st.sidebar:
    st.subheader("API設定")
    
    # Secrets優先で読み取り。UI入力でも上書き可。
    api_key = st.secrets.get("GROQ_API_KEY") or st.text_input(
        "GROQ_API_KEY", type="password", help="Groqコンソールで発行"
    )
    model_name = st.selectbox("モデル", ["llama-3.1-8b-instant","llama-3.1-70b-versatile"], index=0)
    st.caption("※ 無料枠の制限に注意。")

if "llm_client" not in st.session_state and api_key:
    os.environ["OPENAI_API_KEY"] = api_key
    st.session_state["llm_client"] = OpenAI(base_url="https://api.groq.com/openai/v1")
    st.success("Groqクライアント準備OK")

# 共有ステート（各タブ間の受け渡し）
st.session_state.setdefault("tab1_json", None)  # センサ構成（Tab1出力）
st.session_state.setdefault("tab2_json", None)  # GAP分析（Tab2出力）
st.session_state.setdefault("tab3_json", None)  # 構成方針（Tab3出力）

t1, t2, t3 = st.tabs(["① ユースケース定義", "② GAP分析", "③ 構成方針提示"])

with t1:
    tab1_render(st.session_state.get("llm_client"), model_name)

with t2:
    if st.session_state["tab1_json"] is None:
        st.info("まずは『① ユースケース定義』でセンサ構成を生成してください。")
    tab2_render(st.session_state.get("llm_client"), model_name, st.session_state.get("tab1_json"))

with t3:
    if st.session_state["tab2_json"] is None:
        st.info("まずは『② GAP分析』まで実行してください。")
    tab3_render(st.session_state.get("llm_client"), model_name, 
                st.session_state.get("tab1_json"), st.session_state.get("tab2_json"))
