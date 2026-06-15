import json
import re
import datetime as dt
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "current"


def _first_ledger_dates_by_month() -> list[str]:
    first_by_month: dict[str, str] = {}
    for path in sorted(DATA_DIR.glob("ledger_*.json")):
        match = re.match(r"ledger_(\d{8})\.json$", path.name)
        if not match:
            continue
        date_str = f"{match.group(1)[:4]}-{match.group(1)[4:6]}-{match.group(1)[6:]}"
        first_by_month.setdefault(date_str[:7], date_str)
    return list(first_by_month.values())


def _first_ledger_dates_by_week() -> list[str]:
    first_by_week: dict[str, str] = {}
    for path in sorted(DATA_DIR.glob("ledger_*.json")):
        match = re.match(r"ledger_(\d{8})\.json$", path.name)
        if not match:
            continue
        date_str = f"{match.group(1)[:4]}-{match.group(1)[4:6]}-{match.group(1)[6:]}"
        year, month, day = map(int, date_str.split("-"))
        iso = dt.date(year, month, day).isocalendar()
        first_by_week.setdefault(f"{iso.year:04d}-W{iso.week:02d}", date_str)
    return list(first_by_week.values())


def _first_ledger_dates_by_year() -> list[str]:
    first_by_year: dict[str, str] = {}
    for path in sorted(DATA_DIR.glob("ledger_*.json")):
        match = re.match(r"ledger_(\d{8})\.json$", path.name)
        if not match:
            continue
        date_str = f"{match.group(1)[:4]}-{match.group(1)[4:6]}-{match.group(1)[6:]}"
        first_by_year.setdefault(date_str[:4], date_str)
    return list(first_by_year.values())


@pytest.mark.parametrize("date_str", _first_ledger_dates_by_month())
def test_month_start_ledgers_reset_mtd(date_str: str) -> None:
    ledger_path = DATA_DIR / f"ledger_{date_str.replace('-', '')}.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    summary = ledger["summary"]

    assert summary["total_mtd"] == f"{summary['total_diff_pct']:+.2f}%"


@pytest.mark.parametrize("date_str", _first_ledger_dates_by_week())
def test_week_start_ledgers_reset_wtd(date_str: str) -> None:
    ledger_path = DATA_DIR / f"ledger_{date_str.replace('-', '')}.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    summary = ledger["summary"]

    assert summary["total_wtd"] == f"{summary['total_diff_pct']:+.2f}%"


@pytest.mark.parametrize("date_str", _first_ledger_dates_by_year())
def test_year_start_ledgers_reset_ytd(date_str: str) -> None:
    ledger_path = DATA_DIR / f"ledger_{date_str.replace('-', '')}.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    summary = ledger["summary"]

    assert summary["total_ytd"] == f"{summary['total_diff_pct']:+.2f}%"
