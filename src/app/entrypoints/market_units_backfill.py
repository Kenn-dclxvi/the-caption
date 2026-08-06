import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from src.config.settings import DATA_DIR
from src.infra.market_units_snapshot_repository import create_units_snapshot, snapshot_path


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def enumerate_missing_dates(current_dir: str) -> list[str]:
    root = Path(current_dir)
    daily_dates = {path.stem.removeprefix("daily_metrics_") for path in root.glob("daily_metrics_*.json")}
    snapshot_dates = {path.stem.removeprefix("collection_units_") for path in root.glob("collection_units_*.json")}
    return sorted(daily_dates - snapshot_dates)


def parse_source_bindings(values: list[str]) -> dict[str, str]:
    bindings: dict[str, str] = {}
    for value in values:
        target_date, separator, source_path = value.partition("=")
        if not separator or len(target_date) != 10:
            raise ValueError(f"source must be YYYY-MM-DD=/path/to/history.csv: {value}")
        if target_date in bindings:
            raise ValueError(f"duplicate source binding: {target_date}")
        bindings[target_date] = source_path
    return bindings


def backfill_market_units_snapshots(
    current_dir: str,
    bindings: dict[str, str],
    apply: bool = False,
    canonical_ssot_a_path: str = "data/collection/market_units.csv",
) -> dict[str, Any]:
    missing = enumerate_missing_dates(current_dir)
    missing_set = {f"{value[:4]}-{value[4:6]}-{value[6:]}" for value in missing}
    extra = sorted(set(bindings) - missing_set)
    if extra:
        raise ValueError(f"source binding is not a missing daily_metrics date: {extra}")

    artifacts: list[dict[str, str]] = []
    failures: dict[str, str] = {}
    for compact_date in missing:
        target_date = f"{compact_date[:4]}-{compact_date[4:6]}-{compact_date[6:]}"
        source = bindings.get(target_date)
        if not source:
            continue
        try:
            if not os.path.isfile(source):
                raise FileNotFoundError(source)
            target = snapshot_path(target_date, current_dir)
            payload = create_units_snapshot(
                csv_path=source,
                target_date=target_date,
                output_path=target if apply else None,
                ssot_a_path=canonical_ssot_a_path,
            )
            record = {
                "target_date": target_date,
                "source_path": os.path.abspath(source),
                "source_sha256": payload["source"]["ssot_a_sha256"],
            }
            if apply:
                record["snapshot_sha256"] = _sha256_file(target)
            artifacts.append(record)
        except Exception as exc:
            failures[target_date] = str(exc)

    successful_dates = {item["target_date"].replace("-", "") for item in artifacts}
    unresolved = [
        f"{value[:4]}-{value[4:6]}-{value[6:]}"
        for value in missing
        if value not in successful_dates
    ]
    return {
        "mode": "apply" if apply else "dry-run",
        "target_count": len(missing),
        "bound_count": len(bindings),
        "generated_count": len(artifacts) if apply else 0,
        "validated_count": len(artifacts),
        "unresolved_count": len(unresolved),
        "unresolved_dates": unresolved,
        "artifacts": artifacts,
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill only evidence-bound Market Units snapshots")
    parser.add_argument("--data-dir", default=DATA_DIR, help="Data directory containing current/")
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="YYYY-MM-DD=CSV",
        help="Bind one missing target date to one explicit historical CSV",
    )
    parser.add_argument("--apply", action="store_true", help="Atomically create snapshots; default is dry-run")
    args = parser.parse_args()
    report = backfill_market_units_snapshots(
        current_dir=os.path.join(args.data_dir, "current"),
        bindings=parse_source_bindings(args.source),
        apply=args.apply,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
