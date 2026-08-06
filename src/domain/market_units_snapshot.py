"""Units snapshot の正規化と検証。

ファイル入出力は持たない。読み書きは
`src.infra.market_units_snapshot_repository` が担い、本モジュールは
受け取った dict / list の検証と正規化だけを行う。
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Final, List, Literal, TypedDict

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


def normalize_market_units_rows(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """CSV から読み出した行を正規化し、asset_key の一意性を検証する。"""
    rows = [normalize_market_unit_row(row) for row in raw_rows]
    validate_unique_asset_keys(rows)
    return rows


def build_snapshot_payload(
    items: List[Dict[str, Any]],
    target_date: str,
    ssot_a_path: str,
    ssot_a_sha256: str,
    captured_at: str,
) -> Dict[str, Any]:
    """snapshot の payload を組み立てる。時刻とハッシュは呼び出し側が決める。"""
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "snapshot_type": SNAPSHOT_TYPE,
        "target_date": target_date,
        "captured_at": captured_at,
        "source": {
            "ssot_a_path": ssot_a_path,
            "ssot_a_sha256": ssot_a_sha256,
        },
        "items": items,
    }


def validate_snapshot_payload(
    payload: Any,
    target_date: str,
    ssot_a_path: str,
) -> List[Dict[str, Any]]:
    """読み出した snapshot payload を検証し、正規化済み items を返す。"""
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

    validate_unique_asset_keys(normalized_items)
    return normalized_items


def validate_unique_asset_keys(rows: List[Dict[str, Any]]) -> None:
    seen: set[str] = set()
    for row in rows:
        key = build_asset_key(row)
        if key in seen:
            raise MarketUnitsSnapshotError(f"duplicate asset_key: {key}")
        seen.add(key)


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


def _clean(value: Any, default: str = "") -> str:
    return str(value if value is not None else default).strip()
