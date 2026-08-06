# ADR-0001: Trinity Separation

**Status: Superseded**（ADR-0004 により外部取得層は監査層へ降格。公開版では実装ごと除外）

## Context

「Trinity」は本プロダクトで2つの異なる対象を指すため、区別せずに用いると設計判断を誤る。

- **外部取得層の三層分離（本 ADR）**: `BrowserManager` / `Operator` / `Client`。特定金融機関からのブラウザ経由取得に閉じた分離であり、公開版では実装を持たない。
- **アプリケーション全体のレイヤー分離**: Logic（`src/domain`）/ Infrastructure（`src/infra`）/ View（`src/app/renderer`）。README の Core Architecture が指すのはこちらで、[ADR-0007](./ADR-0007-layer-separation-and-ports.md) が定める。

本 ADR は前者に限る。後者と競合しない。

外部サイトからのブラウザ経由取得は、ブラウザ基盤・ドメイン操作・公開Facadeが混在すると、変更影響の境界が曖昧になり障害切り分けが遅延する。

## Decision

外部サイト取得層は `BrowserManager`（Infra）/ `Operator`（Domain Logic）/ `Client`（Facade）の三層分離を採用し、責務越境を禁止する。

## Non-goals

- 単一クラスへの統合による実装短縮
- ドメイン知識をInfra層へ再配置する最適化

## Guardrails

- Infra層にセレクタ・URL・ログイン概念を持ち込まない
- Domain層はブラウザプロセス管理を持たない
- 外部呼び出しはFacade公開IFを経由する

## Consequences

責務境界が固定され、変更時の影響範囲と障害解析の起点が明確になる。実装コストは増えるが、運用安定性を優先する。

## Supersession

ADR-0004 で Collection-Primary へ主従反転し、外部取得層は正規入力から監査層へ降格した。本公開リポジトリでは、特定金融機関のログイン自動化を公開範囲に含めない判断により、この三層に対応する実装を持たない。本ADRは設計判断の経緯としてのみ保持する。

## Related

- [ADR-0004 Collection-Primary v4](./ADR-0004-collection-primary-v4.md)
- [ADR-0007 レイヤー分離と port による依存逆転](./ADR-0007-layer-separation-and-ports.md)（アプリケーション全体のレイヤー分離）
- [ADR Decisions Index](./decisions_index.md)
- [System Reference](../reference/system.md)
- [Logic Reference](../reference/logic.md)
