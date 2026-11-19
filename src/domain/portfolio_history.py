"""Validation for date-scoped Monex portfolio history."""

from datetime import date, datetime, timezone
import re


def history_date(value: str) -> date:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("invalid history date")
    return date.fromisoformat(value)


def history_entry(payload, day: date, now: datetime) -> dict:
    fields = {"scope", "total_amount_jpy", "cumulative_deposits_withdrawals_jpy",
              "source_sha256", "source_received_at"}
    if not isinstance(payload, dict) or payload.keys() != fields:
        raise ValueError("invalid history fields")
    if any(not isinstance(value, str) for value in payload.values()):
        raise ValueError("history values must be strings")
    if payload["scope"] != "securitiesGeneralAndNisa":
        raise ValueError("invalid history scope")
    if not re.fullmatch(r"0|[1-9][0-9]{0,17}", payload["total_amount_jpy"]):
        raise ValueError("invalid total")
    if not re.fullmatch(r"0|-?[1-9][0-9]{0,17}", payload["cumulative_deposits_withdrawals_jpy"]):
        raise ValueError("invalid cumulative deposits and withdrawals")
    if not re.fullmatch(r"[0-9a-f]{64}", payload["source_sha256"]):
        raise ValueError("invalid evidence hash")
    received = payload["source_received_at"]
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})", received):
        raise ValueError("invalid evidence timestamp")
    receipt_time = datetime.fromisoformat(received.replace("Z", "+00:00"))
    if not day <= receipt_time.astimezone(now.tzinfo).date() <= now.date() or receipt_time > now:
        raise ValueError("invalid history date or evidence timestamp")
    return {**payload, "source_received_at": receipt_time.astimezone(timezone.utc).isoformat()}
