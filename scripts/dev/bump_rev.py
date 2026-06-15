import re
import sys
import json
import subprocess
from pathlib import Path

_RE_CLASS_REV = re.compile(r'(__REV: Final\[str\] = "Rev\. )(\d+)(")')


def _parse(text: str):
    m_c = _RE_CLASS_REV.search(text)
    rev_c = int(m_c.group(2)) if m_c else None
    return rev_c


def check(path: str) -> bool:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"[REV_SYNC] SKIP {path} (not found)")
        return True
    rev_c = _parse(text)
    if rev_c is None:
        print(f"[REV_SYNC] SKIP {path} (no versioning)")
        return True
    print(f"[REV_SYNC] OK   {path}: Rev.{rev_c} ✓")
    return True


def bump(path: str) -> None:
    if not path.endswith(".py"):
        return
    p = Path(path)
    if not p.exists():
        return
    text = p.read_text(encoding="utf-8")
    rev_c = _parse(text)
    if rev_c is None:
        return
    new_rev = rev_c + 1
    if rev_c is not None:
        text = _RE_CLASS_REV.sub(lambda m: f"{m.group(1)}{new_rev}{m.group(3)}", text)
    p.write_text(text, encoding="utf-8")
    print(f"[REV_SYNC] BUMP {path}: Rev.{rev_c} -> Rev.{new_rev} ✓")


def check_staged() -> bool:
    root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True
    ).stdout.strip()
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True, text=True, cwd=root
    )
    py_files = [str(Path(root) / f) for f in result.stdout.splitlines() if f.endswith(".py")]
    if not py_files:
        return True
    all_ok = True
    for f in py_files:
        if not check(f):
            all_ok = False
    return all_ok


def post_tool_use() -> None:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return
        data = json.loads(raw)
    except Exception:
        return
    file_path = data.get("file_path") or data.get("tool_input", {}).get("file_path", "")
    if file_path.endswith(".py"):
        bump(file_path)


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("Usage: bump_rev.py --check <file> | --bump <file> | --check-staged | --post-tool-use")
        sys.exit(1)
    mode = args[0]
    if mode == "--check" and len(args) > 1:
        sys.exit(0 if check(args[1]) else 1)
    elif mode == "--bump" and len(args) > 1:
        bump(args[1])
    elif mode == "--check-staged":
        sys.exit(0 if check_staged() else 1)
    elif mode == "--post-tool-use":
        post_tool_use()
    else:
        print(f"[REV_SYNC] Unknown mode: {mode}")
        sys.exit(1)
