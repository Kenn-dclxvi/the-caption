"""Pure validation for month-keyed External Assets and Portfolio Basis inputs."""

from decimal import Decimal, localcontext
import re
from typing import TypedDict

from src.domain.market_units_input import InputFieldError, MarketUnitsInputError


RESOURCES = frozenset({"external-assets", "portfolio-basis"})
_MONTH = re.compile(r"(?!0000)[0-9]{4}-(?:0[1-9]|1[0-2])")
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,12})?")
_UUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


class ExternalEntry(TypedDict):
    entry_id: str | None
    category: str
    amount: str
    name: str


class BasisEntry(TypedDict):
    entry_id: str | None
    total_acquisition_cost_jpy: str


class ExternalMonth(TypedDict):
    items: list[ExternalEntry]


Months = dict[str, ExternalMonth] | dict[str, BasisEntry]


class MonthlyInputError(MarketUnitsInputError):
    pass


def _fail(pointer: str, code: str = "normalized_value_invalid") -> None:
    raise MonthlyInputError([InputFieldError(pointer=pointer, code=code,
                                             message="Invalid monthly input; check this field against the API schema.")])


def _object(value: object, fields: set[str], pointer: str) -> dict:
    if not isinstance(value, dict) or set(value) != fields:
        _fail(pointer)
    return value


def _text(value: object, pointer: str, *, required: bool) -> str:
    limit = 256 if required else 1024
    if not isinstance(value, str) or len(value) > limit or _CONTROL.search(value):
        _fail(pointer)
    result = value.strip()
    if required and not result:
        _fail(pointer)
    return result


def _decimal(value: object, pointer: str, *, positive: bool, legacy: bool) -> str:
    if legacy and isinstance(value, (int, Decimal)) and not isinstance(value, bool):
        value = str(value) if isinstance(value, int) else format(value, "f")
    if not isinstance(value, str) or not _DECIMAL.fullmatch(value):
        _fail(pointer, "invalid_decimal")
    number = Decimal(value)
    if positive and number <= 0:
        _fail(pointer, "invalid_decimal")
    with localcontext() as context:
        context.prec = 32
        return format(number.normalize(), "f")


def entries(months: Months, resource: str):
    for record in months.values():
        yield from record["items"] if resource == "external-assets" else [record]


def is_clear(payload: object, resource: str) -> bool:
    """Detect explicit clear intent and empty data before granting write access."""
    if not isinstance(payload, dict):
        return False
    if payload.get("clear_all") is True:
        return True
    months = payload.get("months")
    if not isinstance(months, dict):
        return False
    if resource == "portfolio-basis":
        return not months
    return all(isinstance(record, dict) and record.get("items") == [] for record in months.values())


def normalize_months(value: object, resource: str, existing_ids: set[str], *, legacy: bool = False) -> Months:
    if resource not in RESOURCES:
        raise ValueError("Unknown monthly resource")
    if not isinstance(value, dict) or len(value) > 1200:
        _fail("/months")
    # The original flat external-assets document is the default input for all months.
    if legacy and resource == "external-assets" and set(value) == {"items"}:
        value = {"default": value}
    result = {}
    seen = set()
    count = 0
    for month, record in value.items():
        pointer = "/months/" + str(month).replace("~", "~0").replace("/", "~1")
        if not isinstance(month, str) or (month != "default" and not _MONTH.fullmatch(month)):
            _fail(pointer, "invalid_month")
        if resource == "external-assets":
            _object(record, {"items"}, pointer)
            if not isinstance(record["items"], list):
                _fail(pointer + "/items")
            rows = record["items"]
        else:
            rows = [record]
        output = []
        count += len(rows)
        if count > 5000:
            _fail("/months")
        for index, row in enumerate(rows):
            base = pointer + f"/items/{index}" if resource == "external-assets" else pointer
            fields = {"category", "amount", "name"} if resource == "external-assets" else {"total_acquisition_cost_jpy"}
            # Existing domain permits a missing external display name; never coerce other fields.
            if legacy and resource == "external-assets" and isinstance(row, dict) and "name" not in row:
                row = {**row, "name": ""}
            _object(row, fields if legacy else fields | {"entry_id"}, base)
            entry_id = None if legacy else row["entry_id"]
            if entry_id is not None:
                if not isinstance(entry_id, str) or not _UUID.fullmatch(entry_id):
                    _fail(base + "/entry_id")
                entry_id = entry_id.lower()
                if entry_id not in existing_ids:
                    _fail(base + "/entry_id", "unknown_identifier")
                if entry_id in seen:
                    _fail(base + "/entry_id", "duplicate_id")
                seen.add(entry_id)
            item = {"entry_id": entry_id}
            for field in fields:
                item[field] = (_decimal(row[field], base + "/" + field,
                                        positive=resource == "portfolio-basis", legacy=legacy)
                               if field in {"amount", "total_acquisition_cost_jpy"}
                               else _text(row[field], base + "/" + field, required=field == "category"))
            output.append(item)
        result[month] = {"items": output} if resource == "external-assets" else output[0]
    return result


def validate_replacement(payload: object, resource: str, existing_ids: set[str]) -> Months:
    _object(payload, {"months", "clear_all"}, "")
    months = normalize_months(payload["months"], resource, existing_ids)
    if not isinstance(payload["clear_all"], bool) or payload["clear_all"] != (not any(entries(months, resource))):
        _fail("/clear_all", "invalid_clear_intent")
    return months


def legacy_document(months: Months, resource: str) -> dict:
    """Keep decimal strings exact; the existing daily reader owns float conversion."""
    if resource == "external-assets":
        return {month: {"items": [{k: v for k, v in item.items() if k != "entry_id"}
                                  for item in record["items"]]} for month, record in months.items()}
    return {month: {"total_acquisition_cost_jpy": record["total_acquisition_cost_jpy"]}
            for month, record in months.items()}
