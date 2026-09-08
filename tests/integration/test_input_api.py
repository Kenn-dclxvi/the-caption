"""Exercise the input application against temporary, durable file stores."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
import csv
from datetime import datetime, timezone
from http.cookies import SimpleCookie
import io
import json
from threading import Event
from uuid import UUID, uuid4

import pytest

from src.app.input_api import InputApi
from src.domain.input_api_auth import OWNER_PERMISSIONS, token_digest
from src.domain.market_units_input import MARKET_UNIT_FIELDS
from src.infra.input_api_credentials import CredentialFile
from src.infra.market_units_input_repository import MarketUnitsInputRepository


PATH = "/api/v1/market-units"
TOKEN = "test_owner_credential_0123456789"
EXACT_UNITS = "123456789012345678.123456789012"


def item(**changes):
    return {
        "asset_id": None, "name": "New fund", "asset_class": "MUTUAL_FUNDS",
        "currency": "JPY", "units": "1", "source_symbol": "NEW",
        "audit_match_key": "", "csv_url": "", **changes,
    }


def replacement(document, *, clear_all=False):
    return {"items": [{key: row[key] for key in (*MARKET_UNIT_FIELDS, "asset_id")}
                      for row in document["items"]], "clear_all": clear_all}


class ApiFixture:
    def __init__(self, directory):
        self.csv_path = directory / "market_units.csv"
        self.credentials_path = directory / "credentials.json"
        self.now = 1788825600.0
        self.records = [self.record()]
        self.save_credentials()
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=[*MARKET_UNIT_FIELDS, "enabled"])
        writer.writeheader()
        for row in [item(name="Existing A", source_symbol="A", units=EXACT_UNITS),
                    item(name="Existing B", source_symbol="B", units="2.5000")]:
            writer.writerow({**{key: row[key] for key in MARKET_UNIT_FIELDS}, "enabled": "false"})
        self.csv_path.write_text(output.getvalue(), encoding="utf-8")
        self.reopen()

    def record(self, *, token=TOKEN, identifier="owner-key", subject="owner", permissions=None):
        return {"id": identifier, "subject": subject, "sha256": token_digest(token),
                "permissions": sorted(OWNER_PERMISSIONS if permissions is None else permissions),
                "expires_at": datetime.fromtimestamp(self.now + 366 * 86400, timezone.utc).isoformat(),
                "revoked": False}

    def save_credentials(self):
        self.credentials_path.write_text(json.dumps({"tokens": self.records}), encoding="utf-8")

    def reopen(self):
        self.repository = MarketUnitsInputRepository(self.csv_path)
        self.api = InputApi(self.repository, CredentialFile(str(self.credentials_path)),
                            clock=lambda: self.now, allowed_price_hosts={"prices.example.com"})

    def request(self, method="GET", *, path=PATH, body="", headers=None, token=TOKEN, **extra):
        supplied = {} if token is None else {"Authorization": f"Bearer {token}"}
        supplied.update(headers or {})
        return self.api.handle({"method": method, "path": path, "body": body,
                                "headers": supplied, **extra})

    def get(self):
        result = self.request()
        assert result["status"] == 200, result
        return result

    def put(self, payload, etag, *, key=None, headers=None, token=TOKEN):
        supplied = {"Content-Type": "application/json", "If-Match": etag,
                    "Idempotency-Key": key or str(uuid4())}
        supplied.update(headers or {})
        return self.request("PUT", body=json.dumps(payload), headers=supplied, token=token)

    def state(self):
        with self.repository.transaction() as transaction:
            return deepcopy(transaction.state)


@pytest.fixture
def service(tmp_path):
    return ApiFixture(tmp_path)


def assert_problem(result, status, code):
    assert result["status"] == status, result
    assert result["headers"]["Content-Type"] == "application/problem+json"
    assert result["headers"]["Cache-Control"] == "no-store"
    assert result["body"]["status"] == status
    assert result["body"]["code"] == code
    assert result["body"]["type"] == "about:blank"
    assert result["body"]["title"]
    assert result["body"]["detail"]
    assert result["body"]["instance"].startswith("urn:uuid:")


def test_get_migrates_once_without_rewriting_exact_legacy_input(service):
    original = service.csv_path.read_bytes()
    first = service.get()
    assert first["headers"]["Cache-Control"] == "no-store"
    assert first["headers"]["ETag"].startswith('"')
    assert not first["headers"]["ETag"].startswith('W/')
    assert first["body"]["storage_state"] == "ready"
    assert first["body"]["items"][0]["units"] == EXACT_UNITS
    assert first["body"]["items"][1]["units"] == "2.5000"
    assert len({UUID(row["asset_id"]) for row in first["body"]["items"]}) == 2
    service.reopen()
    assert service.get() == first
    assert service.csv_path.read_bytes() == original


def test_initial_save_transitions_uninitialized_to_ready(service):
    service.csv_path.unlink()
    initial = service.get()
    assert initial["body"]["storage_state"] == "uninitialized"
    assert initial["body"]["updated_at"] is None
    assert initial["body"]["items"] == []
    result = service.put({"items": [item()], "clear_all": False}, initial["headers"]["ETag"])
    assert result["status"] == 200
    assert result["body"]["changed"] is True
    assert result["body"]["change_id"] is not None
    assert result["body"]["resource"]["storage_state"] == "ready"
    service.reopen()
    assert service.get()["body"] == result["body"]["resource"]


def test_put_normalizes_all_fields_preserves_ids_order_and_legacy_metadata(service):
    initial = service.get()
    payload = replacement(initial["body"])
    retained_id = payload["items"][1]["asset_id"]
    payload["items"] = [
        item(asset_id=retained_id, name="  Edited B  ", asset_class="  custom_class  ",
             currency="  usd  ", units=EXACT_UNITS, source_symbol="  TICKER  ",
             audit_match_key="  alternate-key  ", csv_url="https://prices.example.com/history.csv"),
        item(name=" Added C ", source_symbol="", units="123.450000000000"),
    ]
    result = service.put(payload, initial["headers"]["ETag"])
    assert result["status"] == 200, result
    assert "ETag" not in result["headers"]
    assert "Last-Modified" not in result["headers"]
    assert result["headers"]["Idempotency-Replayed"] == "false"
    saved = result["body"]["resource"]
    first, second = saved["items"]
    assert first["asset_id"] == retained_id
    assert first["name"] == "Edited B"
    assert first["asset_class"] == "CUSTOM_CLASS"
    assert first["currency"] == "USD"
    assert first["units"] == EXACT_UNITS
    assert first["source_symbol"] == "TICKER"
    assert first["audit_match_key"] == "alternate-key"
    assert first["csv_url"] == "https://prices.example.com/history.csv"
    assert second["asset_id"] not in {row["asset_id"] for row in initial["body"]["items"]}
    UUID(second["asset_id"])
    assert second["units"] == "123.45"
    assert second["source_symbol"] == "Added C"
    service.reopen()
    latest = service.get()
    assert latest["body"] == saved
    assert latest["headers"]["ETag"] != initial["headers"]["ETag"]
    rows = list(csv.DictReader(io.StringIO(service.csv_path.read_text(encoding="utf-8"))))
    assert [row["name"] for row in rows] == ["Edited B", "Added C"]
    assert rows[0]["units"] == EXACT_UNITS
    assert rows[0]["enabled"] == "false"
    assert rows[1]["enabled"] == ""
    assert len(service.state()["changes"]) == 1


def test_no_change_keeps_revision_and_does_not_create_change_history(service):
    initial = service.get()
    normalized = service.put(replacement(initial["body"]), initial["headers"]["ETag"])
    assert normalized["status"] == 200
    latest = service.get()
    history_count = len(service.state()["changes"])
    csv_before = service.csv_path.read_bytes()
    result = service.put(replacement(latest["body"]), latest["headers"]["ETag"])
    assert result["status"] == 200
    assert result["body"] == {"changed": False, "change_id": None, "resource": latest["body"]}
    assert service.get() == latest
    assert service.csv_path.read_bytes() == csv_before
    assert len(service.state()["changes"]) == history_count


@pytest.mark.parametrize(("condition", "status", "code"), [
    (None, 428, "precondition_required"), ('W/"stale"', 400, "invalid_request"),
    ("*", 400, "invalid_request"), ('"one", "two"', 400, "invalid_request"),
    ('"stale"', 412, "revision_mismatch"),
])
def test_if_match_rejections_preserve_document(service, condition, status, code):
    initial = service.get()
    original = service.csv_path.read_bytes()
    headers = {"Content-Type": "application/json", "Idempotency-Key": str(uuid4())}
    if condition is not None:
        headers["If-Match"] = condition
    result = service.request("PUT", body=json.dumps(replacement(initial["body"])), headers=headers)
    assert_problem(result, status, code)
    assert service.get() == initial
    assert service.csv_path.read_bytes() == original


@pytest.mark.parametrize(("value", "code"), [
    (1.5, "invalid_decimal"), (True, "invalid_decimal"), (None, "invalid_decimal"),
    ("NaN", "invalid_decimal"), ("Infinity", "invalid_decimal"), ("-1", "invalid_decimal"),
    ("1e2", "invalid_decimal"), (" 1", "invalid_decimal"), ("+1", "invalid_decimal"),
    ("1234567890123456789", "invalid_decimal"), ("0.1234567890123", "invalid_decimal"),
])
def test_invalid_decimal_values_are_rejected_without_rounding(service, value, code):
    initial = service.get()
    original = service.csv_path.read_bytes()
    payload = replacement(initial["body"])
    payload["items"][0]["units"] = value
    result = service.put(payload, initial["headers"]["ETag"])
    assert_problem(result, 422, "invalid_input")
    assert {"pointer": "/items/0/units", "code": code} in [
        {"pointer": error["pointer"], "code": error["code"]} for error in result["body"]["errors"]]
    assert service.get() == initial
    assert service.csv_path.read_bytes() == original


@pytest.mark.parametrize(("mutation", "pointer", "code"), [
    ("unknown_id", "/items/0/asset_id", "unknown_identifier"),
    ("duplicate_id", "/items/1/asset_id", "duplicate_id"),
    ("duplicate_key", "/items/1/audit_match_key", "duplicate_asset_key"),
    ("unknown_field", "/items/0/extra~1key~0", "normalized_value_invalid"),
    ("missing_field", "/items/0/currency", "normalized_value_invalid"),
    ("uppercase_expansion", "/items/0/asset_class", "normalized_value_invalid"),
    ("unsafe_price_url", "/items/0/csv_url", "normalized_value_invalid"),
])
def test_structural_errors_report_json_pointers_and_preserve_state(service, mutation, pointer, code):
    initial = service.get()
    payload = replacement(initial["body"])
    if mutation == "unknown_id":
        payload["items"][0]["asset_id"] = str(uuid4())
    elif mutation == "duplicate_id":
        payload["items"][1]["asset_id"] = payload["items"][0]["asset_id"]
    elif mutation == "duplicate_key":
        payload["items"][1]["source_symbol"] = payload["items"][0]["source_symbol"]
    elif mutation == "unknown_field":
        payload["items"][0]["extra/key~"] = "discarding this would hide a client error"
    elif mutation == "missing_field":
        del payload["items"][0]["currency"]
    elif mutation == "uppercase_expansion":
        payload["items"][0]["asset_class"] = "ß" * 256
    else:
        payload["items"][0]["csv_url"] = "https://127.0.0.1/private.csv"
    original = service.csv_path.read_bytes()
    result = service.put(payload, initial["headers"]["ETag"])
    assert_problem(result, 422, "invalid_input")
    assert any(error["pointer"] == pointer and error["code"] == code
               for error in result["body"]["errors"])
    assert service.get() == initial
    assert service.csv_path.read_bytes() == original


@pytest.mark.parametrize("raw", [
    '{"items": [], "items": [], "clear_all": true}',
    '{"items": [{"name": "A", "name": "B"}], "clear_all": false}',
    '{"items": [NaN], "clear_all": false}',
    '{"items": [Infinity], "clear_all": false}',
])
def test_invalid_json_does_not_reserve_idempotency_key(service, raw):
    initial = service.get()
    key = str(uuid4())
    result = service.request("PUT", body=raw, headers={"Content-Type": "application/json",
        "If-Match": initial["headers"]["ETag"], "Idempotency-Key": key})
    assert_problem(result, 400, "invalid_request")
    assert service.get() == initial
    valid = service.put(replacement(initial["body"]), initial["headers"]["ETag"], key=key)
    assert valid["status"] == 200, valid


@pytest.mark.parametrize("key", [None, "not-a-uuid", '"ae4edca3-8aa8-4daa-a1a8-514ac6820568"'])
def test_missing_or_malformed_idempotency_key_is_rejected(service, key):
    initial = service.get()
    headers = {"Content-Type": "application/json", "If-Match": initial["headers"]["ETag"]}
    if key is not None:
        headers["Idempotency-Key"] = key
    result = service.request("PUT", body=json.dumps(replacement(initial["body"])), headers=headers)
    assert_problem(result, 400, "invalid_request")
    assert service.get() == initial


@pytest.mark.parametrize(("body", "content_type", "status", "code"), [
    ("{}", "text/plain", 415, "unsupported_media_type"),
    ("x" * (2 * 1024 * 1024 + 1), "application/json", 413, "payload_too_large"),
], ids=["unsupported-media-type", "body-exceeds-2-mib"])
def test_transport_validation_preserves_inputs(service, body, content_type, status, code):
    initial = service.get()
    result = service.request("PUT", body=body, headers={"Content-Type": content_type,
        "If-Match": initial["headers"]["ETag"], "Idempotency-Key": str(uuid4())})
    assert_problem(result, status, code)
    assert service.get() == initial


def test_clear_requires_explicit_intent_and_additional_permission(service):
    initial = service.get()
    no_intent = service.put({"items": [], "clear_all": False}, initial["headers"]["ETag"])
    assert_problem(no_intent, 422, "invalid_input")
    assert any(error["code"] == "invalid_clear_intent" for error in no_intent["body"]["errors"])
    nonempty = replacement(initial["body"], clear_all=True)
    assert_problem(service.put(nonempty, initial["headers"]["ETag"]), 422, "invalid_input")
    key = str(uuid4())
    payload = {"items": [], "clear_all": True}
    service.records[0]["permissions"].remove("market-units:clear")
    service.save_credentials()
    assert_problem(service.put(payload, initial["headers"]["ETag"], key=key), 403, "permission_denied")
    assert service.get() == initial
    service.records[0]["permissions"].append("market-units:clear")
    service.save_credentials()
    result = service.put(payload, initial["headers"]["ETag"], key=key)
    assert result["status"] == 200
    assert result["body"]["resource"]["items"] == []
    assert result["body"]["resource"]["storage_state"] == "ready"
    service.reopen()
    assert service.get()["body"] == result["body"]["resource"]
    assert list(csv.DictReader(io.StringIO(service.csv_path.read_text(encoding="utf-8")))) == []


def test_replay_after_later_write_and_restart_returns_original_result(service):
    initial = service.get()
    payload = replacement(initial["body"])
    payload["items"].append(item())
    key = str(uuid4())
    first = service.put(payload, initial["headers"]["ETag"], key=key)
    assert first["status"] == 200
    latest = service.get()
    later_payload = replacement(latest["body"])
    later_payload["items"][0]["name"] = "Later edit"
    assert service.put(later_payload, latest["headers"]["ETag"])["status"] == 200
    latest = service.get()
    csv_before = service.csv_path.read_bytes()
    service.reopen()
    # JSON object ordering and whitespace are immaterial to request identity.
    raw = json.dumps(dict(reversed(list(payload.items()))), indent=3, sort_keys=True)
    replay = service.request("PUT", body=raw, headers={"Content-Type": "application/json",
        "If-Match": initial["headers"]["ETag"], "Idempotency-Key": key})
    assert replay["status"] == first["status"]
    assert replay["body"] == first["body"]
    assert replay["headers"]["Idempotency-Replayed"] == "true"
    assert "ETag" not in replay["headers"]
    assert service.get() == latest
    assert service.csv_path.read_bytes() == csv_before
    assert len(service.state()["changes"]) == 2


@pytest.mark.parametrize("difference", ["body", "if_match", "array_order", "decimal_spelling"])
def test_key_reuse_cannot_change_body_or_precondition(service, difference):
    initial = service.get()
    payload = replacement(initial["body"])
    key = str(uuid4())
    assert service.put(payload, initial["headers"]["ETag"], key=key)["status"] == 200
    latest = service.get()
    condition = initial["headers"]["ETag"]
    if difference == "body":
        payload["items"][0]["name"] = "Changed body"
    elif difference == "if_match":
        condition = latest["headers"]["ETag"]
        assert condition != initial["headers"]["ETag"]
    elif difference == "array_order":
        payload["items"].reverse()
    else:
        payload["items"][1]["units"] = "2.5"
    result = service.put(payload, condition, key=key)
    assert_problem(result, 409, "idempotency_key_reused")
    assert service.get() == latest


@pytest.mark.parametrize("failure", [412, 422])
def test_accepted_failures_are_durable_receipts(service, failure):
    initial = service.get()
    payload = replacement(initial["body"])
    condition = '"stale"' if failure == 412 else initial["headers"]["ETag"]
    if failure == 422:
        payload["items"][0]["asset_id"] = str(uuid4())
    key = str(uuid4())
    first = service.put(payload, condition, key=key)
    assert_problem(first, failure, "revision_mismatch" if failure == 412 else "invalid_input")
    assert service.get() == initial
    assert service.put(replacement(initial["body"]), initial["headers"]["ETag"])["status"] == 200
    service.reopen()
    latest = service.get()
    replay = service.put(payload, condition, key=key)
    assert replay["status"] == failure
    assert replay["body"] == first["body"]
    assert replay["headers"]["Idempotency-Replayed"] == "true"
    assert service.get() == latest
    repaired = replacement(latest["body"])
    assert_problem(service.put(repaired, latest["headers"]["ETag"], key=key), 409, "idempotency_key_reused")


def test_token_rotation_replays_for_same_subject_but_not_a_different_subject(service):
    initial = service.get()
    payload = replacement(initial["body"])
    key = str(uuid4())
    first = service.put(payload, initial["headers"]["ETag"], key=key)
    new_token = "rotated_owner_credential_0123456789"
    other_token = "different_owner_credential_0123456789"
    service.records[0]["revoked"] = True
    service.records += [service.record(token=new_token, identifier="rotated"),
                        service.record(token=other_token, identifier="other", subject="other-owner")]
    service.save_credentials()
    service.reopen()
    replay = service.put(payload, initial["headers"]["ETag"], key=key, token=new_token)
    assert replay["status"] == 200
    assert replay["body"] == first["body"]
    assert replay["headers"]["Idempotency-Replayed"] == "true"
    other = service.put(payload, initial["headers"]["ETag"], key=key, token=other_token)
    assert_problem(other, 412, "revision_mismatch")


@pytest.mark.parametrize("change", ["revocation", "permission_reduction", "expiration"])
def test_current_authorization_is_checked_before_cached_result(service, change):
    initial = service.get()
    payload = replacement(initial["body"])
    key = str(uuid4())
    first = service.put(payload, initial["headers"]["ETag"], key=key)
    assert first["status"] == 200
    before = service.csv_path.read_bytes()
    if change == "revocation":
        service.records[0]["revoked"] = True
    elif change == "permission_reduction":
        service.records[0]["permissions"].remove("market-units:replace")
    else:
        service.records[0]["expires_at"] = datetime.fromtimestamp(service.now, timezone.utc).isoformat()
    service.save_credentials()
    result = service.put(payload, initial["headers"]["ETag"], key=key)
    assert_problem(result, 403 if change == "permission_reduction" else 401,
                   "permission_denied" if change == "permission_reduction" else "authentication_required")
    assert service.csv_path.read_bytes() == before


def test_expired_result_leaves_persistent_tombstone_and_never_reapplies(service):
    initial = service.get()
    payload = replacement(initial["body"])
    key = str(uuid4())
    assert service.put(payload, initial["headers"]["ETag"], key=key)["status"] == 200
    latest = service.get()
    service.now += 30 * 86400
    expired = service.put(payload, initial["headers"]["ETag"], key=key)
    assert_problem(expired, 409, "idempotency_result_expired")
    receipts = list(service.state()["receipts"].values())
    assert len(receipts) == 1
    assert "result" not in receipts[0]
    service.reopen()
    assert_problem(service.put(payload, initial["headers"]["ETag"], key=key),
                   409, "idempotency_result_expired")
    assert service.get() == latest
    assert len(service.state()["changes"]) == 1


def login(service, *, secure=False):
    result = service.request("POST", path="/api/session", body="{}", secure=secure)
    assert result["status"] == 200, result
    cookie = SimpleCookie()
    cookie.load(result["headers"]["Set-Cookie"])
    sid = cookie["caption_session"].value
    return result, f"caption_session={sid}"


def test_session_bootstrap_csrf_logout_and_cookie_attributes(service):
    logged_in, cookie = login(service, secure=True)
    cookie_header = logged_in["headers"]["Set-Cookie"]
    assert all(part in cookie_header for part in ["HttpOnly", "SameSite=Strict", "Secure", "Path=/"])
    csrf = logged_in["body"]["csrf_token"]
    assert TOKEN not in json.dumps(logged_in)
    session = service.request(path="/api/session", token=None, headers={"Cookie": cookie})
    assert session["body"]["csrf_token"] == csrf
    initial = service.get()
    payload = replacement(initial["body"])
    key = str(uuid4())
    for supplied in ({"Cookie": cookie}, {"Cookie": cookie, "X-CSRF-Token": "wrong"}):
        result = service.put(payload, initial["headers"]["ETag"], key=key, token=None, headers=supplied)
        assert_problem(result, 403, "csrf_invalid")
    result = service.put(payload, initial["headers"]["ETag"], key=key, token=None,
                         headers={"Cookie": cookie, "X-CSRF-Token": csrf})
    assert result["status"] == 200
    assert_problem(service.request("DELETE", path="/api/session", token=None,
                   headers={"Cookie": cookie}), 403, "csrf_invalid")
    logged_out = service.request("DELETE", path="/api/session", token=None,
        headers={"Cookie": cookie, "X-CSRF-Token": csrf})
    assert logged_out["status"] == 204
    assert "Max-Age=0" in logged_out["headers"]["Set-Cookie"]
    assert_problem(service.request(token=None, headers={"Cookie": cookie}), 401, "authentication_required")


@pytest.mark.parametrize("method", ["GET", "PUT"])
def test_bearer_and_session_are_not_combined(service, method):
    logged_in, cookie = login(service)
    result = service.request(method, headers={"Cookie": cookie,
        "X-CSRF-Token": logged_in["body"]["csrf_token"]})
    assert_problem(result, 400, "invalid_request")


@pytest.mark.parametrize("change", ["session_expiration", "credential_revocation"])
def test_session_uses_current_credential_and_expiry(service, change):
    _, cookie = login(service)
    if change == "session_expiration":
        service.now += 8 * 3600
    else:
        service.records[0]["revoked"] = True
        service.save_credentials()
    assert_problem(service.request(token=None, headers={"Cookie": cookie}), 401, "authentication_required")


@pytest.mark.parametrize("missing", ["market-units:read", "market-units:replace"])
def test_put_requires_both_permissions(service, missing):
    initial = service.get()
    service.records[0]["permissions"].remove(missing)
    service.save_credentials()
    result = service.put(replacement(initial["body"]), initial["headers"]["ETag"])
    assert_problem(result, 403, "permission_denied")
    assert service.state()["changes"] == []


def test_legacy_paths_and_authorization_envelope_cannot_bypass_policy(service):
    original = service.csv_path.read_bytes()
    assert_problem(service.request(path="/api/funds", token=None), 401, "authentication_required")
    legacy = service.request(path="/api/funds")
    assert legacy["status"] == 200
    assert legacy["body"][0]["units"] == EXACT_UNITS
    assert "asset_id" not in legacy["body"][0]
    rejected = service.request("POST", path="/api/funds", body="[]")
    assert_problem(rejected, 428, "client_upgrade_required")
    assert service.csv_path.read_bytes() == original
    assert service.state()["changes"] == []
    allowed = service.request("POST", path="/api/external-assets", kind="authorize",
                              permissions=["external-assets:read", "external-assets:replace"])
    assert allowed["status"] == 204
    service.records[0]["permissions"].remove("external-assets:replace")
    service.save_credentials()
    denied = service.request("POST", path="/api/external-assets", kind="authorize",
                             permissions=["external-assets:read", "external-assets:replace"])
    assert_problem(denied, 403, "permission_denied")


@pytest.mark.parametrize("failure", ["csv_drift", "csv_missing", "state_missing", "state_corrupt"])
def test_registered_storage_failures_are_503_without_empty_fallback(service, failure):
    service.get()
    if failure == "csv_drift":
        service.csv_path.write_text("unregistered,change\n", encoding="utf-8")
    elif failure == "csv_missing":
        service.csv_path.unlink()
    elif failure == "state_missing":
        service.repository.state_path.unlink()
    else:
        service.repository.state_path.write_text("{}", encoding="utf-8")
    result = service.request()
    assert_problem(result, 503, "input_store_unavailable")
    assert result["headers"]["Retry-After"]
    assert str(service.csv_path) not in json.dumps(result)
    assert "items" not in result["body"]


def test_missing_authentication_configuration_fails_closed_and_health_is_sanitized(service):
    service.credentials_path.unlink()
    result = service.request()
    assert_problem(result, 503, "authentication_unconfigured")
    health = service.request(path="/api/v1/health", token=None)
    assert health["status"] == 503
    assert set(health["body"]) == {"status", "api_version", "contract_version"}
    assert str(service.credentials_path) not in json.dumps(health)
    assert not service.repository.state_path.exists()


def test_same_request_in_progress_returns_retry_after_without_second_write(service, monkeypatch):
    initial = service.get()
    payload = replacement(initial["body"])
    key = str(uuid4())
    entered, release = Event(), Event()
    real_transaction = service.repository.transaction

    @contextmanager
    def blocked_transaction():
        with real_transaction() as transaction:
            entered.set()
            assert release.wait(timeout=10), "test did not release the transaction"
            yield transaction

    monkeypatch.setattr(service.repository, "transaction", blocked_transaction)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(service.put, payload, initial["headers"]["ETag"], key=key)
        try:
            assert entered.wait(timeout=10), "first request did not enter the real transaction"
            pending = service.put(payload, initial["headers"]["ETag"], key=key)
            assert_problem(pending, 409, "idempotency_in_progress")
            assert pending["headers"]["Retry-After"]
        finally:
            release.set()
        assert first.result(timeout=10)["status"] == 200
    assert len(service.state()["changes"]) == 1
