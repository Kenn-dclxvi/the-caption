import argparse
import re
import sys
import time
from pathlib import Path
from typing import Final, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parents[2]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from src.lib.logger import setup_logger
from src.lib.models import Ledger, LedgerMeta, LedgerSummary, Position
from src.infra.context_repository import ContextRepository
from src.domain.curator import MarketCurator
from src.infra.knowledge_manager import KnowledgeManager
from src.infra.ledger_repository import LedgerRepository
from src.lib.timeline_controller import TimelineController

_TOOL_REV: Final[str] = "Rev. 1"
_DEFAULT_DELAY_SEC: Final[int] = 12
_DATE_PATTERN: Final[re.Pattern] = re.compile(r"^\d{4}-\d{2}-\d{2}$")

logger = setup_logger(__name__)


def _fmt_pct(value) -> str:
    return f"{float(value):+.2f}%" if isinstance(value, (int, float)) else "---"


def _position_from_canonical_asset(asset: dict) -> Position:
    """v4 の確定台帳 (ADR-0002) の資産レコードを表示用 Position へ変換する。

    v4 の計算元に資産別取得原価は存在しないため、`acquisition_price` と損益は
    評価額および 0 で埋める。表示・Knowledge 再構築はこれらを参照しない。
    """
    value_jpy = int(asset.get("value_jpy") or 0)
    price = float(asset.get("price") or 0.0)
    is_cash = asset.get("source") == "ABSOLUTE_AMOUNT" or asset.get("pricing_status") == "STATIC"
    return Position(
        id=str(asset.get("id") or asset.get("name") or ""),
        name=str(asset.get("name") or ""),
        raw_name=str(asset.get("name") or ""),
        asset_class="SHORT_TERM" if is_cash else str(asset.get("asset_class") or ""),
        category="CASH" if is_cash else "INVESTMENT",
        quantity=float(asset.get("units") or 0.0),
        unit_price=price,
        current_price=price,
        currency=str(asset.get("currency") or "JPY"),
        value_jpy=value_jpy,
        acquisition_price=value_jpy,
        profit_loss=0,
        profit_loss_pct=0.0,
        prev_day_diff_jpy=int(round(float(asset.get("day_diff_jpy") or 0.0))),
        prev_day_diff_pct=float(asset.get("day_diff_pct") or 0.0),
        is_nisa=False,
        is_specific=False,
        wtd=_fmt_pct(asset.get("wtd_pct")),
        mtd=_fmt_pct(asset.get("mtd_pct")),
        ytd=_fmt_pct(asset.get("ytd_pct")),
    )


def _position_from_dict(asset: dict) -> Position:
    # v3.5 以前の台帳は Position をそのまま dump しているため直接復元できる。
    # v4 の正本は資産別原価を持たず別スキーマなので、変換経路を分ける。
    if "prev_day_diff_jpy" in asset and "raw_name" in asset:
        return Position(**asset)
    return _position_from_canonical_asset(asset)


def _ledger_from_dict(data: dict) -> Ledger:
    return Ledger(
        meta=LedgerMeta(**data["meta"]),
        summary=LedgerSummary(**data["summary"]),
        assets=[_position_from_dict(a) for a in data["assets"]],
    )


def _dates_in_range(start: str, end: str, ledger_repo: LedgerRepository) -> List[str]:
    return sorted(d for d in ledger_repo.scan_dates() if start <= d <= end)


def _rebuild_single(
    date_str: str,
    curator: MarketCurator,
    context_repo: ContextRepository,
    knowledge_mgr: KnowledgeManager,
    ledger_repo: LedgerRepository,
) -> Tuple[bool, str]:
    logger.info(f"[Acquisition] Rebuilding context for {date_str}")

    raw = ledger_repo.load(date_str)
    if raw is None:
        msg = f"Ledger not found: {date_str}"
        logger.warning(f"[Guard] {msg}")
        return False, msg

    try:
        ledger = _ledger_from_dict(raw)
    except (TypeError, KeyError) as e:
        msg = f"Ledger reconstruction failed for {date_str}: {e}"
        logger.error(f"[Outcome] {msg}")
        return False, msg

    report = curator.generate_context_report(date_str, ledger.summary, ledger.assets, ledger)
    if report is None:
        msg = f"Curation returned None for {date_str}"
        logger.error(f"[Outcome] {msg}")
        return False, msg

    context_ok = context_repo.save(report, date_str)
    knowledge_ok = knowledge_mgr.record_insight(date_str, report)

    if context_ok and knowledge_ok:
        logger.info(f"[Outcome] Rebuild complete: {date_str}")
        return True, ""

    msg = f"Partial write failure for {date_str} (context={context_ok}, knowledge={knowledge_ok})"
    logger.warning(f"[Guard] {msg}")
    return False, msg


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Chronicle Rewriter — Rebuilds context_YYYYMMDD.json and knowledge_bank.md "
            "for a specified date range using the latest VIX-enabled prompts."
        )
    )
    parser.add_argument("--start", required=True, metavar="YYYY-MM-DD", help="Rebuild start date (inclusive)")
    parser.add_argument("--end",   required=True, metavar="YYYY-MM-DD", help="Rebuild end date   (inclusive)")
    parser.add_argument(
        "--delay",
        type=int,
        default=_DEFAULT_DELAY_SEC,
        metavar="SECONDS",
        help=f"Sleep between API calls to respect rate limits (default: {_DEFAULT_DELAY_SEC}s)",
    )
    return parser.parse_args()


def main() -> None:
    logger.info(f"[{_TOOL_REV}] Chronicle Rewriter initializing")
    args = _parse_args()

    if not _DATE_PATTERN.match(args.start) or not _DATE_PATTERN.match(args.end):
        print("[Error] --start and --end must be in YYYY-MM-DD format.")
        sys.exit(1)

    if args.start > args.end:
        print(f"[Error] --start ({args.start}) must not be later than --end ({args.end}).")
        sys.exit(1)

    if args.delay < 0:
        print("[Error] --delay must be a non-negative integer.")
        sys.exit(1)

    ledger_repo = LedgerRepository()
    dates = _dates_in_range(args.start, args.end, ledger_repo)

    if not dates:
        print(f"[Guard] No ledger files found in range {args.start} ~ {args.end}. Exiting.")
        sys.exit(0)

    print(f"[Batch] Rebuilding {len(dates)} date(s): {dates[0]} ~ {dates[-1]}")
    print(f"[Batch] API delay: {args.delay}s per interval")

    timeline     = TimelineController()
    curator      = MarketCurator(timeline)
    context_repo = ContextRepository()
    knowledge_mgr = KnowledgeManager()

    success: int = 0
    failure: int = 0

    for i, date_str in enumerate(dates):
        print(f"\n[Batch] [{i + 1}/{len(dates)}] Processing {date_str} ...")
        ok, reason = _rebuild_single(date_str, curator, context_repo, knowledge_mgr, ledger_repo)

        if ok:
            success += 1
            print(f"[Batch] ✓ {date_str}")
        else:
            failure += 1
            print(f"[Batch] ✗ {date_str} — {reason}")

        if i < len(dates) - 1:
            print(f"[Batch] Sleeping {args.delay}s ...")
            time.sleep(args.delay)

    print(f"\n[Batch] Complete — Success: {success} / Failure: {failure} / Total: {len(dates)}")
    logger.info(f"[Outcome] Rebuild batch done. success={success}, failure={failure}, total={len(dates)}")


if __name__ == "__main__":
    main()
