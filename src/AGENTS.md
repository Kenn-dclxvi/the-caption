# src ルール

- 正規のアプリケーションコードは `src/` 配下に置く。
- Daily / Monthly / Weekly の CLI エントリポイントは `src/app/entrypoints/` 配下に置く。
- 正規の v4 daily コマンドは `python -m src.app.entrypoints.v4_daily_main` とする。
- monthly / weekly コマンドは `python -m src.app.entrypoints.monthly_main` と `python -m src.app.entrypoints.weekly_main` を使う。
- `src/app/entrypoints/daily_main.py` と `src/app/entrypoints/collection_main.py` は `legacy/v3/` へ退避済みで、`src/` 配下には存在しない。
- 設定とプロンプトは `src/config/` 配下を正規とする。
- 共有の logger / models / utils は `src/lib/` 配下を正規とする。
- `common/` / `config/` / `modules/` などのレガシー互換ルートやルートエントリポイント shim を再導入しない。
- 責務はレイヤーごとに分割を保つ。
  - `src/app`: オーケストレーションとエントリ向けアプリケーションサービス
  - `src/domain`: 純粋なビジネス・ドメインロジック
  - `src/infra`: 外部 I/O と連携
  - `src/lib`: ドメイン所有を持たない共有ユーティリティ
- 移行時は、大規模な書き換えより、挙動を保つ小さな移動を優先する。
