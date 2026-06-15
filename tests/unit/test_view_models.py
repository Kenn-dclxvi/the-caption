from src.lib.models import Position, LedgerSummary
from src.app.renderer.view_models import (
    PositionViewModel,
    SummaryViewModel,
    CollectionPositionViewModel,
    CollectionSummaryViewModel,
    CollectionSectionViewModel,
)

_C_GOLD = "#c5a059"
_C_INK  = "#1e293b"
_C_SLATE = "#64748b"


def _make_position(**overrides) -> Position:
    defaults = dict(
        id="p1", name="TEST FUND", raw_name="test",
        asset_class="US_STOCK", category="INDIVIDUAL",
        quantity=10.0, unit_price=100.0, current_price=110.0,
        currency="USD", value_jpy=1_100_000, acquisition_price=1_000_000,
        profit_loss=100_000, profit_loss_pct=10.0,
        prev_day_diff_jpy=5_000, prev_day_diff_pct=0.45,
        is_nisa=False, is_specific=True,
    )
    defaults.update(overrides)
    return Position(**defaults)


def _make_summary(**overrides) -> LedgerSummary:
    defaults = dict(
        total_assets_jpy=5_000_000, total_profit_loss_jpy=500_000,
        cash_position_jpy=200_000, total_diff_jpy=10_000,
        total_diff_pct=0.20, total_profit_loss_pct=10.0,
        invested_capital_jpy=4_500_000, capital_gain_jpy=300_000,
    )
    defaults.update(overrides)
    return LedgerSummary(**defaults)


class TestPositionViewModel:
    def test_label_aggregated_known_class(self):
        pos = _make_position(category="AGGREGATED", asset_class="US_STOCK")
        assert PositionViewModel(pos).label == "US STOCKS"

    def test_label_aggregated_unknown_class(self):
        pos = _make_position(category="AGGREGATED", asset_class="UNKNOWN")
        assert PositionViewModel(pos).label == "UNKNOWN"

    def test_label_non_aggregated(self):
        pos = _make_position(category="INDIVIDUAL", name="My Fund")
        assert PositionViewModel(pos).label == "My Fund"

    def test_fmt_value(self):
        pos = _make_position(value_jpy=1_234_567)
        assert PositionViewModel(pos).fmt_value == "1,234,567"

    def test_fmt_diff_jpy_positive(self):
        pos = _make_position(prev_day_diff_jpy=12_345)
        assert PositionViewModel(pos).fmt_diff_jpy == "+12,345"

    def test_fmt_diff_jpy_negative(self):
        pos = _make_position(prev_day_diff_jpy=-5_000)
        assert PositionViewModel(pos).fmt_diff_jpy == "-5,000"

    def test_fmt_diff_pct_positive(self):
        pos = _make_position(prev_day_diff_pct=1.23)
        assert PositionViewModel(pos).fmt_diff_pct == "+1.23%"

    def test_fmt_diff_pct_negative(self):
        pos = _make_position(prev_day_diff_pct=-0.5)
        assert PositionViewModel(pos).fmt_diff_pct == "-0.50%"

    def test_is_cash_short_term(self):
        pos = _make_position(asset_class="SHORT_TERM")
        assert PositionViewModel(pos).is_cash is True

    def test_is_cash_cash_equivalents(self):
        pos = _make_position(asset_class="CASH_EQUIVALENTS")
        assert PositionViewModel(pos).is_cash is True

    def test_is_cash_false(self):
        pos = _make_position(asset_class="US_STOCK")
        assert PositionViewModel(pos).is_cash is False

    def test_metrics_display_style_hidden(self):
        pos = _make_position(asset_class="SHORT_TERM")
        assert PositionViewModel(pos).metrics_display_style == "display: none;"

    def test_metrics_display_style_visible(self):
        pos = _make_position(asset_class="US_STOCK")
        assert PositionViewModel(pos).metrics_display_style == "display: block;"


class TestSummaryViewModel:
    def test_fmt_total_assets(self):
        s = _make_summary(total_assets_jpy=5_000_000)
        assert SummaryViewModel(s).fmt_total_assets == "5,000,000"

    def test_fmt_total_pl_positive(self):
        s = _make_summary(capital_gain_jpy=300_000)
        assert SummaryViewModel(s).fmt_total_pl == "+300,000"

    def test_fmt_total_pl_negative(self):
        s = _make_summary(capital_gain_jpy=-50_000)
        assert SummaryViewModel(s).fmt_total_pl == "-50,000"

    def test_fmt_weekly_range_normal(self):
        s = _make_summary(weekly_low=4_800_000, weekly_high=5_100_000)
        assert SummaryViewModel(s).fmt_weekly_range == "4,800,000 - 5,100,000"

    def test_fmt_weekly_range_zero(self):
        s = _make_summary(weekly_high=0, weekly_low=0)
        assert SummaryViewModel(s).fmt_weekly_range == "---"

    def test_gold_share_normal(self):
        s = _make_summary(capital_gain_jpy=50_000, exposure_jpy=100_000)
        assert SummaryViewModel(s).gold_share == 50.0

    def test_gold_share_capped_at_100(self):
        s = _make_summary(capital_gain_jpy=200_000, exposure_jpy=100_000)
        assert SummaryViewModel(s).gold_share == 100.0

    def test_gold_share_zero_pl(self):
        s = _make_summary(capital_gain_jpy=0, exposure_jpy=100_000)
        assert SummaryViewModel(s).gold_share == 0.0

    def test_gold_share_zero_exposure(self):
        s = _make_summary(capital_gain_jpy=50_000, exposure_jpy=0)
        assert SummaryViewModel(s).gold_share == 0.0

    def test_is_profit_true(self):
        s = _make_summary(capital_gain_jpy=1)
        assert SummaryViewModel(s).is_profit is True

    def test_is_profit_false_zero(self):
        s = _make_summary(capital_gain_jpy=0)
        assert SummaryViewModel(s).is_profit is False

    def test_is_profit_false_negative(self):
        s = _make_summary(capital_gain_jpy=-1)
        assert SummaryViewModel(s).is_profit is False

    def test_total_pl_color_profit(self):
        s = _make_summary(capital_gain_jpy=1)
        assert SummaryViewModel(s).total_pl_color == _C_GOLD

    def test_total_pl_color_loss(self):
        s = _make_summary(capital_gain_jpy=-1)
        assert SummaryViewModel(s).total_pl_color == _C_INK

    def test_day_color_positive(self):
        s = _make_summary(total_diff_jpy=1)
        assert SummaryViewModel(s).day_color == _C_GOLD

    def test_day_color_negative(self):
        s = _make_summary(total_diff_jpy=-1)
        assert SummaryViewModel(s).day_color == _C_SLATE

    def test_day_color_zero(self):
        s = _make_summary(total_diff_jpy=0)
        assert SummaryViewModel(s).day_color == _C_INK


class TestCollectionPositionViewModel:
    def _make(self, **metrics):
        defaults = {
            "asset_class": "MUTUAL_FUNDS",
            "currency": "JPY",
            "current_value": 1_000_000.0, "diff_pct": 0.5,
            "m_pct": 1.2, "y_pct": 3.4, "share_pct": 10.0,
            "native_value": 1_000_000.0,
            "fx_rate": None,
        }
        defaults.update(metrics)
        return CollectionPositionViewModel("TEST FUND", defaults)

    def test_fmt_value(self):
        vm = self._make(current_value=2_345_678.9)
        assert vm.fmt_value == "2,345,678"

    def test_fmt_diff_pct_positive(self):
        vm = self._make(diff_pct=1.23)
        assert vm.fmt_diff_pct == "+1.23%"

    def test_fmt_diff_pct_negative(self):
        vm = self._make(diff_pct=-0.5)
        assert vm.fmt_diff_pct == "-0.50%"

    def test_fmt_diff_jpy_positive(self):
        vm = self._make(diff_val=12_345.0)
        assert vm.fmt_diff_jpy == "+12,345"

    def test_fmt_diff_jpy_negative(self):
        vm = self._make(diff_val=-5_000.0)
        assert vm.fmt_diff_jpy == "-5,000"

    def test_diff_color_positive(self):
        vm = self._make(diff_pct=0.1)
        assert vm.diff_color == _C_GOLD

    def test_diff_color_zero(self):
        vm = self._make(diff_pct=0.0)
        assert vm.diff_color == _C_INK

    def test_diff_color_negative(self):
        vm = self._make(diff_pct=-0.1)
        assert vm.diff_color == _C_INK

    def test_day_color_positive(self):
        vm = self._make(diff_pct=0.1)
        assert vm.day_color == _C_GOLD

    def test_day_color_negative(self):
        vm = self._make(diff_pct=-0.1)
        assert vm.day_color == _C_SLATE

    def test_day_is_positive_true(self):
        vm = self._make(diff_pct=0.01)
        assert vm.day_is_positive is True

    def test_day_is_positive_false_zero(self):
        vm = self._make(diff_pct=0.0)
        assert vm.day_is_positive is False

    def test_us_stock_primary_value_is_usd(self):
        vm = self._make(asset_class="US_STOCK", currency="USD", native_value=12_345.67)
        assert vm.fmt_value == "1,000,000"

    def test_us_fx_caption(self):
        vm = self._make(asset_class="US_STOCK", currency="USD", fx_rate=150.25)
        assert vm.fx_caption == "USD/JPY 150.25"

    def test_us_fmt_usd_value(self):
        vm = self._make(asset_class="US_STOCK", currency="USD", current_value=1_234_567.0)
        assert vm.fmt_usd_value == "1,000,000.00"

    def test_non_us_has_no_day_detail_line(self):
        vm = self._make()
        assert vm.has_day_detail_line is False

    def test_us_has_day_detail_line(self):
        vm = self._make(asset_class="US_STOCK", currency="USD")
        assert vm.has_day_detail_line is True


class TestCollectionSummaryViewModel:
    def _make(
        self,
        total_value: float = 1_000_000.0,
        total_diff_jpy: float = 10_000.0,
        total_diff_pct: float = 1.0,
        display_date: str = "2026-02-25",
        fx_rate: float | None = None,
        fx_date: str | None = None,
    ) -> CollectionSummaryViewModel:
        return CollectionSummaryViewModel(total_value, total_diff_jpy, total_diff_pct, display_date, fx_rate, fx_date)

    def test_fmt_total_value(self):
        vm = self._make(total_value=3_456_789.5)
        assert vm.fmt_total_value == "3,456,789"

    def test_fmt_total_diff_positive(self):
        vm = self._make(total_diff_jpy=12_345.0)
        assert vm.fmt_total_diff == "+12,345"

    def test_fmt_total_diff_negative(self):
        vm = self._make(total_diff_jpy=-5_000.0)
        assert vm.fmt_total_diff == "-5,000"

    def test_fmt_total_diff_zero(self):
        vm = self._make(total_diff_jpy=0.0)
        assert vm.fmt_total_diff == "+0"

    def test_total_diff_color_positive(self):
        vm = self._make(total_diff_jpy=1.0)
        assert vm.total_diff_color == _C_GOLD

    def test_total_diff_color_zero(self):
        vm = self._make(total_diff_jpy=0.0)
        assert vm.total_diff_color == _C_SLATE

    def test_day_color_positive(self):
        vm = self._make(total_diff_jpy=1.0)
        assert vm.day_color == _C_GOLD

    def test_day_color_negative(self):
        vm = self._make(total_diff_jpy=-1.0)
        assert vm.day_color == _C_SLATE

    def test_display_date(self):
        vm = self._make(display_date="2026-01-15")
        assert vm.display_date == "2026-01-15"

    def test_fx_reference_hidden_without_fx(self):
        vm = self._make()
        assert vm.has_fx_reference is False
        assert vm.fmt_fx_reference == ""

    def test_fx_reference_rendered(self):
        vm = self._make(fx_rate=150.25, fx_date="2026.02.25")
        assert vm.has_fx_reference is True
        assert vm.fmt_fx_reference == "USD/JPY 150.25 (2026.02.25)"


class TestCollectionSectionViewModel:
    def test_section_exposes_positions(self):
        pos = CollectionPositionViewModel("TEST FUND", {
            "asset_class": "MUTUAL_FUNDS",
            "currency": "JPY",
            "current_value": 1_000_000.0,
            "diff_val": 5_000.0,
            "diff_pct": 0.5,
            "m_pct": 1.2,
            "y_pct": 3.4,
            "share_pct": 10.0,
            "native_value": 1_000_000.0,
            "fx_rate": None,
        })
        vm = CollectionSectionViewModel("Funds", "MUTUAL_FUNDS", [pos])
        assert vm.title == "Funds"
        assert vm.key == "MUTUAL_FUNDS"
        assert vm.positions == [pos]
