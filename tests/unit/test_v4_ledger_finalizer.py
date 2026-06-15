from unittest.mock import MagicMock

from src.domain.ledger_schema import ShadowAssetRecord, ShadowLedger
from src.domain.v4_ledger_finalizer import V4LedgerFinalizer


def _shadow() -> ShadowLedger:
    return ShadowLedger(
        target_date="2026-04-29",
        generated_at="2026-04-29T20:00:00",
        ssot_a_path="data/collection/market_units.csv",
        ssot_b_path="data/external_assets.json",
        ssot_b_active_key="2026-04",
        total_value_jpy=3000,
        assets=[
            ShadowAssetRecord(
                source="MARKET_UNITS",
                name="JP Fund",
                asset_class="MUTUAL_FUNDS",
                category="MUTUAL_FUNDS",
                current_value_jpy=1000,
                diff_val_jpy=120.0,
                diff_pct=1.2,
                pricing_status="PRICED",
            ),
            ShadowAssetRecord(
                source="MARKET_UNITS",
                name="US Stock",
                asset_class="US_STOCK",
                category="US_STOCK",
                current_value_jpy=1000,
                diff_val_jpy=220.0,
                diff_pct=2.2,
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


def test_finalize_zeroes_jp_market_diff_on_holiday() -> None:
    timeline = MagicMock()
    timeline.is_holiday.return_value = True

    finalizer = V4LedgerFinalizer(timeline)
    finalized = finalizer.finalize(_shadow())

    jp_fund = finalized.assets[0]
    us_stock = finalized.assets[1]
    cash = finalized.assets[2]

    assert jp_fund.diff_val_jpy == 0.0
    assert jp_fund.diff_pct == 0.0
    assert us_stock.diff_val_jpy == 220.0
    assert us_stock.diff_pct == 2.2
    assert cash.diff_val_jpy == 0.0
    assert cash.diff_pct == 0.0
    timeline.is_holiday.assert_called_once_with("2026-04-29")
