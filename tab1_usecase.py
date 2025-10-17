# tab1_usecase.py
import json
import re
import streamlit as st
from uc_seed import UC_DATA

# ============================
# 1) プロンプト（中身を必ず埋める・数値を入れる・実衛星限定）
# ============================
SYSTEM_PROMPT = r"""
あなたは衛星リモートセンシング専門家です。
以下のユースケースのために、①「衛星のみのセンサ構成」と ②「その構成でできること／できないこと」を JSON **のみ**で出力してください。
**空欄やプレースホルダ（"string"）は禁止**。必ず具体名と数値を埋めること。

# 制約
- 非衛星（UAV/HAPS/ドローン/IoT/行政DB 等）は**絶対に含めない**。
- 末尾カンマ、コメント、コードフェンス、説明文は**禁止**。
- 既知の実衛星のみを用いる：{Sentinel-1, Sentinel-2, Landsat-8, Landsat-9, Terra/MODIS, Aqua/MODIS, VIIRS, ALOS-2, PlanetScope, WorldView-3, SMAP}
- sensor_suite は **少なくとも3件**。
- capability_summary の can / cannot は **各5件以上**。各行に**少なくとも2つ以上の数値**（GSD/再訪/しきい値/スワス/雲量% など）を必ず含める。
- 次のフォーマットで書く（日本語、1行1要素）：
  - can: 「<やること>（指標=<指標>, しきい値=<数値>, 解像度=<m>, 再訪=<日>, 対応面積=<km²> など）」 
  - cannot: 「<できない理由>（制約=<原因>, 回避策=<代替手段>, 閾値/条件=<数値>）」
- “高頻度・広域・高精度”等の**曖昧語禁止**。必ず数値で条件を入れる。

# 出力スキーマ（固定）
{
  "sensor_suite": [
    {
      "name": "実衛星名",
      "platform": "LEO|SSO|GEO",
      "bands": ["VNIR","SWIR","TIR","C-SAR","L-SAR"],
      "gsd_m": 10.0,
      "revisit_days": 5.0,
      "swath_km": 290.0,
      "typical_products": ["NDVI","NDWI","LST"],
      "constraints": ["雲被りに弱い"]
    }
  ],
  "capability_summary": {
    "can": [
      "NDVIトレンドの週次監視（10 m, 5日再訪, 290 kmスワス）",
      "干ばつ早期検知（NDVI偏差<-0.1を連続3日で警戒）",
      "冠水面の面的把握（C-SAR, 10 m, 昼夜観測）"
    ],
    "cannot": [
      "雲量>60%地域での連続監視（光学は欠測多発, 代替: SAR）",
      "病害種別同定（分光分解能/教師データ不足）",
      "日次LSTマップの安定取得（TIR再訪不足＋雲影響）"
    ]
  }
}

# ユースケース入力
{usecase_json}
"""

# ============================
# 2) JSONサニタイズ & パース（軽量版）
# ============================
def _strip_code_fences(s: str) -> str:
    # ```json ... ``` / ``` ... ``` を除去
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", s.strip(), flags=re.IGNORECASE|re.MULTILINE)

def _fix_trailing_commas(s: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", s)

def _normalize_scalars(s: str) -> str:
    s = re.sub(r"\bTrue\b", "true", s)
    s = re.sub(r"\bFalse\b", "false", s)
    s = re.sub(r"\bNone\b", "null", s)
    return s

def _safe_parse_json(raw: str) -> dict:
    """
    LLMのゆるJSONをできるだけ救う軽量版。
    """
    raw = _strip_code_fences(raw)
    try:
        return json.loads(raw)
    except Exception:
        try:
            return json.loads(_normalize_scalars(_fix_trailing_commas(raw)))
        except Exception as e:
            raise ValueError(f"JSON解析失敗: {e}\nRaw: {raw[:800]}...")

# ============================
# 3) 旧→新スキーマの正規化（互換）
# ============================
def _normalize_tab1_dict(data: dict) -> dict:
    """
    新スキーマ（sensor_suite/capability_summary）に正規化。
    旧スキーマ（satellite_stack/capabilities_sat_only/limitations_sat_only）にも対応。
    """
    data = data or {}
    if "sensor_suite" in data and "capability_summary" in data:
        return data  # 既に新スキーマ

    # 旧 -> 新（最低限のフィールド移送）
    sensors = []
    if "satellite_stack" in data:
        sats = (data.get("satellite_stack") or {}).get("satellites", []) or []
        for s in sats:
            bands = s.get("bands")
            if not bands:
                b = s.get("band")
                bands = [b] if isinstance(b, str) and b else []
            sensors.append({
                "name": s.get("name", ""),
                "platform": s.get("orbit", ""),
                "bands": bands,
                "gsd_m": s.get("gsd_m", None),
                "revisit_days": s.get("revisit_days", None),
                "swath_km": s.get("swath_km", None),
                "typical_products": s.get("typical_products", []),
                "constraints": list(filter(None, [s.get("role",""), s.get("why","")]))
            })

    capability_summary = {
        "can": data.get("capabilities_sat_only", []) or [],
        "cannot": data.get("limitations_sat_only", []) or []
    }

    return {
        "sensor_suite": sensors,
        "capability_summary": capability_summary
    }

# ============================
# 4) Groq 呼び出し（OpenAI互換クライアントで両系に対応）
# ============================
def _call_llm(client, model: str, payload: dict):
    if client is None:
        return None, "Groq APIキー未設定"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}
    ]

    # openai==1.51+ の chat_completions.create 互換 & 旧 .chat.completions.create 両対応
    if hasattr(client, "chat_completions"):
        resp = client.chat_completions.create(model=model, messages=messages, temperature=0.2, max_tokens=1600)
    else:
        resp = client.chat.completions.create(model=model, messages=messages, temperature=0.2, max_tokens=1600)

    raw = resp.choices[0].message.content or ""
    try:
        parsed = _safe_parse_json(raw)
        normalized = _normalize_tab1_dict(parsed)
        normalized = _apply_quick_facts_corrections(normalized)
        return normalized, None
    except Exception as e:
        return None, str(e)

# --- 追記: 既知センサのクイック補正（事実の下限ガード） ---
def _apply_quick_facts_corrections(data: dict) -> dict:
    facts = {
        "Sentinel-2": {
            "platform": "SSO", "gsd_m": 10, "revisit_days": 5, "swath_km": 290,
            "bands": ["VNIR","SWIR"], "typical_products": ["NDVI","NDWI","EVI"]
        },
        "SMAP": {
            "platform": "SSO", "gsd_m": 36000, "revisit_days": 3, "swath_km": 1000,
            "bands": ["L-Microwave"], "typical_products": ["土壌水分"]
        },
        "VIIRS": {
            "platform": "SSO", "gsd_m": 750, "revisit_days": 1, "swath_km": 3000,
            "bands": ["VNIR","SWIR","TIR"], "typical_products": ["NDVI","LST","雲・火災検知"]
        },
        "Sentinel-1": {
            "platform": "SSO", "gsd_m": 10, "revisit_days": 6, "swath_km": 250,
            "bands": ["C-SAR"], "typical_products": ["冠水検知","土壌水分 proxy"]
        },
        "ALOS-2": {
            "platform": "SSO", "gsd_m": 3, "revisit_days": 14, "swath_km": 50,
            "bands": ["L-SAR"], "typical_products": ["地表変動","森林構造"]
        },
    }

    suite = (data or {}).get("sensor_suite", [])
    for s in suite:
        n = (s.get("name") or "").strip()
        # ゆらぎ対策（例: "Sentinel-2A/B", "SMAP Mission"）
        key = next((k for k in facts.keys() if k.lower() in n.lower()), None)
        if not key:
            continue
        f = facts[key]
        # 既存値が明らかに不合理なときだけ上書き（Noneや0/異常値）
        s["platform"] = f.get("platform", s.get("platform"))
        if not s.get("bands"): s["bands"] = f.get("bands")
        if not s.get("typical_products"): s["typical_products"] = f.get("typical_products")
        try:
            if not s.get("gsd_m") or float(s["gsd_m"]) < 1 or float(s["gsd_m"]) > 100000: s["gsd_m"] = f["gsd_m"]
            if not s.get("revisit_days") or float(s["revisit_days"]) <= 0 or float(s["revisit_days"]) > 60: s["revisit_days"] = f["revisit_days"]
            if not s.get("swath_km") or float(s["swath_km"]) <= 0 or float(s["swath_km"]) > 5000: s["swath_km"] = f["swath_km"]
        except Exception:
            # 数値でない場合も補正
            s["gsd_m"] = f["gsd_m"]
            s["revisit_days"] = f["revisit_days"]
            s["swath_km"] = f["swath_km"]
    return data
  

# ============================
# 5) 人間可読レンダリング（テーブル＋箇条書き＋畳みJSON）
# ============================
def _render_tab1_readable(data: dict):
    import pandas as pd

    data = _normalize_tab1_dict(data)
    suite = data.get("sensor_suite", []) or []
    caps = data.get("capability_summary", {}) or {}
    can = caps.get("can", []) or []
    cannot = caps.get("cannot", []) or []

    # ① センサ構成テーブル
    st.markdown("#### ① 衛星センサ構成（衛星のみ）")
    if suite:
        df = pd.DataFrame([{
            "衛星名": s.get("name",""),
            "軌道": s.get("platform",""),
            "バンド": ", ".join([b for b in (s.get("bands") or []) if b]),
            "GSD(m)": s.get("gsd_m",""),
            "再訪(日)": s.get("revisit_days",""),
            "スワス(km)": s.get("swath_km",""),
            "代表プロダクト": ", ".join(s.get("typical_products", []) or []),
            "制約": ", ".join(s.get("constraints", []) or []),
        } for s in suite])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.warning("センサ構成（sensor_suite）が空です。プロンプトやトークン長を見直してください。")

    # ② できる / できない
    st.markdown("#### ② 衛星のみで **できること / できないこと**")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**できること（can）**")
        if can:
            for it in can: st.markdown(f"- {it}")
        else:
            st.caption("（モデル出力なし）")
    with col2:
        st.markdown("**できないこと（cannot）**")
        if cannot:
            for it in cannot: st.markdown(f"- {it}")
        else:
            st.caption("（モデル出力なし）")

    # JSONプレビュー（畳み）
    with st.expander("現在のTab1 JSON（衛星のみ）", expanded=False):
        st.json(data, expanded=False)

# ============================
# 6) エントリポイント（既存 app.py から呼ばれる）
# ============================
def render_tab(client, model):
    st.subheader("① ユースケース定義 → 衛星（のみ）センサ構成")

    # 入力UI
    uc = st.selectbox("ユースケース", list(UC_DATA.keys()), index=1)
    seed = UC_DATA[uc]
    with st.expander("📌 背景・顧客の問い・現状の課題", expanded=True):
        bg = st.text_area("背景", seed["background"])
        qn = st.text_area("顧客の問い", seed["question"])
        isu = st.text_area("現状の課題", seed["issues"])

    # 生成ボタン
    if st.button("衛星センサ構成を生成", type="primary", use_container_width=True):
        payload = {"usecase": uc, "context": {"background": bg, "question": qn, "issues": isu}}
        with st.spinner("Groqに問い合わせ中…"):
            data, err = _call_llm(client, model, payload)
        if err:
            st.error(err)
        else:
            st.session_state["tab1_json"] = data
            st.success("Tab1 JSON を保存しました。")
            #_render_tab1_readable(st.session_state["tab1_json"])

    # セッションに前回結果があれば表示
    if st.session_state.get("tab1_json"):
        # ユーザーが生成ボタンを押さなくても、常に最新状態を見せる
        _render_tab1_readable(st.session_state["tab1_json"])
