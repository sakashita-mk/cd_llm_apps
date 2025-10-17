# tab1_usecase.py
import json, streamlit as st
from uc_seed import UC_DATA

SYSTEM_PROMPT = r"""
あなたはPwC-CDP準拠の衛星リモートセンシング専門家です。
以下のユースケースのために、①「衛星のみのセンサ構成」と ②「その構成でできること／できないこと」を JSON **のみ**で出力してください。
**空欄やプレースホルダ（"string"）は禁止**。必ず具体名と数値を埋めること。

# 制約
- 非衛星（UAV/HAPS/ドローン/IoT/行政DB 等）は**絶対に含めない**。
- 末尾カンマ、コメント、コードフェンス、説明文は**禁止**。
- 既知の実衛星のみを用いる：{Sentinel-1, Sentinel-2, Landsat-8, Landsat-9, Terra/MODIS, Aqua/MODIS, VIIRS, ALOS-2, PlanetScope, WorldView-3, SMAP}
- sensor_suite は **少なくとも3件**。
- capability_summary の can / cannot は **各3件以上**。各行に**条件の数値**（例：10 m, 5 days, 290 km, NDVI<-0.1）を入れる。

# 出力スキーマ（固定）
{
  "sensor_suite": [
    {
      "name": "実衛星名",             // 例: "Sentinel-2A/B"
      "platform": "LEO|SSO|GEO",
      "bands": ["VNIR","SWIR","TIR","C-SAR","L-SAR" など],
      "gsd_m": 10.0,
      "revisit_days": 5.0,
      "swath_km": 290.0,
      "typical_products": ["NDVI","NDWI","LST" など],
      "constraints": ["雲被りに弱い" など]
    }
  ],
  "capability_summary": {
    "can": [
      "例: NDVIトレンドの週次監視（10 m, 5日再訪, 290 kmスワス）",
      "例: 干ばつ早期検知（NDVI偏差<-0.1を連続3日で警戒）",
      "例: 冠水面の面的把握（C-SAR, 10 m, 昼夜観測）"
    ],
    "cannot": [
      "例: 雲量>60%地域での連続監視（光学は欠測多発, 代替: SAR）",
      "例: 病害種別同定（分光分解能/教師データ不足）",
      "例: 日次LSTマップの安定取得（TIR再訪不足＋雲影響）"
    ]
  }
}

# ユースケース入力
{usecase_json}
"""

# --- ここから追記：人が読めるレンダリング ---
data = st.session_state.get("tab1_json") or parsed  # 既存セッション保存のキー名に合わせて調整
suite = data.get("sensor_suite", [])
caps  = data.get("capability_summary", {})

# ① センサ構成テーブル
if suite:
    st.markdown("#### ① 衛星センサ構成（衛星のみ）")
    import pandas as pd
    df = pd.DataFrame([
        {
            "衛星名": s.get("name",""),
            "軌道": s.get("platform",""),
            "バンド": ", ".join(s.get("bands", [])),
            "GSD(m)": s.get("gsd_m",""),
            "再訪(日)": s.get("revisit_days",""),
            "スワス(km)": s.get("swath_km",""),
            "代表プロダクト": ", ".join(s.get("typical_products", [])),
            "制約": ", ".join(s.get("constraints", [])),
        } for s in suite
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)

# ② できること / できないこと
st.markdown("#### ② 衛星のみで**できること / できないこと**")
can = caps.get("can", [])
cannot = caps.get("cannot", [])
col1, col2 = st.columns(2)
with col1:
    st.markdown("**できること（can）**")
    if can:
        for it in can:
            st.markdown(f"- {it}")
    else:
        st.caption("（モデル出力なし）")
with col2:
    st.markdown("**できないこと（cannot）**")
    if cannot:
        for it in cannot:
            st.markdown(f"- {it}")
    else:
        st.caption("（モデル出力なし）")
# --- 追記ここまで ---


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
