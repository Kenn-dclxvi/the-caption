import json
import stat
import subprocess
from pathlib import Path

_PRE_COMMIT_CONTENT = """\
#!/usr/bin/env bash

PYTHON=python3
MAIN_REPO=$(dirname "$(git rev-parse --git-common-dir)")
if [ -f "$MAIN_REPO/.venv/bin/python" ]; then
    PYTHON="$MAIN_REPO/.venv/bin/python"
elif [ -f .venv/bin/python ]; then
    PYTHON=.venv/bin/python
fi

if [ -f scripts/dev/bump_rev.py ]; then
    echo "[pre-commit] REV_SYNC check..."
    "$PYTHON" scripts/dev/bump_rev.py --check-staged || exit 1
fi

echo "[pre-commit] Running pytest..."
"$PYTHON" -m pytest tests/ -v || exit 1
"""


def _install_pre_commit() -> None:
    git_common = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        capture_output=True, text=True
    ).stdout.strip()
    hooks_dir = Path(git_common) / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hooks_dir / "pre-commit"
    hook_path.write_text(_PRE_COMMIT_CONTENT, encoding="utf-8")
    hook_path.chmod(hook_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"[install] pre-commit hook -> {hook_path} ✓")


def _disable_post_tool_use() -> None:
    settings_path = Path(".claude") / "settings.local.json"
    if not settings_path.exists():
        print(f"[install] PostToolUse disabled (no settings file): {settings_path} ✓")
        return
    try:
        existing = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        print(f"[install] SKIP PostToolUse disable (invalid json): {settings_path}")
        return
    hooks = existing.get("hooks")
    if not isinstance(hooks, dict):
        print(f"[install] PostToolUse disabled (no hooks): {settings_path} ✓")
        return
    if "PostToolUse" not in hooks:
        print(f"[install] PostToolUse already disabled: {settings_path} ✓")
        return
    hooks.pop("PostToolUse", None)
    if not hooks:
        existing.pop("hooks", None)
    settings_path.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8"
    )
    print(f"[install] PostToolUse removed -> {settings_path} ✓")


if __name__ == "__main__":
    _install_pre_commit()
    _disable_post_tool_use()
    print("[install] Done.")
