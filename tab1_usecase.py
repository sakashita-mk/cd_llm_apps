# tab1_usecase.py
import json, streamlit as st
from uc_seed import UC_DATA

SYSTEM_PROMPT = """あなたは衛星リモートセンシングの専門家です。
以下のスキーマの**有効なJSONのみ**を返してください（説明やコードブロックは禁止）。
非衛星（UAV/HAPS/ドローン/IoT/レーダー/行政DB等）は**絶対に含めない**こと。衛星のみ。

{
  "usecase": "ユースケース名",
  "context": {
    "background": "背景",
    "question": "顧客の問い",
    "issues": "現状の課題"
  },
  "satellite_stack": {
     "satellites": [
        {
          "name":"Sentinel-1",     // 具体衛星名（例: Sentinel-1, ALOS-2, SMAP, MODIS, VIIRS, PlanetScope 等）
          "type":"SAR|Optical|Thermal|Microwave",
          "band":"C|L|X|可視-NIR|TIR など",
          "orbit":"LEO|SSO 等",
          "revisit_days": 6,
          "gsd_m": 10,
          "swath_km": 250,
          "day_night":"day|night|both",
          "role":"この衛星の役割",
          "why":"採用理由（1文）"
        }
     ],
     "assumptions": ["衛星のみでの構成。非衛星は含めない。"]
  },
  "capabilities_sat_only": [
     "衛星のみで到達可能なこと1","2","3"
  ],
  "limitations_sat_only": [
     "衛星のみでは難しいこと1（雲被り/再訪/コスト等）","2","3"
  ],
  "summary": "衛星のみの構成で何ができるかの要約"
}
"""

def _call_llm(client, model, payload):
    if client is None:
        return None, "Groq APIキー未設定"
    messages = [
        {"role":"system","content": SYSTEM_PROMPT},
        {"role":"user","content": json.dumps(payload, ensure_ascii=False)}
    ]
    resp = client.chat_completions.create(  # openai>=1.51 なら chat.completions.create
        model=model, messages=messages, temperature=0.25
    ) if hasattr(client, "chat_completions") else client.chat.completions.create(
        model=model, messages=messages, temperature=0.25
    )
    content = resp.choices[0].message.content
    try:
        data = json.loads(content)
        # 念のためガード：非衛星が紛れたら除外
        sats = data.get("satellite_stack", {}).get("satellites", [])
        filtered = []
        ban_words = {"uav","drone","haps","iot","radar","cctv","admin","database","sns"}
        for s in sats:
            text = (" ".join(str(v) for v in s.values())).lower()
            if not any(w in text for w in ban_words):
                filtered.append(s)
        if "satellite_stack" in data:
            data["satellite_stack"]["satellites"] = filtered
        return data, None
    except Exception as e:
        return None, f"JSON解析失敗: {e}\nRaw: {content[:400]}..."

def render_tab(client, model):
    st.subheader("① ユースケース定義 → 衛星（のみ）センサ構成")

    uc = st.selectbox("ユースケース", list(UC_DATA.keys()), index=1)
    seed = UC_DATA[uc]

    with st.expander("📌 背景・顧客の問い・現状の課題", expanded=True):
        bg = st.text_area("背景", seed["background"])
        qn = st.text_area("顧客の問い", seed["question"])
        isu = st.text_area("現状の課題", seed["issues"])

    if st.button("衛星センサ構成を生成"):
        payload = {"usecase": uc, "context": {"background": bg, "question": qn, "issues": isu}}
        data, err = _call_llm(client, model, payload)
        if err:
            st.error(err); return
        st.session_state["tab1_json"] = data
        st.success("Tab1 JSON を保存しました。")
        st.json(data)
        if "summary" in data:
            st.markdown("### 🛰 衛星のみでできること / 限界")
            if data.get("capabilities_sat_only"): 
                st.write("**できること（衛星のみ）**")
                for c in data["capabilities_sat_only"]: st.markdown(f"- {c}")
            if data.get("limitations_sat_only"):
                st.write("**限界（衛星のみ）**")
                for l in data["limitations_sat_only"]: st.markdown(f"- {l}")

    if st.session_state.get("tab1_json"):
        st.caption("現在のTab1 JSON（衛星のみ）")
        st.json(st.session_state["tab1_json"])
