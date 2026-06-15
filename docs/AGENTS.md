# docs rules

- Document canonical CLI paths only.
- Use `python -m src.app.entrypoints.v4_daily_main`, `python -m src.app.entrypoints.monthly_main`, and `python -m src.app.entrypoints.weekly_main` for canonical application entrypoints.
- `python -m src.app.entrypoints.daily_main` and `python -m src.app.entrypoints.collection_main` have been retired to `legacy/v3/` and are no longer present in src/.
- Use `python scripts/dev/...` or `bash scripts/dev/...` for developer tooling.
- Do not document legacy root entrypoint shims such as `main.py`, `monthly_main.py`, or `collection_main.py`.
- Do not document `python tools/...` commands.
- Prefer linking to the nearest directory `AGENTS.md` instead of repeating local placement rules in docs.

# 仕様・設計
- 仕様・設計ドキュメントは、既存同種ドキュメントの構成に従う。
- 既存同種ドキュメントがない場合は、作成前に構成案を提示して確認する。
- 未決事項は、仕様・設計として確定せず、未決事項として明示する。
- 説明・テンプレート・記載例は how-to に置く。
