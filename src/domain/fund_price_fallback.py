"""Date-bound public fund-price candidate validation. No external I/O."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
import re
from uuid import UUID


class FundPriceError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise FundPriceError(code)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def uuid(value):
    try:
        require(isinstance(value, str) and str(UUID(value)) == value, "invalid_identifier")
    except (TypeError, ValueError):
        raise FundPriceError("invalid_identifier") from None
    return value


def decimal(value):
    require(isinstance(value, str) and len(value) <= 64
            and re.fullmatch(r"(?:0|[1-9]\d*)(?:\.\d+)?", value), "invalid_price")
    try:
        number = Decimal(value)
        require(number.is_finite() and number > 0 and number.adjusted() < 18
                and number.as_tuple().exponent >= -12, "invalid_price")
        return number
    except InvalidOperation:
        raise FundPriceError("invalid_price") from None


def validate_candidate(value, request, now):
    require(isinstance(value, dict) and set(value) == {
        "request_id", "asset_id", "target_price_date", "request_revision", "currency", "source",
        "retrieved_at", "source_price", "source_quote_units", "price", "price_quote_units",
    }, "invalid_candidate")
    for field in ("request_id", "asset_id", "target_price_date", "request_revision", "currency", "price_quote_units"):
        require(value[field] == request[field] and type(value[field]) is type(request[field]), "price_request_mismatch")
    require(value["source"] in ("monex_fund_detail", "sbi_securities_nav_history"), "invalid_price_source")
    quote = value["source_quote_units"]
    require(type(quote) is int and 0 < quote <= 9007199254740991, "invalid_price_units")
    try:
        observed = datetime.fromisoformat(value["retrieved_at"])
        require(observed.tzinfo is not None and observed <= now, "invalid_price_receipt_time")
        require(observed.date() >= date.fromisoformat(request["target_price_date"]), "invalid_price_receipt_time")
    except (TypeError, ValueError):
        raise FundPriceError("invalid_price_receipt_time") from None
    with localcontext() as ctx:
        ctx.prec = 160
        require(decimal(value["price"]) * quote == decimal(value["source_price"]) * value["price_quote_units"],
                "price_unit_mismatch")
    return value
