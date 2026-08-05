# tests ルール

- 新しいテストは `tests/unit/` または `tests/integration/` 配下に置く。
- import とコマンドのガードカバレッジを、現行の正規パスと整合させて保つ。
- レガシーのルートエントリポイント・レガシー shim・レガシー import ルートは、テストでブロックしたまま保つ。
- レビュー依頼前に `pytest tests/ -v` を実行する。
- ローカルの pre-commit 期待値は、同じ `pytest tests/ -v` のベースラインと整合させて保つ。

# 実行環境

- pytest は `.venv/bin/pytest` を使う。pre-commit も同じ `.venv` を優先するため、ベースラインを一致させる。
- `pytest.ini` の `addopts` により、単一テストの実行でも `--cov=src --cov-report=term-missing` と `--junit-xml=reports/test-result.xml` が常に付く。coverage 出力の欠落やカバレッジ低下は、対象を絞った実行でも現れる。
- `--junit-xml` は毎回 `reports/test-result.xml` を上書きする。テスト実行はこのパスへの書き込みを伴う。
- 単一テストは locator を渡して実行する。

```bash
.venv/bin/pytest tests/unit/test_v4_engine.py -v
```

```bash
.venv/bin/pytest tests/unit/test_v4_engine.py::test_v4_engine_dispatches_from_universal_ingester -v
```

- coverage を外して切り分けたい場合は `-p no:cacheprovider --no-cov` を付ける。既定の `addopts` は変更しない。
