"""Isolated storage for portfolio history and its durable receipts."""

from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4


class PortfolioHistoryRepository:
    def __init__(self, path: Path):
        self.path = path

    def get(self, day: str) -> dict | None:
        try:
            self.path.stat()
        except FileNotFoundError:
            return None
        with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)) as db:
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'history'"
            ).fetchone()
            return self._get(db, day) if exists else None

    @staticmethod
    def _get(db, day):
        row = db.execute("SELECT entry FROM history WHERE day = ?", (day,)).fetchone()
        return json.loads(row[0]) if row else None

    def record(self, day: str, payload: dict, registered_at: str) -> tuple[bool, dict]:
        self.path.parent.mkdir(mode=0o700, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        entry = {**payload, "date": day, "receipt_id": str(uuid4()), "registered_at": registered_at}
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS history (day TEXT PRIMARY KEY, entry TEXT NOT NULL)")
            insert = db.execute(
                "INSERT INTO history VALUES (?, ?) ON CONFLICT(day) DO NOTHING",
                (day, json.dumps(entry)),
            )
            return insert.rowcount == 1, self._get(db, day)
