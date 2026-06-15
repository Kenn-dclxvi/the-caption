from unittest.mock import patch

from src.lib.models import LedgerSummary, Position
from src.app.renderer.report_fortress import FortressRenderer
from src.app.renderer.view_models import PositionViewModel, SummaryViewModel


def _make_summary(**overrides) -> LedgerSummary:
    defaults = dict(
        total_assets_jpy=5_000_000,
        total_profit_loss_jpy=500_000,
        cash_position_jpy=200_000,
        total_diff_jpy=1_000,
        total_diff_pct=0.20,
        total_profit_loss_pct=10.0,
        invested_capital_jpy=4_500_000,
        capital_gain_jpy=300_000,
    )
    defaults.update(overrides)
    return LedgerSummary(**defaults)


def _make_position(**overrides) -> Position:
    defaults = dict(
        id="p1",
        name="TEST FUND",
        raw_name="test",
        asset_class="US_STOCK",
        category="AGGREGATED",
        quantity=10.0,
        unit_price=100.0,
        current_price=110.0,
        currency="USD",
        value_jpy=1_100_000,
        acquisition_price=1_000_000,
        profit_loss=100_000,
        profit_loss_pct=10.0,
        prev_day_diff_jpy=12_345,
        prev_day_diff_pct=0.67,
        is_nisa=False,
        is_specific=True,
        share=10.0,
        wtd="+0.10%",
        mtd="+0.20%",
        ytd="+0.30%",
    )
    defaults.update(overrides)
    return Position(**defaults)


def test_render_fortress_shows_asset_day_amount_and_pct():
    fake_template = type(
        "FakeTemplate",
        (),
        {"render": lambda self, **kwargs: self.template},
    )()

    with patch("src.app.renderer.report_fortress.Template") as mock_template:
        mock_template.return_value = fake_template
        fake_template.template = ""

        renderer = FortressRenderer()
        renderer.render_vm(
            SummaryViewModel(_make_summary()),
            [PositionViewModel(_make_position())],
        )

        template_source = mock_template.call_args[0][0]

    assert "DAY</span>&nbsp;&nbsp;{{ a.fmt_diff_jpy }}" in template_source
    assert "/</span> {{ a.fmt_diff_pct }}" in template_source
