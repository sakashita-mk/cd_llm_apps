# tab3_plan.py
import json, streamlit as st

SYSTEM_PROMPT = """あなたは衛星データ統合のアーキテクトです。
Tab1（衛星のみ）とTab2（GAP）を踏まえ、下記スキーマの**有効なJSONのみ**を返却。

{
  "constellation": [   // 衛星側の見直し・追加
    {"name":"ALOS-4","type":"SAR","band":"L","role":"植生下/地盤","why":"再訪/貫通性で補完"},
    {"name":"ICEYE","type":"SAR","band":"X","role":"高頻度/夜間","why":"頻度ギャップ解消"}
  ],
  "aerial_layer": [    // 非衛星（空中）で補完
    {"name":"HAPS","role":"雲下の広域・準リアルタイム","why":"頻度と雲被りのギャップ補完"},
    {"name":"UAV-MSI","role":"現地詳細/検証","why":"精度・真値補正"}
  ],
  "ground_layer": [    // 地上・社会で補完
    {"name":"IoT水位計/土壌水分","role":"真値補正","why":"モデル校正・説明可能性"},
    {"name":"GNSS/強震計","role":"InSAR補正","why":""},
    {"name":"行政DB/ハザード","role":"条件付与","why":""}
  ],
  "fusion": {
    "architecture":"衛星(多周波/光学/熱)×HAPS×UAV×IoT を時系列でETL→特徴量→リスクスコア",
    "methods":["時系列異常検知","セマンティックセグメンテーション","ベイズ推定"],
    "cadence":"例: 1-3日更新"
  },
  "outcomes":[
    "支払判定のT+24h化",
    "地点単位のRMSE▲x%（IoT補正込み）",
    "運用コスト最適化（商用/オープン配合）"
  ],
  "cost_note":"サブスク/従量の考え方を簡潔に"
}
"""

def _call_llm(client, model, tab1_json, tab2_json):
    if client is None: 
        return None, "Groq APIキー未設定"
    messages = [
        {"role":"system","content": SYSTEM_PROMPT},
        {"role":"user","content": "Tab1 JSON:\n"+json.dumps(tab1_json, ensure_ascii=False)},
        {"role":"user","content": "Tab2 JSON:\n"+json.dumps(tab2_json, ensure_ascii=False)}
    ]
    resp = client.chat.completions.create(model=model, messages=messages, temperature=0.2)
    content = resp.choices[0].message.content
    try:
        data = json.loads(content)
        return data, None
    except Exception as e:
        return None, f"JSON解析失敗: {e}\nRaw: {content[:400]}..."

def render_tab(client, model, tab1_json, tab2_json):
    st.subheader("③ 構成方針提示（統合案）")
    if not tab1_json or not tab2_json:
        st.stop()
    if st.button("構成方針を生成"):
        data, err = _call_llm(client, model, tab1_json, tab2_json)
        if err: 
            st.error(err); return
        st.session_state["tab3_json"] = data
        st.success("Tab3 JSON を保存しました。")
        st.json(data)
    if st.session_state.get("tab3_json"):
        st.caption("現在のTab3 JSON")
        st.json(st.session_state["tab3_json"])
