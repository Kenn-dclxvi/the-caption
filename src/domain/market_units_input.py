"""Validate Market Units input without reading files or fetching price sources.

The input editor permits an empty collection; the daily snapshot domain has its
own, stricter publication checks. IDs are allocated by the repository only after
this module accepts the complete replacement.
"""

from collections.abc import Mapping
from decimal import Decimal, localcontext
import ipaddress
import re
from typing import Final, TypedDict, cast
from urllib.parse import urlsplit

from src.domain.market_units_snapshot import build_asset_key


MARKET_UNIT_FIELDS: Final[tuple[str, ...]] = (
    "name", "asset_class", "currency", "units", "source_symbol",
    "audit_match_key", "csv_url",
)
_WRITE_FIELDS: Final = frozenset((*MARKET_UNIT_FIELDS, "asset_id"))
_MAX_ITEMS: Final = 5000
_DECIMAL: Final = re.compile(r"(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,12})?")
_UUID: Final = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_DNS_LABEL: Final = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_CONTROL: Final = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_URL_ENCODED_CONTROL: Final = re.compile(r"%(?:0[0-9a-f]|1[0-9a-f]|7f)|%c2%[89][0-9a-f]", re.I)


class InputFieldError(TypedDict):
    pointer: str
    code: str
    message: str


class NormalizedMarketUnitFields(TypedDict):
    name: str
    asset_class: str
    currency: str
    units: str
    source_symbol: str
    audit_match_key: str
    csv_url: str
    asset_key: str


class NormalizedMarketUnit(NormalizedMarketUnitFields):
    asset_id: str | None


class MarketUnitsInputError(ValueError):
    """Validation details safe to include in a Problem Details response."""

    def __init__(self, errors: list[InputFieldError]) -> None:
        self.errors = errors
        super().__init__("Market Units input is invalid.")


def _error(errors: list[InputFieldError], pointer: str, code: str, message: str) -> None:
    errors.append({"pointer": pointer, "code": code, "message": message})


def _pointer(base: str, field: object) -> str:
    return base + "/" + str(field).replace("~", "~0").replace("/", "~1")


def _text(
    value: object,
    pointer: str,
    errors: list[InputFieldError],
    *,
    required: bool = False,
    uppercase: bool = False,
) -> str | None:
    limit = 256 if required else 1024
    if not isinstance(value, str):
        _error(errors, pointer, "normalized_value_invalid", "A text value is required.")
        return None
    if _CONTROL.search(value):
        _error(errors, pointer, "normalized_value_invalid", "Control characters are not allowed.")
        return None
    if len(value) > limit:
        _error(errors, pointer, "normalized_value_invalid", f"Text must not exceed {limit} characters.")
        return None
    result = value.strip()
    if uppercase:
        result = result.upper()
    if (required and not result) or len(result) > limit:
        _error(errors, pointer, "normalized_value_invalid", "Normalized text is blank or exceeds its limit.")
        return None
    return result


def _units(
    value: object, pointer: str, errors: list[InputFieldError], *, preserve: bool,
) -> str | None:
    if not isinstance(value, str) or _DECIMAL.fullmatch(value) is None:
        _error(
            errors, pointer, "invalid_decimal",
            "Use a nonnegative decimal string with at most 18 integer and 12 fractional digits.",
        )
        return None
    if preserve:
        return value
    # Decimal.normalize() uses context precision, including when the input was
    # constructed exactly. Isolate enough precision for all 30 allowed digits.
    with localcontext() as context:
        context.prec = 32
        return format(Decimal(value).normalize(), "f")


def _allowed_price_url(value: str, allowed_hosts: set[str] | None) -> bool:
    """Check new configuration only; DNS resolution belongs to fetch policy."""
    if not value:
        return True
    if "\\" in value or any(ch.isspace() for ch in value) or _URL_ENCODED_CONTROL.search(value):
        return False
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        if (
            parsed.scheme != "https" or not hostname or parsed.username is not None
            or parsed.password is not None or parsed.fragment or parsed.port not in (None, 443)
        ):
            return False
        # No IP literals, single-label/private names, wildcard matching, or
        # subdomain inheritance. Hosts are explicitly injected by the app.
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            pass
        else:
            return False
        labels = hostname.split(".")
        if (
            len(hostname) > 253 or len(labels) < 2
            or any(_DNS_LABEL.fullmatch(label) is None for label in labels)
            or not any("a" <= ch <= "z" for ch in labels[-1])
            or labels[-1] in {"localhost", "local", "internal", "test", "invalid"}
        ):
            return False
        return hostname in {host.lower() for host in (allowed_hosts or set())}
    except ValueError:
        return False


def _normalize_rows(
    items: object,
    existing_ids: set[str],
    *,
    legacy: bool,
    allowed_price_hosts: set[str] | None,
    existing_price_urls: Mapping[str, str] | None,
) -> list[NormalizedMarketUnit]:
    errors: list[InputFieldError] = []
    if not isinstance(items, list):
        raise MarketUnitsInputError([{
            "pointer": "/items", "code": "normalized_value_invalid", "message": "Items must be an array.",
        }])
    if len(items) > _MAX_ITEMS:
        raise MarketUnitsInputError([{
            "pointer": "/items", "code": "normalized_value_invalid", "message": "At most 5000 items are allowed.",
        }])
    normalized: list[NormalizedMarketUnit] = []
    seen_ids: set[str] = set()
    seen_keys: set[str] = set()
    for index, item in enumerate(items):
        base = f"/items/{index}"
        if not isinstance(item, dict):
            _error(errors, base, "normalized_value_invalid", "Each item must be an object.")
            continue
        row_start = len(errors)
        if not legacy:
            for field in sorted(_WRITE_FIELDS - item.keys()):
                _error(errors, _pointer(base, field), "normalized_value_invalid", "Required field is missing.")
            for field in sorted(item.keys() - _WRITE_FIELDS, key=str):
                _error(errors, _pointer(base, field), "normalized_value_invalid", "Unknown field is not allowed.")
        asset_id = None if legacy else item.get("asset_id")
        if asset_id is not None:
            if not isinstance(asset_id, str) or _UUID.fullmatch(asset_id) is None:
                _error(errors, base + "/asset_id", "normalized_value_invalid", "Asset ID must be a UUID or null.")
                asset_id = None
            else:
                asset_id = asset_id.lower()
                if asset_id not in existing_ids:
                    _error(errors, base + "/asset_id", "unknown_identifier", "Asset ID is not part of this resource.")
                if asset_id in seen_ids:
                    _error(errors, base + "/asset_id", "duplicate_id", "Asset ID is repeated.")
                seen_ids.add(asset_id)
        values: dict[str, str] = {}
        for field in MARKET_UNIT_FIELDS:
            raw_value = item.get(field)
            if legacy:
                if field == "asset_class" and (raw_value is None or raw_value == ""):
                    raw_value = "MUTUAL_FUNDS"
                elif field == "currency" and (raw_value is None or raw_value == ""):
                    raw_value = "JPY"
                elif field in {"source_symbol", "audit_match_key", "csv_url"} and raw_value is None:
                    raw_value = ""
                if (
                    field in {"asset_class", "currency"} and isinstance(raw_value, str)
                    and not raw_value.strip() and not _CONTROL.search(raw_value)
                ):
                    raw_value = "MUTUAL_FUNDS" if field == "asset_class" else "JPY"
            if field == "units":
                value = _units(raw_value, base + "/units", errors, preserve=legacy)
            else:
                value = _text(
                    raw_value, _pointer(base, field), errors,
                    required=field in {"name", "asset_class", "currency"},
                    uppercase=field in {"asset_class", "currency"},
                )
            if value is not None:
                values[field] = value
        if len(errors) != row_start:
            continue
        values["source_symbol"] = values["source_symbol"] or values["name"]
        url_unchanged = (
            asset_id is not None and existing_price_urls is not None
            and asset_id in existing_price_urls and values["csv_url"] == existing_price_urls[asset_id]
        )
        if not legacy and not url_unchanged and not _allowed_price_url(values["csv_url"], allowed_price_hosts):
            _error(
                errors, base + "/csv_url", "normalized_value_invalid",
                "A new price source must be an HTTPS URL on an explicitly allowed host, or empty.",
            )
        asset_key = build_asset_key(values)
        if not asset_key or len(asset_key) > 2048:
            _error(errors, base + "/asset_key", "normalized_value_invalid", "Normalized asset key exceeds its limit.")
        if asset_key in seen_keys:
            _error(errors, base + "/audit_match_key", "duplicate_asset_key", "Normalized asset key is repeated.")
        seen_keys.add(asset_key)
        normalized.append(cast(NormalizedMarketUnit, {**values, "asset_key": asset_key, "asset_id": asset_id}))
    if errors:
        raise MarketUnitsInputError(errors)
    return normalized


def normalize_input_rows(
    items: object,
    existing_ids: set[str] | None = None,
    *,
    allowed_price_hosts: set[str] | None = None,
    existing_price_urls: Mapping[str, str] | None = None,
) -> list[NormalizedMarketUnit]:
    """Validate API rows, leaving null IDs unassigned for the repository."""
    return _normalize_rows(
        items, existing_ids or set(), legacy=False,
        allowed_price_hosts=allowed_price_hosts, existing_price_urls=existing_price_urls,
    )


def validate_replacement(
    payload: object,
    existing_ids: set[str],
    *,
    allowed_price_hosts: set[str] | None = None,
    existing_price_urls: Mapping[str, str] | None = None,
) -> list[NormalizedMarketUnit]:
    """Validate whole-replacement shape and explicit empty-collection intent."""
    errors: list[InputFieldError] = []
    if not isinstance(payload, dict):
        raise MarketUnitsInputError([{
            "pointer": "", "code": "normalized_value_invalid", "message": "Request body must be an object.",
        }])
    expected = {"items", "clear_all"}
    for field in sorted(expected - payload.keys()):
        _error(errors, _pointer("", field), "normalized_value_invalid", "Required field is missing.")
    for field in sorted(payload.keys() - expected, key=str):
        _error(errors, _pointer("", field), "normalized_value_invalid", "Unknown field is not allowed.")
    items, clear_all = payload.get("items"), payload.get("clear_all")
    if not isinstance(clear_all, bool) or (isinstance(items, list) and clear_all != (len(items) == 0)):
        _error(errors, "/clear_all", "invalid_clear_intent", "Clear all must be true exactly when items is empty.")
    if errors:
        raise MarketUnitsInputError(errors)
    return normalize_input_rows(
        items, existing_ids, allowed_price_hosts=allowed_price_hosts,
        existing_price_urls=existing_price_urls,
    )


def normalize_legacy_rows(
    rows: object, *, allowed_price_hosts: set[str] | None = None,
) -> list[NormalizedMarketUnitFields]:
    """Validate imported CSV values without changing exact quantity strings.

    Existing source configurations are preserved, even when no host is enabled
    for new API settings. Unknown CSV metadata is retained separately by the
    repository. Migration neither fetches URLs nor invents IDs.
    """
    normalized = _normalize_rows(
        rows, set(), legacy=True, allowed_price_hosts=allowed_price_hosts,
        existing_price_urls=None,
    )
    return [cast(NormalizedMarketUnitFields, {key: value for key, value in row.items() if key != "asset_id"}) for row in normalized]
