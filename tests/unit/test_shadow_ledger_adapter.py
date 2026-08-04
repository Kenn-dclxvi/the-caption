import tempfile
from unittest.mock import patch

from src.domain.ledger_schema import ShadowAssetRecord, ShadowLedger
from src.domain.shadow_ledger_adapter import ShadowLedgerAdapter
from src.infra.ledger_repository import LedgerRepository


def test_shadow_ledger_adapter_creates_legacy_ledger_for_existing_dispatcher():
    shadow = ShadowLedger(
        target_date="2026-04-25",
        generated_at="2026-04-25T00:00:00",
        ssot_a_path="data/collection/market_units.csv",
        ssot_b_path="data/external_assets.json",
        ssot_b_active_key="2026-04",
        total_value_jpy=3000,
        basis_active_key="2026-04",
        return_base_value_jpy=2000,
        total_acquisition_cost_jpy=1500,
        total_return_jpy=500,
        total_return_pct=33.3333333333,
        assets=[
            ShadowAssetRecord(
                source="MARKET_UNITS",
                name="FundA",
                asset_class="MUTUAL_FUNDS",
                category="MUTUAL_FUNDS",
                currency="JPY",
                units=2,
                price=1000,
                source_symbol="FUND_A",
                current_value_jpy=2000,
                diff_val_jpy=100,
                diff_pct=5.2631578947,
                wtd_pct=5.0,
                mtd_pct=6.0,
                ytd_pct=7.0,
                pricing_status="PRICED",
            ),
            ShadowAssetRecord(
                source="ABSOLUTE_AMOUNT",
                name="Cash",
                asset_class="CASH_EXTERNAL",
                category="CASH_EXTERNAL",
                current_value_jpy=1000,
                pricing_status="STATIC",
            ),
        ],
    )

    ledger = ShadowLedgerAdapter().to_legacy_ledger(shadow)

    assert ledger.meta.integrity_status == "VERIFIED"
    assert ledger.summary.total_assets_jpy == 3000
    assert ledger.summary.total_profit_loss_jpy == 500
    assert ledger.summary.capital_gain_jpy == 500
    assert ledger.summary.total_profit_loss_pct == 33.3333333333
    assert ledger.summary.cash_position_jpy == 1000
    assert ledger.summary.exposure_jpy == 2000
    assert ledger.summary.total_diff_jpy == 100
    assert ledger.summary.total_diff_pct == 5.26
    assert ledger.summary.total_wtd == "+5.00%"
    assert ledger.summary.total_mtd == "+6.00%"
    assert ledger.summary.total_ytd == "+7.00%"
    assert ledger.summary.class_totals == {"MUTUAL_FUNDS": 2000, "SHORT_TERM": 1000}
    assert ledger.assets[0].id == "FUND_A"
    assert ledger.assets[0].prev_day_diff_jpy == 100
    assert ledger.assets[0].prev_day_diff_pct == 5.2631578947
    assert ledger.assets[0].wtd == "+5.00%"
    assert ledger.assets[0].mtd == "+6.00%"
    assert ledger.assets[0].ytd == "+7.00%"
    assert ledger.assets[1].category == "CASH"
    assert ledger.assets[1].prev_day_diff_jpy == 0
    assert ledger.assets[1].wtd == "---"
    assert ledger.assets[1].mtd == "---"


def test_shadow_ledger_adapter_marks_missing_price_as_stagnant():
    shadow = ShadowLedger(
        target_date="2026-04-25",
        generated_at="2026-04-25T00:00:00",
        ssot_a_path="data/collection/market_units.csv",
        ssot_b_path="data/external_assets.json",
        ssot_b_active_key="2026-04",
        total_value_jpy=0,
        assets=[
            ShadowAssetRecord(
                source="MARKET_UNITS",
                name="Missing",
                asset_class="US_STOCK",
                category="US_STOCK",
                current_value_jpy=0,
                pricing_status="MISSING",
            ),
        ],
    )

    ledger = ShadowLedgerAdapter().to_legacy_ledger(shadow)

    assert ledger.meta.integrity_status == "STAGNANT"


def test_total_period_returns_use_period_start_equivalent_weights():
    shadow = ShadowLedger(
        target_date="2026-06-10",
        generated_at="2026-06-10T00:00:00",
        ssot_a_path="data/collection/market_units.csv",
        ssot_b_path="data/external_assets.json",
        ssot_b_active_key="2026-06",
        total_value_jpy=800,
        assets=[
            ShadowAssetRecord(
                source="MARKET_UNITS",
                name="Winner",
                asset_class="MUTUAL_FUNDS",
                category="MUTUAL_FUNDS",
                currency="JPY",
                current_value_jpy=200,
                wtd_pct=100.0,
                mtd_pct=100.0,
                ytd_pct=100.0,
                pricing_status="PRICED",
            ),
            ShadowAssetRecord(
                source="MARKET_UNITS",
                name="Flat",
                asset_class="JP_STOCK",
                category="JP_STOCK",
                currency="JPY",
                current_value_jpy=100,
                wtd_pct=0.0,
                mtd_pct=0.0,
                ytd_pct=0.0,
                pricing_status="PRICED",
            ),
            ShadowAssetRecord(
                source="ABSOLUTE_AMOUNT",
                name="Cash",
                asset_class="CASH_EXTERNAL",
                category="CASH_EXTERNAL",
                currency="JPY",
                current_value_jpy=500,
                pricing_status="STATIC",
            ),
        ],
    )

    ledger = ShadowLedgerAdapter().to_legacy_ledger(shadow)

    assert ledger.summary.total_wtd == "+50.00%"
    assert ledger.summary.total_mtd == "+50.00%"
    assert ledger.summary.total_ytd == "+50.00%"


def test_total_period_returns_do_not_underweight_a_loser_after_the_loss():
    shadow = ShadowLedger(
        target_date="2026-06-10",
        generated_at="2026-06-10T00:00:00",
        ssot_a_path="data/collection/market_units.csv",
        ssot_b_path="data/external_assets.json",
        ssot_b_active_key="2026-06",
        total_value_jpy=150,
        assets=[
            ShadowAssetRecord(
                source="MARKET_UNITS",
                name="Loser",
                asset_class="MUTUAL_FUNDS",
                category="MUTUAL_FUNDS",
                currency="JPY",
                current_value_jpy=50,
                ytd_pct=-50.0,
                pricing_status="PRICED",
            ),
            ShadowAssetRecord(
                source="MARKET_UNITS",
                name="Flat",
                asset_class="JP_STOCK",
                category="JP_STOCK",
                currency="JPY",
                current_value_jpy=100,
                ytd_pct=0.0,
                pricing_status="PRICED",
            ),
        ],
    )

    ledger = ShadowLedgerAdapter().to_legacy_ledger(shadow)

    assert ledger.summary.total_ytd == "-25.00%"


def test_v4_ledger_survives_repository_round_trip_for_weekly_monthly_readers():
    # v4 の確定台帳は LedgerRepository.load のスキーマ検証を通る必要がある。
    # 通らないと週次/月次が台帳を読めず、保存しても無意味になる。
    shadow = ShadowLedger(
        target_date="2026-08-04",
        generated_at="2026-08-04T18:30:02",
        ssot_a_path="data/collection/market_units.csv",
        ssot_b_path="data/external_assets.json",
        ssot_b_active_key="2026-08",
        total_value_jpy=1000,
        total_return_jpy=100,
        total_return_pct=11.11,
        assets=[
            ShadowAssetRecord(
                source="MARKET_UNITS",
                name="Gold",
                asset_class="COMMODITIES",
                category="COMMODITIES",
                currency="JPY",
                units=2.95568,
                price=4049.10009765625,
                source_symbol="GC=F",
                source_date="2026-07-31",
                current_value_jpy=1000,
                diff_val_jpy=-10,
                diff_pct=-1.2438720710539055,
                pricing_status="STALE",
            ),
        ],
    )
    document = ShadowLedgerAdapter().to_canonical_document(shadow)
    assert document["meta"]["integrity_status"] == "STAGNANT"

    with tempfile.TemporaryDirectory() as tmp_dir:
        with patch("src.infra.ledger_repository.DIR_CURRENT", tmp_dir):
            repo = LedgerRepository()
            repo.save_document(document, "2026-08-04")
            loaded = repo.load("2026-08-04")

    assert loaded is not None, "v4 ledger failed LedgerRepository schema validation"
    assert loaded["meta"]["target_date"] == "2026-08-04"
    assert loaded["meta"]["integrity_status"] == "STAGNANT"
    assert len(loaded["assets"]) == 1

    gold = loaded["assets"][0]
    # v4 で意味を持つ値は保持し、鮮度も正本に残る。
    assert gold["id"] == "GC=F"
    assert gold["price"] == 4049.10009765625
    assert gold["source_date"] == "2026-07-31"
    assert gold["pricing_status"] == "STALE"
    assert gold["units"] == 2.95568
    # v4 の計算元に資産別取得原価は存在しないため、ダミー値を持たせない。
    assert "acquisition_price" not in gold
    assert "profit_loss" not in gold
    assert "is_nisa" not in gold
