# tab1_usecase.py
import json, streamlit as st

SYSTEM_PROMPT = """あなたは衛星リモートセンシングと保険数理の専門家です。
以下のスキーマの**有効なJSONのみ**を返してください（前後の説明やコードブロックは不要）。
{
  "usecase": "ユースケース名",
  "kpi": "観測目的や評価KPI",
  "current_stack": {
     "satellites": [
        {"name":"Sentinel-1","type":"SAR","band":"C","revisit_days":6,"gsd_m":10,"note":"例"},
        {"name":"ALOS-2","type":"SAR","band":"L","revisit_days":14,"gsd_m":10,"note":""}
     ],
     "non_sat": [
        {"name":"雨量レーダー","type":"radar"},
        {"name":"ハザードマップ","type":"admin_db"}
     ],
     "assumptions": ["前提1","前提2"]
  }
}
返すのは**厳密なJSONのみ**。"""

def _call_llm(client, model, uc, kpi):
    if client is None: 
        return None, "Groq APIキー未設定"
    messages = [
        {"role":"system","content": SYSTEM_PROMPT},
        {"role":"user","content": f"ユースケース:{uc}\nKPI:{kpi}\n国内外データを具体名で。"}
    ]
    resp = client.chat.completions.create(model=model, messages=messages, temperature=0.2)
    content = resp.choices[0].message.content
    try:
        data = json.loads(content)
        return data, None
    except Exception as e:
        return None, f"JSON解析失敗: {e}\nRaw: {content[:400]}..."

def render_tab(client, model):
    st.subheader("① ユースケース定義 → センサ構成")
    uc = st.selectbox("ユースケース", ["洪水・浸水リスク評価","農業保険（干ばつ・冷害）","森林火災モニタリング","地震・地盤沈下（InSAR）","海上保険（AIS異常）"])
    kpi = st.text_area("観測目的/KPI", "被害推定の即時性・空間精度の向上 など")
    if st.button("センサ構成を生成"):
        data, err = _call_llm(client, model, uc, kpi)
        if err: 
            st.error(err); return
        st.session_state["tab1_json"] = data
        st.success("Tab1 JSON を保存しました。")
        st.json(data)
    if st.session_state.get("tab1_json"):
        st.caption("現在のTab1 JSON")
        st.json(st.session_state["tab1_json"])
