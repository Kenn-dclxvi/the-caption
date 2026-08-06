import json
from unittest.mock import MagicMock, patch

import pytest

from src.domain.universal_ingester import CanonicalLedgerInputError, UniversalIngester
from src.infra.market_data import is_market_closed
from src.infra.canonical_ledger_input_repository import CanonicalLedgerInputRepository

_CLOSED = lambda asset_class, symbol, target_date: True
_OPEN = lambda asset_class, symbol, target_date: False


def _write_history(history_dir, name, content):
    (history_dir / f"{name}.csv").write_text(content, encoding="utf-8")


@pytest.mark.parametrize(
    "failure",
    [
        "missing_a",
        "unreadable_a",
        "invalid_a",
        "missing_b",
        "unreadable_b",
        "invalid_b",
        "partial_b",
    ],
)
def test_required_ssot_failure_preserves_previous_canonical_ledger(tmp_path, failure):
    funds_csv = tmp_path / "market_units.csv"
    external_json = tmp_path / "external_assets.json"
    history_dir = tmp_path / "history"
    output_path = tmp_path / "v4_shadow_ledger.json"
    history_dir.mkdir()
    output_path.write_text('{"previous":"valid"}\n', encoding="utf-8")

    valid_a = (
        "name,asset_class,currency,units,source_symbol,audit_match_key,csv_url\n"
        "FundA,MUTUAL_FUNDS,JPY,1,FundA,,\n"
    )
    valid_b = {"default": {"items": [{"category": "CASH", "amount": 1000, "name": "Cash"}]}}

    if failure == "unreadable_a":
        funds_csv.mkdir()
    elif failure == "invalid_a":
        funds_csv.write_text(
            valid_a + "Broken,MUTUAL_FUNDS,JPY,not-a-number,Broken,,\n",
            encoding="utf-8",
        )
    elif failure != "missing_a":
        funds_csv.write_text(valid_a, encoding="utf-8")

    if failure == "unreadable_b":
        external_json.mkdir()
    elif failure == "invalid_b":
        external_json.write_text("[]", encoding="utf-8")
    elif failure == "partial_b":
        external_json.write_text(
            json.dumps(
                {
                    "default": {
                        "items": [
                            {"category": "CASH", "amount": 1000, "name": "Cash"},
                            {"category": "CASH", "amount": "invalid", "name": "Broken"},
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
    elif failure != "missing_b":
        external_json.write_text(json.dumps(valid_b), encoding="utf-8")

    ingester = UniversalIngester(
        funds_csv_path=str(funds_csv),
        external_assets_path=str(external_json),
        history_dir=str(history_dir),
        is_closed_fn=is_market_closed,
        input_store=CanonicalLedgerInputRepository(),
    )

    with pytest.raises(CanonicalLedgerInputError):
        ingester.run("2026-04-25", output_path=str(output_path))

    assert output_path.read_text(encoding="utf-8") == '{"previous":"valid"}\n'


def test_canonical_ledger_atomic_replace_failure_preserves_previous_file(tmp_path):
    funds_csv = tmp_path / "market_units.csv"
    external_json = tmp_path / "external_assets.json"
    history_dir = tmp_path / "history"
    output_path = tmp_path / "v4_shadow_ledger.json"
    history_dir.mkdir()
    funds_csv.write_text(
        "name,asset_class,currency,units,source_symbol,audit_match_key,csv_url\n",
        encoding="utf-8",
    )
    external_json.write_text(
        json.dumps({"default": {"items": [{"category": "CASH", "amount": 1000, "name": "Cash"}]}}),
        encoding="utf-8",
    )
    output_path.write_text('{"previous":"valid"}\n', encoding="utf-8")
    ingester = UniversalIngester(
        funds_csv_path=str(funds_csv),
        external_assets_path=str(external_json),
        history_dir=str(history_dir),
        is_closed_fn=is_market_closed,
        input_store=CanonicalLedgerInputRepository(),
    )

    with patch("src.lib.atomic_write.os.replace", side_effect=OSError("replace failed")):
        with pytest.raises(OSError, match="replace failed"):
            ingester.run("2026-04-25", output_path=str(output_path))

    assert output_path.read_text(encoding="utf-8") == '{"previous":"valid"}\n'
    assert [item for item in tmp_path.iterdir() if item.name.endswith(".tmp")] == []


def test_minimal_documented_ssot_a_schema_uses_existing_defaults(tmp_path):
    funds_csv = tmp_path / "market_units.csv"
    external_json = tmp_path / "external_assets.json"
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    funds_csv.write_text(
        "name,units,csv_url\nFundA,20000,\n",
        encoding="utf-8",
    )
    external_json.write_text(json.dumps({}), encoding="utf-8")
    _write_history(history_dir, "FundA", "基準日,基準価額\n2026-04-20,12000\n")

    ledger = UniversalIngester(
        funds_csv_path=str(funds_csv),
        external_assets_path=str(external_json),
        history_dir=str(history_dir),
        is_closed_fn=is_market_closed,
        input_store=CanonicalLedgerInputRepository(),
    ).build_shadow_ledger("2026-04-20")

    assert len(ledger.assets) == 1
    asset = ledger.assets[0]
    assert asset.name == "FundA"
    assert asset.asset_class == "MUTUAL_FUNDS"
    assert asset.currency == "JPY"
    assert asset.source_symbol == "FundA"
    assert asset.current_value_jpy == pytest.approx(24_000)


@pytest.mark.parametrize("invalid_month_key", ["2026-00", "2026-13"])
def test_ssot_b_rejects_out_of_range_month_keys(tmp_path, invalid_month_key):
    funds_csv = tmp_path / "market_units.csv"
    external_json = tmp_path / "external_assets.json"
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    funds_csv.write_text("name,units,csv_url\n", encoding="utf-8")
    external_json.write_text(
        json.dumps(
            {
                invalid_month_key: {
                    "items": [{"category": "CASH", "amount": 1000, "name": "Cash"}]
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(CanonicalLedgerInputError, match="invalid top-level key"):
        UniversalIngester(
            funds_csv_path=str(funds_csv),
            external_assets_path=str(external_json),
            history_dir=str(history_dir),
            is_closed_fn=is_market_closed,
            input_store=CanonicalLedgerInputRepository(),
        ).build_shadow_ledger("2026-04-20")


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
        is_closed_fn=is_market_closed,
        input_store=CanonicalLedgerInputRepository(),
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
        is_closed_fn=is_market_closed,
        input_store=CanonicalLedgerInputRepository(),
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
                ]
            }
        }),
        encoding="utf-8",
    )

    ledger = UniversalIngester(
        funds_csv_path=str(funds_csv),
        external_assets_path=str(external_json),
        history_dir=str(history_dir),
        is_closed_fn=is_market_closed,
        input_store=CanonicalLedgerInputRepository(),
    ).build_shadow_ledger("2026-04-25")

    values = {record.name: record.current_value_jpy for record in ledger.assets}
    assert ledger.ssot_b_active_key == "default"
    assert values["Default Cash"] == pytest.approx(3_000)
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
        is_closed_fn=is_market_closed,
        input_store=CanonicalLedgerInputRepository(),
    )
    ingester._resolve_us_market_date = lambda _target: "2026-05-21"  # type: ignore[method-assign]
    ledger = ingester.build_shadow_ledger("2026-05-22")

    record = next(r for r in ledger.assets if r.name == "BestAI")
    assert record.source_date == "2026-05-21"
    assert record.pricing_status == "STALE"


def test_jp_assets_use_previous_business_date_on_holiday(tmp_path):
    funds_csv = tmp_path / "funds.csv"
    external_json = tmp_path / "external_assets.json"
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    funds_csv.write_text(
        "\n".join([
            "name,asset_class,currency,units,source_symbol,csv_url",
            "FundA,MUTUAL_FUNDS,JPY,10000,FundA,",
            "BestAI,JP_STOCK,JPY,1,408A.T,",
        ]) + "\n",
        encoding="utf-8",
    )
    external_json.write_text(json.dumps({}), encoding="utf-8")
    _write_history(
        history_dir,
        "FundA",
        "基準日,基準価額\n2026-07-16,11000\n2026-07-17,12000\n2026-07-20,99999\n",
    )
    _write_history(
        history_dir,
        "BestAI",
        "Date,Close\n2026-07-16,300\n2026-07-17,320\n2026-07-20,999\n",
    )
    timeline = MagicMock()
    timeline.get_us_market_context.return_value = {"trading_date": "2026-07-17"}
    timeline.determine_jp_market_date.return_value = "2026-07-17"
    close_check = MagicMock(return_value=True)

    ledger = UniversalIngester(
        funds_csv_path=str(funds_csv),
        external_assets_path=str(external_json),
        history_dir=str(history_dir),
        timeline=timeline,
        is_closed_fn=close_check,
        input_store=CanonicalLedgerInputRepository(),
    ).build_shadow_ledger("2026-07-20")

    records = {record.name: record for record in ledger.assets}
    assert records["FundA"].source_date == "2026-07-17"
    assert records["FundA"].pricing_status == "PRICED"
    assert records["BestAI"].source_date == "2026-07-17"
    assert records["BestAI"].pricing_status == "PRICED"
    assert ledger.jp_market_date == "2026-07-17"
    timeline.determine_jp_market_date.assert_called_once_with("2026-07-20")
    close_check.assert_called_once_with("JP_STOCK", "408A.T", "2026-07-17")


def test_jp_asset_older_than_previous_business_date_stays_stale_on_holiday(tmp_path):
    funds_csv = tmp_path / "funds.csv"
    external_json = tmp_path / "external_assets.json"
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    funds_csv.write_text(
        "name,asset_class,currency,units,source_symbol,csv_url\n"
        "BestAI,JP_STOCK,JPY,1,408A.T,\n",
        encoding="utf-8",
    )
    external_json.write_text(json.dumps({}), encoding="utf-8")
    _write_history(history_dir, "BestAI", "Date,Close\n2026-07-16,300\n")
    timeline = MagicMock()
    timeline.get_us_market_context.return_value = {"trading_date": "2026-07-17"}
    timeline.determine_jp_market_date.return_value = "2026-07-17"
    close_check = MagicMock(return_value=True)

    ledger = UniversalIngester(
        funds_csv_path=str(funds_csv),
        external_assets_path=str(external_json),
        history_dir=str(history_dir),
        timeline=timeline,
        is_closed_fn=close_check,
        input_store=CanonicalLedgerInputRepository(),
    ).build_shadow_ledger("2026-07-20")

    record = next(record for record in ledger.assets if record.name == "BestAI")
    assert record.source_date == "2026-07-16"
    assert record.pricing_status == "STALE"
    close_check.assert_not_called()


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
        is_closed_fn=is_market_closed,
        input_store=CanonicalLedgerInputRepository(),
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
        is_closed_fn=is_market_closed,
        input_store=CanonicalLedgerInputRepository(),
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
        is_closed_fn=is_market_closed,
        input_store=CanonicalLedgerInputRepository(),
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
        is_closed_fn=is_market_closed,
        input_store=CanonicalLedgerInputRepository(),
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
        input_store=CanonicalLedgerInputRepository(),
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
        input_store=CanonicalLedgerInputRepository(),
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
        is_closed_fn=is_market_closed,
        input_store=CanonicalLedgerInputRepository(),
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
        is_closed_fn=is_market_closed,
        input_store=CanonicalLedgerInputRepository(),
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
        input_store=CanonicalLedgerInputRepository(),
    )
    ingester._resolve_us_market_date = lambda _target: "2026-05-28"  # type: ignore[method-assign]
    ledger = ingester.build_shadow_ledger("2026-05-28")
    record = next(r for r in ledger.assets if r.name == "FundA")
    # MUTUAL_FUNDS with matching source_date are PRICED regardless of market open/close
    assert record.pricing_status == "PRICED"


def test_previous_ledger_price_is_used_as_day_baseline():
    # DAY 比較の基準は正本である前営業日の台帳価格であり、
    # history CSV の末尾から2番目の行ではない。
    ingester = UniversalIngester(
        is_closed_fn=is_market_closed,
        input_store=CanonicalLedgerInputRepository(),
    )
    asset = {"name": "Gold", "source_symbol": "GC=F", "asset_class": "COMMODITIES", "units": "1"}

    assert ingester._previous_ledger_price(asset, {"GC=F": {"price": 4049.1}}) == 4049.1
    assert ingester._previous_ledger_price(asset, {"Gold": {"price": 4049.1}}) == 4049.1
    assert ingester._previous_ledger_price(asset, {"GC=F": {"price": 0.0}}) is None
    assert ingester._previous_ledger_price(asset, {}) is None
    assert ingester._previous_ledger_price(asset, None) is None


def test_confirmed_value_is_inherited_only_from_matching_canonical_ledger():
    # 期待日の価格が取得元に無いとき、前営業日に確定した正本の値を継承する。
    ingester = UniversalIngester(
        is_closed_fn=is_market_closed,
        input_store=CanonicalLedgerInputRepository(),
    )
    asset = {"name": "Gold", "source_symbol": "GC=F", "asset_class": "COMMODITIES", "units": "1"}
    confirmed = {
        "GC=F": {
            "price": 4049.1,
            "pricing_status": "PRICED",
            "source_date": "2026-07-31",
            "target_date": "2026-08-03",
        }
    }

    # 正本の対象日が期待日以降 かつ 価格一致 → その確定日を継承する。
    assert ingester._inheritable_confirmed_date(asset, confirmed, "2026-08-03", 4049.1) == "2026-08-03"

    # 期待日が正本の対象日より新しい → 継承しない。
    assert ingester._inheritable_confirmed_date(asset, confirmed, "2026-08-04", 4049.1) is None

    # 取得元の価格が更新された → 確定時と根拠が違うので継承しない。
    assert ingester._inheritable_confirmed_date(asset, confirmed, "2026-08-03", 4105.0) is None

    # 正本側が未確定 → 継承しない。
    stale = {"GC=F": dict(confirmed["GC=F"], pricing_status="STALE")}
    assert ingester._inheritable_confirmed_date(asset, stale, "2026-08-03", 4049.1) is None

    # 資産別の鮮度を持たない v3.5 台帳 → 継承しない。
    legacy = {"GC=F": {"price": 4049.1, "target_date": "2026-08-03"}}
    assert ingester._inheritable_confirmed_date(asset, legacy, "2026-08-03", 4049.1) is None


def test_day_diff_follows_ledger_confirmed_fx_not_just_price():
    # 値段だけを正本基準にすると為替が当日値のまま残り、評価額の変化を
    # DAY が取りこぼす。前日側は値段と為替の両方を正本の確定値で揃える。
    ingester = UniversalIngester(
        is_closed_fn=is_market_closed,
        input_store=CanonicalLedgerInputRepository(),
    )

    # 値段据え置き・為替のみ下落 → 円建て単価は下がる。
    prev_unit = ingester._previous_unit_value_jpy(4049.1, 160.183)
    assert prev_unit is not None
    assert round(prev_unit, 4) == round(4049.1 * 160.183, 4)

    # コモディティはグラム換算を挟む。
    prev_gram = ingester._previous_unit_value_jpy(4049.1, 160.183, divisor=31.1034768)
    assert round(prev_gram, 6) == round(4049.1 * 160.183 / 31.1034768, 6)

    # 為替が欠ける台帳（v3.5 以前）では従来計算へ戻すため None を返す。
    assert ingester._previous_unit_value_jpy(4049.1, None) is None
    assert ingester._previous_unit_value_jpy(None, 160.183) is None
    assert ingester._previous_unit_value_jpy(4049.1, 0.0) is None


def test_unparsable_history_date_degrades_to_missing_not_crash(tmp_path):
    # 日付列に解釈不能な値が混ざると read_csv は例外を投げず列を str のまま返す。
    # 対象日までの切り出しで初めて比較が失敗するため、ここを捕捉しないと
    # 1 資産の履歴不正が build_shadow_ledger 全体を落とす。
    funds_csv = tmp_path / "market_units.csv"
    external_json = tmp_path / "external_assets.json"
    history_dir = tmp_path / "history"
    history_dir.mkdir()

    funds_csv.write_text(
        "name,asset_class,currency,units,source_symbol,csv_url\n"
        "FundA,MUTUAL_FUNDS,JPY,20000,FundA,\n",
        encoding="utf-8",
    )
    external_json.write_text(json.dumps({}), encoding="utf-8")
    _write_history(history_dir, "FundA", "基準日,基準価額\nN/A,12000\n")

    ledger = UniversalIngester(
        funds_csv_path=str(funds_csv),
        external_assets_path=str(external_json),
        history_dir=str(history_dir),
        is_closed_fn=is_market_closed,
        input_store=CanonicalLedgerInputRepository(),
    ).build_shadow_ledger("2026-04-20")

    assert len(ledger.assets) == 1
    assert ledger.assets[0].pricing_status == "MISSING"
