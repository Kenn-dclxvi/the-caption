import json
from pathlib import Path

from src.app.entrypoints.market_units_backfill import backfill_market_units_snapshots


def _write_csv(path: Path) -> None:
    path.write_text(
        "name,asset_class,currency,units,source_symbol,audit_match_key,csv_url\n"
        "FundA,MUTUAL_FUNDS,JPY,10,FundA,,https://example.com/a.csv\n",
        encoding="utf-8",
    )


def test_backfill_dry_run_and_apply_only_create_bound_snapshot(tmp_path):
    current = tmp_path / "data" / "current"
    current.mkdir(parents=True)
    for compact_date in ("20260420", "20260421"):
        (current / f"daily_metrics_{compact_date}.json").write_text("{}\n", encoding="utf-8")
    protected = {
        "last_sent_mail_V2.txt": "2026-04-19\n",
        "v4_shadow_ledger.json": '{"previous":true}\n',
        "market_snapshot_20260420.json": '{"market":true}\n',
    }
    for name, content in protected.items():
        (tmp_path / "data" / name).write_text(content, encoding="utf-8")
    source = tmp_path / "historical_market_units.csv"
    _write_csv(source)

    dry_run = backfill_market_units_snapshots(
        str(current),
        {"2026-04-20": str(source)},
        apply=False,
    )
    assert dry_run["validated_count"] == 1
    assert dry_run["generated_count"] == 0
    assert not (current / "collection_units_20260420.json").exists()

    applied = backfill_market_units_snapshots(
        str(current),
        {"2026-04-20": str(source)},
        apply=True,
    )
    assert applied["generated_count"] == 1
    assert applied["unresolved_dates"] == ["2026-04-21"]
    payload = json.loads((current / "collection_units_20260420.json").read_text(encoding="utf-8"))
    assert payload["target_date"] == "2026-04-20"
    assert payload["source"]["ssot_a_path"] == "data/collection/market_units.csv"
    for name, content in protected.items():
        assert (tmp_path / "data" / name).read_text(encoding="utf-8") == content


def test_backfill_never_overwrites_existing_snapshot(tmp_path):
    current = tmp_path / "current"
    current.mkdir()
    (current / "daily_metrics_20260420.json").write_text("{}\n", encoding="utf-8")
    existing = current / "collection_units_20260420.json"
    existing.write_text('{"existing":true}\n', encoding="utf-8")
    source = tmp_path / "historical_market_units.csv"
    _write_csv(source)

    report = backfill_market_units_snapshots(str(current), {}, apply=True)

    assert report["target_count"] == 0
    assert existing.read_text(encoding="utf-8") == '{"existing":true}\n'
