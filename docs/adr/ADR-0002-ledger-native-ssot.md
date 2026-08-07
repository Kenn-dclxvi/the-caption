# ADR-0002: Ledger Native SSOT

## Context

外部CSVを都度走査する構造は、鮮度判定と再現性を実行タイミングに依存させ、状態の正本が揺れる。

「SSOT」は本プロダクトで2つの異なるレイヤーを指すため、区別せずに用いると設計判断を誤る。

- **計算元の正典（Input SSOT）**: 評価の入力として何を信じるか。ADR-0004 が SSOT A / SSOT B として定める。
- **出力の正本（Canonical Ledger）**: 確定した状態をどこが保持するか。本 ADR が定める。

## Decision

本 ADR が定めるのは**出力の正本**である。日次で確定して製本する Ledger（JSON）を出力の正本とし、確定後の状態判定と期間比較はこの Ledger を基準に行う。

外部CSVは計算元の正典または取得ソースであり、出力の正本ではない。計算元の正典の所在は ADR-0004 が定め、本 ADR と競合しない。

## Non-goals

- 外部CSVを完全に廃止すること
- すべての履歴をCSVのみで再構築する運用維持
- 計算元の正典（SSOT A / SSOT B）の所在を再定義すること

## Guardrails

- 用語は「計算元の正典（SSOT A / SSOT B）」と「出力の正本（Canonical Ledger）」を区別して用いる
- 日次の確定台帳は `data/current/ledger_YYYYMMDD.json` として毎営業日保存する
- 前日比（DAY）の基準は前営業日の確定台帳とし、取得元CSVの末尾行を基準にしない。前日側は値段と為替の両方を正本の確定値で揃え、円建て評価額の変化として算出する（[ADR-0005](./ADR-0005-target-date-us-market-date.md)）
- `integrity_status = VERIFIED` へ到達した確定台帳は後続実行で書き換えない。`STAGNANT` の間は暫定として更新してよい
- 期待日の値段が取得元に無い場合、前営業日の正本から確定値を継承してよい。継承は「正本がその資産を `PRICED` として記録している」「正本の対象日が期待日以降である」「取得元から算出した値段が正本と一致する」の全てを満たす場合に限る
- 継承した資産は `PRICED` として扱い、その日は確定として CompletionLock を記録する。期待セッションが後日取得元へ追加されても、確定済みの日は再確定しない。継承した事実は `warnings` と `source_date` に残す
- 継承の要件が崩れる場合（取得元の値段が正本と異なる場合を含む）は継承せず、通常の鮮度判定へ戻す
- CSVは計算元の正典または取得ソースとしてのみ利用し、確定済み台帳の値を上書きする基準にしない
- 月次の期間比較は対象月の確定台帳を `integrity_status` で絞り込まず走査する。`STAGNANT` を除外すると月境界の日や月そのものが欠落するため、暫定であることは除外ではなく `integrity_status` として月次の出力へ残す
- SSOT定義はReferenceで管理し、Appendixに置かない

## Open items

- 期間騰落（MTD / WTD / YTD）の基準は現時点で取得元CSVの期間起点であり、確定台帳基準へ移行していない。移行は期間起点となる確定台帳が連続して存在することを前提とするため、台帳の欠落期間を解消した後に決定する。

## Consequences

状態判定の一貫性と再現性が向上する。CSV依存の運用差異は縮小し、データ更新責務が明確化される。

## Related

- [ADR Decisions Index](./decisions_index.md)
- [ADR-0004 Collection-Primary v4.0](./ADR-0004-collection-primary-v4.md)（計算元の正典）
- [System Reference](../reference/system.md)
- [Explanation](../explanation/index.md)
