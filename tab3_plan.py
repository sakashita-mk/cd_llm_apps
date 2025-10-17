# tab3_plan.py
import json
import re
import streamlit as st
import pandas as pd

# =========================
# 1) プロンプト：JSONのみ / 統合案スキーマ固定
# =========================
SYSTEM_PROMPT = r"""
あなたは空間データや衛星リモートセンシングの専門家です。
入力（Tab1=衛星のみ構成, Tab2=GAP分析）を読み、GAPを埋めて目的を満たす**統合方針（衛星+UAV/HAPS+地上補完+融合設計）**を設計し、**JSONのみ**で出力してください。
説明文・前置き・コードフェンスは禁止。

# 出力スキーマ（固定）
{
  "constellation": [
    {
      "name": "実衛星名（例: Sentinel-2, Sentinel-1, VIIRS, ALOS-2, WorldView-3 など）",
      "type": "光学|SAR|熱|マイクロ波",
      "band": "VNIR/SWIR|C-SAR|L-SAR|TIR など",
      "gsd_m": 10,
      "revisit_days": 5,
      "role": "役割（例: 植生/土壌水分/冠水/LST/夜間観測 等）",
      "why": "採用理由（数値含む）"
    }
  ],
  "aerial_layer": [
    {
      "name": "UAV|HAPS",
      "platform": "例: quadcopter|fixed-wing|Zephyr等",
      "altitude_m": 2000,
      "endurance_h": 8,
      "gsd_cm": 5,
      "coverage_km2_per_day": 50,
      "role": "衛星の欠測補完/高分解能検証 等",
      "why": "採用理由（欠測率/天候/再訪の数値根拠）"
    }
  ],
  "ground_layer": [
    {
      "name": "地上補完",
      "sensors": ["雨量計","土壌水分センサ","気温/湿度ロガー"],
      "sampling": "地点数/頻度（例: 50点, 10分間隔）",
      "role": "衛星/航空の較正・検証（QA/QC）",
      "why": "閾値/誤差許容の数値根拠"
    }
  ],
  "fusion_design": {
    "data_flow": ["衛星→クラウド→解析→ダッシュボード", "UAV→地上局→クラウド など"],
    "processing": ["NDVI/NDWI/LST計算", "SAR干渉/後方散乱変化", "欠測補間（合成・時空間）"],
    "quality": ["地上観測とのバイアス補正", "雲/影/異常値のフラグ付け"]
  },
  "gap_closures": [
    {
      "axis": "観測頻度|空間分解能|観測範囲|コスト",
      "gap_level": "大|中|小",
      "approach": "採る対策（例: SAR併用/複数衛星合成/HAPSスポット/UAV臨時等）",
      "effect": "期待改善（数値: 日, m, km, % など）"
    }
  ],
  "monthly_cost_estimate": {
    "satellite": "例：0〜20万円/月（オープン＋必要時の商用タスク）",
    "aerial": "例：スポット出動 30〜80万円/月（変動）",
    "ground": "例：機器レンタル + 通信 5〜15万円/月",
    "cloud_processing": "例：5〜15万円/月",
    "total": "例：〜120万円/月"
  },
  "risks_and_mitigations": [
    {"risk": "雲量>60%で光学欠測", "mitigation": "SAR/夜間観測/合成"},
    {"risk": "UAV運航制限（風/許認可）", "mitigation": "HAPS/衛星合成へフォールバック"}
  ],
  "phased_roadmap": [
    {"phase": "P0", "months": "0-1", "scope": "PoC準備：パイプライン雛形/データ接続/地上設置"},
    {"phase": "P1", "months": "2-4", "scope": "対象地域で試行：指標算出・欠測補間・QA/QC"},
    {"phase": "P2", "months": "5-8", "scope": "HAPS/UAVスポット運用・商用衛星の必要時タスク"},
    {"phase": "GA", "months": "9+", "scope": "運用化：月額上限内での最適運用/運航計画の自動化"}
  ]
}
"rationale": {
  "overview": "全体方針（例: 雲被りリスクをSARとHAPSで補完する統合設計）",
  "satellite_choice": "衛星構成をこうした理由（例: 再訪頻度・解像度・コストバランス）",
  "aerial_choice": "UAV/HAPS層を加えた理由（例: 曇天時の光学欠測補完・高分解能検証）",
  "ground_choice": "地上観測を含めた理由（例: バイアス補正・QA/QC向上）",
  "fusion_design_choice": "融合設計をこうした理由（例: NDVI/LST統合解析・欠測補間の必要性）",
  "cost_strategy": "コスト設計の意図（例: 月額上限120万円をターゲットに、商用衛星は必要時タスク化）",
  "risk_policy": "リスク対応方針（例: 曇天時フォールバック・冗長構成）"
}
"""

# =========================
# 2) 軽量サニタイザ & パーサ（Tab2と同等）
# =========================
def _strip_code_fences(s: str) -> str:
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", s.strip(), flags=re.IGNORECASE|re.MULTILINE)

def _fix_trailing_commas(s: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", s)

def _normalize_scalars(s: str) -> str:
    s = re.sub(r"\bTrue\b", "true", s)
    s = re.sub(r"\bFalse\b", "false", s)
    s = re.sub(r"\bNone\b", "null", s)
    return s

def _slice_first_json_block(s: str) -> str:
    start = s.find("{")
    end = s.rfind("}")
    return s[start:end+1] if start != -1 and end != -1 and end > start else s

def _safe_parse_json(raw: str) -> dict:
    raw = _strip_code_fences(raw)
    raw = _slice_first_json_block(raw)
    try:
        return json.loads(raw)
    except Exception:
        cleaned = _normalize_scalars(_fix_trailing_commas(raw))
        return json.loads(cleaned)

# =========================
# 3) Groq 呼び出し
# =========================
def _call_llm(client, model: str, payload: dict):
    if client is None:
        return None, "Groq APIキー未設定"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}
    ]
    try:
        if hasattr(client, "chat_completions"):
            resp = client.chat_completions.create(model=model, messages=messages, temperature=0.2, max_tokens=2200)
        else:
            resp = client.chat.completions.create(model=model, messages=messages, temperature=0.2, max_tokens=2200)
        raw = resp.choices[0].message.content or ""
        data = _safe_parse_json(raw)
        return data, None
    except Exception as e:
        err = f"JSON解析失敗: {e}"
        return None, f"{err}\nRaw: {str(raw)[:700]}..." if 'raw' in locals() else err

# =========================
# 4) レンダリング（表×3 + 補完策 + コスト + リスク + ロードマップ）
# =========================
st.markdown("#### 🎯 構成方針の背景と意図")
rat = data.get("rationale", {}) or {}
if rat:
    st.markdown(f"**全体方針:** {rat.get('overview','')}")
    st.markdown(f"**衛星構成:** {rat.get('satellite_choice','')}")
    st.markdown(f"**航空層:** {rat.get('aerial_choice','')}")
    st.markdown(f"**地上層:** {rat.get('ground_choice','')}")
    st.markdown(f"**融合設計:** {rat.get('fusion_design_choice','')}")
    st.markdown(f"**コスト設計:** {rat.get('cost_strategy','')}")
    st.markdown(f"**リスク方針:** {rat.get('risk_policy','')}")
else:
    st.caption("（構成意図なし）")
  
def _render_plan_readable(data: dict):
    st.markdown("#### 🛰 衛星コンステレーション（改良案）")
    const = data.get("constellation", []) or []
    if const:
        df = pd.DataFrame([{
            "衛星": c.get("name",""),
            "タイプ": c.get("type",""),
            "バンド": c.get("band",""),
            "GSD(m)": c.get("gsd_m",""),
            "再訪(日)": c.get("revisit_days",""),
            "役割": c.get("role",""),
            "理由": c.get("why",""),
        } for c in const])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.caption("（無し）")

    st.markdown("#### ✈️ 航空レイヤ（UAV/HAPS）")
    aerial = data.get("aerial_layer", []) or []
    if aerial:
        df = pd.DataFrame([{
            "名称": a.get("name",""),
            "プラットフォーム": a.get("platform",""),
            "高度(m)": a.get("altitude_m",""),
            "滞空(h)": a.get("endurance_h",""),
            "GSD(cm)": a.get("gsd_cm",""),
            "日量カバー(km²)": a.get("coverage_km2_per_day",""),
            "役割": a.get("role",""),
            "理由": a.get("why",""),
        } for a in aerial])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.caption("（無し）")

    st.markdown("#### 🌱 地上レイヤ（検証・補完）")
    ground = data.get("ground_layer", []) or []
    if ground:
        df = pd.DataFrame([{
            "名称": g.get("name",""),
            "センサ": ", ".join(g.get("sensors", []) or []),
            "サンプリング": g.get("sampling",""),
            "役割": g.get("role",""),
            "理由": g.get("why",""),
        } for g in ground])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.caption("（無し）")

    st.markdown("#### 🔗 融合設計（データフロー / 処理 / 品質）")
    fus = data.get("fusion_design", {}) or {}
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**データフロー**")
        for t in fus.get("data_flow", []) or []: st.markdown(f"- {t}")
    with col2:
        st.markdown("**処理**")
        for t in fus.get("processing", []) or []: st.markdown(f"- {t}")
    with col3:
        st.markdown("**品質(QA/QC)**")
        for t in fus.get("quality", []) or []: st.markdown(f"- {t}")

    st.markdown("#### 🧩 GAPへの対応（軸ごと）")
    gaps = data.get("gap_closures", []) or []
    if gaps:
        df = pd.DataFrame([{
            "軸": g.get("axis",""),
            "ギャップ": g.get("gap_level",""),
            "対策": g.get("approach",""),
            "期待改善": g.get("effect",""),
        } for g in gaps])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.caption("（無し）")

    st.markdown("#### 💰 月額コスト見積（目安）")
    cost = data.get("monthly_cost_estimate", {}) or {}
    if cost:
        df = pd.DataFrame([{
            "項目": k, "目安": v
        } for k, v in cost.items()])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.caption("（無し）")

    st.markdown("#### ⚠️ リスクと対策")
    rsk = data.get("risks_and_mitigations", []) or []
    for item in rsk:
        st.markdown(f"- **{item.get('risk','')}** → 対策: {item.get('mitigation','')}")

    st.markdown("#### 🗺 ロードマップ")
    road = data.get("phased_roadmap", []) or []
    for p in road:
        st.markdown(f"- **{p.get('phase','')} ({p.get('months','')})**: {p.get('scope','')}")

    # JSONプレビューは畳み
    with st.expander("現在のTab3 JSON（構成方針）", expanded=False):
        st.json(data, expanded=False)

# =========================
# 5) エントリポイント
# =========================
def render_tab(client, model, tab1_json, tab2_json):
    st.subheader("③ 構成方針提示（統合案）")

    if not tab1_json or not tab2_json:
        st.info("まずは『① ユースケース定義』『② GAP分析』を実行してください。")
        return

    if st.button("構成方針を生成", type="primary", use_container_width=True):
        payload = {
            "tab1_output": tab1_json,
            "tab2_output": tab2_json
        }
        with st.spinner("Groqに問い合わせ中…"):
            data, err = _call_llm(client, model, payload)
        if err:
            st.error(err)
        else:
            st.session_state["tab3_json"] = data
            st.success("Tab3 JSON を保存しました。")

    if st.session_state.get("tab3_json"):
        _render_plan_readable(st.session_state["tab3_json"])
