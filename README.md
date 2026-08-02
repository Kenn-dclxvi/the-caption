# THE CAPTION v4.3 "The Settled Close"
**Sovereign Portfolio Custodian & Reporting Engine**

>2026年1月17日開始

> **「騒がしい市場の中で、静かに自分の資産を俯瞰する」**

THE CAPTION は、資産の動きを「美術館のキャプション」のような静謐なレポートへと変換するアーカイブシステムです。感情を排した「論理の静寂」の中で、数値の裏側にある因果を AI が鑑定し、知的で落ち着いた資産管理体験を提供します。

同時に本リポジトリは、[orchestration-prompt](https://github.com/Kenn-dclxvi/orchestration-prompt) の実行制御を適用した **AI駆動開発（Director-Led AI Development）の実証リポジトリ**でもあります。実装の大半は AI エージェントが [AGENTS.md](./AGENTS.md) の規約に従って生成しており、設計判断は [docs/adr/](./docs/adr/) に記録されています。

---

## ⚠️ 公開版について

- **実データは一切含まれません。** 保有資産（`data/`）、実行ログ（`logs/`）、資格情報（`.env` / `secret.key`）はすべて `.gitignore` 済みです
- **特定金融機関へのログイン自動化・スクレイピング実装は公開範囲に含めていません。** 該当層は監査系として設計されていましたが（[ADR-0001](./docs/adr/ADR-0001-trinity-separation.md)）、v4 の主系である Collection-Primary は当該実装に依存しません
- 本ソフトウェアは**投資助言を行うものではありません**。生成されるレポートは LLM による記述であり、正確性は保証されません
- セルフホストする場合は [SECURITY.md](./SECURITY.md) を先に読んでください

---

## 📚 Documentation Map (Diátaxis)

詳細な仕様、運用手順、および設計思想は `docs/` 配下に体系化されています。

| Category | Description | Contents |
| :--- | :--- | :--- |
| **[Tutorials](./docs/tutorials/index.md)** | **学び始めのステップ**<br>環境構築から初回実行まで。 | • [Environment Setup & Installation](./docs/tutorials/index.md)<br>• [Infrastructure Architecture](./docs/tutorials/index.md) |
| **[How-to Guides](./docs/how-to/index.md)** | **実践ガイド**<br>日々の運用とトラブルシューティング。 | • [Daily Operations](./docs/how-to/index.md)<br>• [Development Workflow](./docs/how-to/index.md)<br>• [Maintenance & Recovery](./docs/how-to/index.md) |
| **[Reference](./docs/reference/system.md)** | **技術仕様書**<br>厳密な定義、データ構造、API仕様。 | • [System Specifications](./docs/reference/system.md)<br>• [Configuration & Security](./docs/reference/system.md)<br>• [Data Architecture](./docs/reference/system.md)<br>• [Project Contexts](./docs/reference/project-contexts/the-caption.txt) |
| **[Logic Reference](./docs/reference/logic.md)** | **ロジック詳細定義**<br>鮮度判定、実行フロー、AIスキーマ、Curator仕様。 | • [Freshness Guard](./docs/reference/logic.md)<br>• [System Flow & CompletionLock](./docs/reference/logic.md)<br>• [Curator Logic](./docs/reference/logic.md)<br>• [TimelineController](./docs/reference/logic.md)<br>• [Monthly Curator](./docs/reference/logic.md) |
| **[Explanation](./docs/explanation/index.md)** | **背景と理解**<br>設計思想、コンテキスト、歴史。 | • [Project Philosophy](./docs/explanation/index.md)<br>• [Architecture Concepts](./docs/explanation/index.md)<br>• [Knowledge Base](./docs/explanation/index.md) |
| **[Appendix](./docs/appendix/index.md)** | **実装詳細・付録**<br>高度なロジック解説とアーカイブ。 | • [Data Normalization Rules](./docs/appendix/index.md)<br>• [Reporting Implementation](./docs/appendix/index.md)<br>• [COLLECTION Acquisition Logic](./docs/appendix/index.md)<br>• [Monthly Chronicle Implementation](./docs/appendix/index.md) |
| **[Design Specification](./docs/reference/design-system.md)** | **デザイン規定**<br>「鑑賞」としての資産管理を実現するための視覚言語。 | • [Design Philosophy](./docs/reference/design-system.md)<br>• [Color Palette (Slate Symphony)](./docs/reference/design-system.md)<br>• [Typography System](./docs/reference/design-system.md)<br>• [Unified Layout Matrix](./docs/reference/design-system.md) |
| **[Prompt Design](./docs/reference/prompts.md)** | **プロンプト設計仕様**<br>CONTEXT（日次）・CHRONICLE（月次）の LLM プロンプト設計規定。 | • [CONTEXT Prompt Spec](./docs/reference/prompts.md)<br>• [CHRONICLE Prompt Spec](./docs/reference/prompts.md)<br>• [Output Schema & Validation](./docs/reference/prompts.md)<br>• [Generation Rules](./docs/reference/prompts.md) |

---

## 🧭 Repository Layout (AI Development)

新規開発時の配置ルールと責務境界です。v4.3 では Collection 系の保有マスターと外部資産定義を正規入力とします。

| Path | Role |
| :--- | :--- |
| `src/app` | アプリケーション層（オーケストレーション、ユースケース接続） |
| `src/domain` | ドメイン層（純粋ロジック、I/O 依存なし） |
| `src/infra` | インフラ層（外部I/O、通信、永続化） |
| `src/lib` | 共有ライブラリ（ドメイン非依存） |
| `tests/unit` | ユニットテスト |
| `tests/integration` | 結合テスト |
| `scripts/dev` | ローカル開発向けスクリプト |
| `scripts/ci` | CI向けスクリプト |
| `configs` | 非秘匿の静的設定資産 |
| `examples` | サンプル入出力・利用例 |

### Migration Policy

- Daily/Monthly/Collection の CLI 実装の正は `src/app/entrypoints/` です。
- ルートの `main.py` / `monthly_main.py` / `collection_main.py` 互換 shim は **2026-03-05** に廃止済みです。
- Settings/Prompts 実装の正は `src/config/` です（`config/` 互換 shim は **2026-03-05** に廃止済み）。
- 共通ライブラリ（logger/models/utils）実装の正は `src/lib/` です（`common/` 互換 shim は **2026-03-05** に廃止済み）。
- 旧 `modules/` 配下の互換 shim は **2026-03-05** に廃止済みです（参照先は `src/` 配下の正規実装に統一）。
- 開発支援ツールの正は `scripts/dev/` です（`tools/` 互換 shim は **2026-03-05** に廃止済み）。
- 新規ファイルは原則 `src/` 配下へ追加します。
- 既存コードの移行は小さな単位で段階実施します（移動 + 配線更新 + テスト確認）。
- 配置・運用ルールは `src/AGENTS.md`、`scripts/AGENTS.md`、`tests/AGENTS.md`、`docs/AGENTS.md` を参照してください。

---

## 🆕 What's New

### v4.3 "The Settled Close" (Latest)
* **STALE DAY 日付注記**: `pricing_status=STALE` の DAY % に `source_date` の月日注記を付け、古い価格が当日値に見えないようにしました。
* **US_STOCK Alpha Vantage Fallback**: yfinance が expected-date の有効な Close を返さない場合、任意の `ALPHA_VANTAGE_API_KEY` で Alpha Vantage 日足 Close を補完します。対象は US_STOCK 限定で、失敗時は既存挙動を維持します。
* **終値確定ガード**: JP株/US株/コモディティ/FX は基準日一致に加え、市場クローズ確認後のみ `PRICED` へ昇格し、取引時間中の速報値は `STALE` とします。
* **JP Observation Lag Correction**: US株/コモディティの MTD/YTD 基準日に JP 観測ラグ補正を適用し、月初週などの期間パフォーマンス不整合を解消しました。
* **US_STOCK DAY Detail Line**: `asset_class = "US_STOCK"` の資産（静的外部資産を除く）に、USD 評価額と USD/JPY キャプションを DAY 詳細行として表示します。

### v4.2 "Temporal Integrity"
* **V4.2 Refactoring**: v4日次の取得・鮮度判定・再取得フローを整理し、アセットクラス別の日付基準（JP株=`target_date`、US株/コモディティ/FX=`us_market_date`）を明確化しました。
* **FX依存鮮度の統合**: USD建て資産・コモディティの鮮度判定に為替（FX）基準日を統合し、古い為替での確定送信を防止しました。
* **Current Operation Canon**: 通常運用は `src/app/entrypoints/v4_daily_main.py` / `src/app/v4_engine.py` / Collection-Primary の Canonical Ledger を正とします。v3以前の主系・互換shimは本リポジトリに含みません。

### v4.1 "Collection-Primary"
* **Dual Input SSOT**: `data/collection/market_units.csv` を市場連動資産の保有数正典、`data/external_assets.json` を現金・外部資産の絶対額正典として扱います。
* **Units Snapshot Contract**: `data/current/collection_units_YYYYMMDD.json` がある日は日付別 Units 固定入力として採用し、採用元は `ShadowLedger.units_source` に記録します。
* **Universal Ingester**: `src/domain/universal_ingester.py` が両SSOTを統合し、`ShadowLedger` (`data/v4_shadow_ledger.json`) を生成します。
* **Canonical Ledger Promotion**: v4日次パイプラインでは `v4_shadow_ledger.json` を正規台帳として AI 因果推論とレポート生成へ渡します。
* **Monolithic Scroll**: `V4ContentRenderer` が INDEX / CONTEXT / COLLECTION を1通の縦長HTMLメールへ統合し、Unified Ledger と Shield を同一の鑑定書内に描画します。

### v3.5 "Policy Compass"
* **Portfolio Audit（投資方針監査）**: CONTEXT レポートに、コア方針・現金比率・3〜5年停滞耐性を日次市場構造に照らして評価する監査パネルを追加しました。
* **Shield Evaluation との責務分離**: コモディティ（金・銀・プラチナ）の防壁性能は `shield_evaluation` に閉じ、`portfolio_audit` は投資方針の維持・観測・再検証の判断に限定します。
* **Enum Validation 拡張**: `portfolio_audit.core_thesis` / `cash_buffer` / `stagnation_readiness` を検証対象に加え、ledger なし経路でも不正 Enum を再生成対象にします。
* **CONTEXT UI 更新**: Portfolio Audit を Insight パネル先頭に配置し、旧キャッシュや空値ではパネルを描画しない互換レンダリングを追加しました。

---

## 🏗 Core Architecture

システムは「三位一体分離（Trinity Architecture）」により構成されています。

1. **Logic（頭脳）**: `V4PortfolioEngine`, `UniversalIngester`, `MarketCurator`, `GuardRail` 等。正規台帳の生成、配信判定、AI推論に専念。
2. **Infrastructure（運搬）**: `LedgerRepository`, `LlmTransporter`, `MailSender`, `MarketDataFetcher` 等。物理的I/O、通信、外部APIとの接続を担う。
3. **View（表現）**: `V4ContentRenderer`, Jinja2 Template 等。データの視覚表現へのマッピングのみを行う。

---

## ✨ Key Features

1. **Collection-Primary Canonical Ledger**
    `market_units.csv` の保有数と `external_assets.json` の絶対額を統合し、`ShadowLedger` を日次処理の正規台帳として扱います。
2. **AI Causal Engine (因果推論)**
    Claude (Anthropic) を Primary とするマルチプロバイダ対応エンジン。単なる騰落率ではなく、市場ニュースとポートフォリオ感応度を照合した因果推論を提示。Google Gemini へのフェイルオーバー機能を搭載。
3. **Monolithic Scroll UI (統合鑑定書)**
    Evening Anchor、Finalized Monolith、Causal Insight、Unified Ledger、Shield を1通のHTMLメールへ統合します。
4. **Monthly Chronicle (月次総括)**
    v4.3 では日々の `ShadowLedger` 推移と Knowledge Base を束ね、`MARKET_UNITS` と `ABSOLUTE_AMOUNT` を分離したまま月間の構造的変化やパラダイムシフトを総括します。

---

## ⚡ Quickstart

初めて起動する場合・迷ったときはこの表を参照してください。

| シナリオ | コマンド |
| :--- | :--- |
| **通常運用**（v4日次配信） | `python -m src.app.entrypoints.v4_daily_main` |
| **初回／データ確認**（Shadow Ledger生成） | `python scripts/dev/run_shadow_ingester.py` |
| **障害復旧**（監査をスキップしv4を強制送信） | `python -m src.app.entrypoints.v4_daily_main -o -F` |

詰まったときは `logs/finance_report.log` のキーワード一覧（[How-to Guides §3.2](./docs/how-to/index.md)）を参照してください。

---

## 🚀 Quick Usage

`python -m src.app.entrypoints.v4_daily_main` が v4.3 日次実行の正規エントリポイントです。より詳細なコマンドオプションは [How-to Guides](./docs/how-to/index.md) を参照してください。

### Standard Execution (Scout/Sniper)
通常はこのコマンドで実行します。Universal Ingester が Canonical Ledger を生成し、ShadowLedger Gate と GuardRail 条件で配信可否を判定します。
```bash
python -m src.app.entrypoints.v4_daily_main
```

### Monthly Chronicle (月次総括)
月次レポート（前月末基準）の生成と配信を行います。
```bash
python -m src.app.entrypoints.monthly_main
```

### AI Context Reuse (鑑定の再利用)
APIコストを節約し、既存の AI 鑑定結果や月次総括のキャッシュを再利用して配信します。
```bash
python -m src.app.entrypoints.v4_daily_main -u
python -m src.app.entrypoints.monthly_main -u
```

### V4 Offline / Force Recovery (Troubleshooting)
外部監査をスキップし、Collection-Primary 台帳でロックを無視して送信します。
```bash
python -m src.app.entrypoints.v4_daily_main -o -F
```

### Shadow Ledger Probe
v4正規台帳の生成結果だけを確認します。
```bash
python scripts/dev/run_shadow_ingester.py
```

### COLLECTION Web Editor
`data/collection/market_units.csv` と `data/external_assets.json` をブラウザで編集するためのローカル Web UI を同梱しています。
```bash
npm --prefix src/web/market_units_editor install
./run.sh collection-web-prd
./run.sh collection-web-dev
```
起動後は `http://localhost:3001`（PRD）または `http://localhost:3101`（DEV）を開くと `Market Units` と `External Assets` を切り替えて編集できます。保存後は既存の `./run.sh collection -o` などへそのまま接続できます。

PRD は既定で `127.0.0.1:3001` のみで待ち受けます。Tailnet から利用する場合は、UI 起動時にTailscaleの完全ホスト名を `VITE_ALLOWED_HOSTS` へ渡し、Tailscale Serve を3001番ポートで設定します。
```bash
VITE_ALLOWED_HOSTS=<machine>.<tailnet>.ts.net ./run.sh collection-web-prd
tailscale serve --bg --https=3001 http://127.0.0.1:3001
```
この構成の接続先は `https://<machine>.<tailnet>.ts.net:3001/` です。Funnel は使用せず、Tailnet 内のアクセスに限定します。

---

## 🔗 関連リポジトリ

AI駆動開発を「規約 → 計測 → 適用」の3層で回しています。本リポジトリは適用先にあたります。

| リポジトリ | 役割 |
| :--- | :--- |
| [orchestration-prompt](https://github.com/Kenn-dclxvi/orchestration-prompt) | **規約**。エージェント実行制御の汎用プロンプトセット正本。本リポジトリの `AGENTS.md` と `prompts/` はここから適用しています |
| [agent-execution-control-lab](https://github.com/Kenn-dclxvi/agent-execution-control-lab) | **計測**。実行制御が成果品質・token・所要時間へ与える影響を測る研究基盤。本リポジトリを評価対象 instance としています |
| [the-caption](https://github.com/Kenn-dclxvi/the-caption) | **適用**。実運用しているポートフォリオ評価システム（本リポジトリ） |

---

## 🛠️ Technology Stack

* **Core**: Python 3.11+, Playwright (Automation), Pandas (Analysis)
* **Intelligence**: claude-sonnet-4-6 (Primary), Google Gemini (Failover), DeepSeek (Configured, Inactive)
* **Infrastructure**: Docker (Containerization), Twin-Tower Architecture (Local Sync)
* **Output**: Responsive HTML Email (Jinja2), iCloud Drive Sync
* **Data Acquisition**:
  - **UniversalIngester**: `market_units.csv` + `external_assets.json` から Canonical Ledger を生成
  - **CollectionHistoryUpdater / MarketDataFetcher**: yfinance・GAS プロキシ経由で価格とFXを取得

---

## 📜 Version History

### v4.3 "The Settled Close"
* **V4期間収益率の集計補正**: 全体 WTD/MTD/YTD は、個別収益率を現在評価額ではなく期間開始時点相当額で加重平均します。値上がり後の資産を過大加重する偏りを除くための概算指標であり、厳密なTWRRや入出金追跡は導入しません。新規生成分だけへ適用し、過去データは再生成しません。米国市場日付の仕様変更は含みません。
* **STALE DAY 日付注記**: `pricing_status=STALE` の DAY % に `source_date` 月日注記を表示し、古い価格の誤認を防止しました。
* **Alpha Vantage 補完**: US_STOCK で yfinance の expected-date Close が欠落した場合に、任意の `ALPHA_VANTAGE_API_KEY` で Alpha Vantage 日足 Close を補完します。
* **終値確定ガード**: JP株/US株/コモディティ/FX は市場クローズ確認後のみ `PRICED` とし、取引時間中の速報値は `STALE` に留めます。
* **JP 観測ラグ補正**: US株/コモディティの MTD/YTD 基準日に JP 観測ラグ補正を適用し、期間パフォーマンスのズレを解消しました。
* **US_STOCK DAY 詳細行**: 静的外部資産を除く US_STOCK に、USD 評価額と USD/JPY キャプションを DAY 詳細行として追加しました。

### v4.2 "Temporal Integrity"
* **V4.2 リファクタリング**: v4日次の取得・鮮度判定・再取得ロジックを整理し、アセットクラス別の価格基準日ルールをコードと仕様で統一しました。
* **FX鮮度ガード**: USD建て資産・コモディティの評価で FX 基準日を鮮度判定に組み込み、為替の遅延を `STALE` として扱うようにしました。

### v4.1 "Collection-Primary"
* **主従反転**: Collection 側マスターを正規入力に昇格し、証券会社サイトのスクレイピングを監査層へ降格しました（公開版では実装を含みません）。
* **ShadowLedger**: 全資産を `ShadowAssetRecord` のフラットなリストに統合し、`total_value_jpy` を資産合計から検証します。
* **V4 Daily Engine**: `src/app/entrypoints/v4_daily_main.py` と `src/app/v4_engine.py` により、Universal Ingester → V4 Curator → Monolithic Render → Dispatch を実行します。
* **V4 Monolithic Renderer**: `src/app/renderer/templates/v4_monolithic.html` により、Safe Ratio / Exposure / Iron Bank / Total Net Assets (YTD / MTD / WTD + DAY) を含む5フェーズの単一HTMLメールを生成します。

### v3.4 "Signal Clarity"
* **TWRR（時間加重収益率）計算エンジン**: WTD/MTD/YTD の算出方式をアンカー方式から TWRR 幾何連結方式に完全移行しました。期中の入出金による評価額の跳ねを排除し、純粋な市場変動のみを反映した期間パフォーマンスを算出します（`LedgerManager.__calc_twrr`）。
* **インメモリキャッシュ（`__get_ledger_data`）**: 元帳 JSON の反復ディスク読み込みを防止するキャッシュ機構を導入しました。1 インスタンスあたり各日付の JSON は最大 1 回のみ読み込まれ、`rebuild_all` 時の I/O 爆発を根絶します。
* **デッドコード完全削除**: アンカー方式のために存在していた `__get_period_anchor_val` / `__scan_anchor_value` / `__get_asset_period_anchor` / `__scan_asset_value` の4メソッドを完全削除し、コードベースを簡素化しました（-125行）。

### v3.2 "The Vigilant Signal"
* **VIX Market Psychology Vector**: VIX（恐怖指数）を第4の市場心理ベクトルとして Context Engine に統合しました。「市場の恐怖」が因果推論に直接組み込まれ、ボラティリティ文脈を正確にキャプチャします。
* **Chronicle Rewriter**: `scripts/dev/rebuild_knowledge.py` を新設し、過去の Knowledge Base を手動で再構築・修正する運用ツールを提供します。過去レポートへの遡及補正が可能になりました。
* **LLM Trace Log**: `logs/llm_trace.log` に LLM への全プロンプト・全レスポンスを完全記録します。AI の推論根拠を事後監査できる透明性基盤を確立しました。
* **Sign Consistency Guard**: `shield_evaluation` のハルシネーション封殺のため、符号整合性チェックをプロンプトに組み込みました。AI が矛盾した正負符号を出力する構造的問題を根絶します。
* **Prompt Design 仕様書 (`docs/reference/prompts.md`)**: CONTEXT・CHRONICLE プロンプトの設計規定を体系化した公式ドキュメントを新設しました。

### v3.1 "Sovereign Intelligence"
* **Ledger Sovereign Model**: 旧来のCSV依存から脱却し、当日Ledger JSONを唯一の正典とする自律計算アーキテクチャを確立しました。外部不整合を自律計算で吸収します。
* **日次/月次処理の完全分離**: 日次エンジンと月次エンジン（`src/app/entrypoints/monthly_main.py`）を完全に分割し、オーケストレーションの指揮系統を純化しました。
* **コンテキストの再利用 (`-u` オプション)**: AIによる鑑定結果や月次総括のキャッシュ（永続化ファイル）を再利用し、APIコストを消費せずにレポートを再送する機能を追加しました。
* **COLLECTION ドメイン統合**: 証券会社側の主権元帳から完全隔離された独立ドメインとして、外部ファンド（投資信託）の基準価額レポートを配信する経路を新設しました。GAS プロキシ経由の CSV 取得、ローカル履歴管理、および Slate Symphony デザインに準拠したレポート生成を提供します。

### v3.0 "The Chronicle" (2026-02-22)
日々の因果推論に加えて、知識の蓄積からパラダイムシフトを読み解く「月次総括」機能を実装しました。
* **Monthly Chronicle**: 蓄積された `knowledge_bank.md` の Insight を基に、月間の構造的変化を総括するレポートを自律生成します。
* **アーキテクチャの拡張**: `src/app/entrypoints/monthly_main.py` および `monthly_engine.py` を新設し、日次処理と月次処理の指揮系統を完全に分離しました。

### v2.5 "The Capsule Guard" (2026-02-20)
UI/UXの堅牢性を極限まで高め、長大な銘柄名や未知のデータ流入によるレイアウト崩壊を完全に封殺しました。
* **The Truncation & Metric Capsule Guard**: 銘柄名の1行省略強制（`text-overflow: ellipsis`）と、指標ペア（例: `YTD +1.0%`）の不可分なカプセル化（`nowrap`）を適用し、絶対的な空間の美学を死守。
* **Logic as a Prompt の進化**: 長大な銘柄名の略称化ロジックを手動辞書から排除し、AI（LLM）への推論指示として完全に委譲。メンテナンスフリーな命名システムを確立。

### v2.4 "Holiday-Aware Causality" (2026-02-19)
因果推論エンジン（Causal Engine）の論理的精度を向上させました。
* **休場日・為替単独変動の認知**: 米国市場の休場日を自律的に検知し、「変動の主因は為替のみ」という文脈をAIに強制注入。存在しない日付の株価変動に言及する誤った因果推論（ハルシネーション）を構造的に根絶。

### v2.3 "The Curator's Awakening" (2026-02-11)
AI プロバイダを **Claude (Anthropic)** に移行し、レポート品質と運用安定性を大幅に向上させました。
* **🚀 Claude API 統合**: Google Gemini の無料枠（20リクエスト/日）では開発と本番を両立できず枠枯渇が頻発していた問題を解決。claude-sonnet-4-6 を Primary、Google を Secondary（フェイルオーバー用）として運用。
* **📈 品質向上**: レート制限が **20リクエスト/日 → 50リクエスト/分（2500倍）** に改善。論理的で禁止ワード違反のない高品質なレポートを安定生成。
* **💰 コスト**: 月額 約 $0.40（缶コーヒー1本以下）
* **🧹 Legacy モード完全削除**: v2.2 で廃止された Legacy モード関連のデッドコードを完全削除し、コードベースを簡素化。
* **ブラウザ管理と外部サイト操作を、独立した3層構造に完全分割しました**（ADR-0001。公開版では実装を含みません）。

### v2.2 "The Sovereign Hardening" (2026-02-09)
信頼性と運用コスト効率を極限まで高めるため、コアアーキテクチャの全面的な「硬化」を行いました。
* **指揮系統の純化**: オーケストレーター（Engine）から複雑な条件分岐を排除し、実行判断は `GuardRail` へ、配信制御は `DispatchController` へ完全に委譲しました。
* **Model-View 分離の徹底**: INDEXレポート表示用の「アセットクラス集計」責任を View 層（ViewModel）へ完全に移譲しました。
* **AI脱却によるトークン節約**: 米国市場の休場日判定を AI プロンプトから内部の高速算術ロジックへ完全移行しました。
* **異常系の分離**: API制限や検閲違反などの「想定される運用上の制限（Operational Limit）」と、予期せぬ「システムクラッシュ（System Crash）」の処理ルートを明確に分離しました。

---
