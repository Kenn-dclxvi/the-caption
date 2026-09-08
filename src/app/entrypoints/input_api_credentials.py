"""Explicit local administration of API tokens; never called by the web server."""

import argparse
from datetime import datetime, timedelta, timezone
import json
import secrets
import uuid

from src.domain.input_api_auth import OWNER_PERMISSIONS, credential_principals, token_digest
from src.infra.input_api_credentials import CredentialFile


def main() -> None:
    parser = argparse.ArgumentParser(description="THE CAPTION API token management")
    parser.add_argument("action", choices=["create", "list", "revoke"])
    parser.add_argument("--file", required=True, help="credential JSON path (outside Git)")
    parser.add_argument("--subject", default="local-owner")
    parser.add_argument("--permissions", help="comma-separated grants; default: local owner")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--id", help="credential ID to revoke")
    args = parser.parse_args()
    store = CredentialFile(args.file)
    now = datetime.now(timezone.utc)
    if args.action == "list":
        document = store.read()
        credential_principals(document, now.timestamp())
        print(json.dumps([{k: v for k, v in item.items() if k != "sha256"}
                          for item in document["tokens"]], ensure_ascii=False, indent=2))
        return
    if args.action == "create":
        grants = set(args.permissions.split(",")) if args.permissions else set(OWNER_PERMISSIONS)
        if not grants <= OWNER_PERMISSIONS or not 1 <= args.days <= 365:
            parser.error("permissions must be known grants and days must be 1..365")
        token = secrets.token_urlsafe(32)
        record = {"id": str(uuid.uuid4()), "subject": args.subject,
                  "sha256": token_digest(token), "permissions": sorted(grants),
                  "expires_at": (now + timedelta(days=args.days)).isoformat(), "revoked": False}
        with store.edit() as document:
            document["tokens"].append(record)
            credential_principals(document, now.timestamp())
        print(json.dumps({"id": record["id"], "token": token, "expires_at": record["expires_at"]}))
    else:
        if not args.id:
            parser.error("revoke requires --id")
        with store.edit() as document:
            credential_principals(document, now.timestamp())
            found = next((r for r in document["tokens"] if r["id"] == args.id), None)
            if found is None:
                parser.error("credential ID not found")
            found["revoked"] = True
        print(json.dumps({"id": args.id, "revoked": True}))


if __name__ == "__main__":
    main()
