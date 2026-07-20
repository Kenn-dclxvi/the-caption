import json
import os
import stat
import tempfile
from typing import Any, Final


# New files intentionally match the conventional repository data-file mode.
# Existing destinations retain their own permission mode across replacement.
DEFAULT_NEW_FILE_MODE: Final[int] = 0o644


def atomic_write_json(path: str, payload: Any) -> None:
    """Atomically write JSON, preserving an old mode or using 0644 for a new file."""
    target_dir = os.path.dirname(os.path.abspath(path))
    os.makedirs(target_dir, exist_ok=True)
    try:
        destination_mode = stat.S_IMODE(os.stat(path).st_mode)
    except FileNotFoundError:
        destination_mode = DEFAULT_NEW_FILE_MODE
    fd, tmp_path = tempfile.mkstemp(
        dir=target_dir,
        prefix=f".{os.path.basename(path)}.",
        suffix=".tmp",
    )
    try:
        os.fchmod(fd, destination_mode)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
