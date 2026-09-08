"""Units snapshot と SSOT A（market_units.csv）の入出力。

検証と正規化は `src.domain.market_units_snapshot` が持つ。本モジュールは
パス解決・読み書き・ハッシュ計算だけを担う。
"""

import csv
import hashlib
import io
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from src.config.settings import DIR_CURRENT, MARKET_UNITS_CSV
from src.domain.market_units_snapshot import (
    MarketUnitsSnapshotError,
    build_snapshot_payload,
    normalize_market_units_rows,
    validate_snapshot_payload,
)
from src.lib.atomic_write import atomic_write_json
from src.infra.market_units_input_repository import locked_market_units_csv


def snapshot_path(target_date: str, snapshot_dir: Optional[str] = None) -> str:
    compact_date = target_date.replace("-", "")
    return os.path.join(snapshot_dir or DIR_CURRENT, f"collection_units_{compact_date}.json")


def load_market_units_csv(csv_path: str) -> List[Dict[str, Any]]:
    with locked_market_units_csv(csv_path) as raw_csv:
        return _normalize_csv_bytes(raw_csv)


def _normalize_csv_bytes(raw_csv: bytes) -> List[Dict[str, Any]]:
    rows = list(csv.DictReader(io.StringIO(raw_csv.decode("utf-8-sig"), newline="")))
    return normalize_market_units_rows(rows)


def load_units_snapshot(path: str, target_date: str, ssot_a_path: str) -> List[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as exc:
        raise MarketUnitsSnapshotError(f"unreadable snapshot: {exc}") from exc

    return validate_snapshot_payload(payload, target_date, ssot_a_path)


def create_units_snapshot(
    csv_path: str = MARKET_UNITS_CSV,
    target_date: Optional[str] = None,
    output_path: Optional[str] = None,
    ssot_a_path: Optional[str] = None,
) -> Dict[str, Any]:
    with locked_market_units_csv(csv_path) as raw_csv:
        return _create_units_snapshot_locked(raw_csv, csv_path, target_date, output_path, ssot_a_path)


def _create_units_snapshot_locked(
    raw_csv: bytes,
    csv_path: str,
    target_date: Optional[str],
    output_path: Optional[str],
    ssot_a_path: Optional[str],
) -> Dict[str, Any]:
    active_date = target_date or datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d")
    items = _normalize_csv_bytes(raw_csv)
    payload = build_snapshot_payload(
        items=items,
        target_date=active_date,
        ssot_a_path=ssot_a_path or csv_path,
        ssot_a_sha256=hashlib.sha256(raw_csv).hexdigest(),
        captured_at=datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(timespec="seconds"),
    )
    if output_path:
        if os.path.exists(output_path):
            raise FileExistsError(f"market units snapshot already exists: {output_path}")
        atomic_write_json(output_path, payload)
        descriptor = os.open(os.path.dirname(os.path.abspath(output_path)), os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
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
    with locked_market_units_csv(csv_path) as raw_csv:
        # Another daily process may have completed while this one waited.
        if not os.path.exists(path):
            _create_units_snapshot_locked(raw_csv, csv_path, target_date, path, csv_path)
    load_units_snapshot(path, target_date, csv_path)
    return path
