# tests rules

- New tests belong under `tests/unit/` or `tests/integration/`.
- Keep import and command guard coverage aligned with current canonical paths.
- Legacy root entrypoints, legacy shims, and legacy import roots should stay blocked by tests.
- Run `pytest tests/ -v` before requesting review.
- Local pre-commit expectations should stay aligned with the same `pytest tests/ -v` baseline.
