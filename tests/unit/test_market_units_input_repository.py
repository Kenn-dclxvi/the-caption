"""Real temporary-file persistence, interruption and daily capture guarantees."""

import csv
import hashlib
import io
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event
from uuid import uuid4

import pytest

from src.infra import market_units_input_repository as storage
from src.infra import market_units_snapshot_repository as snapshots
from src.infra.market_units_input_repository import MarketUnitsInputRepository, MarketUnitsStoreError


HEADER = "name,asset_class,currency,units,source_symbol,audit_match_key,csv_url"
CSV = HEADER + ",enabled,operator_note\n Fund ,mutual_funds,jpy,123456789012345678.123456789012,,,https://old.example/prices.csv,0,keep me\n"


def _repository(tmp_path, content=CSV):
    path = tmp_path / "market_units.csv"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    return MarketUnitsInputRepository(path)


def _replace(session, units="12.500"):
    session.state["document"]["items"][0]["units"] = units
    session.state["document"]["revision"] = str(uuid4())
    session.state["receipts"]["key"] = {"status": 200, "body": {"changed": True, "units": units}}
    session.state["changes"].append({"change_id": "change-1", "after": deepcopy(session.state["document"])})
    session.commit(write_csv=True)


def test_bootstrap_persists_ids_and_normalizes_without_rewriting_legacy_csv(tmp_path):
    repository = _repository(tmp_path)
    before = repository.csv_path.read_bytes()
    with repository.transaction() as session:
        state = deepcopy(session.state)
        etag = repository.etag(session.state)
    item = state["document"]["items"][0]
    assert item["name"] == "Fund"
    assert item["asset_class"] == "MUTUAL_FUNDS"
    assert item["currency"] == "JPY"
    assert item["source_symbol"] == "Fund"
    assert item["units"] == "123456789012345678.123456789012"
    assert state["legacy_extras"][item["asset_id"]] == {"enabled": "0", "operator_note": "keep me"}
    with MarketUnitsInputRepository(repository.csv_path).transaction() as session:
        assert session.state == state
        assert repository.etag(session.state) == etag
    assert repository.csv_path.read_bytes() == before


def test_uninitialized_document_is_stable_and_first_save_becomes_ready(tmp_path):
    repository = _repository(tmp_path, None)
    with repository.transaction() as session:
        before = deepcopy(session.state["document"])
        etag = repository.etag(session.state)
        assert before["storage_state"] == "uninitialized"
        assert before["updated_at"] is None
        assert before["items"] == []
    assert not repository.csv_path.exists()
    with repository.transaction() as session:
        assert session.state["document"] == before
        assert repository.etag(session.state) == etag
        session.state["document"].update(storage_state="ready", updated_at="2026-09-08T00:00:00+00:00", revision=str(uuid4()))
        session.commit(write_csv=True)
    assert repository.csv_path.read_text() == HEADER + "\n"


@pytest.mark.parametrize("content", ["name,units\nFund,1\n", HEADER + "\nFund,ETF,JPY,NaN,,,,\n",
                                     HEADER + "\nFund,ETF,JPY,1,,,\nFund,ETF,JPY,1,,,\n",
                                     HEADER + ",name\nFund,ETF,JPY,1,,,,duplicate\n"])
def test_malformed_existing_input_is_not_empty_or_rewritten(tmp_path, content):
    repository = _repository(tmp_path, content)
    with pytest.raises(MarketUnitsStoreError):
        with repository.transaction():
            pytest.fail("invalid existing CSV was accepted")
    assert repository.csv_path.read_text() == content
    assert not repository.state_path.exists()


@pytest.mark.parametrize("drift", ["replace", "delete", "metadata", "missing_metadata", "missing_registration"])
def test_registered_storage_drift_is_unavailable(tmp_path, drift):
    repository = _repository(tmp_path)
    with repository.transaction():
        pass
    if drift == "replace":
        repository.csv_path.write_text(CSV.replace("keep me", "manual"))
    elif drift == "delete":
        repository.csv_path.unlink()
    elif drift == "missing_metadata":
        repository.state_path.unlink()
    elif drift == "missing_registration":
        repository.registration_path.unlink()
    else:
        repository.state_path.write_text(repository.state_path.read_text().replace("keep me", "manual"))
    with pytest.raises(MarketUnitsStoreError):
        with repository.transaction():
            pytest.fail("registered drift was accepted")


def test_extras_follow_stable_id_across_rename_reordering_and_new_rows(tmp_path):
    repository = _repository(tmp_path, CSV + "Other,ETF,USD,2,OTH,,,1,second\n")
    with repository.transaction() as session:
        first, second = session.state["document"]["items"]
        first["name"] = "Renamed"
        new = {**second, "asset_id": str(uuid4()), "name": "New", "source_symbol": "NEW", "asset_key": "ETF:USD:NEW"}
        session.state["document"]["items"] = [second, new, first]
        session.commit(write_csv=True)
    rows = list(csv.DictReader(io.StringIO(repository.csv_path.read_text())))
    assert [row["name"] for row in rows] == ["Other", "New", "Renamed"]
    assert [row["enabled"] for row in rows] == ["1", "", "0"]
    assert [row["operator_note"] for row in rows] == ["second", "", "keep me"]
    with repository.transaction() as session:
        session.state["document"]["items"] = [session.state["document"]["items"][0]]
        session.commit(write_csv=True)
        assert list(session.state["legacy_extras"]) == [second["asset_id"]]


def test_receipt_only_commit_preserves_csv_document_and_etag(tmp_path):
    repository = _repository(tmp_path)
    with repository.transaction() as session:
        before = repository.csv_path.read_bytes()
        document = deepcopy(session.state["document"])
        etag = repository.etag(session.state)
        session.state["receipts"]["invalid"] = {"status": 422, "fingerprint": "fingerprint"}
        session.commit()
    with repository.transaction() as session:
        assert session.state["document"] == document
        assert repository.etag(session.state) == etag
        assert session.state["receipts"]["invalid"]["status"] == 422
    assert repository.csv_path.read_bytes() == before


@pytest.mark.parametrize("target,after,committed", [
    ("pending.json", False, False), ("pending.json", True, True),
    ("market_units.csv", False, True), ("market_units.csv", True, True),
    ("state.json", False, True), ("state.json", True, True),
])
def test_interrupted_commit_recovers_document_receipt_history_and_csv_together(tmp_path, monkeypatch, target, after, committed):
    repository = _repository(tmp_path)
    with repository.transaction() as session:
        original = deepcopy(session.state)
    real_replace = storage._replace_bytes
    fired = False

    def fail_once(path, content, **kwargs):
        nonlocal fired
        should_fail = path.name == target and not fired
        if should_fail:
            fired = True
        if should_fail and not after:
            raise OSError("simulated process interruption before replace")
        real_replace(path, content, **kwargs)
        if should_fail:
            raise OSError("simulated process interruption after replace")

    monkeypatch.setattr(storage, "_replace_bytes", fail_once)
    with pytest.raises(MarketUnitsStoreError):
        with repository.transaction() as session:
            _replace(session)
    with MarketUnitsInputRepository(repository.csv_path).transaction() as session:
        if committed:
            assert session.state["document"]["items"][0]["units"] == "12.500"
            assert session.state["receipts"]["key"]["body"]["units"] == "12.500"
            assert len(session.state["changes"]) == 1
            assert session.state["csv_hash"] == hashlib.sha256(repository.csv_path.read_bytes()).hexdigest()
            assert list(csv.DictReader(io.StringIO(repository.csv_path.read_text())))[0]["units"] == "12.500"
        else:
            assert session.state == original
    assert not repository.journal_path.exists()


def test_pending_recovery_never_overwrites_new_manual_input(tmp_path, monkeypatch):
    repository = _repository(tmp_path)
    with repository.transaction():
        pass
    real_replace = storage._replace_bytes

    def fail_csv(path, content, **kwargs):
        if path == repository.csv_path:
            raise OSError("interrupted CSV install")
        real_replace(path, content, **kwargs)

    monkeypatch.setattr(storage, "_replace_bytes", fail_csv)
    with pytest.raises(MarketUnitsStoreError):
        with repository.transaction() as session:
            _replace(session)
    manual = CSV.replace("keep me", "manual edit")
    repository.csv_path.write_text(manual)
    monkeypatch.setattr(storage, "_replace_bytes", real_replace)
    with pytest.raises(MarketUnitsStoreError):
        with repository.transaction():
            pass
    assert repository.csv_path.read_text() == manual
    assert repository.journal_path.exists()


def test_daily_capture_recovers_committed_csv_and_matching_hash(tmp_path, monkeypatch):
    repository = _repository(tmp_path)
    with repository.transaction():
        pass
    real_replace = storage._replace_bytes
    fired = False

    def fail_csv_once(path, content, **kwargs):
        nonlocal fired
        if path == repository.csv_path and not fired:
            fired = True
            raise OSError("interrupted CSV install")
        real_replace(path, content, **kwargs)

    monkeypatch.setattr(storage, "_replace_bytes", fail_csv_once)
    with pytest.raises(MarketUnitsStoreError):
        with repository.transaction() as session:
            _replace(session, "42")
    path = snapshots.ensure_units_snapshot("2026-09-08", str(repository.csv_path), str(tmp_path))
    saved = snapshots.load_units_snapshot(path, "2026-09-08", str(repository.csv_path))
    assert saved[0]["units"] == "42"
    snapshot_bytes = storage.Path(path).read_bytes()
    assert hashlib.sha256(repository.csv_path.read_bytes()).hexdigest().encode() in snapshot_bytes
    with repository.transaction() as session:
        _replace(session, "84")
    assert snapshots.ensure_units_snapshot("2026-09-08", str(repository.csv_path), str(tmp_path)) == path
    assert storage.Path(path).read_bytes() == snapshot_bytes


def test_snapshot_items_and_hash_come_from_one_byte_read(tmp_path, monkeypatch):
    repository = _repository(tmp_path, HEADER + "\nFund,ETF,JPY,1,,,\n")
    before = repository.csv_path.read_bytes()
    normalize = snapshots._normalize_csv_bytes

    def external_edit_after_read(raw_csv):
        repository.csv_path.write_text(HEADER + "\nFund,ETF,JPY,999,,,\n")
        return normalize(raw_csv)

    monkeypatch.setattr(snapshots, "_normalize_csv_bytes", external_edit_after_read)
    payload = snapshots.create_units_snapshot(str(repository.csv_path), "2026-09-08")
    assert payload["items"][0]["units"] == "1"
    assert payload["source"]["ssot_a_sha256"] == hashlib.sha256(before).hexdigest()
    assert not repository.state_path.exists()


def test_daily_reader_waits_for_api_transaction(tmp_path, monkeypatch):
    repository = _repository(tmp_path)
    with repository.transaction():
        pass
    installed_csv = Event()
    release_writer = Event()
    reader_started = Event()
    real_replace = storage._replace_bytes

    def paused_install(path, content, **kwargs):
        real_replace(path, content, **kwargs)
        if path == repository.csv_path:
            installed_csv.set()
            assert release_writer.wait(5)

    monkeypatch.setattr(storage, "_replace_bytes", paused_install)

    def write():
        with repository.transaction() as session:
            _replace(session, "73")

    def read():
        reader_started.set()
        return snapshots.create_units_snapshot(str(repository.csv_path), "2026-09-08")

    with ThreadPoolExecutor(max_workers=2) as executor:
        writer = executor.submit(write)
        try:
            assert installed_csv.wait(5)
            reader = executor.submit(read)
            assert reader_started.wait(5)
            assert not reader.done()
        finally:
            release_writer.set()
        writer.result(timeout=5)
        payload = reader.result(timeout=5)
    assert payload["items"][0]["units"] == "73"
    assert payload["source"]["ssot_a_sha256"] == hashlib.sha256(repository.csv_path.read_bytes()).hexdigest()
