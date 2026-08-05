"""配信済みレポートの記録から、失われた期間の確定台帳を復元する。

`collection_units_YYYYMMDD.json` が残っていない期間は、当時の保有数量を
リポジトリ内から復元できない。現在の `market_units.csv` で代用すると評価額が
狂うため、配信済みレポートに記録された当時の数量・現金内訳・取得原価を入力に
使う（`data/runtime/report_archive_*.json`）。

日次パイプラインと同じ経路（ingester -> finalizer -> adapter）で再計算し、
レポートの値と照合してから保存する。照合が合わない日は保存しない。

方針:
- 保有数量スナップショットは `data/current/` へ作らない。後から「その日に観測した
  入力」を作ると来歴が変わるため、一時ディレクトリで計算にのみ使う。数量は
  確定台帳自身が保持する（ADR-0002 の正本が `units` を持つ）。
- 外部資産と取得原価は月次キーのファイルが最新値へ上書きされており当時の値が
  残っていないため、レポートから日次で注入する。
- 昇順に処理し、前営業日の正本を DAY の基準にする（ADR-0002 / ADR-0005）。

配信系には一切触れない: メール送信 / LLM / CompletionLock /
v4_shadow_ledger.json / daily_metrics は対象外。
確定済み (VERIFIED) の正本は --overwrite-verified を明示しない限り置き換えない。
"""

import argparse
import csv
import json
import os
import sys
import tempfile
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.config.settings import DIR_CURRENT
from src.domain.market_units_snapshot import (
    MARKET_UNITS_CSV,
    create_units_snapshot,
    load_market_units_csv,
    snapshot_path,
)
from src.domain.shadow_ledger_adapter import ShadowLedgerAdapter
from src.domain.universal_ingester import UniversalIngester
from src.domain.v4_ledger_finalizer import V4LedgerFinalizer
from src.infra.ledger_repository import LedgerRepository
from src.lib.timeline_controller import TimelineController

_DEFAULT_ARCHIVE = os.path.join("data", "runtime", "report_archive_20260430_20260728.json")
_PREVIOUS_LEDGER_LOOKBACK_DAYS = 12
_CSV_COLUMNS = ["name", "asset_class", "currency", "units", "source_symbol", "audit_match_key", "csv_url"]

# レポートは表示のために各値を丸めて配信しているため、照合には許容差を設ける。
# 加えて、取得元履歴は後日更新され得る（Alpha Vantage で補完した日の値が後から
# yfinance の値へ置き換わる等）ため、当時の価格を厳密には再現できない。
# 絶対額の丸め誤差と、履歴更新による相対誤差の両方を許容する。
_TOLERANCE_JPY = 3
_TOLERANCE_RATIO = 0.0001
_TOLERANCE_PCT = 0.02


def _ledger_path(date_str: str) -> str:
    return os.path.join(DIR_CURRENT, f"ledger_{date_str.replace('-', '')}.json")


def _previous_ledger_records(
    repo: LedgerRepository,
    date_str: str,
    pending: Optional[Dict[str, dict]] = None,
) -> Dict[str, Dict[str, Any]]:
    """前営業日の正本から DAY 比較の基準を引く（v4_engine と同一方針）。"""
    base = date.fromisoformat(date_str)
    for offset in range(1, _PREVIOUS_LEDGER_LOOKBACK_DAYS + 1):
        previous = (base - timedelta(days=offset)).isoformat()
        ledger = (pending or {}).get(previous) or repo.load(previous)
        if not isinstance(ledger, dict):
            continue
        confirmed_date = (ledger.get("meta") or {}).get("target_date") or previous
        records: Dict[str, Dict[str, Any]] = {}
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
        return records
    return {}


def _write_units_csv(path: str, units_by_name: Dict[str, str]) -> List[str]:
    """当時の数量を持つ SSOT A 相当の CSV を一時生成する。

    資産定義（asset_class / currency / source_symbol / csv_url）は現在の
    `market_units.csv` から引く。FX は評価用の換算レート取得に必要で
    レポートに数量が出ないため、常に現在の定義をそのまま残す。
    レポートに現れない資産は、その日は保有していないものとして除外する。
    """
    base_rows = load_market_units_csv(MARKET_UNITS_CSV)
    rows: List[Dict[str, Any]] = []
    for row in base_rows:
        if row["asset_class"] == "FX":
            rows.append(row)
            continue
        units = units_by_name.get(row["name"])
        if units is None:
            continue
        rows.append({**row, "units": units})

    known = {row["name"] for row in base_rows}
    unknown = sorted(set(units_by_name) - known)

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in _CSV_COLUMNS})
    return unknown


def _write_external_assets(path: str, date_str: str, iron_bank: Dict[str, int]) -> None:
    items = [
        {"category": "CASH_EXTERNAL", "amount": int(amount), "name": name}
        for name, amount in iron_bank.items()
    ]
    payload = {date_str[:7]: {"items": items}, "default": {"items": items}}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


def _write_portfolio_basis(path: str, date_str: str, cost_jpy: int) -> None:
    payload = {
        date_str[:7]: {"total_acquisition_cost_jpy": cost_jpy},
        "default": {"total_acquisition_cost_jpy": cost_jpy},
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


def _acquisition_cost(summary: Dict[str, Any]) -> int:
    """レポートの exposure と total_return から取得原価を復元する。

    どちらも表示のために丸められているため差に最大数円の誤差が出る。
    実際の運用値は 10,000 円単位で管理されているため、その単位へ丸める。
    """
    raw = int(summary["exposure"]) - int(summary["total_return"])
    return int(round(raw / 10000.0) * 10000)


def _parse_pct(value: Any) -> Optional[float]:
    if not isinstance(value, str):
        return None
    try:
        return float(value.replace("%", "").replace("+", ""))
    except ValueError:
        return None


def _verify(summary: Dict[str, Any], expected: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """再計算結果を配信済みレポートと突き合わせる。

    評価額系（総額・Exposure・Iron Bank・Total Return）は必須一致とする。
    騰落率は当時と計算方式が異なるため参考差分として扱う。
    - DAY: 基準を前営業日の正本へ移した（ADR-0002 / ADR-0005）
    - MTD / WTD / YTD: 合計の加重を現在の評価額から期間開始時点の評価額へ変えた
      （`ShadowLedgerAdapter._weighted_period_pct`）
    資産別の騰落率は当時と一致するため、差は合計の集計方法だけに起因する。
    """
    failures: List[str] = []
    notes: List[str] = []

    # 許容差の基準額は評価額とする。Total Return は「評価額 − 取得原価」であり
    # 差の実体は評価額側の誤差なので、Return 自体の絶対値では判定しない。
    for label, actual, want, scale in (
        ("total", summary["total_assets_jpy"], expected["total_net_assets"], expected["total_net_assets"]),
        ("exposure", summary["exposure_jpy"], expected["exposure"], expected["exposure"]),
        ("iron_bank", summary["iron_bank_jpy"], expected["iron_bank"], expected["iron_bank"]),
        ("return", summary["total_profit_loss_jpy"], expected["total_return"], expected["exposure"]),
    ):
        gap = int(actual) - int(want)
        allowed = max(_TOLERANCE_JPY, abs(int(scale)) * _TOLERANCE_RATIO)
        if abs(gap) > allowed:
            failures.append(
                f"{label} {int(actual):,} vs {int(want):,} ({gap:+,} / 許容 ±{allowed:,.0f})"
            )

    for label, actual, want_str in (
        ("mtd", summary["total_mtd"], expected.get("mtd")),
        ("wtd", summary["total_wtd"], expected.get("wtd")),
        ("ytd", summary["total_ytd"], expected.get("ytd")),
    ):
        want = _parse_pct(want_str)
        got = _parse_pct(actual)
        if want is None or got is None:
            continue
        if abs(got - want) > _TOLERANCE_PCT:
            notes.append(f"{label} {actual} vs {want_str} (加重方式変更による差)")

    want_day = _parse_pct(expected.get("day_pct"))
    if want_day is not None:
        got_day = float(summary["total_diff_pct"])
        if abs(got_day - want_day) > _TOLERANCE_PCT:
            notes.append(f"day {got_day:+.2f}% vs {want_day:+.2f}% (DAY 基準変更による差)")

    return failures, notes


def backfill_day(
    date_str: str,
    day: Dict[str, Any],
    repo: LedgerRepository,
    timeline: TimelineController,
    force: bool,
    dry_run: bool,
    overwrite_verified: bool,
    pending: Dict[str, dict],
) -> int:
    target = _ledger_path(date_str)
    if os.path.exists(target) and not force:
        print(f"SKIP {date_str}: ledger already exists")
        return 0
    if os.path.exists(target) and not overwrite_verified:
        existing = repo.load(date_str)
        status = (existing or {}).get("meta", {}).get("integrity_status") if isinstance(existing, dict) else None
        if status == "VERIFIED":
            print(f"SKIP {date_str}: ledger is VERIFIED (use --overwrite-verified)")
            return 0

    summary_expected = day["summary"]
    with tempfile.TemporaryDirectory() as tmp:
        units_csv = os.path.join(tmp, "market_units.csv")
        unknown = _write_units_csv(units_csv, day["assets"])
        if unknown:
            # 現在の SSOT A に定義が無い資産は asset_class や換算方法が決められない。
            print(f"FAIL {date_str}: undefined assets in SSOT A: {', '.join(unknown)}")
            return 1

        external_path = os.path.join(tmp, "external_assets.json")
        _write_external_assets(external_path, date_str, day["iron_bank"])
        basis_path = os.path.join(tmp, "portfolio_basis.json")
        _write_portfolio_basis(basis_path, date_str, _acquisition_cost(summary_expected))

        snapshot_dir = os.path.join(tmp, "snapshots")
        os.makedirs(snapshot_dir, exist_ok=True)
        # snapshot は一時ディレクトリでの計算にのみ使うため、来歴は ingester が
        # 参照する一時 CSV と揃える（load_units_snapshot が両者の一致を検証する）。
        create_units_snapshot(
            csv_path=units_csv,
            target_date=date_str,
            output_path=snapshot_path(date_str, snapshot_dir),
        )

        ingester = UniversalIngester(
            funds_csv_path=units_csv,
            external_assets_path=external_path,
            portfolio_basis_path=basis_path,
            units_snapshot_dir=snapshot_dir,
            timeline=timeline,
        )
        shadow = ingester.run(
            date_str,
            units_mode="strict",
            previous_records=_previous_ledger_records(repo, date_str, pending),
        )

    finalized = V4LedgerFinalizer(timeline).finalize(shadow)
    document = ShadowLedgerAdapter().to_canonical_document(finalized)
    summary = document["summary"]

    failures, notes = _verify(summary, summary_expected)
    skip_reason = day.get("skip_verification")
    if skip_reason and failures:
        # 当時と計算前提が異なることが判明している日は、差の理由を記録して保存する。
        notes.append(f"照合免除: {skip_reason}")
        notes.extend(f"免除した差: {failure}" for failure in failures)
        failures = []
    status = document["meta"]["integrity_status"]
    head = f"{'DRY ' if dry_run else ''}{'NG  ' if failures else 'OK  '} {date_str}"
    print(
        f"{head}: status={status} assets={len(document['assets'])} "
        f"total={summary['total_assets_jpy']:,} day={summary['total_diff_pct']:+.2f}% "
        f"mtd={summary['total_mtd']} wtd={summary['total_wtd']} ytd={summary['total_ytd']}"
    )
    for note in notes:
        print(f"       note: {note}")
    if failures:
        for failure in failures:
            print(f"       MISMATCH: {failure}")
        return 1

    if dry_run:
        pending[date_str] = document
        return 0

    repo.save_document(document, date_str)
    print(f"       wrote {target}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dates", nargs="*", help="対象日 (YYYY-MM-DD)。省略時はアーカイブの全日。")
    parser.add_argument("--archive", default=_DEFAULT_ARCHIVE, help="レポート抽出データの JSON パス。")
    parser.add_argument("--force", action="store_true", help="既存の台帳を上書きする（VERIFIED は保護）。")
    parser.add_argument("--overwrite-verified", action="store_true", help="確定済みの正本も置き換える。")
    parser.add_argument("--dry-run", action="store_true", help="保存せず照合結果だけ表示する。")
    args = parser.parse_args()

    with open(args.archive, encoding="utf-8") as f:
        days = json.load(f)["days"]

    targets = sorted(set(args.dates)) if args.dates else sorted(days)
    unknown_dates = [d for d in targets if d not in days]
    if unknown_dates:
        print(f"FAIL archive has no entry for: {' '.join(unknown_dates)}")
        sys.exit(1)

    repo = LedgerRepository()
    timeline = TimelineController()
    pending: Dict[str, dict] = {}
    failures = 0
    for index, date_str in enumerate(targets):
        if backfill_day(
            date_str,
            days[date_str],
            repo=repo,
            timeline=timeline,
            force=args.force,
            dry_run=args.dry_run,
            overwrite_verified=args.overwrite_verified,
            pending=pending,
        ):
            failures += 1
            # 後続日は失敗した日を前営業日の正本として参照するため、続けると
            # 基準の異なる台帳が固定される。
            remaining = targets[index + 1:]
            if remaining:
                print(f"ABORT dependent dates skipped: {len(remaining)}日 ({remaining[0]}〜{remaining[-1]})")
            break

    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
