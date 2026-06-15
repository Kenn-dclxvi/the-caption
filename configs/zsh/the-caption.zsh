#!/usr/bin/env zsh

# THE-CAPTION shell helpers.
# This file is sourced from ~/.zshenv whenever the current shell enters this repo.

the_caption_repo_root() {
  local git_bin

  git_bin="$(the_caption_git_bin)" || return 1
  "$git_bin" -C "$PWD" rev-parse --show-toplevel 2>/dev/null
}

the_caption_git_bin() {
  local candidate

  for candidate in "${THE_CAPTION_GIT_BIN-}" "$(command -v git 2>/dev/null)" /usr/bin/git /opt/homebrew/bin/git; do
    [[ -n "$candidate" && -x "$candidate" ]] || continue
    print -r -- "$candidate"
    return 0
  done

  return 1
}

the_caption_active_venv_root() {
  print -r -- "${THE_CAPTION_ACTIVE_VENV_ROOT-}"
}

the_caption_deactivate_current_venv() {
  if [[ -n ${VIRTUAL_ENV-} ]] && typeset -f deactivate >/dev/null 2>&1; then
    deactivate
  fi
}

the_caption_deactivate_active_venv() {
  local active_root

  active_root="$(the_caption_active_venv_root)"
  [[ -n "$active_root" ]] || return 0

  the_caption_deactivate_current_venv
  unset THE_CAPTION_ACTIVE_VENV_ROOT THE_CAPTION_MISSING_VENV_ROOT
}

the_caption_venv_bin() {
  local tool repo_root bin

  tool="$1"
  repo_root="$(the_caption_repo_root)" || return 2
  bin="$repo_root/.venv/bin/$tool"
  [[ -x "$bin" ]] || {
    print -u2 "blocking: $bin not found"
    return 1
  }

  print -r -- "$bin"
}

the_caption_run_venv_tool() {
  local tool bin
  local repo_status

  tool="$1"
  shift
  bin="$(the_caption_venv_bin "$tool")"
  repo_status=$?
  case "$repo_status" in
    0)
      command "$bin" "$@"
      ;;
    2)
      command "$tool" "$@"
      ;;
    *)
      return 1
      ;;
  esac
}

python() {
  the_caption_run_venv_tool python "$@"
}

python3() {
  the_caption_run_venv_tool python3 "$@"
}

pip() {
  the_caption_run_venv_tool pip "$@"
}

pytest() {
  local bin repo_status

  bin="$(the_caption_venv_bin python)"
  repo_status=$?
  case "$repo_status" in
    0)
      command "$bin" -m pytest "$@"
      ;;
    2)
      command pytest "$@"
      ;;
    *)
      return 1
      ;;
  esac
}

the_caption_sync_venv() {
  local repo_root activate_path active_root target_venv

  repo_root="$(the_caption_repo_root)" || {
    the_caption_deactivate_active_venv
    return 0
  }

  target_venv="$repo_root/.venv"
  activate_path="$repo_root/.venv/bin/activate"
  [[ -f "$activate_path" ]] || {
    if [[ "${THE_CAPTION_MISSING_VENV_ROOT-}" != "$repo_root" ]]; then
      print -u2 "blocking: $activate_path not found"
      typeset -g THE_CAPTION_MISSING_VENV_ROOT="$repo_root"
    fi
    the_caption_deactivate_active_venv
    return 1
  }

  active_root="$(the_caption_active_venv_root)"
  if [[ "$active_root" == "$repo_root" && "${VIRTUAL_ENV-}" == "$target_venv" ]]; then
    return 0
  fi

  the_caption_deactivate_current_venv
  source "$activate_path"
  VIRTUAL_ENV="$target_venv"
  export VIRTUAL_ENV
  if [[ -z ${VIRTUAL_ENV_DISABLE_PROMPT-} ]]; then
    VIRTUAL_ENV_PROMPT='(.venv) '
    export VIRTUAL_ENV_PROMPT
  fi
  typeset -g THE_CAPTION_ACTIVE_VENV_ROOT="$repo_root"
  unset THE_CAPTION_MISSING_VENV_ROOT
}

if [[ -n ${THE_CAPTION_SHELL_HELPERS_LOADED-} ]]; then
  the_caption_sync_venv
  return 0
fi
typeset -g THE_CAPTION_SHELL_HELPERS_LOADED=1

the_caption_sync_venv
