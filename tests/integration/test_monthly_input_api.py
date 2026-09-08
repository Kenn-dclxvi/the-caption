"""Monthly API contracts against real durable JSON stores and daily readers."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

import pytest

from src.app.input_api import InputApi
from src.domain.input_api_auth import OWNER_PERMISSIONS, token_digest
from src.domain.monthly_inputs import MonthlyInputError, entries, normalize_months, validate_replacement
from src.infra.canonical_ledger_input_repository import CanonicalLedgerInputRepository
from src.infra.input_api_credentials import CredentialFile
from src.infra.market_units_input_repository import MarketUnitsInputRepository
from src.infra.monthly_input_repository import MonthlyInputRepository, MonthlyStoreError
import src.infra.monthly_input_repository as storage

TOKEN = "monthly_test_owner_credential_1234567890"
EXACT = "123456789012345678.123456789012"


class MonthlyApi:
    def __init__(self, directory, resource):
        self.resource = resource
        self.path = "/api/v1/" + resource
        self.file = directory / (resource.replace("-", "_") + ".json")
        self.credentials = directory / "credentials.json"
        self.now = 1788825600.0
        self.record = {"id": "owner", "subject": "owner", "sha256": token_digest(TOKEN),
                       "expires_at": datetime.fromtimestamp(self.now + 365 * 86400, timezone.utc).isoformat(),
                       "permissions": sorted(OWNER_PERMISSIONS), "revoked": False}
        self.save_credentials()
        self.repo = MonthlyInputRepository(self.file, resource)
        self.api = InputApi(MarketUnitsInputRepository(directory / "collection/market_units.csv"),
                            CredentialFile(str(self.credentials)), monthly_repositories={resource: self.repo},
                            clock=lambda: self.now)

    def save_credentials(self):
        self.credentials.write_text(json.dumps({"tokens": [self.record]}))

    def row(self, value=EXACT, entry_id=None):
        return ({"entry_id": entry_id, "category": "CASH_EXTERNAL", "amount": value, "name": ""}
                if self.resource == "external-assets" else {"entry_id": entry_id, "total_acquisition_cost_jpy": value})

    def payload(self, row=None, month="default"):
        row = self.row() if row is None else row
        return {"months": {month: {"items": [row]} if self.resource == "external-assets" else row}, "clear_all": False}

    def request(self, method="GET", payload=None, **headers):
        return self.api.handle({"method": method, "path": self.path, "headers": {
            "Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json", **headers},
            "body": "" if payload is None else json.dumps(payload)})

    def get(self):
        response = self.request()
        assert response["status"] == 200, response
        return response

    def put(self, payload, etag, key=None):
        return self.request("PUT", payload, **{"If-Match": etag, "Idempotency-Key": key or str(uuid4())})


@pytest.fixture(params=["external-assets", "portfolio-basis"])
def monthly(tmp_path, request):
    return MonthlyApi(tmp_path, request.param)


def test_monthly_uninitialized_save_exact_values_move_and_replay(monthly):
    initial = monthly.get()
    assert initial["body"]["storage_state"] == "uninitialized"
    assert initial["body"]["updated_at"] is None and not monthly.file.exists()
    key = str(uuid4())
    saved = monthly.put(monthly.payload(), initial["headers"]["ETag"], key)
    assert saved["status"] == 200, saved
    assert "ETag" not in saved["headers"] and "Last-Modified" not in saved["headers"]
    row = next(entries(saved["body"]["resource"]["months"], monthly.resource))
    assert EXACT in row.values()
    original_id = row["entry_id"]
    new = monthly.get()
    moved = monthly.put(monthly.payload(row, "2026-09"), new["headers"]["ETag"])
    assert moved["status"] == 200
    assert list(moved["body"]["resource"]["months"]) == ["2026-09"]
    assert next(entries(moved["body"]["resource"]["months"], monthly.resource))["entry_id"] == original_id
    before = monthly.file.read_bytes()
    replay = monthly.put(monthly.payload(), initial["headers"]["ETag"], key)
    assert replay["body"] == saved["body"] and replay["headers"]["Idempotency-Replayed"] == "true"
    assert monthly.file.read_bytes() == before
    assert monthly.put(monthly.payload(), initial["headers"]["ETag"])["status"] == 412
    no_change = monthly.put(monthly.payload(row, "2026-09"), monthly.get()["headers"]["ETag"])
    assert no_change["body"]["changed"] is False and no_change["body"]["change_id"] is None
    assert monthly.file.read_bytes() == before
    with monthly.repo.transaction() as session:
        assert len(session.state["changes"]) == 2


@pytest.mark.parametrize("bad", [None, True, 0, 1.5, "-1", "1e2", "NaN", "Infinity", " 1", "01", "1.0000000000001", "1" * 19])
def test_monthly_rejects_invalid_decimal_without_changing_input(monthly, bad):
    etag = monthly.get()["headers"]["ETag"]
    result = monthly.put(monthly.payload(monthly.row(bad)), etag)
    assert result["status"] == 422, result
    assert result["body"]["errors"][0]["code"] == "invalid_decimal"
    assert not monthly.file.exists()


@pytest.mark.parametrize("month", ["0000-01", "2026-00", "2026-13", "2026-1", "items", "a/b~c"])
def test_monthly_rejects_invalid_month(monthly, month):
    result = monthly.put(monthly.payload(month=month), monthly.get()["headers"]["ETag"])
    assert result["status"] == 422 and result["body"]["errors"][0]["code"] == "invalid_month"
    if month == "a/b~c":
        assert result["body"]["errors"][0]["pointer"] == "/months/a~1b~0c"


def test_monthly_ids_and_clear_permission(monthly):
    initial = monthly.get()
    unknown = monthly.put(monthly.payload(monthly.row(entry_id=str(uuid4()))), initial["headers"]["ETag"])
    assert unknown["status"] == 422
    saved = monthly.put(monthly.payload(), initial["headers"]["ETag"])
    row = next(entries(saved["body"]["resource"]["months"], monthly.resource))
    payload = monthly.payload(row)
    payload["months"]["2026-09"] = deepcopy(payload["months"]["default"])
    duplicate = monthly.put(payload, monthly.get()["headers"]["ETag"])
    assert duplicate["body"]["errors"][0]["code"] == "duplicate_id"
    clear = {"months": {"2026-09": {"items": []}} if monthly.resource == "external-assets" else {}, "clear_all": True}
    monthly.record["permissions"].remove(monthly.resource + ":clear")
    monthly.save_credentials()
    assert monthly.put(clear, monthly.get()["headers"]["ETag"])["status"] == 403
    clear["clear_all"] = False
    assert monthly.put(clear, monthly.get()["headers"]["ETag"])["status"] == 403
    monthly.record["permissions"].append(monthly.resource + ":clear")
    monthly.save_credentials()
    assert monthly.put(clear, monthly.get()["headers"]["ETag"])["status"] == 422
    clear["clear_all"] = True
    assert monthly.put(clear, monthly.get()["headers"]["ETag"])["status"] == 200


def test_monthly_receipts_require_current_permission_and_expire(monthly):
    initial = monthly.get()
    key = str(uuid4())
    saved = monthly.put(monthly.payload(), initial["headers"]["ETag"], key)
    assert saved["status"] == 200
    monthly.record["permissions"].remove(monthly.resource + ":replace")
    monthly.save_credentials()
    assert monthly.put(monthly.payload(), initial["headers"]["ETag"], key)["status"] == 403
    monthly.record["permissions"].append(monthly.resource + ":replace")
    monthly.save_credentials()
    assert monthly.put(monthly.payload(monthly.row("2")), initial["headers"]["ETag"], key)["body"]["code"] == "idempotency_key_reused"
    monthly.now += 31 * 86400
    assert monthly.put(monthly.payload(), initial["headers"]["ETag"], key)["body"]["code"] == "idempotency_result_expired"


@pytest.mark.parametrize("stage", ["journal", "data", "metadata", "marker"])
def test_monthly_recovery_finishes_data_and_receipt_before_daily_read(monthly, monkeypatch, stage):
    initial = monthly.get()
    # Include marker creation in each commit to exercise that recovery boundary.
    targets = {"journal": monthly.repo.journal_path, "data": monthly.file,
               "metadata": monthly.repo.state_path, "marker": monthly.repo.registration_path}
    original = storage._replace_bytes
    tripped = False
    def interrupt(path, data, **kwargs):
        nonlocal tripped
        original(path, data, **kwargs)
        if path == targets[stage] and not tripped:
            tripped = True
            raise OSError("simulated process interruption")
    if stage == "marker":
        # The bootstrap installs the marker; interrupt its initial installation instead.
        monthly.repo.registration_path.unlink()
        monthly.repo.state_path.unlink()
    monkeypatch.setattr(storage, "_replace_bytes", interrupt)
    key = str(uuid4())
    failed = monthly.put(monthly.payload(), initial["headers"]["ETag"], key)
    assert failed["status"] == 503 and tripped
    monkeypatch.setattr(storage, "_replace_bytes", original)
    if stage == "marker":
        assert monthly.get()["body"]["storage_state"] == "uninitialized"
        return
    reader = CanonicalLedgerInputRepository()
    legacy = (reader.read_external_assets(str(monthly.file)) if monthly.resource == "external-assets"
              else reader.read_portfolio_basis(str(monthly.file)))
    assert EXACT in json.dumps(legacy)
    replay = monthly.put(monthly.payload(), initial["headers"]["ETag"], key)
    assert replay["status"] == 200 and replay["headers"]["Idempotency-Replayed"] == "true"
    assert not monthly.repo.journal_path.exists()


@pytest.mark.parametrize("damage", ["file", "metadata", "marker"])
def test_monthly_registered_damage_never_becomes_empty(monthly, damage):
    monthly.put(monthly.payload(), monthly.get()["headers"]["ETag"])
    {"file": monthly.file, "metadata": monthly.repo.state_path, "marker": monthly.repo.registration_path}[damage].unlink()
    assert monthly.request()["status"] == 503


def test_monthly_external_edit_is_rejected_and_preserved(monthly):
    monthly.put(monthly.payload(), monthly.get()["headers"]["ETag"])
    monthly.file.write_text('{}')
    assert monthly.request()["status"] == 503
    assert monthly.file.read_text() == '{}'
    with pytest.raises(MonthlyStoreError):
        monthly.repo.read_legacy()


@pytest.mark.parametrize("exact", [EXACT, "123456789012345678"])
def test_monthly_migration_preserves_numeric_precision_and_source_bytes(monthly, exact):
    if monthly.resource == "external-assets":
        raw = ('{"items":[{"category":"CASH_EXTERNAL","amount":' + exact + '}]}').encode()
    else:
        raw = ('{"default":{"total_acquisition_cost_jpy":' + exact + '}}').encode()
    monthly.file.write_bytes(raw)
    first = monthly.get()
    assert exact in next(entries(first["body"]["months"], monthly.resource)).values()
    assert monthly.get() == first and monthly.file.read_bytes() == raw


@pytest.mark.parametrize("raw", [b'{"default":{},"default":{}}', b'{"default":null}', b'not json'])
def test_monthly_invalid_legacy_data_is_not_migrated(monthly, raw):
    monthly.file.write_bytes(raw)
    assert monthly.request()["status"] == 503
    assert monthly.file.read_bytes() == raw and not monthly.repo.state_path.exists()


def test_external_empty_month_and_omission_have_distinct_daily_meaning(tmp_path):
    from src.domain.universal_ingester import UniversalIngester
    api = MonthlyApi(tmp_path, "external-assets")
    payload = api.payload(api.row("100"))
    payload["months"]["2026-09"] = {"items": []}
    assert api.put(payload, api.get()["headers"]["ETag"])["status"] == 200
    # The canonical reader preserves empty months; the existing domain selects fallback.
    ingester = object.__new__(UniversalIngester)
    ingester.external_assets_path = str(api.file)
    ingester._input_store = CanonicalLedgerInputRepository()
    assert ingester._load_external_assets("2026-09-08") == ([], "2026-09")
    months = api.get()["body"]["months"]
    del months["2026-09"]
    assert api.put({"months": months, "clear_all": False}, api.get()["headers"]["ETag"])["status"] == 200
    items, key = ingester._load_external_assets("2026-09-08")
    assert key == "default" and items[0]["amount"] == 100


def test_monthly_shape_limits_and_zero_semantics():
    for resource in ("external-assets", "portfolio-basis"):
        with pytest.raises(MonthlyInputError):
            normalize_months({str(i): {} for i in range(1201)}, resource, set())
        with pytest.raises(MonthlyInputError):
            validate_replacement({"months": {}, "clear_all": True, "unexpected": 1}, resource, set())
    with pytest.raises(MonthlyInputError):
        normalize_months({"default": {"items": [{}] * 5001}}, "external-assets", set())
    with pytest.raises(MonthlyInputError):
        normalize_months({"default": {"entry_id": None, "total_acquisition_cost_jpy": "0"}}, "portfolio-basis", set())
    assert normalize_months({"default": {"items": [{"entry_id": None, "category": "x", "amount": "0", "name": ""}]}}, "external-assets", set())


def test_monthly_permission_is_rechecked_after_lock(monthly, monkeypatch):
    from contextlib import contextmanager
    initial = monthly.get()
    original = monthly.repo.transaction
    @contextmanager
    def revoked_transaction():
        with original() as session:
            monthly.record["permissions"].remove(monthly.resource + ":replace")
            monthly.save_credentials()
            yield session
    monkeypatch.setattr(monthly.repo, "transaction", revoked_transaction)
    result = monthly.put(monthly.payload(), initial["headers"]["ETag"])
    assert result["status"] == 403 and not monthly.file.exists()


def test_monthly_concurrent_same_revision_only_one_write(monthly):
    from concurrent.futures import ThreadPoolExecutor
    initial = monthly.get()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(monthly.put, monthly.payload(monthly.row(value)), initial["headers"]["ETag"]) for value in ("10", "20")]
        assert sorted(future.result()["status"] for future in futures) == [200, 412]
    with monthly.repo.transaction() as session:
        assert len(session.state["changes"]) == 1
