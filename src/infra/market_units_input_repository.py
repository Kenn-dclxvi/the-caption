"""Durable Market Units input transactions shared by API and daily readers.

A flushed forward journal is the commit decision. CSV and metadata are installed
under one process lock; every participating reader finishes recovery first. The
two replacements alone are not an atomic commit. A failed response after the
journal decision may already have committed and is resolved by its saved receipt.
"""

from __future__ import annotations

import csv
import fcntl
import hashlib
import io
import json
import os
import stat
import tempfile
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from src.domain.market_units_input import (
    MARKET_UNIT_FIELDS,
    MarketUnitsInputError,
    normalize_legacy_rows,
)


class MarketUnitsStoreError(RuntimeError):
    """The registered input cannot be read or committed consistently."""

    code = "input_store_unavailable"


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_optional(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _optional_digest(value: bytes | None) -> str | None:
    return None if value is None else _digest(value)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _replace_bytes(path: Path, content: bytes, *, default_mode: int = 0o600) -> None:
    """Flush a same-directory temporary file, replace, then flush its directory."""
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        mode = default_mode
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _envelope(state: dict[str, Any]) -> dict[str, Any]:
    return {"version": 1, "sha256": _digest(_json_bytes(state)), "state": state}


def _decode_envelope(raw: bytes) -> dict[str, Any]:
    try:
        envelope = json.loads(raw)
        state = envelope["state"]
        if envelope["version"] != 1 or envelope["sha256"] != _digest(_json_bytes(state)):
            raise ValueError("metadata checksum mismatch")
        if not isinstance(state, dict) or not isinstance(state["document"], dict):
            raise ValueError("invalid metadata document")
        if not isinstance(state["receipts"], dict) or not isinstance(state["changes"], list):
            raise ValueError("invalid transaction records")
        if not isinstance(state["legacy_extras"], dict) or not isinstance(state["legacy_columns"], list):
            raise ValueError("invalid legacy metadata")
        if state["document"]["storage_state"] not in ("ready", "uninitialized"):
            raise ValueError("invalid storage state")
        state["csv_hash"]
        return state
    except (KeyError, TypeError, ValueError) as exc:
        raise MarketUnitsStoreError("Market Units metadata is invalid") from exc


class MarketUnitsInputRepository:
    def __init__(self, csv_path: str | Path):
        # Resolve aliases so API and daily writers choose the same lock identity.
        self.csv_path = Path(csv_path).resolve()
        self.state_dir = self.csv_path.parent / ".market_units_api" / self.csv_path.name
        self.state_path = self.state_dir / "state.json"
        self.journal_path = self.state_dir / "pending.json"
        self.registration_path = self.state_dir / "registered"

    @staticmethod
    def etag(state: dict[str, Any]) -> str:
        representation = {key: state[key] for key in
                          ("document", "legacy_extras", "legacy_columns", "csv_hash")}
        return '"mu:' + _digest(_json_bytes(representation)) + '"'

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        _fsync_directory(self.state_dir.parent)
        _fsync_directory(self.csv_path.parent)
        descriptor = os.open(self.state_dir / "lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    @contextmanager
    def transaction(self) -> Iterator[MarketUnitsInputSession]:
        try:
            with self._locked():
                self._recover()
                raw_csv = _read_optional(self.csv_path)
                raw_state = _read_optional(self.state_path)
                self._check_registration(raw_state)
                if raw_state is None:
                    state = self._bootstrap(raw_csv)
                    self._write_transaction(state, raw_csv, raw_state, raw_csv)
                    raw_state = _json_bytes(_envelope(state))
                else:
                    state = _decode_envelope(raw_state)
                    self._check_csv(state, raw_csv)
                session = MarketUnitsInputSession(self, state, raw_csv, raw_state)
                try:
                    yield session
                finally:
                    session._active = False
        except MarketUnitsStoreError:
            raise
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise MarketUnitsStoreError("Market Units storage is unavailable") from exc

    def _bootstrap(self, raw_csv: bytes | None) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        extras: dict[str, dict[str, str]] = {}
        columns: list[str] = []
        if raw_csv is not None:
            try:
                reader = csv.DictReader(io.StringIO(raw_csv.decode("utf-8-sig"), newline=""), strict=True)
                headers = reader.fieldnames or []
                if len(set(headers)) != len(headers) or not set(MARKET_UNIT_FIELDS).issubset(headers):
                    raise ValueError("CSV header is invalid")
                rows = list(reader)
                if any(None in row or any(value is None for value in row.values()) for row in rows):
                    raise ValueError("CSV row shape is invalid")
                normalized = normalize_legacy_rows(rows)
                columns = [header for header in headers if header not in MARKET_UNIT_FIELDS]
                for source, item in zip(rows, normalized):
                    asset_id = str(uuid4())
                    items.append({**item, "asset_id": asset_id})
                    extras[asset_id] = {column: source[column] for column in columns}
            except (UnicodeError, csv.Error, ValueError, MarketUnitsInputError) as exc:
                raise MarketUnitsStoreError("Existing Market Units CSV is invalid") from exc
        document = {
            "revision": str(uuid4()),
            "storage_state": "uninitialized" if raw_csv is None else "ready",
            "updated_at": None if raw_csv is None else datetime.now(timezone.utc).isoformat(),
            "items": items,
        }
        return {"document": document, "legacy_extras": extras, "legacy_columns": columns,
                "csv_hash": _optional_digest(raw_csv), "receipts": {}, "changes": []}

    @staticmethod
    def _check_csv(state: dict[str, Any], raw_csv: bytes | None) -> None:
        if _optional_digest(raw_csv) != state["csv_hash"]:
            raise MarketUnitsStoreError("Market Units CSV changed outside the registered transaction")
        if raw_csv is None and state["document"]["storage_state"] != "uninitialized":
            raise MarketUnitsStoreError("Registered Market Units CSV is missing")

    def _check_registration(self, raw_state: bytes | None) -> None:
        marker = _read_optional(self.registration_path)
        if raw_state is None and marker is None:
            return
        if raw_state is None or marker != b"market_units_api.v1\n":
            raise MarketUnitsStoreError("Registered Market Units metadata is missing or invalid")

    def _recover(self) -> None:
        raw_journal = _read_optional(self.journal_path)
        if raw_journal is None:
            return
        try:
            journal = json.loads(raw_journal)
            if journal["version"] != 1:
                raise ValueError("unknown journal version")
            new_state_bytes = _json_bytes(journal["new_state"])
            state = _decode_envelope(new_state_bytes)
            new_csv = None if journal["new_csv"] is None else journal["new_csv"].encode("utf-8")
            if state["csv_hash"] != _optional_digest(new_csv):
                raise ValueError("journal CSV checksum mismatch")
            if journal["sha256"] != _digest(_json_bytes({key: value for key, value in journal.items() if key != "sha256"})):
                raise ValueError("journal checksum mismatch")
            current_csv = _read_optional(self.csv_path)
            current_state = _read_optional(self.state_path)
            if _optional_digest(current_csv) not in (journal["old_csv_hash"], state["csv_hash"]):
                raise ValueError("unregistered CSV change during recovery")
            if _optional_digest(current_state) not in (journal["old_state_hash"], _digest(new_state_bytes)):
                raise ValueError("unregistered metadata change during recovery")
            # A metadata-only receipt commit retains the original CSV byte for byte.
            if current_csv != new_csv:
                if new_csv is None:
                    raise ValueError("a transaction cannot delete the CSV")
                _replace_bytes(self.csv_path, new_csv, default_mode=0o644)
            if current_state != new_state_bytes:
                _replace_bytes(self.state_path, new_state_bytes)
            if _read_optional(self.registration_path) != b"market_units_api.v1\n":
                _replace_bytes(self.registration_path, b"market_units_api.v1\n")
            self.journal_path.unlink()
            _fsync_directory(self.state_dir)
        except MarketUnitsStoreError:
            raise
        except (KeyError, TypeError, ValueError, UnicodeError) as exc:
            raise MarketUnitsStoreError("Market Units recovery journal is invalid") from exc

    def _write_transaction(self, state: dict[str, Any], old_csv: bytes | None,
                           old_state: bytes | None, new_csv: bytes | None) -> None:
        if _read_optional(self.csv_path) != old_csv or _read_optional(self.state_path) != old_state:
            raise MarketUnitsStoreError("Market Units input changed before commit")
        journal = {"version": 1, "old_csv_hash": _optional_digest(old_csv),
                   "old_state_hash": _optional_digest(old_state), "new_state": _envelope(state),
                   "new_csv": None if new_csv is None else new_csv.decode("utf-8")}
        journal["sha256"] = _digest(_json_bytes(journal))
        _replace_bytes(self.journal_path, _json_bytes(journal))
        self._recover()


class MarketUnitsInputSession:
    """Only valid inside its repository's transaction context."""

    def __init__(self, repository: MarketUnitsInputRepository, state: dict[str, Any],
                 raw_csv: bytes | None, raw_state: bytes):
        self.repository = repository
        self.state = state
        self._raw_csv = raw_csv
        self._raw_state = raw_state
        self._original_document = deepcopy(state["document"])
        self._active = True

    def commit(self, *, write_csv: bool = False) -> None:
        if not self._active:
            raise MarketUnitsStoreError("Market Units transaction is no longer active")
        new_csv = self._raw_csv
        if write_csv:
            columns = list(MARKET_UNIT_FIELDS) + self.state["legacy_columns"]
            output = io.StringIO(newline="")
            writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            retained_extras = {}
            for item in self.state["document"]["items"]:
                asset_id = item["asset_id"]
                extras = self.state["legacy_extras"].get(asset_id, {})
                retained_extras[asset_id] = extras
                writer.writerow({**extras, **{field: item[field] for field in MARKET_UNIT_FIELDS}})
            self.state["legacy_extras"] = retained_extras
            new_csv = output.getvalue().encode("utf-8")
            self.state["csv_hash"] = _digest(new_csv)
        elif self.state["document"] != self._original_document:
            raise MarketUnitsStoreError("Document changes must commit their CSV representation")
        self.repository._write_transaction(self.state, self._raw_csv, self._raw_state, new_csv)
        self._raw_csv = new_csv
        self._raw_state = _json_bytes(_envelope(self.state))
        self._original_document = deepcopy(self.state["document"])


@contextmanager
def locked_market_units_csv(csv_path: str | Path) -> Iterator[bytes]:
    """Read one CSV byte version with API recovery, without API bootstrapping.

    Legacy CLI inputs keep their existing normalization contract until registered
    by an API read. Existing immutable snapshots do not depend on today's input.
    """
    repository = MarketUnitsInputRepository(csv_path)
    with repository._locked():
        repository._recover()
        raw_csv = repository.csv_path.read_bytes()
        raw_state = _read_optional(repository.state_path)
        repository._check_registration(raw_state)
        if raw_state is not None:
            repository._check_csv(_decode_envelope(raw_state), raw_csv)
        yield raw_csv
