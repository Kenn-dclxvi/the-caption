"""Durable month-input JSON plus IDs and receipts, with recovery before every read.

A flushed forward journal is the commit decision, as in the Market Units store.
Each resource has its own lock; separate resource PUTs are not one transaction.
"""

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import fcntl
import json
import os
from pathlib import Path
from uuid import uuid4

from src.domain.monthly_inputs import RESOURCES, entries, legacy_document, normalize_months
from src.infra.market_units_input_repository import (
    MarketUnitsStoreError, _digest, _fsync_directory, _json_bytes,
    _optional_digest, _read_optional, _replace_bytes,
)


class MonthlyStoreError(MarketUnitsStoreError):
    pass


def decode_json(raw: bytes, *, exact=False):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    def invalid(_):
        raise ValueError("Nonfinite JSON number")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid,
                      parse_float=Decimal if exact else float)


def envelope(state):
    return {"version": 1, "sha256": _digest(_json_bytes(state)), "state": state}


class MonthlyInputRepository:
    def __init__(self, path: str | Path, resource: str):
        if resource not in RESOURCES:
            raise ValueError("Unknown monthly resource")
        self.path = Path(path).resolve()
        self.resource = resource
        self.state_dir = self.path.parent / ".monthly_inputs_api" / self.path.name
        self.state_path = self.state_dir / "state.json"
        self.journal_path = self.state_dir / "pending.json"
        self.registration_path = self.state_dir / "registered"
        self.marker = (resource + ".v1\n").encode()

    def etag(self, state):
        return '"' + self.resource + ':' + _digest(_json_bytes(
            {key: state[key] for key in ("document", "data_hash")})) + '"'

    def _decode(self, raw):
        value = decode_json(raw)
        state = value["state"]
        if value["version"] != 1 or value["sha256"] != _digest(_json_bytes(state)) or state["resource"] != self.resource:
            raise MonthlyStoreError("Invalid monthly input metadata")
        if (not isinstance(state["receipts"], dict) or not isinstance(state["changes"], list)
                or not isinstance(state["document"]["months"], dict)
                or state["document"]["storage_state"] not in {"ready", "uninitialized"}):
            raise MonthlyStoreError("Invalid monthly input state")
        return state

    @contextmanager
    def _locked(self):
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        _fsync_directory(self.state_dir.parent)
        _fsync_directory(self.path.parent)
        descriptor = os.open(self.state_dir / "lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _check(self, raw, raw_state):
        marker = _read_optional(self.registration_path)
        if raw_state is None and marker is None:
            return None
        if raw_state is None or marker != self.marker:
            raise MonthlyStoreError("Registered monthly metadata is missing")
        state = self._decode(raw_state)
        if state["data_hash"] != _optional_digest(raw) or (raw is None and state["document"]["storage_state"] != "uninitialized"):
            raise MonthlyStoreError("Monthly input changed outside the registered transaction")
        return state

    def _recover(self):
        raw = _read_optional(self.journal_path)
        if raw is None:
            return
        journal = decode_json(raw)
        if journal["version"] != 1 or journal["sha256"] != _digest(_json_bytes(
                {key: value for key, value in journal.items() if key != "sha256"})):
            raise MonthlyStoreError("Invalid monthly recovery journal")
        new_state = _json_bytes(journal["new_state"])
        state = self._decode(new_state)
        new_data = None if journal["new_data"] is None else journal["new_data"].encode("utf-8")
        if state["data_hash"] != _optional_digest(new_data):
            raise MonthlyStoreError("Invalid monthly journal data")
        current_data, current_state = _read_optional(self.path), _read_optional(self.state_path)
        if (_optional_digest(current_data) not in {journal["old_data_hash"], state["data_hash"]}
                or _optional_digest(current_state) not in {journal["old_state_hash"], _digest(new_state)}):
            raise MonthlyStoreError("Unregistered change during monthly recovery")
        if current_data != new_data:
            if new_data is None:
                raise MonthlyStoreError("A transaction cannot delete the input file")
            _replace_bytes(self.path, new_data, default_mode=0o644)
        if current_state != new_state:
            _replace_bytes(self.state_path, new_state)
        if _read_optional(self.registration_path) != self.marker:
            _replace_bytes(self.registration_path, self.marker)
        self.journal_path.unlink()
        _fsync_directory(self.state_dir)

    def _write(self, state, old_data, old_state, new_data):
        if _read_optional(self.path) != old_data or _read_optional(self.state_path) != old_state:
            raise MonthlyStoreError("Monthly input changed before commit")
        journal = {"version": 1, "old_data_hash": _optional_digest(old_data),
                   "old_state_hash": _optional_digest(old_state), "new_state": envelope(state),
                   "new_data": None if new_data is None else new_data.decode("utf-8")}
        journal["sha256"] = _digest(_json_bytes(journal))
        _replace_bytes(self.journal_path, _json_bytes(journal))
        self._recover()

    @contextmanager
    def transaction(self):
        try:
            with self._locked():
                self._recover()
                raw, raw_state = _read_optional(self.path), _read_optional(self.state_path)
                state = self._check(raw, raw_state)
                if state is None:
                    months = normalize_months(decode_json(raw, exact=True) if raw is not None else {},
                                              self.resource, set(), legacy=True)
                    for entry in entries(months, self.resource):
                        entry["entry_id"] = str(uuid4())
                    state = {"resource": self.resource, "document": {
                        "revision": "rev_" + uuid4().hex, "storage_state": "uninitialized" if raw is None else "ready",
                        "updated_at": None if raw is None else datetime.now(timezone.utc).isoformat(), "months": months},
                        "data_hash": _optional_digest(raw), "receipts": {}, "changes": []}
                    self._write(state, raw, raw_state, raw)
                    raw_state = _json_bytes(envelope(state))
                session = MonthlyInputSession(self, state, raw, raw_state)
                try:
                    yield session
                finally:
                    session.active = False
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise MonthlyStoreError("Monthly input storage is unavailable") from exc

    def read_legacy(self):
        """Participate in API recovery without migrating a daily-only input."""
        with self._locked():
            self._recover()
            raw = _read_optional(self.path)
            self._check(raw, _read_optional(self.state_path))
            return None if raw is None else decode_json(raw)


class MonthlyInputSession:
    def __init__(self, repository, state, raw, raw_state):
        self.repository, self.state = repository, state
        self.raw, self.raw_state = raw, raw_state
        self.original_document = deepcopy(state["document"])
        self.active = True

    def commit(self, *, write_input=False):
        if not self.active:
            raise MonthlyStoreError("Monthly transaction is no longer active")
        new_data = self.raw
        if write_input:
            new_data = _json_bytes(legacy_document(self.state["document"]["months"], self.repository.resource)) + b"\n"
            self.state["data_hash"] = _digest(new_data)
        elif self.state["document"] != self.original_document:
            raise MonthlyStoreError("Document changes must persist their input representation")
        self.repository._write(self.state, self.raw, self.raw_state, new_data)
        self.raw, self.raw_state = new_data, _json_bytes(envelope(self.state))
        self.original_document = deepcopy(self.state["document"])
