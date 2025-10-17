# tab3_plan.py
import json, streamlit as st

SYSTEM_PROMPT = """あなたは衛星データ統合のソリューションアーキテクトです。
Tab1/Tab2を踏まえ、下記スキーマで**有効なJSONのみ**を返却。
{
  "constellation": [
    {"name":"ALOS-4","type":"SAR","band":"L","role":"植生下/地盤", "why":"理由"},
    {"name":"ICEYE","type":"SAR","band":"X","role":"高頻度/夜間","why":""},
    {"name":"PlanetScope","type":"Optical","band":"可視-NIR","role":"高頻度光学","why":""}
  ],
  "aerial_layer": [
    {"name":"HAPS","role":"雲下の広域/準リアルタイム","why":""},
    {"name":"UAV-MSI","role":"現地詳細/検証","why":""}
  ],
  "ground_layer": [
    {"name":"IoT水位計","role":"真値補正","why":""},
    {"name":"GNSS/強震計","role":"InSAR補正","why":""},
    {"name":"行政DB/ハザード","role":"条件付与","why":""}
  ],
  "fusion": {
    "architecture":"例: 衛星(SAR/光学/熱)×HAPS×UAV×IoTを時系列で統合。クラウドにETL→特徴量→リスクスコア",
    "methods":["時系列異常検知","セマンティックセグメンテーション","ベイズ推定"],
    "cadence":"更新頻度（例: 1-3日）"
  },
  "outcomes":[
    "被害推定の即時化（例: 支払判定T+24h）",
    "地点単位の精度向上（例: IoT補正でRMSE▲x%）",
    "運用コストの最適化（商用/オープンの最適配分）"
  ],
  "cost_note":"コスト傾向の簡潔な見積の方針（サブスク/従量の考え方）"
}
返すのは**厳密なJSONのみ**。"""

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
