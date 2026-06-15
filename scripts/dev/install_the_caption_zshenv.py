#!/usr/bin/env python3
"""Install THE-CAPTION zsh bootstrap into ~/.zshenv."""

from __future__ import annotations

from pathlib import Path


MARKER_START = "# >>> THE-CAPTION zsh bootstrap >>>"
MARKER_END = "# <<< THE-CAPTION zsh bootstrap <<<"


def replace_bootstrap(existing: str, block: str) -> str:
    lines = existing.splitlines()
    block_lines = block.rstrip("\n").splitlines()
    block_signatures = {line for line in block_lines if line}

    start_idx = next((i for i, line in enumerate(lines) if line == MARKER_START), None)
    end_idx = next((i for i, line in enumerate(lines) if line == MARKER_END), None)

    if start_idx is not None and end_idx is not None and start_idx < end_idx:
        lines = lines[:start_idx] + lines[end_idx + 1 :]
    else:
        signature_indexes = [i for i, line in enumerate(lines) if line in block_signatures]
        if signature_indexes:
            start = signature_indexes[0]
            end = signature_indexes[-1] + 1
            lines = lines[:start] + lines[end:]

    cleaned = "\n".join(lines).rstrip("\n")
    if cleaned:
        cleaned += "\n"
    return cleaned + block.rstrip("\n") + "\n"


def build_bootstrap_block() -> str:
    return f"""\
{MARKER_START}
the_caption_git_bin() {{
  local candidate

  for candidate in "${{THE_CAPTION_GIT_BIN-}}" "$(command -v git 2>/dev/null)" /usr/bin/git /opt/homebrew/bin/git; do
    [[ -n "$candidate" && -x "$candidate" ]] || continue
    print -r -- "$candidate"
    return 0
  done

  return 1
}}

the_caption_bootstrap() {{
  local repo_root helper_path git_bin

  git_bin="$(the_caption_git_bin)" || {{
    if typeset -f the_caption_deactivate_active_venv >/dev/null 2>&1; then
      the_caption_deactivate_active_venv
    fi
    return 0
  }}

  repo_root="$("$git_bin" -C "$PWD" rev-parse --show-toplevel 2>/dev/null)" || {{
    if typeset -f the_caption_deactivate_active_venv >/dev/null 2>&1; then
      the_caption_deactivate_active_venv
    fi
    return 0
  }}

  helper_path="$repo_root/configs/zsh/the-caption.zsh"
  [[ -f "$helper_path" ]] || {{
    if typeset -f the_caption_deactivate_active_venv >/dev/null 2>&1; then
      the_caption_deactivate_active_venv
    fi
    return 0
  }}

  source "$helper_path"
}}

autoload -Uz add-zsh-hook 2>/dev/null || true
add-zsh-hook chpwd the_caption_bootstrap 2>/dev/null || chpwd_functions+=(the_caption_bootstrap)
add-zsh-hook precmd the_caption_bootstrap 2>/dev/null || precmd_functions+=(the_caption_bootstrap)
the_caption_bootstrap
{MARKER_END}
"""


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    source_path = repo_root / "configs" / "zsh" / "the-caption.zsh"
    zshenv_path = Path.home() / ".zshenv"

    if not source_path.is_file():
        raise SystemExit(f"missing source file: {source_path}")

    block = build_bootstrap_block()

    existing = zshenv_path.read_text() if zshenv_path.exists() else ""
    updated = replace_bootstrap(existing, block)
    zshenv_path.write_text(updated)

    print(f"[install] updated {zshenv_path}")
    print(f"[install] template verified -> {source_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
