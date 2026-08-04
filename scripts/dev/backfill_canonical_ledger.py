"""過去日の確定台帳 (ledger_YYYYMMDD.json) を再生成する。

v4 移行時に日次台帳の書き込みが欠落したため、週次/月次が
LedgerRepository.load で参照する正本が 2026-04-24 以降存在しない。
本スクリプトは units snapshot が残っている日について、日次パイプラインと
同じ経路 (ingester -> finalizer -> adapter) で台帳を再構成して保存する。

配信系には一切触れない: メール送信 / LLM / CompletionLock /
v4_shadow_ledger.json / daily_metrics は対象外。
既存の台帳ファイルは --force なしでは上書きしない。
"""

import argparse
import os
import sys
from datetime import date, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.config.settings import DIR_CURRENT
from src.domain.market_units_snapshot import snapshot_path
from src.domain.shadow_ledger_adapter import ShadowLedgerAdapter
from src.domain.universal_ingester import UniversalIngester
from src.domain.v4_ledger_finalizer import V4LedgerFinalizer
from src.infra.ledger_repository import LedgerRepository
from src.lib.timeline_controller import TimelineController


_PREVIOUS_LEDGER_LOOKBACK_DAYS = 12


def _ledger_path(date_str: str) -> str:
    return os.path.join(DIR_CURRENT, f"ledger_{date_str.replace('-', '')}.json")


def _previous_ledger_records(repo: LedgerRepository, date_str: str) -> dict:
    """前営業日の正本から DAY 比較の基準価格を引く（v4_engine と同一方針）。"""
    base = date.fromisoformat(date_str)
    for offset in range(1, _PREVIOUS_LEDGER_LOOKBACK_DAYS + 1):
        previous = (base - timedelta(days=offset)).isoformat()
        ledger = repo.load(previous)
        if not isinstance(ledger, dict):
            continue
        confirmed_date = (ledger.get("meta") or {}).get("target_date") or previous
        records = {}
        for asset in ledger.get("assets") or []:
            if not isinstance(asset, dict):
                continue
            asset_id = asset.get("id")
            price = asset.get("price")
            if not isinstance(price, (int, float)):
                price = asset.get("current_price")
            if not isinstance(asset_id, str) or not isinstance(price, (int, float)) or price <= 0:
                continue
            records[asset_id] = {
                "price": float(price),
                "fx_rate": asset.get("fx_rate"),
                "pricing_status": asset.get("pricing_status"),
                "source_date": asset.get("source_date"),
                "target_date": confirmed_date,
            }
        print(f"     previous ledger: {confirmed_date} ({len(records)} priced assets)")
        return records
    print(f"     previous ledger: none within {_PREVIOUS_LEDGER_LOOKBACK_DAYS} days (history fallback)")
    return {}


def backfill(date_str: str, force: bool, dry_run: bool) -> int:
    target = _ledger_path(date_str)
    if os.path.exists(target) and not force:
        print(f"SKIP {date_str}: ledger already exists ({target})")
        return 0

    snapshot = snapshot_path(date_str)
    if not os.path.exists(snapshot):
        # units snapshot が無い日は当時の保有数量が復元できない。
        # 現在の market_units.csv で代用すると評価額が狂うため生成しない。
        print(f"FAIL {date_str}: units snapshot missing ({snapshot})")
        return 1

    timeline = TimelineController()
    repo = LedgerRepository()
    shadow = UniversalIngester().run(
        date_str,
        units_mode="strict",
        previous_records=_previous_ledger_records(repo, date_str),
    )
    finalized = V4LedgerFinalizer(timeline).finalize(shadow)
    document = ShadowLedgerAdapter().to_canonical_document(finalized)

    meta = document["meta"]
    summary = document["summary"]
    print(
        f"{'DRY ' if dry_run else ''}OK   {date_str}: "
        f"status={meta['integrity_status']} assets={len(document['assets'])} "
        f"total={summary['total_assets_jpy']:,} day={summary['total_diff_pct']:+.2f}% "
        f"mtd={summary['total_mtd']} wtd={summary['total_wtd']} ytd={summary['total_ytd']}"
    )
    if dry_run:
        return 0

    repo.save_document(document, date_str)
    print(f"     wrote {target}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dates", nargs="+", help="対象日 (YYYY-MM-DD)。複数指定可。")
    parser.add_argument("--force", action="store_true", help="既存の台帳を上書きする。")
    parser.add_argument("--dry-run", action="store_true", help="保存せず結果だけ表示する。")
    args = parser.parse_args()

    # 後の日は前営業日の正本を DAY 基準に使うため、降順や順不同で渡されると
    # 先行日が未生成のまま計算され history フォールバックへ落ちる。昇順に固定する。
    dates = sorted(set(args.dates))
    if dates != list(args.dates):
        print(f"NOTE ordering normalized to ascending: {' '.join(dates)}")

    failures = 0
    for date_str in dates:
        failures += backfill(date_str, force=args.force, dry_run=args.dry_run)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
