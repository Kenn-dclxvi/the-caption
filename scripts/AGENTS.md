# scripts ルール

- 正規の開発者向けユーティリティは `scripts/dev/` 配下に置く。
- CI で安全に実行できるスクリプトは `scripts/ci/` 配下に置く。
- `scripts/` 直下に新しい互換ラッパーを追加しない。
- `tools/` のコマンド例を追加せず、`python scripts/dev/...` または `bash scripts/dev/...` のみを使う。
- 新しいスクリプトファイルは、実行ランタイムに応じて `scripts/dev/` または `scripts/ci/` 配下に置く。
- 主要な開発者向けエントリポイントは `python scripts/dev/bump_rev.py --check-staged` / `python scripts/dev/bump_rev.py --bump <file.py>` / `python scripts/dev/install_hooks.py` とする。
