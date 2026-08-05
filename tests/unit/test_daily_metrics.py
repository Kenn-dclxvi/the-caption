import json

import pytest

from src.domain.daily_metrics import build_daily_metrics
from src.domain.ledger_schema import ShadowAssetRecord, ShadowLedger
from src.domain.shadow_ledger_adapter import ShadowLedgerAdapter
from src.domain.universal_ingester import UniversalIngester
from src.infra.market_data import is_market_closed


def test_build_daily_metrics_separates_sources_and_counts_missing():
    ledger = ShadowLedger(
        target_date="2026-04-25",
        generated_at="2026-04-25T00:00:00",
        ssot_a_path="data/collection/market_units.csv",
        ssot_b_path="data/external_assets.json",
        ssot_b_active_key="2026-04",
        total_value_jpy=3500,
        return_base_value_jpy=1000,
        total_acquisition_cost_jpy=800,
        total_return_jpy=200,
        total_return_pct=25.0,
        assets=[
            ShadowAssetRecord(
                source="MARKET_UNITS",
                name="FundA",
                asset_class="MUTUAL_FUNDS",
                category="MUTUAL_FUNDS",
                current_value_jpy=1000,
                diff_val_jpy=50,
                diff_pct=5.0,
                pricing_status="PRICED",
            ),
            ShadowAssetRecord(
                source="MARKET_UNITS",
                name="FundB",
                asset_class="MUTUAL_FUNDS",
                category="MUTUAL_FUNDS",
                current_value_jpy=0,
                pricing_status="MISSING",
            ),
            ShadowAssetRecord(
                source="ABSOLUTE_AMOUNT",
                name="Cash",
                asset_class="CASH",
                category="CASH",
                current_value_jpy=2500,
                pricing_status="STATIC",
            ),
        ],
    )

    metrics = build_daily_metrics(ledger)

    assert metrics["schema_version"] == "v4.1-daily-metrics"
    assert metrics["target_date"] == "2026-04-25"
    assert metrics["total_value_jpy"] == 3500
    assert metrics["market_units_value_jpy"] == 1000
    assert metrics["absolute_amount_value_jpy"] == 2500
    assert metrics["return_base_value_jpy"] == 1000
    assert metrics["total_acquisition_cost_jpy"] == 800
    assert metrics["total_return_jpy"] == 200
    assert metrics["total_return_pct"] == 25.0
    assert metrics["pricing_missing_count"] == 1
    assert metrics["asset_count"] == 3
    assert metrics["market_units_count"] == 2
    assert metrics["absolute_amount_count"] == 1
    assert metrics["data_quality"] == {
        "has_assets": True,
        "has_positive_total": True,
        "has_missing_pricing": True,
        "has_stale_pricing": False,
    }
    assert metrics["top_movers"] == [
        {
            "name": "FundA",
            "source": "MARKET_UNITS",
            "asset_class": "MUTUAL_FUNDS",
            "current_value_jpy": 1000,
            "diff_val_jpy": 50,
            "diff_pct": 5.0,
            "pricing_status": "PRICED",
        }
    ]


# ---------------------------------------------------------------------------
# WTD boundary condition tests (TWRR geometric chain from previous Friday base)
#
# Fact data:
#   prev-Fri 2026-05-15: portfolio close 417.72  ← absolute WTD origin
#   Mon 2026-05-18: 404.35  DAY=-3.20%  WTD=-3.20%
#   Tue 2026-05-19: 395.95  DAY=-2.08%  WTD=-5.21%
#   Wed 2026-05-20: 392.61  DAY=-0.84%  WTD=-6.01%
#
# The fund history CSV uses NAV * 10000 per unit convention.
# With units=1 and scaled NAV the portfolio value equals NAV/10000.
# ---------------------------------------------------------------------------

def _make_wtd_fund_ingester(tmp_path):
    """Return a (tmp_path, UniversalIngester) configured for the WTD boundary test."""
    funds_csv = tmp_path / "funds.csv"
    external_json = tmp_path / "external_assets.json"
    history_dir = tmp_path / "history"
    history_dir.mkdir()

    # units=1, NAV column = portfolio_value * 10000 so current_value_jpy = nav/10000 * 1
    # prev-Fri:417.72, Mon:404.35, Tue:395.95, Wed:392.61
    funds_csv.write_text(
        "name,asset_class,currency,units,source_symbol,csv_url\n"
        "TSM,MUTUAL_FUNDS,JPY,1,TSM,\n",
        encoding="utf-8",
    )
    external_json.write_text(json.dumps({}), encoding="utf-8")

    # NAV values scaled ×10000 so current_value_jpy = nav/10000 * 1
    nav_rows = "\n".join([
        "基準日,基準価額",
        "2026-05-15,4177200",   # previous Friday  (417.72 × 10000)
        "2026-05-18,4043500",   # Monday           (404.35 × 10000)
        "2026-05-19,3959500",   # Tuesday          (395.95 × 10000)
        "2026-05-20,3926100",   # Wednesday        (392.61 × 10000)
    ])
    (history_dir / "TSM.csv").write_text(nav_rows + "\n", encoding="utf-8")

    ingester = UniversalIngester(
        funds_csv_path=str(funds_csv),
        external_assets_path=str(external_json),
        history_dir=str(history_dir),
        is_closed_fn=is_market_closed,
    )
    return ingester


def test_wtd_monday_equals_day_return(tmp_path):
    """On Monday the WTD origin is the previous Friday close; WTD == DAY return."""
    ingester = _make_wtd_fund_ingester(tmp_path)
    ledger = ingester.build_shadow_ledger("2026-05-18")
    record = next(r for r in ledger.assets if r.name == "TSM")
    # DAY = (404.35 - 417.72) / 417.72 = -3.20%
    assert record.wtd_pct == pytest.approx(-3.201, abs=0.01)


def test_wtd_tuesday_chains_from_friday_not_monday(tmp_path):
    """On Tuesday WTD must compound from Friday base, NOT reset to single-day DAY return.

    Regression guard: the accumulated WTD cache must not be overwritten by the
    Tuesday DAY return alone (-2.08%). Correct WTD from Friday base = -5.21%.
    """
    ingester = _make_wtd_fund_ingester(tmp_path)
    ledger = ingester.build_shadow_ledger("2026-05-19")
    record = next(r for r in ledger.assets if r.name == "TSM")
    # WTD from Friday base: (395.95 - 417.72) / 417.72 = -5.21%
    # Wrong (DAY reset): -2.08%
    assert record.wtd_pct == pytest.approx(-5.213, abs=0.01), (
        f"Tuesday WTD should be -5.21% (from Friday base), got {record.wtd_pct:.2f}%"
    )


def test_wtd_wednesday_geometric_chain_from_friday(tmp_path):
    """On Wednesday WTD from previous-Friday base must be -6.01% (geometric = simple)."""
    ingester = _make_wtd_fund_ingester(tmp_path)
    ledger = ingester.build_shadow_ledger("2026-05-20")
    record = next(r for r in ledger.assets if r.name == "TSM")
    assert record.wtd_pct == pytest.approx(-6.01, abs=0.01), (
        f"Wednesday WTD should be -6.01%, got {record.wtd_pct:.2f}%"
    )


def test_wtd_summary_wednesday_via_shadow_ledger_adapter(tmp_path):
    """End-to-end: ShadowLedgerAdapter total_wtd on Wednesday = -6.01%."""
    ingester = _make_wtd_fund_ingester(tmp_path)
    ledger = ingester.build_shadow_ledger("2026-05-20")
    canonical = ShadowLedgerAdapter().to_legacy_ledger(ledger)
    # total_wtd is a formatted string ("+X.XX%" convention)
    assert canonical.summary.total_wtd == "-6.01%", (
        f"total_wtd should be '-6.01%', got {canonical.summary.total_wtd!r}"
    )


# ---------------------------------------------------------------------------
# WTD boundary tests for US stocks (Date/Close, US market dates)
#
# For assets whose history CSV uses US market dates (US_STOCK, COMMODITIES),
# US Friday's close is first observed by the JP system on JP Monday — it is
# the FIRST day of the new JP week, not the WTD base.
#
# Fact data (matching real TSMC / production scenario):
#   prev-Thu 2026-05-14: 417.72  ← absolute WTD origin (last JP-week confirmed close)
#   prev-Fri 2026-05-15: 404.35  ← first observation of JP week (JP Mon morning)
#   cur-Mon  2026-05-18: 395.95
#   cur-Tue  2026-05-19: 392.61
#
# JP target dates: Mon 2026-05-18, Tue 2026-05-19, Wed 2026-05-20
# Each uses the most recent US close available at JP processing time.
#
# Correct TWRR chain from US-Thu 5/14 base (417.72):
#   JP Mon (source US-Fri 5/15): WTD = (404.35-417.72)/417.72 = -3.20%
#   JP Tue (source US-Mon 5/18): WTD = (395.95-417.72)/417.72 = -5.21%
#   JP Wed (source US-Tue 5/19): WTD = (392.61-417.72)/417.72 = -6.01%
# ---------------------------------------------------------------------------

def _make_wtd_stock_ingester(tmp_path, max_us_date: str):
    """Return a UniversalIngester configured for the US stock WTD boundary test.

    ``max_us_date`` limits the US market data available in the history CSV to
    simulate what is visible at JP processing time (before the current US session).
    """
    import json as _json

    funds_csv = tmp_path / "funds.csv"
    external_json = tmp_path / "external_assets.json"
    history_dir = tmp_path / "history"
    history_dir.mkdir()

    # All known US-date/close pairs for the test window
    all_us_rows = [
        ("2026-05-14", "417.72"),   # previous Thursday  ← WTD origin
        ("2026-05-15", "404.35"),   # previous Friday    (first JP-week observation)
        ("2026-05-18", "395.95"),   # current Monday
        ("2026-05-19", "392.61"),   # current Tuesday
        ("2026-05-20", "401.62"),   # later row must not be adopted for JP 2026-05-20 recompute
    ]

    # Minimal FX stub (rate=1 so current_value_jpy == close price)
    fx_rows = [d for (d, _) in all_us_rows if d <= max_us_date]
    fx_lines = ["Date,Close"] + [f"{d},1.0" for d in fx_rows]
    (history_dir / "USDJPY.csv").write_text("\n".join(fx_lines) + "\n", encoding="utf-8")

    stock_rows = ["Date,Close"] + [f"{d},{c}" for (d, c) in all_us_rows if d <= max_us_date]
    (history_dir / "TSM.csv").write_text("\n".join(stock_rows) + "\n", encoding="utf-8")

    funds_csv.write_text(
        "name,asset_class,currency,units,source_symbol,csv_url\n"
        "USDJPY,FX,JPY,1,JPY=X,\n"
        "TSM,US_STOCK,USD,1,TSM,\n",
        encoding="utf-8",
    )
    external_json.write_text(_json.dumps({}), encoding="utf-8")

    return UniversalIngester(
        funds_csv_path=str(funds_csv),
        external_assets_path=str(external_json),
        history_dir=str(history_dir),
        is_closed_fn=is_market_closed,
    )


def test_us_stock_wtd_monday_uses_prev_thursday_as_base(tmp_path):
    """JP Monday WTD for a US stock must chain from the prev-Thursday close (417.72).

    JP Monday morning: US Friday close (404.35) is the latest available.
    US Friday is the FIRST observation of the new JP week, not the WTD base.
    WTD = (404.35 - 417.72) / 417.72 = -3.20%.
    """
    # max_us_date=2026-05-15 simulates JP Monday morning (US Mon hasn't traded yet)
    ingester = _make_wtd_stock_ingester(tmp_path, max_us_date="2026-05-15")
    ledger = ingester.build_shadow_ledger("2026-05-18")
    record = next(r for r in ledger.assets if r.name == "TSM")
    # WTD == DAY return on Monday: (404.35 - 417.72) / 417.72
    assert record.wtd_pct == pytest.approx(-3.201, abs=0.01), (
        f"JP Monday WTD should be -3.20% (from prev-Thu base), got {record.wtd_pct:.2f}%"
    )


def test_us_stock_wtd_tuesday_chains_from_prev_thursday(tmp_path):
    """JP Tuesday WTD for a US stock must compound from prev-Thursday base (417.72).

    JP Tuesday morning: US Monday close (395.95) is the latest available.
    Regression guard: WTD must NOT reset to US Monday single-day return (-2.08%)
    or anchor to US Friday (404.35).  Correct WTD = -5.21%.
    """
    # max_us_date=2026-05-18 simulates JP Tuesday morning (US Mon closed, Tue hasn't)
    ingester = _make_wtd_stock_ingester(tmp_path, max_us_date="2026-05-18")
    ledger = ingester.build_shadow_ledger("2026-05-19")
    record = next(r for r in ledger.assets if r.name == "TSM")
    # (395.95 - 417.72) / 417.72 = -5.21%
    assert record.wtd_pct == pytest.approx(-5.213, abs=0.01), (
        f"JP Tuesday WTD should be -5.21% (from prev-Thu base), got {record.wtd_pct:.2f}%"
    )


def test_us_stock_wtd_wednesday_full_chain_minus_six_percent(tmp_path):
    """JP Wednesday WTD from prev-Thursday base must be -6.01% (geometric chain).

    This is the production scenario: TSMC wtd_pct was -2.90% (used US Friday as base).
    Correct value: (392.61 - 417.72) / 417.72 = -6.01%.
    """
    # max_us_date=2026-05-19 simulates JP Wednesday morning (US Tue closed)
    ingester = _make_wtd_stock_ingester(tmp_path, max_us_date="2026-05-19")
    ledger = ingester.build_shadow_ledger("2026-05-20")
    record = next(r for r in ledger.assets if r.name == "TSM")
    assert record.wtd_pct == pytest.approx(-6.01, abs=0.01), (
        f"JP Wednesday US-stock WTD should be -6.01%, got {record.wtd_pct:.2f}%"
    )


def test_us_stock_ledger_caps_history_at_us_trading_date_even_if_future_row_exists(tmp_path):
    """JP target_date is the ledger date; US-stock price data must be capped separately.

    For JP 2026-05-20 evening processing, the latest admissible US market date is
    2026-05-19.  A 2026-05-20 US row may exist in local history after a later
    refresh, but must not be adopted when recomputing the JP 2026-05-20 ledger.
    """
    ingester = _make_wtd_stock_ingester(tmp_path, max_us_date="2026-05-20")
    ledger = ingester.build_shadow_ledger("2026-05-20")
    record = next(r for r in ledger.assets if r.name == "TSM")

    assert record.source_date == "2026-05-19"
    assert record.price == pytest.approx(392.61)
    assert record.current_value_jpy == pytest.approx(392.61)
    assert record.wtd_pct == pytest.approx(-6.01, abs=0.01)


def test_us_stock_wtd_monday_not_dropped_from_chain(tmp_path):
    """Explicit guard: JP Monday must be counted as the first WTD day, not dropped.

    If Monday were dropped from the chain, Wednesday WTD would equal a 2-day chain
    starting from US Friday: (392.61 - 404.35) / 404.35 = -2.90%.  The correct
    3-day chain from prev-Thursday is -6.01%.
    """
    ingester = _make_wtd_stock_ingester(tmp_path, max_us_date="2026-05-19")
    ledger = ingester.build_shadow_ledger("2026-05-20")
    record = next(r for r in ledger.assets if r.name == "TSM")
    wrong_two_day_wtd = pytest.approx(-2.90, abs=0.05)
    assert record.wtd_pct != wrong_two_day_wtd, (
        "JP Monday was silently dropped from the WTD chain (2-day result instead of 3-day)"
    )
    assert record.wtd_pct == pytest.approx(-6.01, abs=0.01)
