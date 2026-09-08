# Reference Index

事実仕様（SSOT）の参照入口。

## Core References

- [System Reference](./system.md)
- [Logic Reference](./logic.md)
- [Project Contexts](./project-contexts/the-caption.txt)
- [Design System](./design-system.md)
- [Prompt Design](./prompts.md)

## V4.0 Primary References

- [System Reference §1.1 Requirements V4](./system.md#11-requirements-v4-collection-primary-canonical-ledger)
- [Logic Reference §1 V4 Canonical Ledger Guard](./logic.md#1-v4-canonical-ledger-guard-collection-primary)
- [Design System §5 V4 Monolithic Scroll](./design-system.md#5-v4-monolithic-scroll統合鑑定書)
- [ADR-0004 Collection-Primary v4.0](../adr/ADR-0004-collection-primary-v4.md)
- [ADR-0005 `target_date` 基準の米国市場日付](../adr/ADR-0005-target-date-us-market-date.md)

## Feature Change Reading Guide

- Daily mail / v4 pipeline changes: read [Project Contexts](./project-contexts/the-caption.txt), [System Reference §1.1 Requirements V4](./system.md#11-requirements-v4-collection-primary-canonical-ledger), and [Logic Reference §3 System Flow & CompletionLock](./logic.md#3-system-flow--completionlock).
- Ledger / valuation / SSOT changes: read [System Reference §3 Data Architecture](./system.md#3-data-architecture) and [Logic Reference §3.1 V4 Ledger Finalization](./logic.md#31-v4-ledger-finalization).
- US market date / holiday / FX-date changes: read [ADR-0005](../adr/ADR-0005-target-date-us-market-date.md) and [Logic Reference §6 TimelineController](./logic.md#6-timelinecontroller-date-resolution--holiday-aware-us-market-context).
- Renderer / mail layout changes: read [Design System](./design-system.md) and renderer/view-model references.
- Monthly / Chronicle changes: read the V4 Monthly Chronicle sections in [Logic Reference](./logic.md) and [Prompt Design](./prompts.md).
- Prompt / LLM output changes: read [Prompt Design](./prompts.md) and the Prompt Injection Guard section in [System Reference](./system.md#23-prompt-injection-guard-プロンプトインジェクション防御).
- Legacy changes: read legacy sections explicitly; do not apply legacy assumptions to v4 daily.

## API Contract and Migration

- [THE CAPTION API v1 契約と WebUI 操作対応](./api-v1.md)（段階B：Market Units実装、残り2リソース移行予定）
- [OpenAPI v1](./openapi-v1.json)（契約版 0.1.0）
- [Market Units API の起動と利用](../how-to/market-units-api.md)

## Related

- [Docs Index](../_index.md)
- [Explanation](../explanation/index.md)
- [ADR Decisions](../adr/decisions_index.md)
