"""Market Units API boundaries, exact quantities, and legacy compatibility."""

from copy import deepcopy
from decimal import getcontext, localcontext

import pytest

from src.domain.market_units_input import (
    MARKET_UNIT_FIELDS,
    MarketUnitsInputError,
    normalize_input_rows,
    normalize_legacy_rows,
    validate_replacement,
)


KNOWN_ID = "a1234567-89ab-4cde-8fab-0123456789ab"
OTHER_ID = "b1234567-89ab-4cde-8fab-0123456789ab"


def item(**changes):
    return {
        "asset_id": None, "name": " Fund ", "asset_class": " custom_class ",
        "currency": " xcoin ", "units": "1.000", "source_symbol": "",
        "audit_match_key": "", "csv_url": "", **changes,
    }


def errors_for(rows, **kwargs):
    with pytest.raises(MarketUnitsInputError) as caught:
        normalize_input_rows(rows, **kwargs)
    return {(error["pointer"], error["code"]) for error in caught.value.errors}


def test_normalizes_all_seven_fields_without_mutating_or_allocating_ids():
    rows = [item(audit_match_key=" history-id ")]
    original = deepcopy(rows)
    result = normalize_input_rows(rows)
    assert result == [{
        "asset_id": None, "name": "Fund", "asset_class": "CUSTOM_CLASS",
        "currency": "XCOIN", "units": "1", "source_symbol": "Fund",
        "audit_match_key": "history-id", "csv_url": "", "asset_key": "history-id",
    }]
    assert rows == original
    assert set(MARKET_UNIT_FIELDS) == set(result[0]) - {"asset_id", "asset_key"}


def test_preserves_order_and_existing_identity_after_edit():
    result = normalize_input_rows([
        item(asset_id=KNOWN_ID.upper(), name="Renamed", units="0"),
        item(name="Added", source_symbol=" custom "),
    ], {KNOWN_ID})
    assert [row["name"] for row in result] == ["Renamed", "Added"]
    assert [row["asset_id"] for row in result] == [KNOWN_ID, None]
    assert result[1]["source_symbol"] == "custom"
    assert result[1]["asset_key"] == "CUSTOM_CLASS:XCOIN:custom"


@pytest.mark.parametrize("raw,normalized", [
    ("0", "0"), ("0.000000000000", "0"), ("1.010000000000", "1.01"),
    ("999999999999999999.999999999999", "999999999999999999.999999999999"),
    ("100000000000000000.000000000001", "100000000000000000.000000000001"),
])
def test_quantities_are_exact_even_under_small_decimal_context(raw, normalized):
    with localcontext() as context:
        context.prec = 6
        assert normalize_input_rows([item(units=raw)])[0]["units"] == normalized
        assert getcontext().prec == 6


@pytest.mark.parametrize("raw", [
    None, True, False, 0, 1.25, "", "-1", "+1", "-0", "1e2", "NaN", "Infinity",
    " 1", "1 ", "01", ".5", "1.", "1,000", "１", "1\n",
    "1000000000000000000", "0.0000000000001",
])
def test_rejects_noncanonical_or_inexact_quantity_inputs(raw):
    assert ("/items/0/units", "invalid_decimal") in errors_for([item(units=raw)])


@pytest.mark.parametrize("field", ["name", "asset_class", "currency", "source_symbol", "audit_match_key", "csv_url"])
@pytest.mark.parametrize("value", [None, 123, "a\x00b", "\tb", "a\x7fb", "a\x85b", "a\x9fb"])
def test_rejects_nontext_and_all_control_ranges(field, value):
    assert (f"/items/0/{field}", "normalized_value_invalid") in errors_for([item(**{field: value})])


@pytest.mark.parametrize("field", ["name", "asset_class", "currency"])
def test_required_text_must_be_nonblank_after_trim(field):
    assert (f"/items/0/{field}", "normalized_value_invalid") in errors_for([item(**{field: "   "})])


def test_rejects_limits_before_trim_and_after_unicode_uppercase():
    assert ("/items/0/name", "normalized_value_invalid") in errors_for([item(name=" " * 257 + "a")])
    assert ("/items/0/currency", "normalized_value_invalid") in errors_for([item(currency="ß" * 129)])
    assert normalize_input_rows([item(currency="ß" * 128)])[0]["currency"] == "SS" * 128
    assert ("/items/0/source_symbol", "normalized_value_invalid") in errors_for([item(source_symbol="s" * 1025)])


@pytest.mark.parametrize("field", ["asset_id", *MARKET_UNIT_FIELDS])
def test_every_write_field_is_required(field):
    value = item()
    del value[field]
    assert (f"/items/0/{field}", "normalized_value_invalid") in errors_for([value])


def test_rejects_unknown_fields_including_derived_key_with_json_pointer_escaping():
    result = errors_for([item(asset_key="injected", **{"x/y~z": 1})])
    assert ("/items/0/asset_key", "normalized_value_invalid") in result
    assert ("/items/0/x~1y~0z", "normalized_value_invalid") in result


@pytest.mark.parametrize("value", [1, True, "", "a" * 32, "{" + KNOWN_ID + "}", " " + KNOWN_ID])
def test_rejects_invalid_identifiers(value):
    assert ("/items/0/asset_id", "normalized_value_invalid") in errors_for([item(asset_id=value)])


def test_rejects_unknown_and_duplicate_identifiers():
    assert ("/items/0/asset_id", "unknown_identifier") in errors_for([item(asset_id=OTHER_ID)], existing_ids={KNOWN_ID})
    result = errors_for([
        item(asset_id=KNOWN_ID), item(asset_id=KNOWN_ID.upper(), name="Other"),
    ], existing_ids={KNOWN_ID})
    assert ("/items/1/asset_id", "duplicate_id") in result


def test_rejects_duplicate_keys_after_fallback_trim_and_uppercase():
    result = errors_for([item(), item(name="Fund", asset_class="CUSTOM_CLASS", source_symbol=" Fund ")])
    assert ("/items/1/audit_match_key", "duplicate_asset_key") in result
    result = errors_for([item(audit_match_key="custom"), item(name="Other", audit_match_key=" custom ")])
    assert ("/items/1/audit_match_key", "duplicate_asset_key") in result
    result = errors_for([item(), item(name="Other", audit_match_key="CUSTOM_CLASS:XCOIN:Fund")])
    assert ("/items/1/audit_match_key", "duplicate_asset_key") in result


@pytest.mark.parametrize("rows", [None, {}, "", [None], [1], [True]])
def test_rejects_invalid_collection_shape(rows):
    assert errors_for(rows)


def test_item_count_limit_and_empty_rows():
    assert normalize_input_rows([]) == []
    assert errors_for([item()] * 5001) == {("/items", "normalized_value_invalid")}
    assert len(normalize_input_rows([item(name=str(index)) for index in range(5000)])) == 5000


@pytest.mark.parametrize("payload", [
    None, [], {}, {"items": []}, {"clear_all": True},
    {"items": [], "clear_all": True, "revision": "unexpected"},
    {"items": {}, "clear_all": True},
])
def test_replacement_shape_rejects_missing_unknown_and_invalid_fields(payload):
    with pytest.raises(MarketUnitsInputError):
        validate_replacement(payload, set())


@pytest.mark.parametrize("rows,flag", [([], False), ([], 1), ([], "true"), ([item()], True), ([item()], 0)])
def test_clear_intent_is_boolean_and_matches_empty_state(rows, flag):
    with pytest.raises(MarketUnitsInputError) as caught:
        validate_replacement({"items": rows, "clear_all": flag}, set())
    assert any(error["code"] == "invalid_clear_intent" for error in caught.value.errors)


def test_empty_to_empty_requires_explicit_intent_and_nonempty_is_accepted():
    assert validate_replacement({"items": [], "clear_all": True}, set()) == []
    assert len(validate_replacement({"items": [item()], "clear_all": False}, set())) == 1


def test_new_url_requires_exact_configured_host_and_https():
    url = "https://prices.example.com/nav.csv?code=123"
    assert ("/items/0/csv_url", "normalized_value_invalid") in errors_for([item(csv_url=url)])
    assert normalize_input_rows([item(csv_url=" " + url + " ")], allowed_price_hosts={"prices.example.com"})[0]["csv_url"] == url
    assert errors_for([item(csv_url=url)], allowed_price_hosts={"example.com"})
    assert errors_for([item(csv_url="https://evil.prices.example.com/nav.csv")], allowed_price_hosts={"prices.example.com"})
    assert normalize_input_rows(
        [item(csv_url="https://prices.example.com/%E3%81%82.csv")], allowed_price_hosts={"prices.example.com"},
    )[0]["csv_url"].endswith("%E3%81%82.csv")


@pytest.mark.parametrize("url,host", [
    ("http://prices.example.com/nav.csv", "prices.example.com"),
    ("file:///etc/passwd", "prices.example.com"),
    ("yfinance:ABC", "prices.example.com"),
    ("https://user:secret@prices.example.com/nav", "prices.example.com"),
    ("https://prices.example.com:8443/nav", "prices.example.com"),
    ("https://prices.example.com:broken/nav", "prices.example.com"),
    ("https://prices.example.com/nav#part", "prices.example.com"),
    ("https://prices.example.com/a b", "prices.example.com"),
    ("https://prices.example.com/a%0a", "prices.example.com"),
    ("https://prices.example.com\\@evil.example/nav", "evil.example"),
    ("https://127.0.0.1/nav", "127.0.0.1"),
    ("https://8.8.8.8/nav", "8.8.8.8"),
    ("https://[::1]/nav", "::1"),
    ("https://localhost/nav", "localhost"),
    ("https://host.local/nav", "host.local"),
    ("https://host.internal/nav", "host.internal"),
    ("https://127.1/nav", "127.1"),
    ("https://prices.example.com./nav", "prices.example.com."),
])
def test_rejects_unsafe_or_unsupported_new_source_configuration(url, host):
    assert errors_for([item(csv_url=url)], allowed_price_hosts={host})


def test_registered_url_compatibility_is_tied_to_exact_existing_id_and_value():
    old_url = "http://legacy.example.com/nav.csv"
    result = normalize_input_rows([item(asset_id=KNOWN_ID, csv_url=old_url)], {KNOWN_ID}, existing_price_urls={KNOWN_ID: old_url})
    assert result[0]["csv_url"] == old_url
    assert errors_for([item(csv_url=old_url)], existing_price_urls={KNOWN_ID: old_url})
    assert errors_for([item(asset_id=KNOWN_ID, csv_url=old_url + "?different")], existing_ids={KNOWN_ID}, existing_price_urls={KNOWN_ID: old_url})
    assert normalize_input_rows([item(asset_id=KNOWN_ID, csv_url="")], {KNOWN_ID}, existing_price_urls={KNOWN_ID: old_url})[0]["csv_url"] == ""


def test_legacy_migration_preserves_exact_units_and_keeps_defaults_without_ids():
    rows = [{
        "name": " Fund ", "units": "999999999999999999.999999999990",
        "csv_url": "http://legacy.example.com/nav.csv", "enabled": "false", "custom": "retained elsewhere",
    }]
    original = deepcopy(rows)
    result = normalize_legacy_rows(rows)
    assert result == [{
        "name": "Fund", "units": rows[0]["units"], "asset_class": "MUTUAL_FUNDS",
        "currency": "JPY", "source_symbol": "Fund", "audit_match_key": "",
        "csv_url": rows[0]["csv_url"], "asset_key": "MUTUAL_FUNDS:JPY:Fund",
    }]
    assert rows == original


@pytest.mark.parametrize("units", [None, 1.0, "-2", "1e3", " 1 ", "bad"])
def test_legacy_invalid_units_are_rejected_without_coercion(units):
    with pytest.raises(MarketUnitsInputError):
        normalize_legacy_rows([{"name": "Fund", "units": units}])


def test_legacy_duplicate_keys_and_invalid_fields_remain_rejected():
    with pytest.raises(MarketUnitsInputError):
        normalize_legacy_rows([{"name": "Fund", "units": "1"}] * 2)
    with pytest.raises(MarketUnitsInputError):
        normalize_legacy_rows([{"name": "Fund\x00", "units": "1"}])
    with pytest.raises(MarketUnitsInputError):
        normalize_legacy_rows([{"name": "Fund", "units": "1", "asset_class": "\t"}])
