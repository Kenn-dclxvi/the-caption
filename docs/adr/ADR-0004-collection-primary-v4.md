# ADR-0004: Collection-Primary v4.0

## Context

旧日次パイプラインは証券会社サイトのスクレイピングとCSV仕様に強く依存していた。ログイン失敗、メンテナンス、画面変更、CSV仕様変更が発生すると、AI因果推論と日次レポート配信まで停止する構造だった。

一方、Collection 系には保有数を管理する `data/collection/market_units.csv` と、現金・外部資産の絶対額を管理する `data/external_assets.json` が存在する。これらは性質が異なるため、単一ファイルへ統合せず、Dual Input SSOT として扱う。

本 ADR が定めるのは**計算元の正典**（評価の入力として何を信じるか）に限る。**出力の正本**（確定した状態をどこが保持するか）は [ADR-0002](./ADR-0002-ledger-native-ssot.md) が定める。両者は別レイヤーであり競合しない。以降、計算元には「正典」、出力には「正本」を用いる。

## Decision

v4.0 では Collection-Primary へ主従反転する。

- `data/collection/market_units.csv` を SSOT A とし、市場連動資産の `units` を正典とする。
- `data/current/collection_units_YYYYMMDD.json` を日付別 Units 固定入力 snapshot とし、`strict` mode では snapshot 欠損・不正を blocking とする。
- `data/external_assets.json` を SSOT B とし、現金・外部資産の `amount` を正典とする。
- `UniversalIngester` が両入力を統合し、`ShadowLedger` (`data/v4_shadow_ledger.json`) を生成する。
- `ShadowLedger.ssot_a_path` は計算元の正典 `market_units.csv` のパスを示し、実際に採用した Units 入力元は `ShadowLedger.units_source` に記録する。
- v4日次パイプラインは同一実行内の統合結果 `ShadowLedger` を AI因果推論とレポート生成へ渡す。日次で確定して保存する出力の正本は `data/current/ledger_YYYYMMDD.json` であり、その扱いは ADR-0002 に従う。
- 外部取得系は監査層へ隔離し、差分比較と到達不能警告のみを担わせる（公開版では実装を持たない）。
- 日次HTMLメールは `V4ContentRenderer` の Monolithic Scroll へ統合する。

## Non-goals

- `daily_main.py` を削除または破壊すること
- `collection_main.py` の単独レポート経路を即時廃止すること
- `market_units.csv` と `external_assets.json` を物理的に統合すること
- runtime で旧 `data/collection/funds.csv` へ自動フォールバックすること
- 旧レンダラー (`report_fortress.py`, `report_context.py`, `report_collection.py`) を変更すること

## Guardrails

- v4標準日次の正規CLIは `python -m src.app.entrypoints.v4_daily_main` とする。
- 監査層で発生する例外は配信停止理由にしない。
- `[AUDIT]` ログには監査比較結果、または到達不能である旨を明記する。
- `ShadowLedger.total_value_jpy` は `assets[].current_value_jpy` の合計と一致させる。
- `external_assets.json` は対象月 `YYYY-MM` を優先し、なければ `default` にフォールバックする。

## Consequences

日次レポートは外部サイトの可用性から切り離され、20:00 の安定配信を優先できる。外部取得は監査情報としてのみ位置づけられ、主系切り替え後も差分観測の余地を残す。

## Related

- [ADR Decisions Index](./decisions_index.md)
- [ADR-0002 Ledger Native SSOT](./ADR-0002-ledger-native-ssot.md)（出力の正本）
- [System Reference](../reference/system.md)
- [Logic Reference](../reference/logic.md)
- [Design System](../reference/design-system.md)
