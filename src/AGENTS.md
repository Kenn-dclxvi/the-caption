# src ルール

- 正規のアプリケーションコードは `src/` 配下に置く。
- Daily / Monthly / Weekly の CLI エントリポイントは `src/app/entrypoints/` 配下に置く。
- 正規の v4 daily コマンドは `python -m src.app.entrypoints.v4_daily_main` とする。
- monthly / weekly コマンドは `python -m src.app.entrypoints.monthly_main` と `python -m src.app.entrypoints.weekly_main` を使う。
- `src/app/entrypoints/daily_main.py` と `src/app/entrypoints/collection_main.py` は本リポジトリに存在しない（v3 主系は公開範囲外）。
- 設定とプロンプトは `src/config/` 配下を正規とする。
- 共有の logger / models / utils は `src/lib/` 配下を正規とする。
- `common/` / `config/` / `modules/` などのレガシー互換ルートやルートエントリポイント shim を再導入しない。
- 責務はレイヤーごとに分割を保つ。
  - `src/app`: オーケストレーションとエントリ向けアプリケーションサービス
  - `src/domain`: 純粋なビジネス・ドメインロジック
  - `src/infra`: 外部 I/O と連携
  - `src/lib`: ドメイン所有を持たない共有ユーティリティ
- 移行時は、大規模な書き換えより、挙動を保つ小さな移動を優先する。

# 実行経路（`run.sh` と `python -m`）

- `python -m src.app.entrypoints.*` は正規のモジュールパスであり、ドキュメント記載とテスト・デバッグ実行の基準とする。
- 運用実行は `./run.sh` を使う。`run.sh` は薄いエイリアスではなく、`python -m` 直叩きでは得られない制御を持つ。
  - `logs/run.sh.lock` の `flock` による多重起動防止。既に実行中の場合は警告のみを出して exit 0 で終了する。
  - `.venv/bin/python` → `python` → `python3` の順でインタプリタを解決する。
  - 実行前に `SCRIPT_DIR` へ `cd` する。
- `run.sh` のモード対応は `v4`/`v`、`weekly`/`w`、`monthly`/`m` とする。日付のみ（`YYYY-MM-DD`）と `-` 始まりの引数は v4 daily へ解決する。`daily` / `collection` は廃止モードとしてエラー終了する。
- v4 daily は `./run.sh v4` を使う。引数なしの `./run.sh` は、`v4|v` 分岐の `shift` が位置パラメータ 0 個で失敗し、`set -euo pipefail` によりエンジンを起動せず exit 1 で終了する。`run.sh` の usage が例示する `./run.sh` は現状動作しない。
- Web UI は `./run.sh collection-web-prd`（`127.0.0.1:3001`）と `./run.sh collection-web-dev`（`127.0.0.1:3101`）から起動する。これらは node/npm の解決を含むため `python -m` の対象外とする。
- 多重起動防止が要件に含まれる変更では、`python -m` を前提にせず `run.sh` 側の経路を確認する。
