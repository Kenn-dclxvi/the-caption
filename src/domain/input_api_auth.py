"""THE CAPTION API credential policy. No filesystem or network access."""

from dataclasses import dataclass
from datetime import datetime
import hashlib
import hmac
import re
from typing import Any, Mapping


OWNER_PERMISSIONS = frozenset({
    "market-units:read", "market-units:replace", "market-units:clear",
    "external-assets:read", "external-assets:replace", "external-assets:clear",
    "portfolio-basis:read", "portfolio-basis:replace", "portfolio-basis:clear",
    "inputs:schema:read",
})


class CredentialPolicyError(ValueError):
    """The configured credential document is invalid."""


@dataclass(frozen=True)
class Principal:
    token_id: str
    subject: str
    permissions: frozenset[str]
    expires_at: float


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def credential_principals(document: Any, now: float) -> list[tuple[str, Principal]]:
    if not isinstance(document, dict) or set(document) != {"tokens"}:
        raise CredentialPolicyError("invalid credential document")
    records = document["tokens"]
    if not isinstance(records, list) or len(records) > 1000:
        raise CredentialPolicyError("invalid credential list")
    result = []
    ids = set()
    hashes = set()
    for record in records:
        if not isinstance(record, Mapping) or set(record) != {
            "id", "subject", "sha256", "permissions", "expires_at", "revoked"
        }:
            raise CredentialPolicyError("invalid credential record")
        identifier, subject, digest = record["id"], record["subject"], record["sha256"]
        if not all(isinstance(v, str) and 0 < len(v) <= 256 for v in (identifier, subject)):
            raise CredentialPolicyError("invalid credential identity")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise CredentialPolicyError("invalid credential digest")
        if identifier in ids or digest in hashes:
            raise CredentialPolicyError("duplicate credential")
        ids.add(identifier)
        hashes.add(digest)
        permissions = record["permissions"]
        if not isinstance(permissions, list) or any(
            not isinstance(p, str) or p not in OWNER_PERMISSIONS for p in permissions
        ) or type(record["revoked"]) is not bool:
            raise CredentialPolicyError("invalid credential permission")
        try:
            expiry = datetime.fromisoformat(record["expires_at"])
            if expiry.tzinfo is None:
                raise ValueError("timezone required")
            timestamp = expiry.timestamp()
        except (TypeError, ValueError, OverflowError) as exc:
            raise CredentialPolicyError("invalid credential expiry") from exc
        if not record["revoked"] and timestamp > now:
            result.append((digest, Principal(identifier, subject, frozenset(permissions), timestamp)))
    return result


def principal_for_token(document: Any, token: str, now: float) -> Principal | None:
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{20,256}", token):
        return None
    wanted = token_digest(token)
    principals = credential_principals(document, now)
    return next((p for digest, p in principals if hmac.compare_digest(digest, wanted)), None)


def principal_for_session(document: Any, token_id: str, subject: str, now: float) -> Principal | None:
    return next((p for _, p in credential_principals(document, now)
                 if p.token_id == token_id and p.subject == subject), None)
