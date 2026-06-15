import importlib.util
import json
import re
from pathlib import Path
from unittest.mock import patch

from src.domain.ledger_schema import ShadowAssetRecord, ShadowLedger
from src.domain.monthly_curator import MonthlyCurator


def _load_real_prompts_module():
    """実体の src/config/prompts.py を sys.modules のモックを介さず直接ロードする。

    tests/conftest.py が sys.modules["src.config.prompts"] を MagicMock に差し替えている
    ため、通常の import では実定数を取得できない。ここでは実ファイルを isolated に読み込み、
    sys.modules を汚さずに実定数 PROMPT_CHRONICLE_SYSTEM_V4 を検証する（patch はしない）。
    prompts.py は typing 以外を import しないため、副作用なくロードできる。
    """
    prompts_path = Path(__file__).resolve().parents[2] / "src" / "config" / "prompts.py"
    spec = importlib.util.spec_from_file_location("_real_src_config_prompts", prompts_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

_PROMPT_CHRONICLE_SYSTEM_V4 = """
<role>Chronicle Aggregator (System Agent)</role>
<analytical_focus>
  <focus area="MARKET_UNITS">長期的な潮流を特定せよ。</focus>
  <focus area="ABSOLUTE_AMOUNT">市場因果とは切り離し、家計・運用の構造的変化として解釈せよ。</focus>
</analytical_focus>
"""
_OUTPUT_SCHEMA_CHRONICLE_V4 = {
    "chronicle": {
        "title": "title",
        "overview": "overview",
        "structural_change": "structural_change",
        "shield_review": "shield_review",
    }
}


def _ledger(day: str, stock_value: float, cash_value: float) -> ShadowLedger:
    return ShadowLedger(
        target_date=f"2026-04-{day}",
        generated_at=f"2026-04-{day}T20:00:00",
        ssot_a_path="data/collection/market_units.csv",
        ssot_b_path="data/external_assets.json",
        ssot_b_active_key="2026-04",
        total_value_jpy=stock_value + cash_value,
        assets=[
            ShadowAssetRecord(
                source="MARKET_UNITS",
                name="US Equity",
                asset_class="US_STOCK",
                category="US_STOCK",
                currency="USD",
                units=10,
                price=100,
                fx_rate=150,
                current_value_jpy=stock_value,
                pricing_status="PRICED",
            ),
            ShadowAssetRecord(
                source="ABSOLUTE_AMOUNT",
                name="Cash",
                asset_class="CASH",
                category="CASH",
                current_value_jpy=cash_value,
                pricing_status="STATIC",
            ),
        ],
    )


def _response() -> str:
    return json.dumps(
        {
            "chronicle": {
                "title": "静かな構造転換",
                "overview": "月間の潮流を総括します。",
                "structural_change": "現金は家計側の構造変化として扱います。",
                "shield_review": "防壁は中立に機能しました。",
            }
        }
    )


def test_generate_v4_chronicle_aggregates_dynamic_and_static_sources() -> None:
    with patch("src.domain.monthly_curator.LlmTransporter") as mock_transporter_cls, \
            patch("src.domain.monthly_curator.PROMPT_CHRONICLE_SYSTEM_V4", _PROMPT_CHRONICLE_SYSTEM_V4), \
            patch("src.domain.monthly_curator.OUTPUT_SCHEMA_CHRONICLE_V4", _OUTPUT_SCHEMA_CHRONICLE_V4):
        transporter = mock_transporter_cls.return_value
        transporter.generate.return_value = _response()
        curator = MonthlyCurator()

        result = curator.generate_v4_chronicle(
            "2026-04",
            shadow_ledgers=[_ledger("01", 100_000, 50_000), _ledger("30", 120_000, 60_000)],
            insights=[{
                "date": "2026-04-15",
                "content": (
                    "## 2026-04-15\n"
                    "- **State**: WATCH | NYFANG / -0.54pt | WATCH / ADEQUATE / HIGH | NEUTRAL\n"
                    "- **Archive**: TECH_DRIVEN | CALM | MINOR | CALM | TECH_CONCENTRATION,LOW_VIX\n"
                    "- **Archive Note**: Daily insight body"
                ),
            }],
        )

    assert result["chronicle"]["title"] == "静かな構造転換"
    assert result["meta"]["ledger_days"] == 2
    assert result["meta"]["total_change_jpy"] == 30_000
    trends = result["meta"]["asset_class_trends"]
    assert {row["source"] for row in trends} == {"MARKET_UNITS", "ABSOLUTE_AMOUNT"}
    assert any(row["asset_class"] == "US_STOCK" and row["change_jpy"] == 20_000 for row in trends)
    assert any(row["asset_class"] == "CASH" and row["change_jpy"] == 10_000 for row in trends)
    daily_context = result["meta"]["daily_context_summary"]
    assert daily_context["state_distribution"] == {"WATCH": 1}
    assert daily_context["causal_vectors"] == {"TECH_DRIVEN": 1}
    assert daily_context["monthly_tags"]["TECH_CONCENTRATION"] == 1

    transporter.generate.assert_called_once()
    system_prompt, user_prompt, schema = transporter.generate.call_args[0]
    assert system_prompt == _PROMPT_CHRONICLE_SYSTEM_V4
    assert '<focus area="ABSOLUTE_AMOUNT">' in system_prompt
    assert "市場因果とは切り離し" in system_prompt
    assert schema == _OUTPUT_SCHEMA_CHRONICLE_V4
    assert "<daily_insights>" in user_prompt
    assert "<daily_context_summary>" in user_prompt
    assert "<monthly_trend_data>" in user_prompt
    assert "<output_schema>" in user_prompt
    assert "MARKET_UNITS" in user_prompt
    assert "ABSOLUTE_AMOUNT" in user_prompt
    assert "Daily insight body" in user_prompt
    assert "state_distribution" in user_prompt


def test_generate_v4_chronicle_falls_back_to_request_intelligence() -> None:
    with patch("src.domain.monthly_curator.LlmTransporter") as mock_transporter_cls, \
            patch("src.domain.monthly_curator.PROMPT_CHRONICLE_SYSTEM_V4", _PROMPT_CHRONICLE_SYSTEM_V4), \
            patch("src.domain.monthly_curator.OUTPUT_SCHEMA_CHRONICLE_V4", _OUTPUT_SCHEMA_CHRONICLE_V4):
        transporter = mock_transporter_cls.return_value
        del transporter.generate
        transporter.request_intelligence.return_value = f"[JSON_START]{_response()}[JSON_END]"
        curator = MonthlyCurator()

        result = curator.generate_v4_chronicle(
            "2026-04",
            shadow_ledgers=[_ledger("01", 100_000, 50_000), _ledger("30", 120_000, 60_000)],
            insights=[],
        )

    assert result["chronicle"]["shield_review"] == "防壁は中立に機能しました。"
    transporter.request_intelligence.assert_called_once()
    fallback_prompt = transporter.request_intelligence.call_args[0][0]
    assert "<role>Chronicle Aggregator" in fallback_prompt
    assert "<monthly_trend_data>" in fallback_prompt
    assert '<focus area="ABSOLUTE_AMOUNT">' in fallback_prompt


def test_generate_v4_chronicle_uses_daily_metrics_total_path_without_ledger_trend() -> None:
    with patch("src.domain.monthly_curator.LlmTransporter") as mock_transporter_cls, \
            patch("src.domain.monthly_curator.PROMPT_CHRONICLE_SYSTEM_V4", _PROMPT_CHRONICLE_SYSTEM_V4), \
            patch("src.domain.monthly_curator.OUTPUT_SCHEMA_CHRONICLE_V4", _OUTPUT_SCHEMA_CHRONICLE_V4):
        transporter = mock_transporter_cls.return_value
        transporter.generate.return_value = _response()
        curator = MonthlyCurator()

        result = curator.generate_v4_chronicle(
            "2026-04",
            shadow_ledgers=[],
            insights=[],
            daily_metrics=[
                {
                    "target_date": "2026-04-01",
                    "total_value_jpy": 1_000_000,
                    "market_units_value_jpy": 700_000,
                    "absolute_amount_value_jpy": 300_000,
                },
                {
                    "target_date": "2026-04-30",
                    "total_value_jpy": 1_150_000,
                    "market_units_value_jpy": 820_000,
                    "absolute_amount_value_jpy": 330_000,
                },
            ],
        )

    assert result["meta"]["ledger_days"] == 0
    assert result["meta"]["start_total_jpy"] == 1_000_000
    assert result["meta"]["end_total_jpy"] == 1_150_000
    assert result["meta"]["total_change_jpy"] == 150_000
    assert result["meta"]["total_change_pct"] == 15.0


# --- 本文③〜⑥ 1,000字カウント定義の検証（titleは枠外） ---
#
# カウント定義（docs/reference/prompts.md §3.4「1,000字カウント定義」と整合）:
#   - 対象は③〜⑥（titleは枠外）: ③monthly_summary
#            / ④market_causality + phase_analysis + asset_contribution
#            / ⑤portfolio_audit / ⑥next_month_watch
#   - ②title は1,000字カウントの枠外（対象外）。
#   - MonthlyRenderer.__html_text / __render_v4_list が生成するHTMLからタグを除去した
#     可読テキストを対象とする。
#   - 改行・空白、および __render_v4_list の区切り文字 " / " は数えない。
#   - ①KPIヘッダ・⑦フッタ・meta.* は対象外。

_TAG_RE = re.compile(r"<[^>]*>")


def _readable_len(chronicle: dict) -> int:
    """本文③〜⑥の可読テキストを 1,000字カウント定義に従って合計する（titleは枠外）。

    report_monthly.py の __html_text / __render_v4_list と整合する形で:
      - 文字列フィールド (title / monthly_summary / market_causality / portfolio_audit)
        は __html_text 相当（タグ除去後の素テキスト）。
      - リストフィールド (phase_analysis / asset_contribution / next_month_watch)
        は __render_v4_list 相当（各要素を結合し、dict 要素は " / " 連結）。
    最後にタグ除去・改行/空白/" / " 除外のうえ文字数を数える。
    """
    parts: list[str] = []
    # 対象は③〜⑥（titleは枠外）。②title は 1,000字カウント枠外のため合計対象に含めない。
    # ③ monthly_summary
    parts.append(str(chronicle.get("monthly_summary") or chronicle.get("overview", "")))
    # ④ market_causality + phase_analysis + asset_contribution
    parts.append(str(chronicle.get("market_causality", "")))
    for row in chronicle.get("phase_analysis", []):
        if isinstance(row, dict):
            parts.append(" / ".join(str(v) for v in row.values() if v not in (None, "")))
        else:
            parts.append(str(row))
    for row in chronicle.get("asset_contribution", []):
        if isinstance(row, dict):
            parts.append(" / ".join(str(v) for v in row.values() if v not in (None, "")))
        else:
            parts.append(str(row))
    # ⑤ portfolio_audit
    parts.append(str(chronicle.get("portfolio_audit") or chronicle.get("structural_change", "")))
    # ⑥ next_month_watch
    for row in chronicle.get("next_month_watch", []):
        if isinstance(row, dict):
            parts.append(" / ".join(str(v) for v in row.values() if v not in (None, "")))
        else:
            parts.append(str(row))

    joined = "".join(parts)
    # HTMLタグ除去
    joined = _TAG_RE.sub("", joined)
    # 区切り文字 " / " を除外
    joined = joined.replace(" / ", "")
    # 改行・空白（全角空白含む）を除外
    joined = re.sub(r"[\s　]", "", joined)
    return len(joined)


def test_v4_chronicle_body_within_1000_chars() -> None:
    # 各セクションを配分上限近辺の日本語テキストで埋めた固定サンプル
    # ③≤200 / ④≤400(3フィールド合計) / ⑤≤250 / ⑥≤150
    chronicle = {
        "title": "静かな構造転換の月",  # 1,000字カウント枠外
        "monthly_summary": "あ" * 195,  # ③ ≤200字
        "market_causality": "い" * 200,  # ④ 内訳1
        "phase_analysis": ["う" * 100],  # ④ 内訳2
        "asset_contribution": ["え" * 95],  # ④ 内訳3 → ④合計 395 ≤400
        "portfolio_audit": "お" * 245,  # ⑤ ≤250字
        "next_month_watch": ["か" * 50, "き" * 50, "く" * 45],  # ⑥ 145 ≤150（" / "は数えない）
    }

    total = _readable_len(chronicle)
    # ③195 + ④395 + ⑤245 + ⑥145 = 980 ≤ 1000
    assert total == 980
    assert total <= 1000


def test_v4_chronicle_count_excludes_separators_tags_and_whitespace() -> None:
    # 区切り文字 " / "・HTMLタグ・改行/空白がカウントから除外されることを検証
    chronicle = {
        "title": "見出し",  # 枠外
        "monthly_summary": "総括<br>本文\nテキスト",  # タグ・改行を除外 → 「総括本文テキスト」=8字
        "market_causality": "",
        "phase_analysis": [],
        "asset_contribution": [{"a": "寄与A", "b": "寄与B"}],  # " / "連結 → 区切りは数えない → 「寄与A寄与B」=6字
        "portfolio_audit": "  監査　文  ",  # 半角・全角空白を除外 → 「監査文」=3字
        "next_month_watch": ["注視 点"],  # 単独空白も除外 → 「注視点」=3字
    }
    # 8 + 6 + 3 + 3 = 20
    assert _readable_len(chronicle) == 20
    assert _readable_len(chronicle) <= 1000


def test_prompt_chronicle_system_v4_carries_length_constraints() -> None:
    """実定数 PROMPT_CHRONICLE_SYSTEM_V4（patchしない）が本文長制約の文言を保持していることを検証。

    既存の generate_v4_chronicle 系テストはダミー定数に patch しているため、実定数から
    制約文言が消えても検知できない。この回帰防止のため実定数を直接 assert する。
    部分一致のみで、配分値・カウント定義の意味は検証しない（脆くなりすぎないため）。
    """
    prompt = _load_real_prompts_module().PROMPT_CHRONICLE_SYSTEM_V4

    # 本文長制約（1,000字以内）の存在
    assert "1,000字" in prompt
    # 字数配分: ③≤200 / ④≤400 / ⑤≤250 / ⑥≤150
    assert "≤200字" in prompt
    assert "≤400字" in prompt
    assert "≤250字" in prompt
    assert "≤150字" in prompt
    # title は1,000字カウントの枠外である旨
    assert "枠外" in prompt
    # data_quality を本文に出さない旨
    assert "data_quality" in prompt
    assert "本文③〜⑥には出すな" in prompt


def test_generate_v4_chronicle_prefers_ledger_trend_over_daily_metrics_total_path() -> None:
    with patch("src.domain.monthly_curator.LlmTransporter") as mock_transporter_cls, \
            patch("src.domain.monthly_curator.PROMPT_CHRONICLE_SYSTEM_V4", _PROMPT_CHRONICLE_SYSTEM_V4), \
            patch("src.domain.monthly_curator.OUTPUT_SCHEMA_CHRONICLE_V4", _OUTPUT_SCHEMA_CHRONICLE_V4):
        transporter = mock_transporter_cls.return_value
        transporter.generate.return_value = _response()
        curator = MonthlyCurator()

        result = curator.generate_v4_chronicle(
            "2026-04",
            shadow_ledgers=[_ledger("01", 100_000, 50_000), _ledger("30", 120_000, 60_000)],
            insights=[],
            daily_metrics=[
                {
                    "target_date": "2026-04-01",
                    "total_value_jpy": 1_000_000,
                    "market_units_value_jpy": 700_000,
                    "absolute_amount_value_jpy": 300_000,
                },
                {
                    "target_date": "2026-04-30",
                    "total_value_jpy": 1_150_000,
                    "market_units_value_jpy": 820_000,
                    "absolute_amount_value_jpy": 330_000,
                },
            ],
        )

    assert result["meta"]["ledger_days"] == 2
    assert result["meta"]["total_change_jpy"] == 30_000
    assert result["meta"]["total_change_pct"] == 20.0
