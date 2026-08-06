# ADR-0007: レイヤー分離と port による依存逆転

**Status: Accepted**

## Context

README の Core Architecture は Logic / Infrastructure / View の分離を掲げるが、これを定める ADR が存在しなかった。[ADR-0001](./ADR-0001-trinity-separation.md) も「Trinity」を名乗るが対象は外部取得層の三層（`BrowserManager` / `Operator` / `Client`）であり、Status は Superseded、公開版では実装も持たない。裏付けが無いため、実装は次のように逸脱していた。

- `src/domain` から `src/infra` への import が 8 箇所
- `src/domain` から `src/app/renderer` への逆依存が 3 箇所（Logic が View の整形済み文字列を消費し、数値へ再パースしていた）
- `src/domain` 内でのファイル入出力とネットワーク取得

`src/AGENTS.md` は「`src/domain`: 純粋なビジネス・ドメインロジック」と規定していたが、判断の根拠が層規約の一行に留まり、逸脱を戻す基準として機能していなかった。

## Decision

アプリケーション全体のレイヤー分離を次のとおり定める。依存は一方向とする。

- **Logic（`src/domain`）**: 台帳の構築、検証、正規化、配信可否の判定。外部 I/O を持たない。
- **Infrastructure（`src/infra`）**: ファイル・ネットワーク・LLM・メールの入出力。domain の検証を呼んでよい。
- **View（`src/app/renderer`）**: データの視覚表現へのマッピング。計算を再実行しない。
- **Orchestration（`src/app`）**: 実装の生成と注入、実行順序の決定。

domain が外部 I/O を必要とする場合は、`src/infra` の具象を import せず `src/domain/ports.py` へ Protocol を宣言する。実装は `src/infra` が持ち、注入は `src/app` が行う（依存性逆転）。

## Non-goals

- 既存の判定ロジックや期間騰落の計算方式を変更すること
- `src/lib` をレイヤーの一つとして扱うこと（ドメイン所有を持たない共有ユーティリティであり、いずれの層からも参照してよい）
- 外部取得層の三層分離（ADR-0001）を再導入すること

## Guardrails

- `src/domain` から `src/app` と `src/infra` を import しない。ViewModel は View 層の型であり domain の signature へ現れない。domain へ渡す値は `src/lib/models` の `Ledger` / `LedgerSummary` / `Position` を使う
- domain が表示用の文字列を必要とする場合は、View の整形結果を受け取らず domain 側で組む。View と同じ書式を使う箇所は二重定義である旨をコメントで残す
- 検証・正規化と入出力を同一モジュールへ置かない。検証・正規化は `src/domain`、パス解決と読み書きは `src/infra` の repository に置く
- ファイルパス定数は `src/config/settings` に置く。domain と infra の双方から参照する定数を一方のモジュールへ持たせない
- 使っていない依存は Protocol へ包まず引数から外す
- port と実装の乖離は `tests/unit/test_ports.py` で突き合わせる。port を変更したら同テストも更新する
- 移行は挙動を保つ小さな移動を優先する。表示書式を経た値を再パースしている箇所など、値の同一性が崩れうる変更は分離して扱う

## Consequences

依存の向きが一方向に固定され、domain のテストが外部 I/O を伴わなくなる。infra の差し替えは port の実装追加で済む。

一方で、domain が I/O を必要とするたびに port の宣言と注入が必要になり、生成箇所の記述量は増える。port を機能ごとに細かく分けると注入の追加が広範囲へ波及するため、入出力の系統単位で集約する。

`is_market_closed` のように外部データを参照する判定は infra に残す。どの資産クラスを判定対象とするかのような方針は domain に置く。

## Related

- [ADR Decisions Index](./decisions_index.md)
- [ADR-0001 Trinity Separation](./ADR-0001-trinity-separation.md)（外部取得層の三層分離。対象が異なる）
- [src ルール](../../src/AGENTS.md)
- [System Reference](../reference/system.md)
