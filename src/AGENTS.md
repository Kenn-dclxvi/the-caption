# src rules

- Canonical application code lives under `src/`.
- Daily/Monthly/Weekly CLI entrypoints live under `src/app/entrypoints/`.
- Canonical v4 daily command is `python -m src.app.entrypoints.v4_daily_main`.
- Monthly and weekly commands use `python -m src.app.entrypoints.monthly_main` and `python -m src.app.entrypoints.weekly_main`.
- `src/app/entrypoints/daily_main.py` and `src/app/entrypoints/collection_main.py` have been retired to `legacy/v3/` and are no longer present in src/.
- Settings and prompts are canonical under `src/config/`.
- Shared logger/models/utils are canonical under `src/lib/`.
- Do not reintroduce legacy compatibility roots such as `common/`, `config/`, `modules/`, or root entrypoint shims.
- Keep responsibilities split by layer:
  - `src/app`: orchestration and entry-facing application services
  - `src/domain`: pure business/domain logic
  - `src/infra`: external I/O and integrations
  - `src/lib`: shared utilities without domain ownership
- During migrations, prefer small behavior-preserving moves over large rewrites.
