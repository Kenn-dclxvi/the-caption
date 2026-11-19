"""Authenticated HTTP operations for the date-bound fund price fallback."""
from src.domain.fund_price_fallback import FundPriceError, uuid, validate_candidate
from src.infra.canonical_ledger_input_repository import CanonicalLedgerInputRepository


def handle(api, principal, method, path, headers, raw):
    from src.app.input_api import ApiError, response, strict_json
    api._require(principal, {"fund-prices:read"})
    service = api.fund_price_fallback
    if service is None:
        raise ApiError(503, "fund_price_fallback_disabled", "価格補完は有効になっていません。")
    parts = path.removeprefix("/api/v1/fund-price-requests").strip("/").split("/")
    try:
        if parts == [""] and method == "GET":
            return response(200, service.list_requests())
        uuid(parts[0])
        if len(parts) == 1 and method == "GET":
            return response(200, service.get(parts[0]))
        if method == "POST" and len(parts) == 2:
            if headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
                raise ApiError(415, "unsupported_media_type", "JSONを送信してください。")
            uuid(headers.get("idempotency-key"))
            body = strict_json(raw)
            if parts[1] == "candidate":
                api._require(principal, {"fund-prices:adopt"})
                # A recovered normal price takes precedence until a candidate is
                # adopted. Only the missing points are read; all other inputs stay frozen.
                current = service.get(parts[0])
                validate_candidate(body, current, service.clock())
                service.refresh_primary(current["calculation_date"], CanonicalLedgerInputRepository())
                current = service.get(parts[0])
                if current["status"] == "primary":
                    return response(200, current)
                return response(200, service.adopt(parts[0], body, headers["idempotency-key"]))
            if parts[1] == "complete":
                api._require(principal, {"fund-prices:complete"})
                if body != {}:
                    raise ApiError(422, "invalid_input", "完了要求は空のJSONにしてください。")
                return response(200, service.complete(parts[0]))
    except FundPriceError as error:
        code = str(error)
        status = 404 if code == "price_request_not_found" else 409 if code in {
            "price_candidate_conflict", "price_already_adopted", "calculation_closed",
            "price_request_mismatch"} else 422
        raise ApiError(status, code, "価格要求・日付・単位・状態を確認してください。") from None
    raise ApiError(404, "not_found", "この価格補完操作は提供されていません。")
