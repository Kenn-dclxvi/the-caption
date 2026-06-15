# ADR-0003: Risk Acceptance Policy

## Context

金融レポート配信では、完全性を待つ遅延と不完全状態での継続処理の間に常時トレードオフが存在する。

## Decision

GuardRailとFreshness判定を基準に、許容可能なリスクのみ明示的に受け入れる方針を採用する。未許容リスクは停止または再取得を選ぶ。

## Non-goals

- すべての異常ケースを自動継続にすること
- 運用判断を暗黙ルールへ委ねること

## Guardrails

- CompletionLockで重複送信を防止する
- STAGNANT判定は再取得または停止を優先する
- 受容したリスクは仕様上の判定条件として固定する

## Consequences

停止条件と継続条件が可視化され、運用時の判断ぶれが減少する。即時性よりも整合性を優先する設計になる。

## Related

- [ADR Decisions Index](./decisions_index.md)
- [Logic Reference](../reference/logic.md)
- [How-to Guides](../how-to/index.md)
