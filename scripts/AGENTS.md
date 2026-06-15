# scripts rules

- Canonical developer utilities live under `scripts/dev/`.
- CI-safe scripts live under `scripts/ci/`.
- Do not add new top-level compatibility wrappers under `scripts/`.
- Do not add `tools/` command examples; use `python scripts/dev/...` or `bash scripts/dev/...` only.
- New script files should be placed under `scripts/dev/` or `scripts/ci/` based on their runtime.
- Common developer entrypoints are `python scripts/dev/bump_rev.py --check-staged`, `python scripts/dev/bump_rev.py --bump <file.py>`, and `python scripts/dev/install_hooks.py`.
