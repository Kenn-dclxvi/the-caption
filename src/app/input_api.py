"""Application boundary shared by the web gateway and API integration tests."""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import hmac
from http import HTTPStatus
from http.cookies import SimpleCookie
import json
import math
import re
import secrets
import threading
import time
from typing import Callable
import uuid

from src.domain.input_api_auth import (
    CredentialPolicyError, OWNER_PERMISSIONS, Principal, credential_principals,
    principal_for_session, principal_for_token,
)
from src.domain.market_units_input import MarketUnitsInputError, validate_replacement
from src.domain.monthly_inputs import entries, is_clear, legacy_document, validate_replacement as validate_monthly_replacement
from src.infra.market_units_input_repository import MarketUnitsStoreError


MAX_BODY_BYTES = 2 * 1024 * 1024
RECEIPT_SECONDS = 30 * 86400


class ApiError(Exception):
    def __init__(self, status: int, code: str, detail: str, errors=None):
        self.status, self.code, self.detail, self.errors = status, code, detail, errors


def response(status: int, body=None, headers=None) -> dict:
    return {"status": status, "body": body,
            "headers": {"Cache-Control": "no-store", **(headers or {})}}


def problem(error: ApiError) -> dict:
    body = {"type": "about:blank", "title": HTTPStatus(error.status).phrase,
            "status": error.status, "detail": error.detail,
            "instance": f"urn:uuid:{uuid.uuid4()}", "code": error.code}
    if error.errors is not None:
        body["errors"] = error.errors
    headers = {"Content-Type": "application/problem+json"}
    if error.status == 401:
        headers["WWW-Authenticate"] = 'Bearer realm="caption"'
    if error.status in {429, 503} or error.code == "idempotency_in_progress":
        headers["Retry-After"] = "5"
    return response(error.status, body, headers)


def strict_json(raw: str):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("duplicate JSON property")
            result[key] = value
        return result
    def invalid_constant(_value):
        raise ValueError("nonfinite JSON number")
    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("nonfinite JSON number")
        return number
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant, parse_float=finite_float)
    except (ValueError, TypeError, RecursionError) as exc:
        raise ApiError(400, "invalid_request", "正しいJSONを送信してください。重複キーは使用できません。") from exc


class InputApi:
    def __init__(self, repository, credential_file, *, allowed_price_hosts=None,
                 clock: Callable[[], float] = time.time, requests_per_minute: int = 240, personal_origins=None,
                 session_namespace: str = "", monthly_repositories=None):
        if not isinstance(session_namespace, str) or not re.fullmatch(r"[A-Za-z0-9_-]{0,64}", session_namespace):
            raise ValueError("session_namespace must contain at most 64 ASCII letters, digits, underscores or hyphens")
        self.session_cookie_name = "caption_session" + (f"_{session_namespace}" if session_namespace else "")
        self.repository = repository
        self.monthly_repositories = dict(monthly_repositories or {})
        self.credential_file = credential_file
        self.allowed_price_hosts = set(allowed_price_hosts or ())
        self.clock = clock
        self.requests_per_minute = requests_per_minute
        self.personal_origins = set(personal_origins or ())
        self._sessions = {}
        self._active = set()
        self._rates = {}
        self._guard = threading.Lock()

    def _credentials(self):
        try:
            document = self.credential_file.read()
            credential_principals(document, self.clock())
            return document
        except (OSError, ValueError, CredentialPolicyError) as exc:
            raise ApiError(503, "authentication_unconfigured",
                           "APIの認証設定を確認してください。管理者が資格情報ファイルを設定する必要があります。") from exc

    def _bearer(self, headers) -> str | None:
        value = headers.get("authorization")
        if value is None:
            return None
        match = re.fullmatch(r"Bearer ([A-Za-z0-9_-]{20,256})", value, re.IGNORECASE)
        if not match:
            raise ApiError(401, "authentication_required", "有効なアクセストークンが必要です。")
        return match.group(1)

    def _session_id(self, headers) -> str | None:
        try:
            raw = headers.get("cookie", "")
            if len(re.findall(rf"(?:^|;)\s*{re.escape(self.session_cookie_name)}=", raw)) > 1:
                raise ValueError("duplicate session cookie")
            jar = SimpleCookie()
            jar.load(raw)
            return jar[self.session_cookie_name].value if self.session_cookie_name in jar else None
        except Exception as exc:
            raise ApiError(400, "invalid_request", "session cookieが不正です。") from exc

    def _authenticate(self, headers, *, write=False) -> Principal:
        token, sid = self._bearer(headers), self._session_id(headers)
        if token is not None and sid is not None:
            raise ApiError(400, "invalid_request", "Bearerとsessionを同時に指定できません。")
        document = None if self.personal_origins else self._credentials()
        if token is not None:
            principal = principal_for_token(document or self._credentials(), token, self.clock())
        else:
            with self._guard:
                session = self._sessions.get(sid)
            principal = None
            if session and session["expires_at"] > self.clock():
                if session.get("personal") and self.personal_origins:
                    principal = Principal("personal-ui", "personal-owner", OWNER_PERMISSIONS, session["expires_at"])
                else:
                    principal = principal_for_session(document or self._credentials(), session["token_id"], session["subject"], self.clock())
                if principal and write and not hmac.compare_digest(
                    str(headers.get("x-csrf-token", "")), session["csrf_token"]
                ):
                    raise ApiError(403, "csrf_invalid", "画面を再読込みして認証状態を確認してください。")
        if principal is None:
            raise ApiError(401, "authentication_required", "ログインしてください。")
        return principal

    @staticmethod
    def _require(principal, permissions):
        if not set(permissions) <= principal.permissions:
            raise ApiError(403, "permission_denied", "この操作に必要な権限がありません。")

    def _rate_limit(self, peer):
        now = self.clock()
        key = str(peer)[:256]
        with self._guard:
            self._rates = {k: v for k, v in self._rates.items() if v[0] > now - 60}
            start, count = self._rates.get(key, (now, 0))
            if count >= self.requests_per_minute or (key not in self._rates and len(self._rates) >= 1024):
                raise ApiError(429, "rate_limited", "しばらく待ってから再試行してください。")
            self._rates[key] = (start, count + 1)

    def handle(self, request: dict) -> dict:
        try:
            return self._handle(request)
        except ApiError as exc:
            return problem(exc)
        except (OSError, ValueError, MarketUnitsStoreError):
            return problem(ApiError(503, "input_store_unavailable",
                                    "入力データを安全に読み書きできません。結果不明の保存は同じ要求で確認してください。"))
        except Exception:
            return problem(ApiError(500, "internal_error", "処理に失敗しました。保存の結果が不明な場合は同じ要求で確認してください。"))

    def _handle(self, request):
        method = request.get("method", "GET").upper()
        path = request.get("path", "")
        headers = {str(k).lower(): str(v) for k, v in request.get("headers", {}).items()}
        if path in {"/api/v1/health", "/api/health"} and method == "GET":
            try:
                if not self.personal_origins:
                    self._credentials()
                status = 200
            except ApiError:
                status = 503
            return response(status, {"status": "ok" if status == 200 else "unavailable",
                                     "api_version": "v1", "contract_version": "0.1.0"})
        self._rate_limit(request.get("peer", "local"))
        raw = request.get("body", "")
        if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_BODY_BYTES:
            raise ApiError(413, "payload_too_large", "入力は2 MiB以下にしてください。")
        write = method in {"PUT", "POST", "PATCH", "DELETE"}
        if path == "/api/session":
            return self._session(method, headers, request.get("secure", False), request.get("local_peer", False))
        principal = self._authenticate(headers, write=write)
        if request.get("kind") == "authorize":
            self._require(principal, request.get("permissions", []))
            return response(204)
        if path == "/api/v1/input-schema" and method == "GET":
            self._require(principal, {"inputs:schema:read"})
            return response(200, {
                "contract_version": "0.1.0",
                "suggested_asset_classes": ["MUTUAL_FUNDS", "JP_STOCK", "US_STOCK", "FX", "COMMODITIES"],
                "suggested_external_categories": ["CASH_EXTERNAL"],
                "month_order": "descending_default_last",
                "new_month_default": "latest_existing_non_default_or_default",
                "external_category_default": "CASH_EXTERNAL", "decimal_integer_digits": 18,
                "decimal_fraction_digits": 12, "max_market_units": 5000,
                "max_external_entries": 5000, "max_month_keys": 1200,
                "max_request_bytes": MAX_BODY_BYTES,
            })
        aliases = {"/api/funds": "market-units", "/api/external-assets": "external-assets",
                   "/api/portfolio-basis": "portfolio-basis"}
        resource = aliases.get(path, path.removeprefix("/api/v1/"))
        repository = self.repository if resource == "market-units" else self.monthly_repositories.get(resource)
        if repository is None or path not in {*aliases, *(f"/api/v1/{name}" for name in ("market-units", "external-assets", "portfolio-basis"))}:
            raise ApiError(404, "not_found", "このAPI操作はまだ提供されていません。")
        self._require(principal, {f"{resource}:read"})
        if method == "GET":
            with repository.transaction() as session:
                body = deepcopy(session.state["document"])
                etag = repository.etag(session.state)
            if path in aliases:
                body = ([{k: v for k, v in row.items() if k not in {"asset_id", "asset_key"}} for row in body["items"]]
                        if resource == "market-units" else legacy_document(body["months"], resource))
            return response(200, body, {"ETag": etag})
        self._require(principal, {f"{resource}:replace"})
        if path in aliases:
            raise ApiError(428, "client_upgrade_required", "保存にはAPI v1と読込み時のETagを使用してください。")
        if method != "PUT":
            raise ApiError(405, "method_not_allowed", "GETまたはPUTを使用してください。")
        if headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise ApiError(415, "unsupported_media_type", "Content-Typeをapplication/jsonにしてください。")
        if_match = headers.get("if-match")
        if if_match is None:
            raise ApiError(428, "precondition_required", "読込み時のETagをIf-Matchに指定してください。")
        if not re.fullmatch(r'"[A-Za-z0-9:_-]+"', if_match):
            raise ApiError(400, "invalid_request", "If-Matchには強いETagを一つ指定してください。")
        key = headers.get("idempotency-key", "")
        try:
            if str(uuid.UUID(key)) != key.lower():
                raise ValueError("noncanonical UUID")
        except (ValueError, AttributeError):
            raise ApiError(400, "invalid_request", "Idempotency-KeyにはUUIDを指定してください。")
        payload = strict_json(raw)
        if self._clears(payload, resource):
            self._require(principal, {f"{resource}:clear"})
        fingerprint = hashlib.sha256(json.dumps(
            {"body": payload, "if_match": if_match}, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ).encode()).hexdigest()
        receipt_id = hashlib.sha256(json.dumps(
            [principal.subject, method, path, key.lower()], separators=(",", ":")
        ).encode()).hexdigest()
        with self._guard:
            if receipt_id in self._active:
                raise ApiError(409, "idempotency_in_progress", "同じ保存要求を処理しています。")
            self._active.add(receipt_id)
        try:
            return self._replace(principal, headers, payload, if_match, fingerprint, receipt_id, repository, resource)
        finally:
            with self._guard:
                self._active.discard(receipt_id)

    @staticmethod
    def _clears(payload, resource):
        if resource != "market-units":
            return is_clear(payload, resource)
        return isinstance(payload, dict) and (payload.get("clear_all") is True or payload.get("items") == [])

    def _replace(self, principal, headers, payload, if_match, fingerprint, receipt_id, repository, resource):
        with repository.transaction() as session:
            state = session.state
            # A request may have waited for another process while grants were revoked.
            current = self._authenticate(headers, write=True)
            if current.subject != principal.subject:
                raise ApiError(401, "authentication_required", "認証主体が変更されました。再認証してください。")
            self._require(current, {f"{resource}:read", f"{resource}:replace"})
            if self._clears(payload, resource):
                self._require(current, {f"{resource}:clear"})
            receipt = state["receipts"].get(receipt_id)
            if receipt:
                if receipt["fingerprint"] != fingerprint:
                    raise ApiError(409, "idempotency_key_reused", "同じkeyを異なる内容に再利用できません。")
                if self.clock() - receipt["created_at"] >= RECEIPT_SECONDS or "result" not in receipt:
                    receipt.pop("result", None)
                    session.commit()
                    raise ApiError(409, "idempotency_result_expired", "元の結果の保持期間を過ぎています。最新の入力と履歴を確認してください。")
                result = deepcopy(receipt["result"])
                result["headers"]["Idempotency-Replayed"] = "true"
                return result
            write_input = False
            try:
                if repository.etag(state) != if_match:
                    raise ApiError(412, "revision_mismatch", "別の更新がありました。最新の入力と下書きを比較してください。")
                old = deepcopy(state["document"])
                if resource == "market-units":
                    content_key = "items"
                    items = validate_replacement(
                        payload, {row["asset_id"] for row in old["items"]},
                        allowed_price_hosts=self.allowed_price_hosts,
                        existing_price_urls={row["asset_id"]: row["csv_url"] for row in old["items"]},
                    )
                    for item in items:
                        if item["asset_id"] is None:
                            item["asset_id"] = str(uuid.uuid4())
                else:
                    content_key = "months"
                    items = validate_monthly_replacement(payload, resource,
                        {row["entry_id"] for row in entries(old["months"], resource)})
                    for item in entries(items, resource):
                        if item["entry_id"] is None:
                            item["entry_id"] = str(uuid.uuid4())
                changed = items != old[content_key] or old["storage_state"] == "uninitialized"
                change_id = str(uuid.uuid4()) if changed else None
                if changed:
                    state["document"] = {"revision": "rev_" + uuid.uuid4().hex,
                                         "storage_state": "ready",
                                         "updated_at": datetime.fromtimestamp(self.clock(), timezone.utc).isoformat(),
                                         content_key: items}
                    if resource == "market-units":
                        state["legacy_extras"] = {k: v for k, v in state["legacy_extras"].items()
                                                  if k in {item["asset_id"] for item in items}}
                    state["changes"].append({"change_id": change_id, "subject": principal.subject,
                                              "before": old, "after": deepcopy(state["document"])})
                    write_input = True
                result = response(200, {"changed": changed, "change_id": change_id,
                                        "resource": deepcopy(state["document"])},
                                  {"Idempotency-Replayed": "false"})
            except MarketUnitsInputError as exc:
                result = problem(ApiError(422, "invalid_input", "入力項目を確認してください。", exc.errors))
            except ApiError as exc:
                if exc.status not in {412, 422}:
                    raise
                result = problem(exc)
            state["receipts"][receipt_id] = {"fingerprint": fingerprint,
                                             "created_at": self.clock(), "result": deepcopy(result)}
            if resource == "market-units":
                session.commit(write_csv=write_input)
            else:
                session.commit(write_input=write_input)
            return result

    def _session(self, method, headers, secure, local_peer=False):
        origin = ("https://" if secure else "http://") + headers.get("host", "")
        personal = (local_peer and origin in self.personal_origins
                    and headers.get("origin", origin) == origin
                    and headers.get("sec-fetch-site", "none") in {"same-origin", "none"})
        if method == "GET" and personal and "authorization" not in headers:
            try:
                self._authenticate(headers)
            except ApiError as exc:
                if exc.status != 401:
                    raise
                principal = Principal("personal-ui", "personal-owner", OWNER_PERMISSIONS, self.clock() + 8 * 3600)
                return self._create_session(principal, headers, secure, personal=True)
        if method == "POST":
            # Login explicitly exchanges a bearer credential and replaces an old cookie.
            token = self._bearer(headers)
            principal = principal_for_token(self._credentials(), token or "", self.clock())
            if principal is None:
                raise ApiError(401, "authentication_required", "アクセストークンを確認してください。")
            return self._create_session(principal, headers, secure)
        if method not in {"GET", "DELETE"}:
            raise ApiError(405, "method_not_allowed", "GET、POST、DELETEを使用してください。")
        principal = self._authenticate(headers, write=method == "DELETE")
        sid = self._session_id(headers)
        with self._guard:
            session = self._sessions.get(sid)
            if session is None:
                raise ApiError(401, "authentication_required", "ブラウザsessionが必要です。")
            if method == "DELETE":
                del self._sessions[sid]
        if method == "DELETE":
            return response(204, headers={"Set-Cookie": f"{self.session_cookie_name}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"})
        return response(200, {"authenticated": True, "csrf_token": session["csrf_token"],
                              "permissions": sorted(principal.permissions), "personal_mode": session.get("personal", False)})

    def _create_session(self, principal, headers, secure, *, personal=False):
        sid, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        expiry = min(principal.expires_at, self.clock() + 8 * 3600)
        with self._guard:
            self._sessions = {k: v for k, v in self._sessions.items() if v["expires_at"] > self.clock()}
            old = self._session_id(headers)
            self._sessions.pop(old, None)
            if len(self._sessions) >= 1000:
                raise ApiError(429, "rate_limited", "session数の上限に達しています。")
            self._sessions[sid] = {"token_id": principal.token_id, "subject": principal.subject,
                                   "expires_at": expiry, "csrf_token": csrf, "personal": personal}
        cookie = f"{self.session_cookie_name}={sid}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max(0, int(expiry - self.clock()))}"
        if secure:
            cookie += "; Secure"
        return response(200, {"authenticated": True, "csrf_token": csrf,
                              "permissions": sorted(principal.permissions), "personal_mode": personal}, {"Set-Cookie": cookie})
