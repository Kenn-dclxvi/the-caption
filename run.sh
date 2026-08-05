#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./run.sh [v4|weekly|monthly|collection-web|collection-web-prd|collection-web-dev] [args...]

Examples:
  ./run.sh
  ./run.sh v4 -F
  ./run.sh weekly -F -u
  ./run.sh monthly -F -u
  ./run.sh collection-web-prd
  ./run.sh collection-web-dev
EOF
}

die() {
  printf '[error] %s\n' "$1" >&2
  exit 1
}

run_with_lock() {
  local module="$1"
  shift

  mkdir -p "${SCRIPT_DIR}/logs"

  exec "${PYTHON}" - "${SCRIPT_DIR}/logs/run.sh.lock" "${module}" "$@" <<'PY'
import fcntl
import subprocess
import sys

lock_path = sys.argv[1]
module = sys.argv[2]
args = sys.argv[3:]

with open(lock_path, "w", encoding="utf-8") as lock_file:
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("[warn] another run.sh invocation is already active; exiting.", file=sys.stderr)
        raise SystemExit(0)

    result = subprocess.run([sys.executable, "-m", module, *args], check=False)
    raise SystemExit(result.returncode)
PY
}

is_usable_node_binary() {
  local candidate="$1"

  [[ -x "${candidate}" ]] || return 1

  "${PYTHON}" - "${candidate}" <<'PY'
import os
import subprocess
import sys

candidate = sys.argv[1]

try:
    result = subprocess.run(["otool", "-L", candidate], check=True, capture_output=True, text=True)
except Exception:
    raise SystemExit(1)

for line in result.stdout.splitlines()[1:]:
    dependency = line.strip().split(" ", 1)[0]
    if dependency.startswith("/opt/homebrew/") or dependency.startswith("/usr/local/"):
        if not os.path.exists(dependency):
            raise SystemExit(1)

raise SystemExit(0)
PY
}

run_collection_web() {
  local profile="$1"
  shift

  local web_root
  local app_port
  local hmr_port
  case "${profile}" in
    prd)
      web_root="${SCRIPT_DIR}"
      app_port=3001
      hmr_port=3002
      ;;
    dev)
      web_root="${SCRIPT_DIR}/../THE-CAPTION-DEV"
      app_port=3101
      hmr_port=3102
      ;;
    *)
      die "unknown collection-web profile: ${profile}"
      ;;
  esac

  local web_dir="${web_root}/src/web/market_units_editor"
  [[ -f "${web_dir}/package.json" ]] || die "Web app package.json not found: ${web_dir}"

  local node_bin=""
  local npm_cli=""
  local resolved_node_bin=""

  local candidates=(
    "${NODE_BIN:-}"
  )

  local prefix
  for prefix in /opt/homebrew/opt /opt/homebrew/Cellar /usr/local/opt /usr/local/Cellar; do
    [[ -d "${prefix}" ]] || continue
    for candidate in "${prefix}"/node*/bin/node "${prefix}"/node@*/bin/node; do
      [[ -e "${candidate}" ]] || continue
      candidates+=("${candidate}")
    done
  done

  if command -v node >/dev/null 2>&1; then
    candidates+=("$(command -v node)")
  fi

  local candidate
  for candidate in "${candidates[@]}"; do
    [[ -n "${candidate}" ]] || continue
    if is_usable_node_binary "${candidate}"; then
      resolved_node_bin="$("${PYTHON}" - "${candidate}" <<'PY'
import os
import sys

print(os.path.realpath(sys.argv[1]))
PY
)"
      node_bin="${candidate}"
      local npm_cli_candidates=()
      # 候補1（後方互換・最優先）: keg 相対の npm-cli.js
      npm_cli_candidates+=("$(dirname "$(dirname "${resolved_node_bin}")")/lib/node_modules/npm/bin/npm-cli.js")
      # 候補2（node>=26 Homebrew 配置）: 共有 prefix の npm-cli.js
      local brew_prefix=""
      if command -v brew >/dev/null 2>&1; then
        brew_prefix="$(brew --prefix 2>/dev/null || true)"
      fi
      local npm_prefix
      for npm_prefix in "${brew_prefix}" /opt/homebrew /usr/local; do
        [[ -n "${npm_prefix}" ]] || continue
        npm_cli_candidates+=("${npm_prefix}/lib/node_modules/npm/bin/npm-cli.js")
      done
      local npm_cli_candidate
      for npm_cli_candidate in "${npm_cli_candidates[@]}"; do
        if [[ -f "${npm_cli_candidate}" ]]; then
          npm_cli="${npm_cli_candidate}"
          break
        fi
      done
      break
    fi
  done

  [[ -n "${node_bin}" ]] || die "usable node executable not found"
  [[ -f "${npm_cli}" ]] || die "npm cli not found for ${node_bin}"

  local node_dir
  node_dir="$(dirname "${resolved_node_bin}")"

  PATH="${node_dir}:${PATH}" PORT="${PORT:-${app_port}}" VITE_HMR_PORT="${VITE_HMR_PORT:-${hmr_port}}" exec "${node_bin}" "${npm_cli}" --prefix "${web_dir}" run dev -- "$@"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

if [[ -x ".venv/bin/python" ]]; then
  PYTHON=".venv/bin/python"
elif command -v python >/dev/null 2>&1; then
  PYTHON="$(command -v python)"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
else
  die "python executable not found (.venv/bin/python, python, python3)"
fi

# 位置パラメータを補ってから解決する。`${1:-v4}` で既定値を与えるだけでは、
# 引数なしの実行が v4 分岐の `shift` に到達し、`set -euo pipefail` の下で
# 終了ステータス 1 のまま停止する。
if [[ $# -eq 0 ]]; then
  set -- v4
fi

target="$1"
module=""

case "${target}" in
  v4|v)
    module="src.app.entrypoints.v4_daily_main"
    shift
    ;;
  daily|d|legacy|collection|c)
    die "retired legacy mode: '${target}'. v3 entrypoints are not part of this repository. Use './run.sh v4' for the current daily pipeline."
    ;;
  weekly|w)
    module="src.app.entrypoints.weekly_main"
    shift
    ;;
  monthly|m)
    module="src.app.entrypoints.monthly_main"
    shift
    ;;
  collection-web|cw|collection-web-prd|cwp)
    shift
    run_collection_web prd "$@"
    ;;
  collection-web-dev|cwd)
    shift
    run_collection_web dev "$@"
    ;;
  -h|--help|help)
    usage
    exit 0
    ;;
  -*)
    module="src.app.entrypoints.v4_daily_main"
    ;;
  [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9])
    module="src.app.entrypoints.v4_daily_main"
    ;;
  "")
    module="src.app.entrypoints.v4_daily_main"
    shift
    ;;
  *)
    usage
    die "unknown mode: ${target}"
    ;;
esac

run_with_lock "${module}" "$@"
