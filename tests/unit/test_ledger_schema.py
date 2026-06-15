import pytest
from src.domain.ledger_schema import ShadowAssetRecord, ShadowLedger, validate_ledger_dict, LedgerJsonSchema

_VALID = {
    "meta": {
        "target_date": "2026-02-28",
        "version": "3.3",
        "integrity_status": "VERIFIED",
        "generated_at": "2026-02-28T00:00:00",
        "has_next_day_record": False,
    },
    "summary": {
        "total_assets_jpy": 10_000_000,
        "total_profit_loss_jpy": 500_000,
        "cash_position_jpy": 1_000_000,
        "total_diff_jpy": -50_000,
        "total_diff_pct": -0.5,
        "total_profit_loss_pct": 5.0,
        "invested_capital_jpy": 9_500_000,
        "capital_gain_jpy": 500_000,
    },
    "assets": [],
}


def _patch(key_path: str, value) -> dict:
    import copy
    d = copy.deepcopy(_VALID)
    keys = key_path.split(".")
    node = d
    for k in keys[:-1]:
        node = node[k]
    node[keys[-1]] = value
    return d


def _remove(key_path: str) -> dict:
    import copy
    d = copy.deepcopy(_VALID)
    keys = key_path.split(".")
    node = d
    for k in keys[:-1]:
        node = node[k]
    del node[keys[-1]]
    return d


class TestValidateLedgerDict:

    def test_valid_dict_returns_true(self):
        assert validate_ledger_dict(_VALID) is True

    def test_missing_meta_returns_false(self):
        assert validate_ledger_dict(_remove("meta")) is False

    def test_missing_summary_returns_false(self):
        assert validate_ledger_dict(_remove("summary")) is False

    def test_missing_assets_returns_false(self):
        assert validate_ledger_dict(_remove("assets")) is False

    def test_invalid_date_format_returns_false(self):
        assert validate_ledger_dict(_patch("meta.target_date", "20260228")) is False

    def test_invalid_date_format_slashes_returns_false(self):
        assert validate_ledger_dict(_patch("meta.target_date", "2026/02/28")) is False

    def test_invalid_integrity_status_returns_false(self):
        assert validate_ledger_dict(_patch("meta.integrity_status", "UNKNOWN")) is False

    def test_stagnant_status_is_valid(self):
        assert validate_ledger_dict(_patch("meta.integrity_status", "STAGNANT")) is True

    def test_missing_total_assets_returns_false(self):
        assert validate_ledger_dict(_remove("summary.total_assets_jpy")) is False

    def test_assets_list_with_items_is_valid(self):
        d = _patch("assets", [{"id": "A1", "name": "Test", "value_jpy": 1_000_000}])
        assert validate_ledger_dict(d) is True

    def test_source_label_included_in_log_on_failure(self):
        from unittest.mock import patch
        with patch("src.domain.ledger_schema.logger") as mock_logger:
            validate_ledger_dict(_remove("meta"), source="ledger_20260228.json")
        error_msg = mock_logger.error.call_args[0][0]
        assert "ledger_20260228.json" in error_msg

    def test_empty_dict_returns_false(self):
        assert validate_ledger_dict({}) is False


class TestShadowLedgerSchema:

    def test_shadow_ledger_accepts_flat_assets(self):
        asset = ShadowAssetRecord(
            source="ABSOLUTE_AMOUNT",
            name="Cash",
            asset_class="CASH",
            category="CASH",
            current_value_jpy=1000,
            pricing_status="STATIC",
        )
        ledger = ShadowLedger(
            target_date="2026-04-25",
            generated_at="2026-04-25T00:00:00",
            ssot_a_path="data/collection/market_units.csv",
            ssot_b_path="data/external_assets.json",
            ssot_b_active_key="2026-04",
            total_value_jpy=1000,
            basis_active_key="2026-04",
            return_base_value_jpy=1000,
            total_acquisition_cost_jpy=900,
            total_return_jpy=100,
            total_return_pct=11.111,
            assets=[asset],
        )
        assert ledger.total_value_jpy == 1000
        assert ledger.basis_active_key == "2026-04"
        assert ledger.return_base_value_jpy == 1000
        assert ledger.total_return_jpy == 100
        assert ledger.assets[0].source == "ABSOLUTE_AMOUNT"

    def test_shadow_ledger_units_source_is_optional_for_legacy_compatibility(self):
        ledger = ShadowLedger(
            target_date="2026-04-25",
            generated_at="2026-04-25T00:00:00",
            ssot_a_path="data/collection/market_units.csv",
            ssot_b_path="data/external_assets.json",
            ssot_b_active_key="2026-04",
            total_value_jpy=0,
            assets=[],
        )
        assert ledger.units_source is None

    def test_shadow_ledger_rejects_total_mismatch(self):
        with pytest.raises(ValueError, match="total_value_jpy must match"):
            ShadowLedger(
                target_date="2026-04-25",
                generated_at="2026-04-25T00:00:00",
                ssot_a_path="data/collection/market_units.csv",
                ssot_b_path="data/external_assets.json",
                ssot_b_active_key="2026-04",
                total_value_jpy=999,
                assets=[
                    ShadowAssetRecord(
                        source="ABSOLUTE_AMOUNT",
                        name="Cash",
                        asset_class="CASH",
                        category="CASH",
                        current_value_jpy=1000,
                        pricing_status="STATIC",
                    )
                ],
            )
