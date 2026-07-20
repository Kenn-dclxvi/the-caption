from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.domain.guard_rail import GuardRail
from src.domain.ledger_schema import ShadowAssetRecord, ShadowLedger


def _ledger(*assets: ShadowAssetRecord) -> ShadowLedger:
    return ShadowLedger(
        target_date="2026-04-25",
        generated_at="2026-04-25T00:00:00",
        ssot_a_path="data/collection/market_units.csv",
        ssot_b_path="data/external_assets.json",
        ssot_b_active_key="2026-04",
        total_value_jpy=sum(asset.current_value_jpy for asset in assets),
        assets=list(assets),
    )


def _asset(name: str, value: float, status: str) -> ShadowAssetRecord:
    return ShadowAssetRecord(
        source="MARKET_UNITS" if status == "MISSING" else "ABSOLUTE_AMOUNT",
        name=name,
        asset_class="MUTUAL_FUNDS" if status == "MISSING" else "CASH",
        category="MUTUAL_FUNDS" if status == "MISSING" else "CASH",
        current_value_jpy=value,
        pricing_status=status,
    )


def test_context_scope_does_not_bypass_completion_lock():
    timeline = MagicMock()
    guard = GuardRail(timeline)

    with patch("src.domain.guard_rail.SystemUtils.get_flag", return_value="2026-04-25"):
        result = guard.should_proceed(
            target_date_str="2026-04-25",
            lock_file="completion.lock",
            force_send=False,
            scope="context",
            format_test=False,
        )

    assert result is False
    timeline.is_holiday.assert_not_called()


def test_empty_shadow_ledger_cannot_dispatch():
    guard = GuardRail(MagicMock())

    assert guard.should_dispatch_shadow_ledger(_ledger(), allow_missing=True) is False


@pytest.mark.parametrize("total", [0, -1, float("nan")])
def test_non_positive_or_invalid_total_cannot_dispatch(total):
    guard = GuardRail(MagicMock())
    shadow = SimpleNamespace(assets=[_asset("Cash", 100, "STATIC")], total_value_jpy=total)

    assert guard.should_dispatch_shadow_ledger(shadow, allow_missing=True) is False


def test_positive_shadow_ledger_with_some_missing_assets_remains_dispatchable():
    guard = GuardRail(MagicMock())
    shadow = _ledger(
        _asset("Missing Fund", 0, "MISSING"),
        _asset("Cash", 1000, "STATIC"),
    )

    assert guard.should_dispatch_shadow_ledger(shadow, allow_missing=True) is True
