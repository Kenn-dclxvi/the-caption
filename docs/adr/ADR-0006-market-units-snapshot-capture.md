# ADR-0006: 日次 Market Units 入力の事前固定

## Context

従来の `daily` mode は対象日の Units snapshot が欠落または不正でも、`data/collection/market_units.csv` へフォールバックした。このため日次処理自体は成功する一方、後日の再計算で当時の保有数量を再現できず、`units_source.type = LIVE_CSV` の確定台帳が継続して生成された。

## Decision

- JST 当日の通常日次は、台帳計算より先に `collection_units_YYYYMMDD.json` を atomic write で生成する。
- 同日の有効な既存 snapshot は不変入力として再利用し、上書きしない。
- snapshot の保存、再読込検証、既存ファイル検証のいずれかが失敗した場合は、確定台帳、`daily_metrics`、`market_snapshot`、メール送信、CompletionLock更新へ進まない。
- 日次台帳計算と選択再取得後の再計算は、同じ snapshot を `strict` mode で採用する。
- 明示した過去日付は既存の有効な snapshot を必須とし、現在の CSV から暗黙生成しない。
- 過去欠落日は専用バックフィル経路で扱う。対象日へ一意にbindした歴史CSVだけを許可し、既存 snapshot と他の確定成果物を変更しない。

## Availability Boundary

この判断では、Market Units 入力を固定できない日の配信可用性より、確定成果物の再現性を優先する。価格履歴の `MISSING` / `STALE` に対する既存の暫定配信契約は変更しない。変更するのは Units 入力が未固定な場合の境界だけである。

## Consequences

通常日次で生成した台帳は常に `units_source.type = SNAPSHOT` を持ち、同日再実行でも同じ Units 入力を使う。ディスク障害や不正 snapshot がある日は配信が止まるため、運用者は原因を解消して同じ日を再実行する必要がある。過去入力を復元できない日は unresolved のまま残り、現在値による推測で埋めない。

## Related

- [Market Units migration spec](../how-to/market-units-migration-spec.md)
- [System Reference](../reference/system.md)
- [ADR Decisions Index](./decisions_index.md)
