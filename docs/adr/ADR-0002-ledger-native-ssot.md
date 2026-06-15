# ADR-0002: Ledger Native SSOT

## Context

外部CSVを都度走査する構造は、鮮度判定と再現性を実行タイミングに依存させ、状態の正本が揺れる。

## Decision

システム内部で生成・管理するLedger（JSON）を正本（SSOT）とし、外部CSVは取得ソースとして扱う。

## Non-goals

- 外部CSVを完全に廃止すること
- すべての履歴をCSVのみで再構築する運用維持

## Guardrails

- 状態判定はLedger基準で実施する
- CSVは取り込み入力としてのみ利用する
- SSOT定義はReferenceで管理し、Appendixに置かない

## Consequences

状態判定の一貫性と再現性が向上する。CSV依存の運用差異は縮小し、データ更新責務が明確化される。

## Related

- [ADR Decisions Index](./decisions_index.md)
- [System Reference](../reference/system.md)
- [Explanation](../explanation/index.md)
