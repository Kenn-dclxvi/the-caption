"""Private credential file I/O; credential policy lives in domain."""

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import tempfile


class CredentialFile:
    def __init__(self, path: str | None):
        self.path = Path(path).expanduser().absolute() if path else None

    def read(self):
        if self.path is None:
            raise OSError("credential file not configured")
        with self.path.open("rb") as handle:
            data = handle.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise OSError("credential file too large")
        return json.loads(data)

    @contextmanager
    def edit(self):
        if self.path is None:
            raise OSError("credential file not configured")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_name(self.path.name + ".lock")
        with open(lock_path, "a+b") as lock:
            os.chmod(lock_path, 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                document = self.read() if self.path.exists() else {"tokens": []}
                yield document
                self._write(document)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _write(self, document):
        assert self.path is not None
        fd, temporary = tempfile.mkstemp(prefix=".caption-auth-", dir=self.path.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(document, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            directory = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
