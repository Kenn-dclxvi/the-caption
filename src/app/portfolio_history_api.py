"""Authenticated v1 API for historical observations."""

from datetime import datetime, timezone
import sqlite3
from zoneinfo import ZoneInfo

from src.app.input_api import ApiError, response, strict_json
from src.domain.portfolio_history import history_date, history_entry


PREFIX = "/api/v1/portfolio-history/"


def handle(api, principal, method, path, headers, raw):
    if method not in {"GET", "PUT"}:
        raise ApiError(405, "method_not_allowed", "GETまたはPUTを使用してください。")
    api._require(principal, {"portfolio-history:read" if method == "GET" else "portfolio-history:record"})
    try:
        day = history_date(path.removeprefix(PREFIX))
    except ValueError as exc:
        raise ApiError(400, "invalid_history_date", "実在する日付をYYYY-MM-DD形式で指定してください。") from exc
    repository = api.portfolio_history
    try:
        if method == "GET":
            entry = repository.get(day.isoformat())
            if entry is None:
                raise ApiError(404, "history_not_found", "指定日の日次履歴がありません。")
            return response(200, entry)

        if headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise ApiError(415, "unsupported_media_type", "Content-Typeをapplication/jsonにしてください。")
        now = datetime.fromtimestamp(api.clock(), ZoneInfo("Asia/Tokyo"))
        try:
            payload = history_entry(strict_json(raw), day, now)
        except ValueError as exc:
            raise ApiError(400, "invalid_history_entry", "日次履歴の項目、金額、対象範囲、原応答の日時を確認してください。") from exc
        created, entry = repository.record(day.isoformat(), payload, now.astimezone(timezone.utc).isoformat())
        if any(entry[key] != value for key, value in payload.items()):
            raise ApiError(409, "history_conflict", "指定日に異なる日次履歴が登録されています。")
        return response(201 if created else 200, entry)
    except (OSError, sqlite3.Error) as exc:
        raise ApiError(503, "history_store_unavailable", "日次履歴を安全に読み書きできません。") from exc
