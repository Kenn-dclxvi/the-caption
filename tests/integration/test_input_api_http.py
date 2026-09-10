"""Exercise Express and its real private Python worker with isolated input data."""

import csv
from datetime import datetime, timedelta, timezone
import hashlib
from http.client import HTTPConnection
from http.cookiejar import CookieJar
from http.cookies import SimpleCookie
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import time
from uuid import UUID, uuid4
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener

import pytest


ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = ROOT / "src/web/market_units_editor"
API_PATH = "/api/v1/market-units"
TOKEN = "http_test_owner_credential_0123456789"
EXACT_UNITS = "123456789012345678.123456789012"
FIELDS = ("name", "asset_class", "currency", "units", "source_symbol", "audit_match_key", "csv_url")


class HttpApi:
    def __init__(self, directory, *, session_namespace="", run_script=None, profile=None):
        self.session_namespace = session_namespace
        self.run_script = run_script
        self.profile = profile
        self.data_dir = directory / "data"
        self.csv_path = self.data_dir / "collection/market_units.csv"
        self.csv_path.parent.mkdir(parents=True)
        with self.csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=[*FIELDS, "enabled"])
            writer.writeheader()
            writer.writerow({"name": "既存ファンド", "asset_class": "MUTUAL_FUNDS",
                             "currency": "JPY", "units": EXACT_UNITS, "source_symbol": "EXISTING",
                             "audit_match_key": "", "csv_url": "", "enabled": "false"})
        self.credentials_path = directory / "credentials.json"
        permissions = [f"{resource}:{action}"
                       for resource in ("market-units", "external-assets", "portfolio-basis")
                       for action in ("read", "replace", "clear")]
        self.credentials = {"tokens": [{"id": "http-test-owner", "subject": "http-test-owner",
            "sha256": hashlib.sha256(TOKEN.encode()).hexdigest(),
            "permissions": [*permissions, "inputs:schema:read"],
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "revoked": False}]}
        self.save_credentials()
        self.log_path = directory / "server.log"
        self.process = None
        self.log = None

    def save_credentials(self):
        self.credentials_path.write_text(json.dumps(self.credentials), encoding="utf-8")
        self.credentials_path.chmod(0o600)

    def start(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            self.port = listener.getsockname()[1]
        environment = {**os.environ, "NODE_ENV": "production", "HOST": "127.0.0.1",
            "PORT": str(self.port), "CAPTION_DATA_DIR": str(self.data_dir),
            "CAPTION_API_CREDENTIALS_FILE": str(self.credentials_path),
            "CAPTION_PERSONAL_UI_ORIGINS": "",
            "CAPTION_API_PYTHON": str(ROOT / ".venv/bin/python"),
            "CAPTION_API_PRICE_HOSTS": "", "PYTHONDONTWRITEBYTECODE": "1"}
        environment.pop("CAPTION_API_SESSION_NAMESPACE", None)
        if self.session_namespace is not None:
            environment["CAPTION_API_SESSION_NAMESPACE"] = self.session_namespace
        command = [str(WEB_ROOT / "node_modules/.bin/tsx"), "server.ts"]
        if self.run_script is not None:
            environment["NODE_BIN"] = shutil.which("node")
            command = ["bash", str(self.run_script), f"collection-web-{self.profile}"]
        self.log = self.log_path.open("ab")
        self.process = subprocess.Popen(
            command, cwd=WEB_ROOT,
            env=environment, stdout=self.log, stderr=subprocess.STDOUT, start_new_session=True,
        )
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and self.process.poll() is None:
            try:
                ready = self.request(path="/api/v1/health", token=None)
                assert ready["status"] == 200, ready
                return
            except (ConnectionError, TimeoutError):
                time.sleep(0.05)
        pytest.fail(f"HTTP server did not start: {self.log_path.read_text(encoding='utf-8')}")

    def stop(self):
        if self.process is not None:
            # tsx, Express, and the worker all belong to this dedicated process group.
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=5)
            self.process = None
        if self.log is not None:
            self.log.close()
            self.log = None

    def request(self, method="GET", *, path=API_PATH, body=None, headers=None, token=TOKEN):
        supplied = {} if token is None else {"Authorization": f"Bearer {token}"}
        supplied.update(headers or {})
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            supplied.setdefault("Content-Type", "application/json")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        connection = HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=supplied)
            response = connection.getresponse()
            raw = response.read()
            return {"status": response.status,
                    "headers": {name.lower(): value for name, value in response.getheaders()},
                    "body": json.loads(raw) if raw else None}
        finally:
            connection.close()

    def get(self):
        result = self.request()
        assert result["status"] == 200, result
        return result

    def put(self, body, etag, *, key=None, headers=None, token=TOKEN):
        supplied = {"Content-Type": "application/json", "If-Match": etag,
                    "Idempotency-Key": key or str(uuid4())}
        supplied.update(headers or {})
        return self.request("PUT", body=body, headers=supplied, token=token)

    def login(self):
        result = self.request("POST", path="/api/session", body={},
                              headers={"X-Forwarded-Proto": "https"})
        assert result["status"] == 200, result
        jar = SimpleCookie()
        jar.load(result["headers"]["set-cookie"])
        return result, {"Cookie": f"caption_session={jar['caption_session'].value}"}


@pytest.fixture
def http_api(tmp_path):
    if shutil.which("node") is None or not (WEB_ROOT / "node_modules/.bin/tsx").is_file():
        pytest.skip("HTTP integration requires Node and the editor's installed npm dependencies")
    service = HttpApi(tmp_path)
    try:
        service.start()
        yield service
    finally:
        service.stop()


def replacement(document):
    return {"items": [{field: row[field] for field in (*FIELDS, "asset_id")}
                      for row in document["items"]], "clear_all": False}


def assert_problem(result, status, code):
    assert result["status"] == status, result
    assert result["headers"]["content-type"].split(";", 1)[0] == "application/problem+json"
    assert result["headers"]["cache-control"] == "no-store"
    assert result["body"]["status"] == status
    assert result["body"]["code"] == code
    assert result["body"]["instance"].startswith("urn:uuid:")


def test_http_health_and_private_data_authentication(http_api):
    health = http_api.request(path="/api/v1/health?probe=1", token=None)
    assert health["status"] == 200
    assert health["body"] == {"status": "ok", "api_version": "v1", "contract_version": "0.1.0"}
    assert health["headers"]["cache-control"] == "no-store"
    denied = http_api.request(token=None)
    assert_problem(denied, 401, "authentication_required")
    assert denied["headers"]["www-authenticate"] == 'Bearer realm="caption"'
    assert str(http_api.data_dir) not in json.dumps(denied)


def test_http_save_replay_after_restart_and_stale_precondition(http_api):
    initial = http_api.get()
    etag = initial["headers"]["etag"]
    assert etag.startswith('"') and not etag.startswith("W/")
    assert initial["body"]["items"][0]["units"] == EXACT_UNITS
    payload = replacement(initial["body"])
    original_id = payload["items"][0]["asset_id"]
    UUID(original_id)
    payload["items"][0]["name"] = "  更新ファンド  "
    key = str(uuid4())
    saved = http_api.put(payload, etag, key=key)
    assert saved["status"] == 200, saved
    assert "etag" not in saved["headers"]
    assert "last-modified" not in saved["headers"]
    assert saved["headers"]["idempotency-replayed"] == "false"
    assert saved["body"]["changed"] is True
    resource = saved["body"]["resource"]
    assert resource["items"][0]["name"] == "更新ファンド"
    assert resource["items"][0]["asset_id"] == original_id
    assert resource["items"][0]["units"] == EXACT_UNITS
    current = http_api.get()
    assert current["body"] == resource
    assert current["headers"]["etag"] != etag
    csv_after = http_api.csv_path.read_bytes()
    http_api.stop()
    http_api.start()
    replay = http_api.put(json.dumps(payload, sort_keys=True, indent=2), etag, key=key)
    assert replay["status"] == 200, replay
    assert replay["body"] == saved["body"]
    assert replay["headers"]["idempotency-replayed"] == "true"
    assert "etag" not in replay["headers"] and "last-modified" not in replay["headers"]
    assert_problem(http_api.put(payload, etag), 412, "revision_mismatch")
    assert http_api.get()["body"] == resource
    assert http_api.csv_path.read_bytes() == csv_after


def test_http_session_cookie_csrf_and_logout(http_api):
    logged_in, cookie = http_api.login()
    cookie_header = logged_in["headers"]["set-cookie"]
    assert all(value in cookie_header for value in ("HttpOnly", "SameSite=Strict", "Secure", "Path=/"))
    assert TOKEN not in json.dumps(logged_in)
    csrf = logged_in["body"]["csrf_token"]
    session = http_api.request(path="/api/session", headers=cookie, token=None)
    assert session["status"] == 200 and session["body"]["csrf_token"] == csrf
    initial = http_api.get()
    payload = replacement(initial["body"])
    payload["items"][0]["units"] = "2.5000"
    key = str(uuid4())
    rejected = http_api.put(payload, initial["headers"]["etag"], key=key, headers=cookie, token=None)
    assert_problem(rejected, 403, "csrf_invalid")
    assert http_api.get()["body"] == initial["body"]
    authorized = {**cookie, "X-CSRF-Token": csrf}
    saved = http_api.put(payload, initial["headers"]["etag"], key=key, headers=authorized, token=None)
    assert saved["status"] == 200, saved
    assert saved["body"]["resource"]["items"][0]["units"] == "2.5"
    assert_problem(http_api.request(headers=cookie), 400, "invalid_request")
    assert_problem(http_api.request("DELETE", path="/api/session", headers=cookie, token=None),
                   403, "csrf_invalid")
    logout = http_api.request("DELETE", path="/api/session", headers=authorized, token=None)
    assert logout["status"] == 204 and logout["body"] is None
    assert "Max-Age=0" in logout["headers"]["set-cookie"]
    assert_problem(http_api.request(headers=cookie, token=None), 401, "authentication_required")


@pytest.fixture
def web_run_script(tmp_path):
    if shutil.which("node") is None or not (WEB_ROOT / "node_modules/.bin/tsx").is_file():
        pytest.skip("HTTP integration requires Node and the editor's installed npm dependencies")
    if shutil.which("otool") is None:
        pytest.skip("run.sh currently requires macOS otool to validate Node")
    # Preserve the launcher's sibling-checkout layout without using live data or ports.
    for name in ("THE-CAPTION", "THE-CAPTION-DEV"):
        checkout = tmp_path / name
        checkout.mkdir()
        (checkout / "src").symlink_to(ROOT / "src", target_is_directory=True)
        (checkout / ".venv").symlink_to(ROOT / ".venv", target_is_directory=True)
    script = tmp_path / "THE-CAPTION/run.sh"
    shutil.copy2(ROOT / "run.sh", script)
    return script


@pytest.mark.parametrize("namespace_setting", [None, "", "custom"], ids=["unset", "empty", "explicit"])
@pytest.mark.parametrize("logout_profile", ["prd", "dev"])
def test_http_profile_sessions_coexist_in_one_cookie_jar(tmp_path, web_run_script, logout_profile, namespace_setting):
    # Run the actual launcher, npm, Express, and independent Python workers.
    namespaces = {profile: f"custom_{profile}" if namespace_setting == "custom" else profile
                  for profile in ("prd", "dev")}
    servers = {profile: HttpApi(tmp_path / profile, run_script=web_run_script, profile=profile,
                               session_namespace=namespaces[profile] if namespace_setting == "custom" else namespace_setting)
               for profile in ("prd", "dev")}
    jar = CookieJar()
    browser = build_opener(ProxyHandler({}), HTTPCookieProcessor(jar))

    def request(profile, method="GET", *, path="/api/session", headers=None):
        server = servers[profile]
        req = Request(f"http://127.0.0.1:{server.port}{path}", method=method,
                      data=b"{}" if method == "POST" else None, headers=headers or {})
        try:
            reply = browser.open(req, timeout=5)
        except HTTPError as error:
            reply = error
        with reply:
            raw = reply.read()
            return reply.status, json.loads(raw) if raw else None

    try:
        for server in servers.values():
            server.start()
        sessions = {}
        for profile in ("prd", "dev", "prd", "dev"):
            status, session = request(profile, "POST", headers={"Authorization": f"Bearer {TOKEN}"})
            assert status == 200, session
            sessions[profile] = session["csrf_token"]
            for active, csrf in sessions.items():
                status, current = request(active)
                assert status == 200 and current["csrf_token"] == csrf
                assert request(active, path=API_PATH)[0] == 200
        assert {cookie.name for cookie in jar} == {f"caption_session_{namespace}" for namespace in namespaces.values()}
        assert len(jar) == 2
        assert request(logout_profile, "DELETE", headers={"X-CSRF-Token": sessions[logout_profile]})[0] == 204
        assert request(logout_profile)[0] == 401
        remaining = "dev" if logout_profile == "prd" else "prd"
        status, current = request(remaining)
        assert status == 200 and current["csrf_token"] == sessions[remaining]
        assert request(remaining, path=API_PATH)[0] == 200
        assert [cookie.name for cookie in jar] == [f"caption_session_{namespaces[remaining]}"]
    finally:
        for server in servers.values():
            server.stop()


def test_http_escaped_body_at_limit_preserves_existing_worker_session(http_api):
    logged_in, cookie = http_api.login()
    # Each NUL expands to six bytes in the gateway's JSON stdio envelope.
    # A request at the HTTP body limit must not exceed the worker's frame limit.
    rejected = http_api.request("POST", path="/api/session", body=b"\x00" * (2 * 1024 * 1024),
                                headers={"Content-Type": "text/plain"}, token=None)
    assert_problem(rejected, 401, "authentication_required")
    session = http_api.request(path="/api/session", headers=cookie, token=None)
    assert session["status"] == 200, session
    assert session["body"]["csrf_token"] == logged_in["body"]["csrf_token"]


def test_http_legacy_funds_cannot_write(http_api):
    original = http_api.csv_path.read_bytes()
    assert_problem(http_api.request(path="/api/funds", token=None), 401, "authentication_required")
    legacy = http_api.request(path="/api/funds")
    assert legacy["status"] == 200
    assert legacy["body"][0]["units"] == EXACT_UNITS
    assert "asset_id" not in legacy["body"][0]
    assert_problem(http_api.request("POST", path="/api/funds", body=[]),
                   428, "client_upgrade_required")
    assert http_api.csv_path.read_bytes() == original


@pytest.mark.parametrize(("resource", "payload"), [
    ("external-assets", {"default": {"items": [{"category": "CASH_EXTERNAL", "amount": 100, "name": "現金"}]}}),
    ("portfolio-basis", {"default": {"total_acquisition_cost_jpy": 100}}),
])
def test_http_legacy_resources_require_auth_csrf_and_current_permission(http_api, resource, payload):
    path = f"/api/{resource}"
    stored_path = http_api.data_dir / f"{resource.replace('-', '_')}.json"
    assert_problem(http_api.request(path=path, token=None), 401, "authentication_required")
    assert_problem(http_api.request("POST", path=path, body=payload, token=None),
                   401, "authentication_required")
    logged_in, cookie = http_api.login()
    assert_problem(http_api.request("POST", path=path, body=payload, headers=cookie, token=None),
                   403, "csrf_invalid")
    assert not stored_path.exists()
    authorized = {**cookie, "X-CSRF-Token": logged_in["body"]["csrf_token"]}
    rejected = http_api.request("POST", path=path, body=payload, headers=authorized, token=None)
    assert_problem(rejected, 428, "client_upgrade_required")
    assert not stored_path.exists()


@pytest.mark.parametrize("resource", ["external-assets", "portfolio-basis"])
def test_http_monthly_api_save_replay_csrf_and_legacy_read(http_api, resource):
    path = f"/api/v1/{resource}"
    assert_problem(http_api.request(path=path, token=None), 401, "authentication_required")
    initial = http_api.request(path=path)
    assert initial["status"] == 200 and initial["body"]["storage_state"] == "uninitialized"
    row = ({"entry_id": None, "category": "CASH_EXTERNAL", "amount": EXACT_UNITS, "name": ""}
           if resource == "external-assets" else {"entry_id": None, "total_acquisition_cost_jpy": EXACT_UNITS})
    payload = {"months": {"default": {"items": [row]} if resource == "external-assets" else row}, "clear_all": False}
    key = str(uuid4())
    headers = {"If-Match": initial["headers"]["etag"], "Idempotency-Key": key}
    logged_in, cookie = http_api.login()
    assert_problem(http_api.request("PUT", path=path, body=payload, headers={**headers, **cookie}, token=None), 403, "csrf_invalid")
    saved = http_api.request("PUT", path=path, body=payload,
                            headers={**headers, **cookie, "X-CSRF-Token": logged_in["body"]["csrf_token"]}, token=None)
    assert saved["status"] == 200, saved
    assert "etag" not in saved["headers"] and "last-modified" not in saved["headers"]
    assert EXACT_UNITS in json.dumps(saved["body"])
    legacy = http_api.request(path=f"/api/{resource}")
    assert legacy["status"] == 200 and EXACT_UNITS in json.dumps(legacy["body"])
    assert "entry_id" not in json.dumps(legacy["body"])
    http_api.stop()
    http_api.start()
    replay = http_api.request("PUT", path=path, body=payload, headers=headers)
    assert replay["status"] == 200 and replay["body"] == saved["body"]
    assert replay["headers"]["idempotency-replayed"] == "true"
    assert_problem(http_api.request("PUT", path=path, body=payload,
                   headers={**headers, "Idempotency-Key": str(uuid4())}), 412, "revision_mismatch")
    http_api.credentials["tokens"][0]["permissions"].remove(f"{resource}:replace")
    http_api.save_credentials()
    assert_problem(http_api.request("PUT", path=path, body=payload, headers=headers), 403, "permission_denied")


@pytest.mark.parametrize(("body", "content_type", "status", "code"), [
    (b'{"items":', "application/json", 400, "invalid_request"),
    (b'{"items":[],"items":[],"clear_all":true}', "application/json", 400, "invalid_request"),
    (b'{"name":"\xff"}', "application/json", 400, "invalid_request"),
    (b"{}", "text/plain", 415, "unsupported_media_type"),
    (b"x" * (2 * 1024 * 1024 + 1), "application/json", 413, "payload_too_large"),
], ids=["malformed-json", "duplicate-json-key", "invalid-utf8", "unsupported-media", "over-2-mib"])
def test_http_transport_errors_preserve_data_and_allow_corrected_request(http_api, body, content_type, status, code):
    initial = http_api.get()
    original = http_api.csv_path.read_bytes()
    key = str(uuid4())
    rejected = http_api.put(body, initial["headers"]["etag"], key=key,
                            headers={"Content-Type": content_type})
    assert_problem(rejected, status, code)
    assert http_api.get()["body"] == initial["body"]
    assert http_api.csv_path.read_bytes() == original
    corrected = http_api.put(replacement(initial["body"]), initial["headers"]["etag"], key=key)
    assert corrected["status"] == 200, corrected


@pytest.mark.parametrize("resource", ["external-assets", "portfolio-basis"])
def test_http_monthly_input_root_does_not_follow_a_csv_file_symlink(http_api, tmp_path, resource):
    http_api.stop()
    target = tmp_path / "elsewhere/market_units.csv"
    target.parent.mkdir()
    http_api.csv_path.replace(target)
    http_api.csv_path.symlink_to(target)
    record = {"items": [{"category": "CASH_EXTERNAL", "amount": "123", "name": ""}]} if resource == "external-assets" else {"total_acquisition_cost_jpy": "123"}
    (http_api.data_dir / (resource.replace("-", "_") + ".json")).write_text(json.dumps({"default": record}))
    http_api.start()
    result = http_api.request(path=f"/api/v1/{resource}")
    assert result["status"] == 200, result
    assert result["body"]["storage_state"] == "ready"
    saved = result["body"]["months"]["default"]
    assert (saved["items"][0]["amount"] if resource == "external-assets" else saved["total_acquisition_cost_jpy"]) == "123"
