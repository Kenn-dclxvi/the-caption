import json
from unittest.mock import patch

import pytest

from src.domain.market_units_snapshot import MarketUnitsSnapshotError, build_asset_key
from src.infra.market_units_snapshot_repository import (
    create_units_snapshot,
    ensure_units_snapshot,
    load_units_snapshot,
    load_market_units_csv,
    snapshot_path,
)
from src.domain.universal_ingester import UniversalIngester


def _write_market_units(path, rows: list[str] | None = None) -> None:
    path.write_text(
        "\n".join(
            rows
            or [
                "name,asset_class,currency,units,source_symbol,audit_match_key,csv_url",
                "FundA,MUTUAL_FUNDS,JPY,20000,FundA,,",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_history(history_dir, name="FundA") -> None:
    history_dir.mkdir(exist_ok=True)
    (history_dir / f"{name}.csv").write_text("基準日,基準価額\n2026-04-20,12000\n", encoding="utf-8")


def _ingester(tmp_path, market_units_csv, snapshot_dir):
    external_json = tmp_path / "external_assets.json"
    external_json.write_text(json.dumps({}), encoding="utf-8")
    history_dir = tmp_path / "history"
    _write_history(history_dir)
    return UniversalIngester(
        funds_csv_path=str(market_units_csv),
        external_assets_path=str(external_json),
        history_dir=str(history_dir),
        units_snapshot_dir=str(snapshot_dir),
    )


def _write_snapshot(market_units_csv, snapshot_dir, mutator=None):
    payload = create_units_snapshot(
        csv_path=str(market_units_csv),
        target_date="2026-04-20",
    )
    if mutator is not None:
        mutator(payload)
    path = snapshot_dir / "collection_units_20260420.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_snapshot_adoption_path_records_units_source(tmp_path):
    market_units_csv = tmp_path / "market_units.csv"
    snapshot_dir = tmp_path / "current"
    snapshot_dir.mkdir()
    _write_market_units(market_units_csv)
    create_units_snapshot(
        csv_path=str(market_units_csv),
        target_date="2026-04-20",
        output_path=snapshot_path("2026-04-20", str(snapshot_dir)),
    )

    ledger = _ingester(tmp_path, market_units_csv, snapshot_dir).build_shadow_ledger("2026-04-20")

    assert ledger.ssot_a_path == str(market_units_csv)
    assert ledger.units_source is not None
    assert ledger.units_source.type == "SNAPSHOT"
    assert ledger.units_source.path == snapshot_path("2026-04-20", str(snapshot_dir))
    assert ledger.units_source.snapshot_target_date == "2026-04-20"
    assert ledger.assets[0].units == pytest.approx(20000)


def test_ensure_snapshot_atomically_creates_and_reuses_immutable_file(tmp_path):
    market_units_csv = tmp_path / "market_units.csv"
    snapshot_dir = tmp_path / "current"
    _write_market_units(market_units_csv)

    path = ensure_units_snapshot(
        "2026-04-20",
        csv_path=str(market_units_csv),
        snapshot_dir=str(snapshot_dir),
    )
    original = (snapshot_dir / "collection_units_20260420.json").read_bytes()
    ledger = _ingester(tmp_path, market_units_csv, snapshot_dir).build_shadow_ledger(
        "2026-04-20",
        units_mode="strict",
    )

    assert ledger.units_source is not None
    assert ledger.units_source.type == "SNAPSHOT"
    assert ledger.assets[0].units == pytest.approx(20000)

    _write_market_units(
        market_units_csv,
        rows=[
            "name,asset_class,currency,units,source_symbol,audit_match_key,csv_url",
            "FundB,MUTUAL_FUNDS,JPY,999,FundB,,https://example.com/b.csv",
        ],
    )
    reused = ensure_units_snapshot(
        "2026-04-20",
        csv_path=str(market_units_csv),
        snapshot_dir=str(snapshot_dir),
    )

    assert reused == path
    assert (snapshot_dir / "collection_units_20260420.json").read_bytes() == original


def test_ensure_snapshot_atomic_write_failure_leaves_no_target(tmp_path):
    market_units_csv = tmp_path / "market_units.csv"
    snapshot_dir = tmp_path / "current"
    _write_market_units(market_units_csv)

    with patch(
        "src.infra.market_units_snapshot_repository.atomic_write_json",
        side_effect=OSError("disk full"),
    ), pytest.raises(OSError, match="disk full"):
        ensure_units_snapshot(
            "2026-04-20",
            csv_path=str(market_units_csv),
            snapshot_dir=str(snapshot_dir),
        )

    assert not (snapshot_dir / "collection_units_20260420.json").exists()


def test_ensure_snapshot_blocks_invalid_existing_file_without_overwrite(tmp_path):
    market_units_csv = tmp_path / "market_units.csv"
    snapshot_dir = tmp_path / "current"
    snapshot_dir.mkdir()
    _write_market_units(market_units_csv)
    target = snapshot_dir / "collection_units_20260420.json"
    target.write_text('{"schema_version":"wrong"}\n', encoding="utf-8")

    with pytest.raises(MarketUnitsSnapshotError):
        ensure_units_snapshot(
            "2026-04-20",
            csv_path=str(market_units_csv),
            snapshot_dir=str(snapshot_dir),
        )

    assert target.read_text(encoding="utf-8") == '{"schema_version":"wrong"}\n'


def test_ensure_snapshot_blocks_historical_creation_without_explicit_source(tmp_path):
    market_units_csv = tmp_path / "market_units.csv"
    snapshot_dir = tmp_path / "current"
    _write_market_units(market_units_csv)

    with pytest.raises(MarketUnitsSnapshotError, match="snapshot missing"):
        ensure_units_snapshot(
            "2026-04-20",
            csv_path=str(market_units_csv),
            snapshot_dir=str(snapshot_dir),
            allow_create=False,
        )

    assert not (snapshot_dir / "collection_units_20260420.json").exists()


def test_daily_mode_snapshot_missing_falls_back_to_live_csv(tmp_path):
    market_units_csv = tmp_path / "market_units.csv"
    snapshot_dir = tmp_path / "current"
    snapshot_dir.mkdir()
    _write_market_units(market_units_csv)

    ledger = _ingester(tmp_path, market_units_csv, snapshot_dir).build_shadow_ledger("2026-04-20")

    assert ledger.units_source is not None
    assert ledger.units_source.type == "LIVE_CSV"
    assert ledger.units_source.path == str(market_units_csv)


def test_daily_mode_snapshot_invalid_falls_back_to_live_csv(tmp_path):
    market_units_csv = tmp_path / "market_units.csv"
    snapshot_dir = tmp_path / "current"
    snapshot_dir.mkdir()
    _write_market_units(market_units_csv)
    (snapshot_dir / "collection_units_20260420.json").write_text('{"schema_version":"wrong"}', encoding="utf-8")

    ledger = _ingester(tmp_path, market_units_csv, snapshot_dir).build_shadow_ledger("2026-04-20")

    assert ledger.units_source is not None
    assert ledger.units_source.type == "LIVE_CSV"


def test_strict_mode_snapshot_invalid_blocks(tmp_path):
    market_units_csv = tmp_path / "market_units.csv"
    snapshot_dir = tmp_path / "current"
    snapshot_dir.mkdir()
    _write_market_units(market_units_csv)
    (snapshot_dir / "collection_units_20260420.json").write_text('{"schema_version":"wrong"}', encoding="utf-8")

    with pytest.raises(MarketUnitsSnapshotError):
        _ingester(tmp_path, market_units_csv, snapshot_dir).build_shadow_ledger("2026-04-20", units_mode="strict")


def test_strict_mode_snapshot_missing_blocks(tmp_path):
    market_units_csv = tmp_path / "market_units.csv"
    snapshot_dir = tmp_path / "current"
    snapshot_dir.mkdir()
    _write_market_units(market_units_csv)

    with pytest.raises(MarketUnitsSnapshotError, match="snapshot missing"):
        _ingester(tmp_path, market_units_csv, snapshot_dir).build_shadow_ledger("2026-04-20", units_mode="strict")


def test_strict_mode_snapshot_missing_allows_live_csv_when_explicit(tmp_path):
    market_units_csv = tmp_path / "market_units.csv"
    snapshot_dir = tmp_path / "current"
    snapshot_dir.mkdir()
    _write_market_units(market_units_csv)

    ledger = _ingester(tmp_path, market_units_csv, snapshot_dir).build_shadow_ledger(
        "2026-04-20",
        units_mode="strict",
        allow_live_csv_in_strict=True,
    )

    assert ledger.units_source is not None
    assert ledger.units_source.type == "LIVE_CSV"


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda payload: payload.pop("captured_at"), "captured_at missing"),
        (lambda payload: payload.__setitem__("captured_at", "not-a-date"), "captured_at must be ISO 8601"),
        (lambda payload: payload.__setitem__("captured_at", "2026-04-20T12:00:00"), "captured_at must include JST timezone"),
    ],
)
def test_snapshot_captured_at_missing_or_invalid_is_invalid(tmp_path, mutator, message):
    market_units_csv = tmp_path / "market_units.csv"
    snapshot_dir = tmp_path / "current"
    snapshot_dir.mkdir()
    _write_market_units(market_units_csv)
    snapshot = _write_snapshot(market_units_csv, snapshot_dir, mutator)

    with pytest.raises(MarketUnitsSnapshotError, match=message):
        load_units_snapshot(str(snapshot), "2026-04-20", str(market_units_csv))


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda payload: payload["source"].pop("ssot_a_sha256"), "ssot_a_sha256 missing"),
        (lambda payload: payload["source"].__setitem__("ssot_a_sha256", "not-sha256"), "SHA-256 hex digest"),
    ],
)
def test_snapshot_ssot_a_sha256_missing_or_invalid_is_invalid(tmp_path, mutator, message):
    market_units_csv = tmp_path / "market_units.csv"
    snapshot_dir = tmp_path / "current"
    snapshot_dir.mkdir()
    _write_market_units(market_units_csv)
    snapshot = _write_snapshot(market_units_csv, snapshot_dir, mutator)

    with pytest.raises(MarketUnitsSnapshotError, match=message):
        load_units_snapshot(str(snapshot), "2026-04-20", str(market_units_csv))


def test_snapshot_units_numeric_invalid_is_invalid(tmp_path):
    market_units_csv = tmp_path / "market_units.csv"
    snapshot_dir = tmp_path / "current"
    snapshot_dir.mkdir()
    _write_market_units(market_units_csv)
    snapshot = _write_snapshot(
        market_units_csv,
        snapshot_dir,
        lambda payload: payload["items"][0].__setitem__("units", "not-a-number"),
    )

    with pytest.raises(MarketUnitsSnapshotError, match=r"item\[0\] units must be numeric"):
        load_units_snapshot(str(snapshot), "2026-04-20", str(market_units_csv))


def test_snapshot_empty_items_is_invalid(tmp_path):
    market_units_csv = tmp_path / "market_units.csv"
    snapshot_dir = tmp_path / "current"
    snapshot_dir.mkdir()
    _write_market_units(market_units_csv)
    snapshot = _write_snapshot(
        market_units_csv,
        snapshot_dir,
        lambda payload: payload.__setitem__("items", []),
    )

    with pytest.raises(MarketUnitsSnapshotError, match="snapshot items must not be empty"):
        load_units_snapshot(str(snapshot), "2026-04-20", str(market_units_csv))


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload.pop("captured_at"),
        lambda payload: payload["source"].__setitem__("ssot_a_sha256", "not-sha256"),
        lambda payload: payload["items"][0].__setitem__("units", "not-a-number"),
        lambda payload: payload.__setitem__("items", []),
    ],
)
def test_daily_mode_new_invalid_snapshot_checks_fall_back_to_live_csv(tmp_path, mutator):
    market_units_csv = tmp_path / "market_units.csv"
    snapshot_dir = tmp_path / "current"
    snapshot_dir.mkdir()
    _write_market_units(market_units_csv)
    _write_snapshot(market_units_csv, snapshot_dir, mutator)

    ledger = _ingester(tmp_path, market_units_csv, snapshot_dir).build_shadow_ledger("2026-04-20")

    assert ledger.units_source is not None
    assert ledger.units_source.type == "LIVE_CSV"


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload.pop("captured_at"),
        lambda payload: payload["source"].__setitem__("ssot_a_sha256", "not-sha256"),
        lambda payload: payload["items"][0].__setitem__("units", "not-a-number"),
    ],
)
def test_strict_mode_new_invalid_snapshot_checks_block(tmp_path, mutator):
    market_units_csv = tmp_path / "market_units.csv"
    snapshot_dir = tmp_path / "current"
    snapshot_dir.mkdir()
    _write_market_units(market_units_csv)
    _write_snapshot(market_units_csv, snapshot_dir, mutator)

    with pytest.raises(MarketUnitsSnapshotError):
        _ingester(tmp_path, market_units_csv, snapshot_dir).build_shadow_ledger("2026-04-20", units_mode="strict")


def test_asset_key_generation_priority():
    assert build_asset_key({"audit_match_key": " audited ", "asset_class": "jp_stock", "currency": "jpy"}) == "audited"
    assert build_asset_key({"asset_class": "jp_stock", "currency": "jpy", "source_symbol": " 1234.T "}) == "JP_STOCK:JPY:1234.T"
    assert build_asset_key({"asset_class": "us_stock", "currency": "usd", "name": " Cashlike "}) == "US_STOCK:USD:Cashlike"


def test_asset_key_duplicate_detection(tmp_path):
    market_units_csv = tmp_path / "market_units.csv"
    _write_market_units(
        market_units_csv,
        [
            "name,asset_class,currency,units,source_symbol,audit_match_key,csv_url",
            "FundA,MUTUAL_FUNDS,JPY,1,FundA,DUP,",
            "FundB,MUTUAL_FUNDS,JPY,2,FundB,DUP,",
        ],
    )

    with pytest.raises(MarketUnitsSnapshotError, match="duplicate asset_key"):
        load_market_units_csv(str(market_units_csv))


def test_enabled_is_optional_and_not_used_for_v1_exclusion(tmp_path):
    market_units_csv = tmp_path / "market_units.csv"
    snapshot_dir = tmp_path / "current"
    snapshot_dir.mkdir()
    _write_market_units(
        market_units_csv,
        [
            "name,asset_class,currency,units,source_symbol,audit_match_key,csv_url,enabled",
            "FundA,MUTUAL_FUNDS,JPY,20000,FundA,,,false",
        ],
    )

    ledger = _ingester(tmp_path, market_units_csv, snapshot_dir).build_shadow_ledger("2026-04-20")

    assert [asset.name for asset in ledger.assets] == ["FundA"]
    assert ledger.assets[0].current_value_jpy == pytest.approx(24000)
