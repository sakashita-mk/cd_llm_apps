# tab1_usecase.py
import json, streamlit as st
from uc_seed import UC_DATA

SYSTEM_PROMPT = """
あなたは衛星リモートセンシングの専門家です。以下のユースケースのために、
①「衛星のみのセンサ構成」と ②「その構成でできること／できないこと」を JSON で出力してください。

# 出力仕様（必須、厳守）
- 文章や前置きは禁止。JSON **のみ**を返す。
- 末尾カンマ・コメントは禁止。
- キーは以下のみ。型も固定。

{
  "sensor_suite": [
    {
      "name": "string",                // 例: "Sentinel-2A/B"
      "platform": "LEO|GEO|SSO",
      "bands": ["string"],             // 例: ["VNIR","SWIR"]
      "gsd_m": number,                 // 空間分解能 (m)
      "revisit_days": number,          // 公称再訪 (日)
      "swath_km": number,              // 観測幅 (km)
      "typical_products": ["string"],  // 例: ["NDVI","LAI"]
      "constraints": ["string"]        // 例: ["雲被りに弱い"]
    }
  ],
  "capability_summary": {
    "can": [
      "圃場レベルのNDVIトレンド監視（>10m GSD, 5日再訪で週次把握）",
      "干ばつストレスの面的把握（NDVI/NDWIの偏差で早期検知）"
    ],
    "cannot": [
      "雲量>60%での連続監視（光学のみでは欠測が多い）",
      "地表温度の高頻度取得（LST衛星の再訪が不足）"
    ]
  }
}

[capability_summaryの書き方]
- can：目的・測れるもの・条件（GSD/再訪/指標・しきい値）が一文に入ること。
  例：「圃場の乾燥ストレス早期検知（NDVI偏差-0.1以下を3日以上継続でアラート）」
- cannot：理由を必ず添える（雲被り/再訪不足/スペクトル不足/地上検証必須など）。
  例：「作物別の病害種別判定（分光解像度不足・教師データ不足）」
- “曖昧語（高頻度・広域）”は禁止。数値で書く。

# ユースケース入力
{{usecase_json}}
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
