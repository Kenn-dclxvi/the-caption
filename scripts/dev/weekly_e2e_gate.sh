#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./scripts/dev/weekly_e2e_gate.sh
  ./scripts/dev/weekly_e2e_gate.sh --live YYYY-MM-DD
EOF
}

die() {
  printf '[error] %s\n' "$1" >&2
  exit 1
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${ROOT_DIR}"

if [[ -x ".venv/bin/python" ]]; then
  PYTHON=".venv/bin/python"
elif command -v python >/dev/null 2>&1; then
  PYTHON="$(command -v python)"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
else
  die "python executable not found (.venv/bin/python, python, python3)"
fi

LIVE_MODE="false"
LIVE_DATE=""

if [[ $# -eq 0 ]]; then
  :
elif [[ $# -eq 2 && "$1" == "--live" ]]; then
  LIVE_MODE="true"
  LIVE_DATE="$2"
  [[ "${LIVE_DATE}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || die "invalid date format: ${LIVE_DATE} (expected YYYY-MM-DD)"
else
  usage
  exit 1
fi

printf '[step] weekly help check\n'
"${PYTHON}" -m src.app.entrypoints.weekly_main -h >/dev/null

printf '[step] weekly format-test check\n'
"${PYTHON}" -m src.app.entrypoints.weekly_main -t

printf '[step] weekly unit checks\n'
if [[ -x ".venv/bin/pytest" ]]; then
  .venv/bin/pytest tests/unit/test_weekly_guard.py tests/unit/test_weekly_engine.py -v
else
  "${PYTHON}" -m pytest tests/unit/test_weekly_guard.py tests/unit/test_weekly_engine.py -v
fi

if [[ "${LIVE_MODE}" == "true" ]]; then
  printf '[step] weekly live check (%s)\n' "${LIVE_DATE}"
  "${PYTHON}" -m src.app.entrypoints.weekly_main "${LIVE_DATE}" -u
fi

printf '[ok] weekly_e2e_gate completed\n'
