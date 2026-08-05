"""Units snapshot と SSOT A（market_units.csv）の入出力。

検証と正規化は `src.domain.market_units_snapshot` が持つ。本モジュールは
パス解決・読み書き・ハッシュ計算だけを担う。
"""

import csv
import hashlib
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


def snapshot_path(target_date: str, snapshot_dir: Optional[str] = None) -> str:
    compact_date = target_date.replace("-", "")
    return os.path.join(snapshot_dir or DIR_CURRENT, f"collection_units_{compact_date}.json")


def load_market_units_csv(csv_path: str) -> List[Dict[str, Any]]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        raw_rows = list(csv.DictReader(f))
    return normalize_market_units_rows(raw_rows)


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
    active_date = target_date or datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d")
    items = load_market_units_csv(csv_path)
    payload = build_snapshot_payload(
        items=items,
        target_date=active_date,
        ssot_a_path=ssot_a_path or csv_path,
        ssot_a_sha256=_sha256_file(csv_path),
        captured_at=datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(timespec="seconds"),
    )
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


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
