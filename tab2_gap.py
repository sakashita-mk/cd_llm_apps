import json, streamlit as st

SYSTEM_PROMPT = """あなたはデータアーキテクトです。
入力（Tab1のJSON：衛星のみ）を踏まえ、下記スキーマで**有効なJSONのみ**を返却。
非衛星はここでは提案しない。衛星のみ構成の評価に限定。

{
  "gap_summary": "総評（1-2文）",
  "dimensions": [
     {"axis":"観測頻度","current":"例: 再訪6-14日","target":"例: 1-3日","gap":"大|中|小","reason":"根拠"},
     {"axis":"空間分解能","current":"10m","target":"1-3m","gap":"中","reason":""},
     {"axis":"観測範囲","current":"都市域中心","target":"流域全体","gap":"中","reason":""},
     {"axis":"コスト","current":"オープン中心 + 一部商用","target":"商用混在、月額~$Xk","gap":"小","reason":""}
  ],
  "what_we_can_do_now_sat_only": ["衛星のみで到達可能なこと1","2","3"],
  "what_we_cannot_do_sat_only": ["衛星のみでは困難なこと1","2","3"]
}
"""

def _call_llm(client, model, tab1_json):
    if client is None: 
        return None, "Groq APIキー未設定"
    messages = [
        {"role":"system","content": SYSTEM_PROMPT},
        {"role":"user","content": "Tab1 JSON:\n"+json.dumps(tab1_json, ensure_ascii=False)}
    ]
    resp = client.chat.completions.create(model=model, messages=messages, temperature=0.2)
    content = resp.choices[0].message.content
    try:
        data = json.loads(content)
        return data, None
    except Exception as e:
        return None, f"JSON解析失敗: {e}\nRaw: {content[:400]}..."

def render_tab(client, model, tab1_json):
    st.subheader("② GAP分析（頻度 / 分解能 / 範囲 / コスト）")
    if not tab1_json:
        st.stop()
    if st.button("GAP分析を実行"):
        data, err = _call_llm(client, model, tab1_json)
        if err: 
            st.error(err); return
        st.session_state["tab2_json"] = data
        st.success("Tab2 JSON を保存しました。")
        st.json(data)
    if st.session_state.get("tab2_json"):
        st.caption("現在のTab2 JSON")
        st.json(st.session_state["tab2_json"])
