"""Private durable pending calculations, protected by one process-shared lock."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import stat

from src.domain.fund_price_fallback import encoded, require
from src.infra.market_units_input_repository import _replace_bytes


def secure_open(path, create=False):
    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK | (os.O_CREAT | os.O_EXCL if create else 0), 0o600)
    info = os.fstat(fd)
    if not (stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
            and info.st_uid == os.getuid() and info.st_nlink == 1):
        os.close(fd)
        require(False, "insecure_price_state")
    return fd


class FundPriceRepository:
    def __init__(self, directory):
        self.directory = Path(directory)

    @contextmanager
    def transaction(self):
        directory = self.directory
        directory.mkdir(mode=0o700, exist_ok=True)
        info = directory.lstat()
        require(stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o700
                and info.st_uid == os.getuid(), "insecure_price_state")
        try:
            fd = secure_open(directory / "writer.lock", True)
            fresh = True
        except FileExistsError:
            fd = secure_open(directory / "writer.lock")
            fresh = False
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            path = directory / "state.json"
            if not os.path.lexists(path):
                require(fresh, "price_state_missing")
                state = {"version": 1, "calculations": {}}
                _replace_bytes(path, encoded(state).encode())
            with os.fdopen(secure_open(path), "r") as handle:
                state = json.load(handle)
            require(isinstance(state, dict) and state.get("version") == 1
                    and isinstance(state.get("calculations"), dict), "invalid_price_state")
            original = encoded(state)
            yield state
            if encoded(state) != original:
                _replace_bytes(path, encoded(state).encode())
        finally:
            os.close(fd)
