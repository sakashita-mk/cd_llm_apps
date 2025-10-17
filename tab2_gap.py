# tab2_gap.py
import json
import re
import streamlit as st
import pandas as pd

# =========================================
# 1) プロンプト：JSONのみ / 具体数値 / 軸を固定
# =========================================
SYSTEM_PROMPT = r"""
あなたはGAP分析アナリストです。
入力（Tab1の衛星のみ構成JSON）を読み、観測体制のGAPを4軸で定量的に評価し、JSONのみで出力してください。
説明文・コードフェンス・スキーマ例・前置きは禁止。**JSONのみ**を返すこと。

# 分析軸（固定）
- 観測頻度（revisit）
- 空間分解能（gsd）
- 観測範囲（swath / 面積 / 雲量条件）
- コスト（概算：相対的なOPEX/CAPEX感度）

# 出力スキーマ（固定）
{
  "gap_summary": "短い要約（1-2文）",
  "dimensions": [
    {
      "axis": "観測頻度|空間分解能|観測範囲|コスト",
      "current": "例: 再訪6-14日 / 10m / スワス290km / 年間OPEX X",
      "target": "例: 1-3日 / 1-3m / 流域全体 / コストY以下 など",
      "gap": "大|中|小",
      "reason": "ギャップの根拠（数値を必ず含める。例: 雲量>60%地域では欠測多発、TIRは再訪>5日 等）",
      "risk": "影響（検知遅延, 欠測率, コスト超過 等）",
      "mitigation": "軽減策（SAR併用, 合成, 複数衛星, 地上補完 等）"
    }
  ],
  "priority_gaps_top3": [
    {
      "axis": "観測頻度|空間分解能|観測範囲|コスト",
      "why": "優先理由（数値を1つ以上含める）",
      "impact": "顧客価値への影響",
      "quick_win": true
    }
  ]
}

# ルール
- 各フィールドに**少なくとも1つ以上の数値**（m, 日, km, %, 件など）を入れる。
- dimensions は **4件すべて**出す（順不同可）。
- priority_gaps_top3 は **3件**。quick_win は boolean。
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
    """先頭の { .. 最後の } までを抜き出す（説明文が混ざるケース対策）"""
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
            resp = client.chat_completions.create(model=model, messages=messages, temperature=0.2, max_tokens=1800)
        else:
            resp = client.chat.completions.create(model=model, messages=messages, temperature=0.2, max_tokens=1800)
        raw = resp.choices[0].message.content or ""
        data = _safe_parse_json(raw)
        return data, None
    except Exception as e:
        # なるべくRawを見たいので先頭だけ付ける
        err = f"JSON解析失敗: {e}"
        return None, f"{err}\nRaw: {str(raw)[:700]}..." if 'raw' in locals() else err

# =========================================
# 4) レンダリング（表 + 優先GAP）
# =========================================
def _render_gap_readable(data: dict):
    dims = data.get("dimensions", []) or []
    top3 = data.get("priority_gaps_top3", []) or []

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
        st.warning("dimensions が空でした。プロンプトやトークン長を見直してください。")

    st.markdown("#### 優先GAP（Top3）")
    if top3:
        for i, g in enumerate(top3, 1):
            st.markdown(
                f"**{i}. {g.get('axis', '')}** — 影響: {g.get('impact','')} / "
                f"理由: {g.get('why','')} / Quick win: {g.get('quick_win', False)}"
            )
    else:
        st.caption("（モデル出力なし）")

    # JSONプレビューは畳み
    with st.expander("現在のTab2 JSON（GAP分析）", expanded=False):
        st.json(data, expanded=False)

# =========================================
# 5) エントリポイント（app.py から呼ばれる）
# =========================================
def render_tab(client, model, tab1_json):
    st.subheader("② GAP分析（頻度 / 分解能 / 範囲 / コスト）")

    if not tab1_json:
        st.info("まずは『① ユースケース定義』でセンサ構成を生成してください。")
        return

    if st.button("GAP分析を実行", type="primary", use_container_width=True):
        payload = {
            "tab1_output": tab1_json  # そのまま渡す（LLM側で読む）
        }
        with st.spinner("Groqに問い合わせ中…"):
            data, err = _call_llm(client, model, payload)
        if err:
            st.error(err)
        else:
            st.session_state["tab2_json"] = data
            st.success("Tab2 JSON を保存しました。")

    # 既存結果があれば表示
    if st.session_state.get("tab2_json"):
        _render_gap_readable(st.session_state["tab2_json"])
