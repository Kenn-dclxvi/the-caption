# scripts ルール

- 正規の開発者向けユーティリティは `scripts/dev/` 配下に置く。
- CI で安全に実行できるスクリプトは `scripts/ci/` 配下に置く。
- `scripts/` 直下に新しい互換ラッパーを追加しない。
- `tools/` のコマンド例を追加せず、`python scripts/dev/...` または `bash scripts/dev/...` のみを使う。
- 新しいスクリプトファイルは、実行ランタイムに応じて `scripts/dev/` または `scripts/ci/` 配下に置く。
- 主要な開発者向けエントリポイントは `python scripts/dev/bump_rev.py --check-staged` / `python scripts/dev/bump_rev.py --bump <file.py>` / `python scripts/dev/install_hooks.py` とする。

# コミットゲート

- `python scripts/dev/install_hooks.py` が仕込む pre-commit は 2 段で、いずれかが失敗するとコミットが中断する。
  - `python scripts/dev/bump_rev.py --check-staged`（REV_SYNC チェック）
  - `python -m pytest tests/ -v`（全件）
- pre-commit は `.venv/bin/python` を優先し、無い場合のみ `python3` へ落ちる。worktree からは `git rev-parse --git-common-dir` でメインリポジトリの `.venv` を解決する。
- `bump_rev.py` の対象は `__REV: Final[str] = "Rev. N"` を持つ `.py` のみとする。この宣言を持たないファイルは SKIP 扱いで、チェックを通過する。
- `install_hooks.py` は `.claude/settings.local.json` の `hooks.PostToolUse` を削除する。フック設定を戻す場合は同ファイルを直接編集する。
