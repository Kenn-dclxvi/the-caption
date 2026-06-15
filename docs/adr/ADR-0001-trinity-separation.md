# ADR-0001: Trinity Separation

## Context

Broker連携はブラウザ基盤・ドメイン操作・公開Facadeが混在すると、変更影響の境界が曖昧になり障害切り分けが遅延する。

## Decision

Broker連携は `BrowserManager`（Infra）/ `BrokerOperator`（Domain Logic）/ `BrokerClient`（Facade）の三層分離を採用し、責務越境を禁止する。

## Non-goals

- 単一クラスへの統合による実装短縮
- ドメイン知識をInfra層へ再配置する最適化

## Guardrails

- Infra層にセレクタ・URL・ログイン概念を持ち込まない
- Domain層はブラウザプロセス管理を持たない
- 外部呼び出しはFacade公開IFを経由する

## Consequences

責務境界が固定され、変更時の影響範囲と障害解析の起点が明確になる。実装コストは増えるが、運用安定性を優先する。

## Related

- [ADR Decisions Index](./decisions_index.md)
- [System Reference](../reference/system.md)
- [Logic Reference](../reference/logic.md)
