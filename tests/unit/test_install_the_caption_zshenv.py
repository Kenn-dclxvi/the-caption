import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.dev.install_the_caption_zshenv import (
    MARKER_END,
    MARKER_START,
    build_bootstrap_block,
    replace_bootstrap,
)


def test_bootstrap_block_manages_activate_and_deactivate() -> None:
    block = build_bootstrap_block()

    assert MARKER_START in block
    assert MARKER_END in block
    assert 'source "$helper_path"' in block
    assert "the_caption_deactivate_active_venv" in block
    assert "add-zsh-hook chpwd the_caption_bootstrap" in block
    assert "add-zsh-hook precmd the_caption_bootstrap" in block


def test_replace_bootstrap_replaces_existing_block_without_touching_neighbors() -> None:
    existing = """\
before
# >>> THE-CAPTION zsh bootstrap >>>
old
# <<< THE-CAPTION zsh bootstrap <<<
after
"""
    block = build_bootstrap_block()

    updated = replace_bootstrap(existing, block)

    assert updated.startswith("before\n")
    assert "after\n" in updated
    assert block.rstrip("\n") in updated
    assert "old" not in updated


@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh is required for this test")
def test_bootstrap_works_with_minimal_path(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    zshenv_path = tmp_path / ".zshenv"
    zshenv_path.write_text(build_bootstrap_block())

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    for name, body in {
        "python": '#!/bin/sh\necho FAKE_PYTHON\n',
        "pip": '#!/bin/sh\necho FAKE_PIP\n',
        "pytest": '#!/bin/sh\necho FAKE_PYTEST\n',
    }.items():
        script_path = fake_bin / name
        script_path.write_text(body)
        script_path.chmod(0o755)

    fake_bin_quoted = shlex.quote(str(fake_bin))
    repo_root_quoted = shlex.quote(str(repo_root))
    zshenv_quoted = shlex.quote(str(zshenv_path))

    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    env.pop("VIRTUAL_ENV_PROMPT", None)
    env.update(
        {
            "PATH": "/bin",
            "TERM_PROGRAM": "vscode",
        }
    )

    result = subprocess.run(
        [
            "/bin/zsh",
            "-ic",
            (
                f"source {zshenv_quoted}; "
                f"cd {repo_root_quoted} >/dev/null; "
                f"PATH={fake_bin_quoted}:$PATH; "
                'printf "in_repo=%s\\n" "${VIRTUAL_ENV-}"; '
                'printf "python=%s\\n" "$(python -c \'import sys; print(sys.executable)\')"; '
                'printf "pip=%s\\n" "$(pip --version)"; '
                'printf "pytest=%s\\n" "$(pytest --version)"; '
                f"VIRTUAL_ENV=/tmp/other THE_CAPTION_ACTIVE_VENV_ROOT={repo_root_quoted} the_caption_bootstrap; "
                'printf "resynced=%s\\n" "${VIRTUAL_ENV-}"; '
                "cd /tmp >/dev/null; "
                f"PATH={fake_bin_quoted}:$PATH; "
                "rehash; "
                'printf "after_leave=%s\\n" "${VIRTUAL_ENV-}"; '
                'printf "outside_python=%s\\n" "$(python --version)"; '
                'printf "outside_pip=%s\\n" "$(pip)"; '
                'printf "outside_pytest=%s\\n" "$(pytest)"'
            ),
        ],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )

    lines = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    assert lines["in_repo"] == f"{repo_root}/.venv"
    assert lines["python"] == f"{repo_root}/.venv/bin/python"
    assert "FAKE_PIP" not in lines["pip"]
    assert "FAKE_PYTEST" not in lines["pytest"]
    assert lines["resynced"] == f"{repo_root}/.venv"
    assert lines["after_leave"] == ""
    assert lines["outside_python"] == "FAKE_PYTHON"
    assert lines["outside_pip"] == "FAKE_PIP"
    assert lines["outside_pytest"] == "FAKE_PYTEST"
