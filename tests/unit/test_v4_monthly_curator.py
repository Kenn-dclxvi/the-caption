import importlib.util
import json
import re
from pathlib import Path
from unittest.mock import patch

from src.domain.ledger_schema import ShadowAssetRecord, ShadowLedger
from src.domain.monthly_curator import (
    MonthlyCurator,
    V4ChronicleBannedWordsViolation,
    V4ChronicleSchemaViolation,
)


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
    "type": "object",
    "required": ["chronicle", "meta"],
    "chronicle": {
        "title": "title",
        "monthly_summary": "monthly_summary",
        "market_causality": "market_causality",
        "phase_analysis": [],
        "asset_contribution": [],
        "portfolio_audit": "portfolio_audit",
        "next_month_watch": [],
    },
    "meta": {
        "dominant_regime": "dominant_regime",
        "primary_causality": "primary_causality",
        "fx_impact": "fx_impact",
        "risk_temperature": "risk_temperature",
        "data_quality": "data_quality",
    }
}

_MONTHLY_CHRONICLE_BANNED_WORDS = [
    "静観",
    "様子見",
    "一旦",
    "と思われる",
    "一喜一憂",
    "検討",
    "見守り",
    "ホールド",
    "距離を置く",
]


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
                "monthly_summary": "月間の潮流を総括します。",
                "market_causality": "市場要因はMARKET_UNITSに限定します。",
                "phase_analysis": ["月央にVIXが落ち着きました。"],
                "asset_contribution": ["US_STOCKが寄与しました。"],
                "portfolio_audit": "現金は家計側の構造変化として扱います。",
                "next_month_watch": ["VIX水準の継続観測"],
            },
            "meta": {
                "dominant_regime": "CALM",
                "primary_causality": "TECH_DRIVEN",
                "fx_impact": "NEUTRAL",
                "risk_temperature": "LOW",
                "data_quality": "OK",
            },
        }
    )


def test_generate_v4_chronicle_aggregates_dynamic_and_static_sources() -> None:
    with patch("src.domain.monthly_curator.LlmTransporter") as mock_transporter_cls, \
            patch("src.domain.monthly_curator.PROMPT_CHRONICLE_SYSTEM_V4", _PROMPT_CHRONICLE_SYSTEM_V4), \
            patch("src.domain.monthly_curator.OUTPUT_SCHEMA_CHRONICLE_V4", _OUTPUT_SCHEMA_CHRONICLE_V4):
        transporter = mock_transporter_cls.return_value
        transporter.request_intelligence.return_value = _response()
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
            market_snapshots=[
                {
                    "target_date": "2026-04-15",
                    "us_market": {"trading_date": "2026-04-14", "is_holiday": False},
                    "market_summary": "S&P500: +0.10% | VIX: 18.00",
                }
            ],
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
    market_snapshot_summary = result["meta"]["market_snapshot_summary"]
    assert market_snapshot_summary["snapshot_days"] == 1
    assert market_snapshot_summary["daily_market_summaries"][0]["us_trading_date"] == "2026-04-14"
    assert market_snapshot_summary["daily_market_summaries"][0]["market_observations"]["indices"]["S&P500"] == {
        "change_pct": 0.1
    }
    assert market_snapshot_summary["daily_market_summaries"][0]["market_observations"]["vix"] == {
        "level": 18.0,
        "change": None,
    }

    transporter.request_intelligence.assert_called_once()
    prompt = transporter.request_intelligence.call_args[0][0]
    assert _PROMPT_CHRONICLE_SYSTEM_V4 in prompt
    assert '<focus area="ABSOLUTE_AMOUNT">' in prompt
    assert "市場因果とは切り離し" in prompt
    assert json.dumps(_OUTPUT_SCHEMA_CHRONICLE_V4, ensure_ascii=False, indent=2) in prompt
    assert "<daily_insights>" in prompt
    assert "<daily_context_summary>" in prompt
    assert "<monthly_trend_data>" in prompt
    assert "<market_snapshot_summary>" in prompt
    assert "<output_schema>" in prompt
    assert "MARKET_UNITS" in prompt
    assert "ABSOLUTE_AMOUNT" in prompt
    assert "Daily insight body" in prompt
    assert "state_distribution" in prompt


def test_generate_v4_chronicle_uses_request_intelligence() -> None:
    with patch("src.domain.monthly_curator.LlmTransporter") as mock_transporter_cls, \
            patch("src.domain.monthly_curator.PROMPT_CHRONICLE_SYSTEM_V4", _PROMPT_CHRONICLE_SYSTEM_V4), \
            patch("src.domain.monthly_curator.OUTPUT_SCHEMA_CHRONICLE_V4", _OUTPUT_SCHEMA_CHRONICLE_V4):
        transporter = mock_transporter_cls.return_value
        transporter.request_intelligence.return_value = f"[JSON_START]{_response()}[JSON_END]"
        curator = MonthlyCurator()

        result = curator.generate_v4_chronicle(
            "2026-04",
            shadow_ledgers=[_ledger("01", 100_000, 50_000), _ledger("30", 120_000, 60_000)],
            insights=[],
        )

    assert result["chronicle"]["portfolio_audit"] == "現金は家計側の構造変化として扱います。"
    transporter.request_intelligence.assert_called_once()
    fallback_prompt = transporter.request_intelligence.call_args[0][0]
    assert "<role>Chronicle Aggregator" in fallback_prompt
    assert "<monthly_trend_data>" in fallback_prompt
    assert "<market_snapshot_summary>" in fallback_prompt
    assert '<focus area="ABSOLUTE_AMOUNT">' in fallback_prompt


def test_generate_v4_chronicle_uses_daily_metrics_total_path_without_ledger_trend() -> None:
    with patch("src.domain.monthly_curator.LlmTransporter") as mock_transporter_cls, \
            patch("src.domain.monthly_curator.PROMPT_CHRONICLE_SYSTEM_V4", _PROMPT_CHRONICLE_SYSTEM_V4), \
            patch("src.domain.monthly_curator.OUTPUT_SCHEMA_CHRONICLE_V4", _OUTPUT_SCHEMA_CHRONICLE_V4):
        transporter = mock_transporter_cls.return_value
        transporter.request_intelligence.return_value = _response()
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


def test_generate_v4_chronicle_summarizes_market_snapshot_boundaries() -> None:
    with patch("src.domain.monthly_curator.LlmTransporter") as mock_transporter_cls, \
            patch("src.domain.monthly_curator.PROMPT_CHRONICLE_SYSTEM_V4", _PROMPT_CHRONICLE_SYSTEM_V4), \
            patch("src.domain.monthly_curator.OUTPUT_SCHEMA_CHRONICLE_V4", _OUTPUT_SCHEMA_CHRONICLE_V4):
        transporter = mock_transporter_cls.return_value
        transporter.request_intelligence.return_value = _response()
        curator = MonthlyCurator()

        result = curator.generate_v4_chronicle(
            "2026-04",
            shadow_ledgers=[],
            insights=[],
            market_snapshots=[
                {
                    "target_date": "2026-04-01",
                    "us_market": {"trading_date": "2026-03-31", "is_holiday": False},
                    "market_summary": (
                        "S&P500: +1.18% | NASDAQ100: +1.81% | SOX: +2.04% | "
                        "米10年債: 4.26% (-0.04) | USD/JPY: 159.21 (-0.29%) | VIX: 18.36 (-0.76)"
                    ),
                },
                {
                    "target_date": "2026-04-02",
                    "us_market": {"trading_date": "2026-04-01", "is_holiday": True},
                    "market_summary": "",
                },
                {
                    "target_date": "2026-04-03",
                    "us_market": "closed",
                    "market_summary": "USD/JPY: unavailable | VIX: 17.50",
                },
            ],
        )

    summary = result["meta"]["market_snapshot_summary"]
    assert summary["snapshot_days"] == 3
    assert summary["holiday_days"] == ["2026-04-02"]
    assert summary["missing_summary_days"] == ["2026-04-02"]

    first_observations = summary["daily_market_summaries"][0]["market_observations"]
    assert first_observations["indices"] == {
        "S&P500": {"change_pct": 1.18},
        "NASDAQ100": {"change_pct": 1.81},
        "SOX": {"change_pct": 2.04},
    }
    assert first_observations["us_10y_yield"] == {"yield_pct": 4.26, "change": -0.04}
    assert first_observations["usd_jpy"] == {"rate": 159.21, "change_pct": -0.29}
    assert first_observations["vix"] == {"level": 18.36, "change": -0.76}

    missing_observations = summary["daily_market_summaries"][1]["market_observations"]
    assert missing_observations == {
        "indices": {},
        "us_10y_yield": None,
        "usd_jpy": None,
        "vix": None,
    }

    non_dict_us_market = summary["daily_market_summaries"][2]
    assert non_dict_us_market["us_trading_date"] == ""
    assert non_dict_us_market["is_holiday"] is False
    assert non_dict_us_market["market_observations"]["usd_jpy"] is None
    assert non_dict_us_market["market_observations"]["vix"] == {"level": 17.5, "change": None}


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
    assert "market_snapshot_summary" in prompt
    assert "next_month_watchは翌月の予測ではない" in prompt
    assert "固定主語として強制してはならない" in prompt
    assert "検討" in prompt

    prompts_module = _load_real_prompts_module()
    assert "検討" not in prompts_module.CURATOR_BANNED_WORDS
    assert "検討" in prompts_module.MONTHLY_CHRONICLE_BANNED_WORDS


def test_generate_v4_chronicle_prefers_ledger_trend_over_daily_metrics_total_path() -> None:
    with patch("src.domain.monthly_curator.LlmTransporter") as mock_transporter_cls, \
            patch("src.domain.monthly_curator.PROMPT_CHRONICLE_SYSTEM_V4", _PROMPT_CHRONICLE_SYSTEM_V4), \
            patch("src.domain.monthly_curator.OUTPUT_SCHEMA_CHRONICLE_V4", _OUTPUT_SCHEMA_CHRONICLE_V4):
        transporter = mock_transporter_cls.return_value
        transporter.request_intelligence.return_value = _response()
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


def test_generate_v4_chronicle_rejects_schema_mismatch() -> None:
    with patch("src.domain.monthly_curator.LlmTransporter") as mock_transporter_cls, \
            patch("src.domain.monthly_curator.PROMPT_CHRONICLE_SYSTEM_V4", _PROMPT_CHRONICLE_SYSTEM_V4), \
            patch("src.domain.monthly_curator.OUTPUT_SCHEMA_CHRONICLE_V4", _OUTPUT_SCHEMA_CHRONICLE_V4):
        transporter = mock_transporter_cls.return_value
        transporter.request_intelligence.return_value = json.dumps({
            "chronicle": {
                "title": "構造転換",
                "monthly_summary": "総括",
                "market_causality": "因果",
                "phase_analysis": "文字列は不可",
                "asset_contribution": [],
                "portfolio_audit": "監査",
                "next_month_watch": [],
            },
            "meta": {
                "dominant_regime": "CALM",
                "primary_causality": "TECH_DRIVEN",
                "fx_impact": "NEUTRAL",
                "risk_temperature": "LOW",
                "data_quality": "OK",
            },
        })
        curator = MonthlyCurator()

        try:
            curator.generate_v4_chronicle("2026-04", shadow_ledgers=[], insights=[])
        except V4ChronicleSchemaViolation as exc:
            assert "chronicle.phase_analysis type mismatch" in str(exc)
        else:
            raise AssertionError("schema mismatch was not rejected")


def test_generate_v4_chronicle_rejects_banned_words() -> None:
    with patch("src.domain.monthly_curator.LlmTransporter") as mock_transporter_cls, \
            patch("src.domain.monthly_curator.PROMPT_CHRONICLE_SYSTEM_V4", _PROMPT_CHRONICLE_SYSTEM_V4), \
            patch("src.domain.monthly_curator.OUTPUT_SCHEMA_CHRONICLE_V4", _OUTPUT_SCHEMA_CHRONICLE_V4), \
            patch("src.domain.monthly_curator.MONTHLY_CHRONICLE_BANNED_WORDS", _MONTHLY_CHRONICLE_BANNED_WORDS):
        transporter = mock_transporter_cls.return_value
        payload = json.loads(_response())
        payload["chronicle"]["portfolio_audit"] = "様子見を続けます。"
        transporter.request_intelligence.return_value = json.dumps(payload, ensure_ascii=False)
        curator = MonthlyCurator()

        try:
            curator.generate_v4_chronicle("2026-04", shadow_ledgers=[], insights=[])
        except V4ChronicleBannedWordsViolation as exc:
            assert "Action Ban Violation" in str(exc)
            assert "様子見" in str(exc)
        else:
            raise AssertionError("banned word was not rejected")
