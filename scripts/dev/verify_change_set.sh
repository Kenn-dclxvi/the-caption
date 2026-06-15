#!/usr/bin/env bash
set -euo pipefail

LEVEL="normal"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --level)
      LEVEL="${2:-normal}"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done

if [[ "${LEVEL}" != "normal" ]]; then
  printf '[warn] unsupported level: %s (using normal)\n' "${LEVEL}" >&2
fi

exec .venv/bin/python -m pytest tests/ -v
