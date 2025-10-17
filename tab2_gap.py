# tab2_gap.py
import json
import re
import streamlit as st
import pandas as pd

# =========================================
# 0) 仮説目的（ハードコーディング）※編集可
# =========================================
PURPOSE_HYPOTHESIS = (
    "干ばつ・低温等の気象ストレスを、圃場レベル（~10m）で3日以内に面的検知し、"
    "欠測率を20%未満に抑えたうえで、保険金仮査定を7日以内に自動化したい。"
)

# =========================================
# 1) プロンプト：JSONのみ / 具体数値 / 目的→To-Be→Gap
# =========================================
SYSTEM_PROMPT = r"""
あなたはPwC-CDP準拠のGAP分析アナリストです。
入力（Tab1の衛星のみ構成JSON と goal）を読み、目的達成に必要な **To-Be観測要件** を定義し、
現状（As-Is=Tab1）との **GAP** を4軸で定量化し、**JSONのみ**で出力してください。
説明・前置き・コードフェンスは禁止。

# 分析軸（固定）
- 観測頻度（revisit）
- 空間分解能（gsd）
- 観測範囲（swath / 面積 / 雲量条件）
- コスト（**月額の予算上限（円）**）

# 出力スキーマ（固定）
{
  "goal": "入力goalを要約（1文）",
  "to_be_requirements": {
    "revisit_days": "数値 + 条件（例：<=3日, 雲量<40%）",
    "gsd_m": "数値条件（例：<=10m）",
    "coverage": "面積や流域など（例：対象流域全体, スワス>=250km）",
    "reliability": "欠測率や雲量など（例：欠測率<20%）",
    "cost": "月額の上限（例：<=500,000円/月 など）",
    "indicators": ["使用指標（例：NDVI, NDWI, LST など）"]
  },
  "dimensions": [
    {
      "axis": "観測頻度|空間分解能|観測範囲|コスト",
      "current": "As-Is（Sentinel-2:5日, 10m, 290km 等）",
      "target": "To-Be（<=3日, <=10m, 流域全体 等）",
      "gap": "大|中|小",
      "reason": "根拠（数値を含める）",
      "risk": "影響（検知遅延, 欠測率, コスト超過 等）",
      "mitigation": "軽減策（SAR併用, 合成, 複数衛星, 地上補完 等）"
    }
  ]
}

# ルール
- 各フィールドに**少なくとも1つ以上の数値**（m, 日, km, %, 円 など）を入れる。
- dimensions は **4件すべて**（順不同可）。
- 非衛星（UAV/HAPS/IoT/行政DBなど）はここでは提案しない（Tab3で扱う）。
"""

# =========================================
# 2) 軽量サニタイザ & パーサ（LLM出力救済）
# =========================================
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

# =========================================
# 3) Groq呼び出し（OpenAI互換：新旧両方に対応）
# =========================================
def _call_llm(client, model: str, payload: dict):
    if client is None:
        return None, "Groq APIキー未設定"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}
    ]

    try:
        if hasattr(client, "chat_completions"):
            resp = client.chat_completions.create(model=model, messages=messages, temperature=0.2, max_tokens=2000)
        else:
            resp = client.chat.completions.create(model=model, messages=messages, temperature=0.2, max_tokens=2000)
        raw = resp.choices[0].message.content or ""
        data = _safe_parse_json(raw)
        return data, None
    except Exception as e:
        err = f"JSON解析失敗: {e}"
        return None, f"{err}\nRaw: {str(raw)[:700]}..." if 'raw' in locals() else err

# =========================================
# 4) レンダリング（目的・To-Be・GAP表・Top3）
# =========================================
def _render_gap_readable(data: dict):
    tobe = data.get("to_be_requirements", {}) or {}
    dims = data.get("dimensions", []) or []


    st.markdown("#### 目的（To-Beに反映）")
    st.write(data.get("goal", "（モデル出力なし）"))

    st.markdown("#### To-Be観測要件（LLM推定）")
    tobe_rows = [{
        "観測頻度（revisit_days）": tobe.get("revisit_days",""),
        "空間分解能（gsd_m）": tobe.get("gsd_m",""),
        "観測範囲（coverage）": tobe.get("coverage",""),
        "信頼性（reliability）": tobe.get("reliability",""),
        "コスト（cost）": tobe.get("cost",""),
        "指標（indicators）": ", ".join(tobe.get("indicators", []) or [])
    }]
    st.dataframe(pd.DataFrame(tobe_rows), use_container_width=True, hide_index=True)

    st.markdown("#### ギャップ一覧（4軸）")
    if dims:
        df = pd.DataFrame([{
            "軸": d.get("axis",""),
            "現状": d.get("current",""),
            "目標": d.get("target",""),
            "ギャップ": d.get("gap",""),
            "根拠": d.get("reason",""),
            "リスク": d.get("risk",""),
            "軽減策": d.get("mitigation",""),
        } for d in dims])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.warning("dimensions が空でした。プロンプト/トークン長を見直してください。")

    st.markdown("#### 優先GAP（Top3）")
    if top3:
        for i, g in enumerate(top3, 1):
            st.markdown(
                f"**{i}. {g.get('axis', '')}** — 影響: {g.get('impact','')} / "
                f"理由: {g.get('why','')} / Quick win: {g.get('quick_win', False)}"
            )
    else:
        st.caption("（モデル出力なし）")

    with st.expander("現在のTab2 JSON（GAP分析）", expanded=False):
        st.json(data, expanded=False)

# =========================================
# 5) エントリポイント
# =========================================
def render_tab(client, model, tab1_json):
    st.subheader("② GAP分析（目的→To-Be→差分）")

    if not tab1_json:
        st.info("まずは『① ユースケース定義』でセンサ構成を生成してください。")
        return

    # 目的：仮説を初期値にしてユーザーが編集可能
    st.markdown("#### このユースケースで実現したいこと（目的）")
    default_goal = st.session_state.get("tab2_goal", PURPOSE_HYPOTHESIS)
    goal = st.text_area("目的（編集可）", value=default_goal, height=80, help="To-Be観測要件の導出に使います。")
    st.session_state["tab2_goal"] = goal

    if st.button("GAP分析を実行", type="primary", use_container_width=True):
        payload = {"tab1_output": tab1_json, "goal": goal}
        with st.spinner("Groqに問い合わせ中…"):
            data, err = _call_llm(client, model, payload)
        if err:
            st.error(err)
        else:
            st.session_state["tab2_json"] = data
            st.success("Tab2 JSON を保存しました。")

    if st.session_state.get("tab2_json"):
        _render_gap_readable(st.session_state["tab2_json"])
