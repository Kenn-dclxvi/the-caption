from unittest.mock import MagicMock

from src.app.renderer.report_monthly import MonthlyRenderer
from src.app.renderer.view_models import SummaryViewModel
from src.lib.models import LedgerSummary


def _v4_monthly_data() -> dict:
    return {
        "chronicle": {
            "title": "静かな構造転換",
            "overview": "一ヶ月の潮流を鑑定します。",
            "structural_change": "ABSOLUTE_AMOUNTは市場要因から切り離して扱います。",
            "shield_review": "防壁は中立に機能しました。",
        },
        "meta": {
            "year_month": "2026-04",
            "ledger_days": 30,
            "total_change_jpy": 12000,
            "total_change_pct": 1.5,
            "asset_class_trends": [
                {
                    "source": "MARKET_UNITS",
                    "asset_class": "US_STOCK",
                    "end_value_jpy": 120000,
                    "change_jpy": 20000,
                    "end_share_pct": 66.67,
                },
                {
                    "source": "ABSOLUTE_AMOUNT",
                    "asset_class": "CASH",
                    "end_value_jpy": 60000,
                    "change_jpy": 10000,
                    "end_share_pct": 33.33,
                },
            ],
        },
    }


def _summary_vm() -> SummaryViewModel:
    return SummaryViewModel(
        LedgerSummary(
            total_assets_jpy=1_000_000,
            total_profit_loss_jpy=100_000,
            cash_position_jpy=100_000,
            total_diff_jpy=10_000,
            total_diff_pct=1.0,
            total_profit_loss_pct=10.0,
            invested_capital_jpy=900_000,
            capital_gain_jpy=100_000,
            exposure_jpy=800_000,
            iron_bank_jpy=200_000,
            safe_ratio_pct=20.0,
            damper_coef=0.8,
        )
    )


def test_render_v4_monthly_chronicle_uses_slate_symphony_template() -> None:
    renderer = MonthlyRenderer()
    renderer.render_safe_ratio_section = MagicMock(return_value="<div>Safe Ratio</div>")

    html = renderer.render_v4(
        _v4_monthly_data()
    )

    assert "V4 Monthly Chronicle / 2026-04" in html
    assert "静かな構造転換" in html
    assert "Market Regime" in html
    assert "Portfolio Movement" in html
    assert "Portfolio Audit" in html
    assert "MARKET_UNITS / 66.67% / +20,000 JPY" in html
    assert "ABSOLUTE_AMOUNT / 33.33% / +10,000 JPY" in html
    assert "font-weight:300" in html
    assert "margin-bottom:60px" in html
    assert "Safe Ratio" not in html
    assert "Iron Bank" not in html
    assert "Total Return" not in html
    renderer.render_safe_ratio_section.assert_not_called()


def test_render_v4_monthly_chronicle_shows_safe_ratio_metrics_when_summary_present() -> None:
    renderer = MonthlyRenderer()

    html = renderer.render_v4(_v4_monthly_data(), _summary_vm())

    assert "Safe Ratio" in html
    assert "Exposure" in html
    assert "Iron Bank" in html
    assert "20.0%" in html
    assert "800,000" in html
    assert "200,000" in html
    assert "Total Return" in html
    assert _summary_vm().fmt_total_pl in html
