import csv
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Final, List, Literal, Optional, TypedDict
from zoneinfo import ZoneInfo

from src.config.settings import DIR_COLLECTION, DIR_CURRENT
from src.lib.atomic_write import atomic_write_json

MARKET_UNITS_CSV: Final[str] = os.path.join(DIR_COLLECTION, "market_units.csv")
SNAPSHOT_SCHEMA_VERSION: Final[str] = "market_units_snapshot.v1"
SNAPSHOT_TYPE: Final[str] = "FULL_SNAPSHOT"
_SHA256_HEX_LENGTH: Final[int] = 64
_JST: Final[timezone] = timezone(timedelta(hours=9))
_REQUIRED_ITEM_FIELDS: Final[set[str]] = {
    "asset_key",
    "name",
    "asset_class",
    "currency",
    "units",
    "source_symbol",
    "audit_match_key",
    "csv_url",
}


class UnitsSource(TypedDict, total=False):
    type: Literal["SNAPSHOT", "LIVE_CSV"]
    path: str
    snapshot_target_date: str


class UnitsResolution(TypedDict):
    items: List[Dict[str, Any]]
    source: UnitsSource


class MarketUnitsSnapshotError(ValueError):
    pass


def snapshot_path(target_date: str, snapshot_dir: Optional[str] = None) -> str:
    compact_date = target_date.replace("-", "")
    return os.path.join(snapshot_dir or DIR_CURRENT, f"collection_units_{compact_date}.json")


def build_asset_key(row: Dict[str, Any]) -> str:
    audit_match_key = _clean(row.get("audit_match_key"))
    if audit_match_key:
        return audit_match_key

    asset_class = _clean(row.get("asset_class")).upper()
    currency = _clean(row.get("currency")).upper()
    source_symbol = _clean(row.get("source_symbol"))
    name = _clean(row.get("name"))
    identity = source_symbol or name
    return f"{asset_class}:{currency}:{identity}"


def load_market_units_csv(csv_path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            normalized = normalize_market_unit_row(row)
            rows.append(normalized)
    _validate_unique_asset_keys(rows)
    return rows


def normalize_market_unit_row(row: Dict[str, Any]) -> Dict[str, Any]:
    name = _clean(row.get("name"))
    asset_class = _clean(row.get("asset_class"), "MUTUAL_FUNDS").upper() or "MUTUAL_FUNDS"
    currency = _clean(row.get("currency"), "JPY").upper() or "JPY"
    source_symbol = _clean(row.get("source_symbol")) or name
    normalized: Dict[str, Any] = {
        "name": name,
        "asset_class": asset_class,
        "currency": currency,
        "units": _clean(row.get("units")),
        "source_symbol": source_symbol,
        "audit_match_key": _clean(row.get("audit_match_key")),
        "csv_url": _clean(row.get("csv_url")),
    }
    if "enabled" in row:
        normalized["enabled"] = _clean(row.get("enabled"))
    normalized["asset_key"] = build_asset_key(normalized)
    return normalized


def load_units_snapshot(path: str, target_date: str, ssot_a_path: str) -> List[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as exc:
        raise MarketUnitsSnapshotError(f"unreadable snapshot: {exc}") from exc

    if not isinstance(payload, dict):
        raise MarketUnitsSnapshotError("snapshot payload must be an object")
    if payload.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise MarketUnitsSnapshotError("snapshot schema_version mismatch")
    if payload.get("snapshot_type") != SNAPSHOT_TYPE:
        raise MarketUnitsSnapshotError("snapshot_type mismatch")
    if payload.get("target_date") != target_date:
        raise MarketUnitsSnapshotError("snapshot target_date mismatch")
    _validate_captured_at(payload.get("captured_at"))

    source = payload.get("source")
    if not isinstance(source, dict):
        raise MarketUnitsSnapshotError("snapshot source must be an object")
    if source.get("ssot_a_path") != ssot_a_path:
        raise MarketUnitsSnapshotError("snapshot source.ssot_a_path mismatch")
    _validate_ssot_a_sha256(source.get("ssot_a_sha256"))

    items = payload.get("items")
    if not isinstance(items, list):
        raise MarketUnitsSnapshotError("snapshot items must be a list")
    if not items:
        raise MarketUnitsSnapshotError("snapshot items must not be empty")

    normalized_items: List[Dict[str, Any]] = []
    for index, raw_item in enumerate(items):
        if not isinstance(raw_item, dict):
            raise MarketUnitsSnapshotError(f"snapshot item[{index}] must be an object")
        missing = sorted(_REQUIRED_ITEM_FIELDS - set(raw_item))
        if missing:
            raise MarketUnitsSnapshotError(f"snapshot item[{index}] missing fields: {missing}")
        _validate_units(raw_item.get("units"), index)
        item = normalize_market_unit_row(raw_item)
        if item["asset_key"] != _clean(raw_item.get("asset_key")):
            raise MarketUnitsSnapshotError(f"snapshot item[{index}] asset_key mismatch")
        normalized_items.append(item)

    _validate_unique_asset_keys(normalized_items)
    return normalized_items


def _validate_captured_at(value: Any) -> None:
    captured_at = _clean(value)
    if not captured_at:
        raise MarketUnitsSnapshotError("snapshot captured_at missing")
    try:
        parsed = datetime.fromisoformat(captured_at)
    except ValueError as exc:
        raise MarketUnitsSnapshotError("snapshot captured_at must be ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != _JST.utcoffset(None):
        raise MarketUnitsSnapshotError("snapshot captured_at must include JST timezone")


def _validate_ssot_a_sha256(value: Any) -> None:
    digest = _clean(value)
    if not digest:
        raise MarketUnitsSnapshotError("snapshot source.ssot_a_sha256 missing")
    if len(digest) != _SHA256_HEX_LENGTH or any(ch not in "0123456789abcdef" for ch in digest.lower()):
        raise MarketUnitsSnapshotError("snapshot source.ssot_a_sha256 must be a SHA-256 hex digest")


def _validate_units(value: Any, index: int) -> None:
    raw_units = _clean(value)
    if not raw_units:
        raise MarketUnitsSnapshotError(f"snapshot item[{index}] units missing")
    try:
        float(raw_units)
    except ValueError as exc:
        raise MarketUnitsSnapshotError(f"snapshot item[{index}] units must be numeric") from exc


def create_units_snapshot(
    csv_path: str = MARKET_UNITS_CSV,
    target_date: Optional[str] = None,
    output_path: Optional[str] = None,
    ssot_a_path: Optional[str] = None,
) -> Dict[str, Any]:
    active_date = target_date or datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d")
    items = load_market_units_csv(csv_path)
    payload = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "snapshot_type": SNAPSHOT_TYPE,
        "target_date": active_date,
        "captured_at": datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(timespec="seconds"),
        "source": {
            "ssot_a_path": ssot_a_path or csv_path,
            "ssot_a_sha256": _sha256_file(csv_path),
        },
        "items": items,
    }
    if output_path:
        if os.path.exists(output_path):
            raise FileExistsError(f"market units snapshot already exists: {output_path}")
        atomic_write_json(output_path, payload)
    return payload


def ensure_units_snapshot(
    target_date: str,
    csv_path: str = MARKET_UNITS_CSV,
    snapshot_dir: Optional[str] = None,
    allow_create: bool = True,
) -> str:
    """Validate and reuse a snapshot, or atomically create today's snapshot."""
    path = snapshot_path(target_date, snapshot_dir)
    if os.path.exists(path):
        load_units_snapshot(path, target_date, csv_path)
        return path
    if not allow_create:
        raise MarketUnitsSnapshotError(f"market units snapshot missing: {path}")
    create_units_snapshot(
        csv_path=csv_path,
        target_date=target_date,
        output_path=path,
        ssot_a_path=csv_path,
    )
    load_units_snapshot(path, target_date, csv_path)
    return path


def _validate_unique_asset_keys(rows: List[Dict[str, Any]]) -> None:
    seen: set[str] = set()
    for row in rows:
        key = build_asset_key(row)
        if key in seen:
            raise MarketUnitsSnapshotError(f"duplicate asset_key: {key}")
        seen.add(key)


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clean(value: Any, default: str = "") -> str:
    return str(value if value is not None else default).strip()
