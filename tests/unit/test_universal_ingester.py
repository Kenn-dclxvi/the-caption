import json

import pytest

from src.domain.universal_ingester import UniversalIngester

_CLOSED = lambda asset_class, symbol, target_date: True
_OPEN = lambda asset_class, symbol, target_date: False


def _write_history(history_dir, name, content):
    (history_dir / f"{name}.csv").write_text(content, encoding="utf-8")


def test_build_shadow_ledger_merges_market_units_and_absolute_amounts(tmp_path):
    funds_csv = tmp_path / "funds.csv"
    external_json = tmp_path / "external_assets.json"
    portfolio_basis_json = tmp_path / "portfolio_basis.json"
    history_dir = tmp_path / "history"
    history_dir.mkdir()

    funds_csv.write_text(
        "\n".join([
            "name,asset_class,currency,units,source_symbol,csv_url",
            "FundA,MUTUAL_FUNDS,JPY,20000,FundA,",
            "JpStock,JP_STOCK,JPY,3,1234.T,",
            "UsStock,US_STOCK,USD,2,USX,",
            "USDJPY,FX,JPY,1,JPY=X,",
            "Gold,COMMODITIES,JPY,31.1034768,GC=F,",
        ]) + "\n",
        encoding="utf-8",
    )
    external_json.write_text(
        json.dumps({
            "2026-04": {
                "items": [
                    {"category": "CASH", "amount": 1000, "name": "Cash"},
                    {"category": "DC", "amount": 2000, "name": "Defined Contribution"},
                ]
            }
        }),
        encoding="utf-8",
    )
    portfolio_basis_json.write_text(
        json.dumps({"2026-04": {"total_acquisition_cost_jpy": 480000}}),
        encoding="utf-8",
    )
    _write_history(history_dir, "FundA", "基準日,基準価額\n2025-12-30,10000\n2026-03-31,11000\n2026-04-19,11500\n2026-04-20,12000\n")
    _write_history(history_dir, "JpStock", "Date,Close\n2026-04-19,480\n2026-04-20,500\n")
    _write_history(history_dir, "UsStock", "Date,Close\n2026-04-19,9\n2026-04-20,10\n")
    _write_history(history_dir, "USDJPY", "Date,Close\n2026-04-20,150\n")
    _write_history(history_dir, "Gold", "Date,Close\n2026-04-19,3000\n2026-04-20,3100\n")

    ledger = UniversalIngester(
        funds_csv_path=str(funds_csv),
        external_assets_path=str(external_json),
        portfolio_basis_path=str(portfolio_basis_json),
        history_dir=str(history_dir),
    ).build_shadow_ledger("2026-04-25")

    values = {record.name: record.current_value_jpy for record in ledger.assets}
    assert ledger.ssot_b_active_key == "2026-04"
    assert ledger.basis_active_key == "2026-04"
    assert "USDJPY" not in values
    assert values["FundA"] == pytest.approx(24_000)
    assert values["JpStock"] == pytest.approx(1_500)
    assert values["UsStock"] == pytest.approx(3_000)
    assert values["Gold"] == pytest.approx(465_000)
    assert values["Cash"] == pytest.approx(1_000)
    assert values["Defined Contribution"] == pytest.approx(2_000)
    assert ledger.total_value_jpy == pytest.approx(sum(values.values()))
    market_total = values["FundA"] + values["JpStock"] + values["UsStock"] + values["Gold"]
    assert ledger.return_base_value_jpy == pytest.approx(market_total)
    assert ledger.total_acquisition_cost_jpy == pytest.approx(480_000)
    assert ledger.total_return_jpy == pytest.approx(market_total - 480_000)
    assert ledger.total_return_pct == pytest.approx((market_total - 480_000) / 480_000 * 100)
    records = {record.name: record for record in ledger.assets}
    assert records["FundA"].diff_val_jpy == pytest.approx(0)
    assert records["FundA"].diff_pct == pytest.approx(0)
    assert records["FundA"].wtd_pct == pytest.approx(500 / 11500 * 100)
    assert records["FundA"].mtd_pct == pytest.approx(1000 / 11000 * 100)
    assert records["FundA"].ytd_pct == pytest.approx(2000 / 10000 * 100)
    assert records["JpStock"].diff_val_jpy == pytest.approx(60)
    assert records["UsStock"].diff_val_jpy == pytest.approx(300)
    assert records["Gold"].diff_val_jpy == pytest.approx(15_000)
    assert records["Cash"].diff_val_jpy is None


def test_fund_diff_is_nonzero_when_source_date_matches_target_date(tmp_path):
    funds_csv = tmp_path / "funds.csv"
    external_json = tmp_path / "external_assets.json"
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    funds_csv.write_text(
        "name,asset_class,currency,units,source_symbol,csv_url\nFundA,MUTUAL_FUNDS,JPY,20000,FundA,\n",
        encoding="utf-8",
    )
    external_json.write_text(json.dumps({}), encoding="utf-8")
    _write_history(history_dir, "FundA", "基準日,基準価額\n2026-04-19,11500\n2026-04-20,12000\n")

    ledger = UniversalIngester(
        funds_csv_path=str(funds_csv),
        external_assets_path=str(external_json),
        history_dir=str(history_dir),
    ).build_shadow_ledger("2026-04-20")

    record = next(r for r in ledger.assets if r.name == "FundA")
    assert record.diff_val_jpy == pytest.approx(1_000)
    assert record.diff_pct == pytest.approx(500 / 11500 * 100)


def test_external_assets_falls_back_to_default(tmp_path):
    funds_csv = tmp_path / "funds.csv"
    external_json = tmp_path / "external_assets.json"
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    funds_csv.write_text("name,asset_class,currency,units,source_symbol,csv_url\n", encoding="utf-8")
    external_json.write_text(
        json.dumps({
            "default": {
                "items": [
                    {"category": "CASH", "amount": "3000", "name": "Default Cash"},
                    {"category": "BROKEN", "amount": "invalid", "name": "Invalid Amount"},
                ]
            }
        }),
        encoding="utf-8",
    )

    ledger = UniversalIngester(
        funds_csv_path=str(funds_csv),
        external_assets_path=str(external_json),
        history_dir=str(history_dir),
    ).build_shadow_ledger("2026-04-25")

    values = {record.name: record.current_value_jpy for record in ledger.assets}
    assert ledger.ssot_b_active_key == "default"
    assert values["Default Cash"] == pytest.approx(3_000)
    assert values["Invalid Amount"] == pytest.approx(0)
    assert ledger.total_value_jpy == pytest.approx(3_000)


def test_jp_stock_is_marked_stale_when_source_date_is_previous_day(tmp_path):
    funds_csv = tmp_path / "funds.csv"
    external_json = tmp_path / "external_assets.json"
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    funds_csv.write_text(
        "name,asset_class,currency,units,source_symbol,csv_url\nBestAI,JP_STOCK,JPY,1,408A.T,\n",
        encoding="utf-8",
    )
    external_json.write_text(json.dumps({}), encoding="utf-8")
    _write_history(history_dir, "BestAI", "Date,Close\n2026-05-21,306.2\n")

    ingester = UniversalIngester(
        funds_csv_path=str(funds_csv),
        external_assets_path=str(external_json),
        history_dir=str(history_dir),
    )
    ingester._resolve_us_market_date = lambda _target: "2026-05-21"  # type: ignore[method-assign]
    ledger = ingester.build_shadow_ledger("2026-05-22")

    record = next(r for r in ledger.assets if r.name == "BestAI")
    assert record.source_date == "2026-05-21"
    assert record.pricing_status == "STALE"


def test_us_stock_is_marked_stale_when_fx_date_is_previous_to_us_market_date(tmp_path):
    funds_csv = tmp_path / "funds.csv"
    external_json = tmp_path / "external_assets.json"
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    funds_csv.write_text(
        "\n".join([
            "name,asset_class,currency,units,source_symbol,csv_url",
            "UsStockA,US_STOCK,USD,1,USX,",
            "USDJPY,FX,JPY,1,JPY=X,",
        ]) + "\n",
        encoding="utf-8",
    )
    external_json.write_text(json.dumps({}), encoding="utf-8")
    _write_history(history_dir, "UsStockA", "Date,Close\n2026-05-21,100\n")
    _write_history(history_dir, "USDJPY", "Date,Close\n2026-05-20,150\n")

    ingester = UniversalIngester(
        funds_csv_path=str(funds_csv),
        external_assets_path=str(external_json),
        history_dir=str(history_dir),
    )
    ingester._resolve_us_market_date = lambda _target: "2026-05-21"  # type: ignore[method-assign]
    ledger = ingester.build_shadow_ledger("2026-05-22")

    record = next(r for r in ledger.assets if r.name == "UsStockA")
    assert record.source_date == "2026-05-21"
    assert record.pricing_status == "STALE"
    assert "fx rate stale or unavailable for expected market date" in record.warnings


def test_us_stock_is_missing_when_fx_metrics_unavailable(tmp_path):
    funds_csv = tmp_path / "funds.csv"
    external_json = tmp_path / "external_assets.json"
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    funds_csv.write_text(
        "\n".join([
            "name,asset_class,currency,units,source_symbol,csv_url",
            "UsStockA,US_STOCK,USD,1,USX,",
            "USDJPY,FX,JPY,1,JPY=X,",
        ]) + "\n",
        encoding="utf-8",
    )
    external_json.write_text(json.dumps({}), encoding="utf-8")
    _write_history(history_dir, "UsStockA", "Date,Close\n2026-05-21,100\n")
    # USDJPY history intentionally missing

    ingester = UniversalIngester(
        funds_csv_path=str(funds_csv),
        external_assets_path=str(external_json),
        history_dir=str(history_dir),
    )
    ingester._resolve_us_market_date = lambda _target: "2026-05-21"  # type: ignore[method-assign]
    ledger = ingester.build_shadow_ledger("2026-05-22")

    record = next(r for r in ledger.assets if r.name == "UsStockA")
    assert record.pricing_status == "MISSING"


def test_commodity_is_marked_stale_when_fx_date_is_previous_to_us_market_date(tmp_path):
    funds_csv = tmp_path / "funds.csv"
    external_json = tmp_path / "external_assets.json"
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    funds_csv.write_text(
        "\n".join([
            "name,asset_class,currency,units,source_symbol,csv_url",
            "Gold,COMMODITIES,JPY,1,GC=F,",
            "USDJPY,FX,JPY,1,JPY=X,",
        ]) + "\n",
        encoding="utf-8",
    )
    external_json.write_text(json.dumps({}), encoding="utf-8")
    _write_history(history_dir, "Gold", "Date,Close\n2026-05-21,3200\n")
    _write_history(history_dir, "USDJPY", "Date,Close\n2026-05-20,150\n")

    ingester = UniversalIngester(
        funds_csv_path=str(funds_csv),
        external_assets_path=str(external_json),
        history_dir=str(history_dir),
    )
    ingester._resolve_us_market_date = lambda _target: "2026-05-21"  # type: ignore[method-assign]
    ledger = ingester.build_shadow_ledger("2026-05-22")

    record = next(r for r in ledger.assets if r.name == "Gold")
    assert record.source_date == "2026-05-21"
    assert record.pricing_status == "STALE"


def test_portfolio_basis_falls_back_to_default(tmp_path):
    funds_csv = tmp_path / "funds.csv"
    external_json = tmp_path / "external_assets.json"
    portfolio_basis_json = tmp_path / "portfolio_basis.json"
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    funds_csv.write_text("name,asset_class,currency,units,source_symbol,csv_url\n", encoding="utf-8")
    external_json.write_text(
        json.dumps({"2026-04": {"items": [{"category": "CASH", "amount": 3000, "name": "Cash"}]}}),
        encoding="utf-8",
    )
    portfolio_basis_json.write_text(
        json.dumps({"default": {"total_acquisition_cost_jpy": 2500}}),
        encoding="utf-8",
    )

    ledger = UniversalIngester(
        funds_csv_path=str(funds_csv),
        external_assets_path=str(external_json),
        portfolio_basis_path=str(portfolio_basis_json),
        history_dir=str(history_dir),
    ).build_shadow_ledger("2026-04-25")

    assert ledger.basis_active_key == "default"
    assert ledger.return_base_value_jpy == pytest.approx(0)
    assert ledger.total_acquisition_cost_jpy == pytest.approx(2_500)
    assert ledger.total_return_jpy == pytest.approx(-2_500)
    assert ledger.total_return_pct == pytest.approx(-100.0)


def _make_jp_stock_ingester(tmp_path, *, is_closed_fn):
    funds_csv = tmp_path / "funds.csv"
    external_json = tmp_path / "external_assets.json"
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    funds_csv.write_text(
        "name,asset_class,currency,units,source_symbol,csv_url\nBestAI,JP_STOCK,JPY,1,408A.T,\n",
        encoding="utf-8",
    )
    external_json.write_text(json.dumps({}), encoding="utf-8")
    _write_history(history_dir, "BestAI", "Date,Close\n2026-05-28,320.9\n")
    ingester = UniversalIngester(
        funds_csv_path=str(funds_csv),
        external_assets_path=str(external_json),
        history_dir=str(history_dir),
        is_closed_fn=is_closed_fn,
    )
    ingester._resolve_us_market_date = lambda _target: "2026-05-28"  # type: ignore[method-assign]
    return ingester


def test_jp_stock_is_stale_when_source_date_matches_but_market_not_closed(tmp_path):
    ledger = _make_jp_stock_ingester(tmp_path, is_closed_fn=_OPEN).build_shadow_ledger("2026-05-28")
    record = next(r for r in ledger.assets if r.name == "BestAI")
    assert record.pricing_status == "STALE"
    assert any("intraday" in w for w in record.warnings)


def test_jp_stock_is_priced_when_source_date_matches_and_market_closed(tmp_path):
    ledger = _make_jp_stock_ingester(tmp_path, is_closed_fn=_CLOSED).build_shadow_ledger("2026-05-28")
    record = next(r for r in ledger.assets if r.name == "BestAI")
    assert record.pricing_status == "PRICED"
    assert not any("intraday" in w for w in record.warnings)


def test_past_date_is_priced_regardless_of_market_open(tmp_path):
    # Past-date re-calculation: is_closed_fn=_OPEN always returns False,
    # but target_date "2026-04-20" is in the past so the implementation must
    # skip the close check and yield PRICED (not STALE).
    import datetime as _dt
    from src.infra.market_data import is_market_closed

    # Bind now_jst to a future time (10:00 JST, market open) so the time-based
    # fallback would return False — only the past-date guard can make it True.
    _jst = _dt.timezone(_dt.timedelta(hours=9))
    future_open = _dt.datetime(2030, 1, 1, 10, 0, tzinfo=_jst)
    is_closed_past_aware = lambda ac, sym, td: is_market_closed(ac, sym, target_date=td, now_jst=future_open)

    funds_csv = tmp_path / "funds.csv"
    external_json = tmp_path / "external_assets.json"
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    funds_csv.write_text(
        "name,asset_class,currency,units,source_symbol,csv_url\nBestAI,JP_STOCK,JPY,1,408A.T,\n",
        encoding="utf-8",
    )
    external_json.write_text(json.dumps({}), encoding="utf-8")
    _write_history(history_dir, "BestAI", "Date,Close\n2026-04-20,300.0\n")
    ingester = UniversalIngester(
        funds_csv_path=str(funds_csv),
        external_assets_path=str(external_json),
        history_dir=str(history_dir),
        is_closed_fn=is_closed_past_aware,
    )
    ingester._resolve_us_market_date = lambda _target: "2026-04-20"  # type: ignore[method-assign]
    ledger = ingester.build_shadow_ledger("2026-04-20")
    record = next(r for r in ledger.assets if r.name == "BestAI")
    assert record.pricing_status == "PRICED"


# --- JP-observation lag correction for MTD/YTD (US_STOCK & COMMODITIES) -------
#
# US/commodity history is in USD on US-market dates.  The US Friday close is first
# observed by the JP system on the following JP Monday (start of the new JP week),
# so a period's "base" (denominator) must be the US close observed on the JP
# weekday immediately before the JP period start — not the US close the JP system
# first observes on the period's opening day.  These fixed TSMC closes exercise
# month- and year-boundary base selection deterministically.

_TSMC_NOV_DEC = (
    "Date,Close\n"
    "2025-11-26,288.366760\n"
    "2025-11-28,289.908234\n"
    "2025-12-01,286.099274\n"
    "2025-12-02,290.485046\n"
    "2025-12-03,293.826630\n"
)
_TSMC_MAR_APR = (
    "Date,Close\n"
    "2026-03-26,326.1099853515625\n"
    "2026-03-27,326.739990234375\n"
    "2026-03-30,316.5\n"
    "2026-03-31,337.950012\n"
    "2026-04-01,341.490000\n"
)
_TSMC_DEC_JAN = (
    "Date,Close\n"
    "2025-12-30,298.7381896972656\n"
    "2025-12-31,303.0361328125\n"
    "2026-01-02,318.7119140625\n"
    "2026-01-07,317.780000\n"
)


def _build_us_stock_record(tmp_path, *, history_csv, target_date, us_market_date):
    funds_csv = tmp_path / "funds.csv"
    external_json = tmp_path / "external_assets.json"
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    funds_csv.write_text(
        "\n".join([
            "name,asset_class,currency,units,source_symbol,csv_url",
            "UsStockA,US_STOCK,USD,1,USX,",
            "USDJPY,FX,JPY,1,JPY=X,",
        ]) + "\n",
        encoding="utf-8",
    )
    external_json.write_text(json.dumps({}), encoding="utf-8")
    _write_history(history_dir, "UsStockA", history_csv)
    _write_history(history_dir, "USDJPY", f"Date,Close\n{us_market_date},150\n")
    ingester = UniversalIngester(
        funds_csv_path=str(funds_csv),
        external_assets_path=str(external_json),
        history_dir=str(history_dir),
    )
    ingester._resolve_us_market_date = lambda _target: us_market_date  # type: ignore[method-assign]
    ledger = ingester.build_shadow_ledger(target_date)
    return next(r for r in ledger.assets if r.name == "UsStockA")


def test_us_stock_mtd_equals_wtd_when_month_starts_on_monday(tmp_path):
    # Case A: JP month start 2025-12-01 is a Monday → MTD base == WTD base == 2025-11-26.
    record = _build_us_stock_record(
        tmp_path,
        history_csv=_TSMC_NOV_DEC,
        target_date="2025-12-04",
        us_market_date="2025-12-03",
    )
    expected = (293.826630 / 288.366760 - 1) * 100  # base 2025-11-26 ≈ +1.89%
    pre_fix_wrong = (293.826630 / 289.908234 - 1) * 100  # base 2025-11-28 ≈ +1.35%
    assert record.mtd_pct == pytest.approx(expected, rel=1e-9)
    assert record.mtd_pct == pytest.approx(record.wtd_pct, rel=1e-9)
    assert record.mtd_pct != pytest.approx(pre_fix_wrong, rel=1e-6)


def test_us_stock_mtd_uses_prior_jp_weekday_when_month_starts_midweek(tmp_path):
    # Case B: JP month start 2026-04-01 is a Wednesday → MTD base == 2026-03-30
    # (prior JP weekday is Tue 2026-03-31, exclusive bound picks 2026-03-30),
    # NOT 2026-03-31.
    record = _build_us_stock_record(
        tmp_path,
        history_csv=_TSMC_MAR_APR,
        target_date="2026-04-02",
        us_market_date="2026-04-01",
    )
    expected = (341.490000 / 316.5 - 1) * 100  # base 2026-03-30 ≈ +7.90%
    pre_fix_wrong = (341.490000 / 337.950012 - 1) * 100  # base 2026-03-31 ≈ +1.05%
    assert record.mtd_pct == pytest.approx(expected, rel=1e-9)
    assert record.mtd_pct != pytest.approx(pre_fix_wrong, rel=1e-6)


def test_us_stock_ytd_uses_prior_jp_weekday_at_year_boundary(tmp_path):
    # Case C: JP year start 2026-01-01 is a Thursday → YTD base == 2025-12-30
    # (prior JP weekday is Wed 2025-12-31, exclusive bound picks 2025-12-30),
    # NOT 2025-12-31.
    record = _build_us_stock_record(
        tmp_path,
        history_csv=_TSMC_DEC_JAN,
        target_date="2026-01-08",
        us_market_date="2026-01-07",
    )
    expected = (317.780000 / 298.7381896972656 - 1) * 100  # base 2025-12-30 ≈ +6.38%
    pre_fix_wrong = (317.780000 / 303.0361328125 - 1) * 100  # base 2025-12-31 ≈ +4.87%
    assert record.ytd_pct == pytest.approx(expected, rel=1e-9)
    assert record.ytd_pct != pytest.approx(pre_fix_wrong, rel=1e-6)


def test_commodity_mtd_equals_wtd_when_month_starts_on_monday(tmp_path):
    # Case D: commodities share the same JP-observation lag correction.
    funds_csv = tmp_path / "funds.csv"
    external_json = tmp_path / "external_assets.json"
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    funds_csv.write_text(
        "\n".join([
            "name,asset_class,currency,units,source_symbol,csv_url",
            "Gold,COMMODITIES,JPY,1,GC=F,",
            "USDJPY,FX,JPY,1,JPY=X,",
        ]) + "\n",
        encoding="utf-8",
    )
    external_json.write_text(json.dumps({}), encoding="utf-8")
    _write_history(history_dir, "Gold", _TSMC_NOV_DEC)
    _write_history(history_dir, "USDJPY", "Date,Close\n2025-12-03,150\n")
    ingester = UniversalIngester(
        funds_csv_path=str(funds_csv),
        external_assets_path=str(external_json),
        history_dir=str(history_dir),
    )
    ingester._resolve_us_market_date = lambda _target: "2025-12-03"  # type: ignore[method-assign]
    ledger = ingester.build_shadow_ledger("2025-12-04")
    record = next(r for r in ledger.assets if r.name == "Gold")
    expected = (293.826630 / 288.366760 - 1) * 100  # base 2025-11-26
    assert record.mtd_pct == pytest.approx(expected, rel=1e-9)
    assert record.mtd_pct == pytest.approx(record.wtd_pct, rel=1e-9)


def test_mutual_fund_is_not_subject_to_close_check(tmp_path):
    funds_csv = tmp_path / "funds.csv"
    external_json = tmp_path / "external_assets.json"
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    funds_csv.write_text(
        "name,asset_class,currency,units,source_symbol,csv_url\n"
        "FundA,MUTUAL_FUNDS,JPY,1000,FundA,\n",
        encoding="utf-8",
    )
    external_json.write_text(json.dumps({}), encoding="utf-8")
    _write_history(history_dir, "FundA", "基準日,基準価額\n2026-05-28,12000\n")
    ingester = UniversalIngester(
        funds_csv_path=str(funds_csv),
        external_assets_path=str(external_json),
        history_dir=str(history_dir),
        is_closed_fn=_OPEN,  # market "open" — should not affect MUTUAL_FUNDS
    )
    ingester._resolve_us_market_date = lambda _target: "2026-05-28"  # type: ignore[method-assign]
    ledger = ingester.build_shadow_ledger("2026-05-28")
    record = next(r for r in ledger.assets if r.name == "FundA")
    # MUTUAL_FUNDS with matching source_date are PRICED regardless of market open/close
    assert record.pricing_status == "PRICED"
