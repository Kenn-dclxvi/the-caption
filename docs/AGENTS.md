# docs ルール

- ドキュメントには正規の CLI パスのみを記載する。
- アプリケーションの正規エントリポイントには `python -m src.app.entrypoints.v4_daily_main` / `python -m src.app.entrypoints.monthly_main` / `python -m src.app.entrypoints.weekly_main` を使う。
- `python -m src.app.entrypoints.daily_main` と `python -m src.app.entrypoints.collection_main` は本リポジトリに存在しない（v3 主系は公開範囲外）。
- 開発者向けツールには `python scripts/dev/...` または `bash scripts/dev/...` を使う。
- `main.py` / `monthly_main.py` / `collection_main.py` などのルートエントリポイント shim は記載しない。
- `python tools/...` コマンドは記載しない。
- ローカルの配置ルールをドキュメントへ繰り返さず、最も近いディレクトリの `AGENTS.md` へのリンクを優先する。

# CI ガード

- `.github/workflows/docs-canonical-command-guard.yml` が `README.md` と `docs/how-to/index.md` を対象に、行頭の `python tools/` を検出して CI を失敗させる。上記の記載禁止はこのワークフローで強制されている。
- 検出対象は行頭（前置の空白のみ許容）の `python tools/` に限る。コード例の途中に現れる同じ文字列は検出されない。ガードの通過を記載可否の判断根拠にしない。
- ガード対象は上記 2 ファイルのみで、`docs/` 配下の他のファイルは CI で検査されない。検査されないことを記載可の根拠にしない。

# 仕様・設計
- 仕様・設計ドキュメントは、既存同種ドキュメントの構成に従う。
- 既存同種ドキュメントがない場合は、作成前に構成案を提示して確認する。
- 未決事項は、仕様・設計として確定せず、未決事項として明示する。
- 説明・テンプレート・記載例は how-to に置く。
