# tests ルール

- 新しいテストは `tests/unit/` または `tests/integration/` 配下に置く。
- import とコマンドのガードカバレッジを、現行の正規パスと整合させて保つ。
- レガシーのルートエントリポイント・レガシー shim・レガシー import ルートは、テストでブロックしたまま保つ。
- レビュー依頼前に `pytest tests/ -v` を実行する。
- ローカルの pre-commit 期待値は、同じ `pytest tests/ -v` のベースラインと整合させて保つ。
