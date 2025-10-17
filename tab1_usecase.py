# tab1_usecase.py
import json, streamlit as st
from uc_seed import UC_DATA

SYSTEM_PROMPT = """あなたは衛星リモートセンシングと保険数理の専門家です。
以下のスキーマの**有効なJSONのみ**を返してください（前後の説明やコードブロックは不要）。

{
  "usecase": "ユースケース名",
  "kpi": "観測目的や評価KPI",
  "context": {
    "background": "背景",
    "question": "顧客の問い",
    "issues": "現状の課題"
  },
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

def _call_llm(client, model, payload):
    if client is None:
        return None, "Groq APIキー未設定"
    messages = [
        {"role":"system","content": SYSTEM_PROMPT},
        {"role":"user","content": json.dumps(payload, ensure_ascii=False)}
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

    # 1) UC選択
    uc = st.selectbox(
        "ユースケース",
        list(UC_DATA.keys()),
        index=1  # デフォルトは農業保険
    )

    # 2) ハードコード値をフォームに展開（編集可）
    seed = UC_DATA[uc]
    with st.expander("📌 背景・顧客の問い・現状の課題（画像表をハードコード）", expanded=True):
        bg = st.text_area("背景", seed["background"])
        qn = st.text_area("顧客の問い", seed["question"])
        isu = st.text_area("現状の課題", seed["issues"])

    kpi = st.text_area("観測目的/KPI", "被害推定の即時性・空間精度の向上 など")

    # 3) 生成ボタン
    if st.button("センサ構成を生成"):
        payload = {
            "usecase": uc,
            "kpi": kpi,
            "context": {"background": bg, "question": qn, "issues": isu},
            # 任意：前提条件を少し与えるとブレにくい
            "current_stack": {
                "satellites": [],
                "non_sat": [],
                "assumptions": ["国内外データの実運用を意識した提案を希望"]
            }
        }
        data, err = _call_llm(client, model, payload)
        if err:
            st.error(err); return
        st.session_state["tab1_json"] = data
        st.success("Tab1 JSON を保存しました。")
        st.json(data)

    # 4) 現在値の表示
    if st.session_state.get("tab1_json"):
        st.caption("現在のTab1 JSON")
        st.json(st.session_state["tab1_json"])
