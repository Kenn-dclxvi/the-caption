# Prompt Design

## 1. Overview

CONTEXTレポート（日次）とCHRONICLEレポート（月次）のプロンプト設計の単一参照点。プロンプトテンプレートの正本は `src/config/prompts.py`。本ドキュメントは設計意図・変数仕様・バリデーション機構を文書化する。

- 対象: `src/config/prompts.py` / `src/domain/curator.py` / `src/domain/monthly_curator.py`
- v4.2 入力: `src/app/v4_engine.py` が `ShadowLedger` を `ShadowLedgerAdapter` で既存 `Ledger` 互換モデルへ変換し、`MarketCurator` へ渡す。
- レガシー非対象: `collection_main` の単独 COLLECTION レポート。v4日次では COLLECTION 資産も Canonical Ledger の一部としてプロンプト入力に含まれる。

---

## 2. CONTEXT Prompt Design（日次レポート）

v4.2 では `MarketCurator` のプロンプト契約は維持しつつ、入力元を旧主系 Ledger から Collection-Primary Canonical Ledger へ切り替える。`Portfolio Audit` は日次 CONTEXT から廃止し、月次 CHRONICLE で投資方針の監査軸として扱う。これは `Shield Evaluation` の防壁評価とは別責務であり、コア方針・現金比率・3〜5年停滞耐性のみを扱う。

### 2.1 入力変数マップ

テンプレート `CURATOR_EXHIBITION_REPORT` に注入される変数一覧。

| 変数 | 供給元 | 内容 |
| :--- | :--- | :--- |
| `{jp_date}` | `_get_context_dates()` | 日本市場の基準日 (YYYY-MM-DD) |
| `{us_date}` | `_get_context_dates()["us_full"]` | 直近 NYSE 取引日（`trading_date`）。AIの市場データ参照日。 |
| `{us_market_context}` | MarketCurator + MarketDataFetcher | 休場状態の文脈ノート + `S&P500: X% \| NASDAQ100: X% \| SOX: X% \| 米10年債: X% \| USD/JPY: X% \| VIX: X.XX (±X.XX)` 形式の実市場データ |
| `{theme}` | `__determine_exhibition_theme()` | 騰落率に基づくテーマコード |
| `{angle}` | `EXHIBITION_THEMES` | テーマに対応する分析視点 |
| `{total_diff_pct}` | `SummaryViewModel` | 当日の総資産騰落率 |
| `{safe_ratio}` | `SummaryViewModel` | 安全資産比率 |
| `{total_return}` | `SummaryViewModel` | 通算損益 |
| `{gallery_text}` | `__generate_exhibition_report()` | 個別資産の一覧。フォーマット: `[ID: {asset_id}] {name} \| Share: X.X% \| 単日騰落: X.XX%`（WTD/MTD/YTD除外） |
| `{sys_tech_pct}` | `__compute_actual_evidence()` | ハイテク/グロース資産の加重平均騰落率（システム計算値）。資金移動ノイズ排除済み。保有なしの場合は `"保有なし (N/A)"`、存在する場合は `"+X.XX%"` 形式。 |
| `{sys_metal_pct}` | `__compute_actual_evidence()` | コモディティ（金属）資産の加重平均騰落率（システム計算値）。資金移動ノイズ排除済み。保有なしの場合は `"保有なし (N/A)"`、存在する場合は `"+X.XX%"` 形式。 |

### 2.2 テーマ選択ロジック

v4日次では `ShadowLedgerAdapter` が `ShadowAssetRecord` を既存 `Position` 互換へ変換してから `SummaryViewModel` / `PositionViewModel` を構築するため、プロンプト側は旧 Ledger と同じ入力変数名で動作する。これによりプロンプト契約を変更せず、データ正典だけを差し替える。

`__determine_exhibition_theme(diff_pct)` が `EXHIBITION_THEMES` から `(theme, angle)` を選択する。

| コード | theme名 | 閾値 (diff_pct) | angle（分析視点） |
| :--- | :--- | :--- | :--- |
| CRASH | The Seed | < -2.0% | 大幅な価格調整。下落を主導した要因（金利・決算・需給）の特定と、バリュエーションへの影響。 |
| BEAR | The Shelter | -2.0% 〜 -0.5% | 下落局面。為替や分散効果が防御要因（Buffer）として機能したか、あるいは市場と連動したかの構造分析。 |
| FLAT | The Rotation | -0.5% 〜 +0.5% | 表面的な総額は静止しているが、水面下でセクター循環が起きている動的平衡。 |
| BULL | The Progress | ≥ +0.5% | 能書きを排し、淡々と事実を称える。上昇を牽引したセクターと為替寄与の確認。 |

### 2.3 市場コンテキスト注入

`_get_context_dates()` が `TimelineController.get_us_market_context()` の結果を使用し、`{us_market_context}` へ注入するテキストを構築する（→ `logic.md §5` 参照）。さらに `MarketDataFetcher.fetch_market_context()` が取得した実市場データ文字列を同変数に追記する。

**注入テキストの分岐**:

| 条件 | テンプレート | 制約事項 |
| :--- | :--- | :--- |
| `is_holiday = False`（通常取引日） | `US_MARKET_CONTEXT_NORMAL` | `[ステータス: 通常取引日] 参照日付: {cal_label}` |
| `is_holiday = True`（米国市場休場日） | `US_MARKET_CONTEXT_HOLIDAY` | `[ステータス: 米国市場休場日]`。価格変動の主因を **為替（USD/JPY）のみ** に限定。`{cal_label}` の米国市場変動のハルシネーション禁止。原資産センチメントは `{trading_label}` 参照。 |

**設計意図**: 休場日にAIが存在しない市場データに基づく誤った因果推論を生成することを構造的に排除する。

**現行実装との境界**: 上表は AI への文章生成制約である。台帳計算では米国株・コモディティだけでなく FX も直近 NYSE 実取引日 `trading_date` に固定し、`DAY` は純粋な FX 寄与を含めない。このため、NYSE 休場中に後続の FX 履歴が存在しても、休場日用プロンプトが示す「FX のみの変化」を台帳数値が表現するとは限らない。これは [ADR-0005](../adr/ADR-0005-target-date-us-market-date.md) で受容した既知の不整合であり、現時点ではプロンプト本文と計算式を変更しない。

### 2.4 ギャラリーアセンブリ

`__generate_exhibition_report()` 内でポジションを集約し `gallery_text` を構築する。

- **集約ルール**: 同名ポジションを `asset_id` 単位で合算
- **フィルタ**: `share_pct < 0.1%` の資産を除外（ノイズ排除）
- **フォーマット**: `[ID: {asset_id}] {name} | Share: X.X% | 単日騰落: X.XX%`（WTD/MTD/YTD除外）
- **ID不変契約**: `[ID: ...]` プレフィックスはAIの `asset_id` 参照キー。AIはこの値をそのまま `featured_assets[].asset_id` に返す。一切の改変・省略・推測を禁ずる。
- **Flat Injection Boundary (アーキテクチャ上の割り切り)**: 現在、`Share: 0.1%` 以上の全資産をフラットにプロンプトへ注入している。一般的には微小資産がコンテキストを汚染しトークン爆発を招くリスクがあるが、本システムは「個人の投資計画に基づきポートフォリオの銘柄数（N）は将来もスケールせず固定的に推移する」という強固な前提（Boundary）に立脚している。そのため、上位N件抽出等のプレフィルタリング層は**過剰設計（Over-engineering）として意図的に排除**している。

### 2.5 出力JSONスキーマ

AIは以下のJSON構造を厳格に遵守する。

```json
{
  "display_context": {
    "state": "QUIET | NORMAL | WATCH | STRESS | BREAK",
    "primary": "日次メールに表示する主因ラベル",
    "policy": "日次メールに表示する方針状態",
    "shield": "日次メールに表示する防壁状態"
  },
  "archive_context": {
    "causal_vector": "TECH_DRIVEN | YIELD_PRESSURE | YEN_IMPACT | ROTATION | FLAT | UNKNOWN",
    "market_regime": "CALM | WATCHFUL | RISK_OFF | UNKNOWN",
    "fx_effect": "YEN_WEAKNESS | YEN_STRENGTH | MINOR | UNKNOWN",
    "vix_band": "CALM | ELEVATED | HIGH | UNKNOWN",
    "monthly_tags": ["TECH_CONCENTRATION", "LOW_VIX"],
    "short_note": "月次再蒸留用の短い因果メモ"
  },
  "state_classification": {
    "label": "QUIET | NORMAL | WATCH | STRESS | BREAK",
    "summary": "今日の状態を観測分類として説明する80文字以内の短文",
    "primary_force": "Share × Diff の影響度を踏まえた主要因。静的資産を市場要因に含めない",
    "action_posture": "行動なし | 追加判断は保留 | 新規リスクを抑制 | 方針を再確認"
  },
  "theme_title": "テーマを表現する20文字以内の日本語タイトル",
  "statement_headline": "ベクトル解析の主因（Primary Force）を断言する30文字以内の短評",
  "statement_body": "金利・価格・為替・VIX・合力を150〜250文字で構造的に解説。主要因1つ・副因最大2つ・結論1つに圧縮し、数値引用は最大4個まで",
  "featured_assets": [
    { "asset_id": "ギャラリーテキストの [ID: ...] 値をそのまま使用", "caption": "事実＋要因の体言止め（50〜100文字程度）" }
  ],
  "insight": "6指標相関から導き出される補強セクター（米日株式限定）を150〜250文字でスカウティング。6指標は分析に使い本文で全列挙しない。補強候補は最大2カテゴリ。貴金属・REIT言及禁止。数値捏造禁止。体言止め。",
  "shield_evaluation": "コモディティ（金・銀・プラチナ）のヘッジ機能（逆相関の成否）を最大80文字で評価",
  "portfolio_audit": {
    "core_thesis": "STAY_COURSE | WATCH | THESIS_REVIEW",
    "cash_buffer": "EFFECTIVE | ADEQUATE | THIN | UNKNOWN",
    "stagnation_readiness": "HIGH | MEDIUM | LOW | UNKNOWN",
    "summary": "安全資産比率・コア方針・3〜5年停滞耐性を120〜180文字で評価"
  },
  "causality_vector": "TECH_DRIVEN | YIELD_PRESSURE | YEN_IMPACT | ROTATION | FLAT",
  "shield_status": "ACTIVE | CORRELATED | NEUTRAL"
}
```

**フィールド定義**:

| フィールド | 型 | 制約 | 内容 |
| :--- | :--- | :--- | :--- |
| `display_context` | object | optional | 日次メール表示専用の縮約フィールド。長文を出さず、状態・主因・方針・防壁のみを計器盤として表示する。未提供時は ViewModel が補完する。 |
| `archive_context` | object | optional | 月次再蒸留専用の保存フィールド。日次メールで非表示にした因果ベクトル、市場レジーム、為替影響、VIX帯、月次タグ、短い因果メモを保持する。 |
| `state_classification` | object | optional | V4 Monolithic の冒頭に表示する観測分類。毎日同じ安心文ではなく、`QUIET / NORMAL / WATCH / STRESS / BREAK` で温度を示す。未提供時は ViewModel が `total_diff_pct`、Safe Ratio、pricing_status、`Share × Diff` から補完する。 |
| `theme_title` | string | 最大20文字 | テーマコードを反映した日本語タイトル。英語禁止。 |
| `statement_headline` | string | 最大30文字 | 最大変動要因の統合。体言止め or「〜な一日でした。」 |
| `statement_body` | string | 150〜250文字 | 丁寧語。金利・価格・為替・VIX・合力を統合解説。250文字上限を最優先し、全指標を個別説明せず、主要因1つ・副因最大2つ・結論1つへ圧縮。数値引用は最大4個。 |
| `featured_assets` | array | 2〜3件 | 変動上位資産。`asset_id` は `[ID: ...]` の値をそのまま使用。 |
| `insight` | string | 150〜250文字 | ポートフォリオ・スカウティング。6指標（S&P500/NASDAQ100/SOX/米10年債/USD/JPY/VIX）の相関構造からポートフォリオ外の補強セクター（米日株式限定）を特定。ただし6指標は分析に使い、本文では全列挙しない。補強候補は最大2カテゴリ。貴金属・REIT言及禁止。外部セクターの数値捏造禁止。体言止め。 |
| `shield_evaluation` | string | 最大80文字 | コモディティのヘッジ機能評価。SIGN LOCK必須（→ Rule 5参照）。 |
| `portfolio_audit` | object | optional | v3.5 追加。投資方針の監査素材。日次 CONTEXT の表示契約では使わず、月次 CHRONICLE の監査コンテキストとして扱う。`core_thesis` / `cash_buffer` / `stagnation_readiness` / `summary` を持つ。コモディティのヘッジ評価は禁止し、`shield_evaluation` と役割を分離する。 |
| `causality_vector` | enum | 5値 | TECH_DRIVEN / YIELD_PRESSURE / YEN_IMPACT / ROTATION / FLAT |
| `shield_status` | enum | 3値 | ACTIVE / CORRELATED / NEUTRAL |

### 2.6 生成ルール 10原則

`GENERATION RULES (CRITICAL)` としてプロンプトに埋め込まれる。

| # | 原則 | 設計意図 |
| :--- | :--- | :--- |
| 1 | **ファクトによる裏付け（Narrative with Evidence）** | `statement_body` / `insight` に `us_market_context` の具体的数値をカッコ書きで引用。推測ではなく証拠に基づく分析を強制。 |
| 2 | **Share基準スケール感の厳守** | 微小Shareの資産が大Shareの損益を「補填/相殺した」という数学的不正確表現を排除。面積比を尊重した記述を強制。 |
| 3 | **主要変動要因（ドライバー）の明示** | 選択した `causality_vector` を `statement_body` の論理展開の主軸として反映させる。 |
| 4 | **VIXの厳格な解釈** | VIX < 20: リスクオン / 20〜30: 警戒域 / > 30: リスクオフ。提供数値のみに基づきセンチメントを判定。事前知識による補完禁止。VIXデータが存在しない場合、センチメントに関する一切の推測を禁ずる。 |
| 5 | **方向性の厳格な整合（Sign Consistency — ABSOLUTE）** | テキスト内の騰落方向と提供数値の符号（+/−）を厳密に一致させる。特に `shield_evaluation` は、[ポートフォリオ指標]で提供された「ハイテク/グロース加重平均騰落率」および「コモディティ（金属）加重平均騰落率」の符号を唯一の事実根拠として参照し、テキストの方向性と必ず整合させること。 |
| 6 | **スカウティング・スコープの厳守と思考停止ワードの全面排除** | `insight` の推論は `causality_vector` / VIX 数値を根拠とし方向性を厳密に整合させること（SIGN LOCK 拡張）。また `CURATOR_BANNED_WORDS` の検閲を `statement_body` に限らず全出力フィールド（theme_title / statement_headline / insight / featured_assets.caption / shield_evaluation）に拡大適用し、`portfolio_audit` は月次 CHRONICLE 側で別途検証する（→ §4.2参照）。 |
| 7 | **方針監査と防壁評価の分離** | `portfolio_audit` は月次 CHRONICLE の監査素材として扱い、コア方針・現金比率・停滞耐性に限定する。コモディティ（金・銀・プラチナ）の評価は `shield_evaluation` のみに閉じる。 |
| 8 | **Enumバリデーション・フィードバック機構** | `causality_vector` / `shield_status` は日次 CONTEXT、`portfolio_audit` 配下は月次 CHRONICLE で有効値でない場合、`[VALIDATION_FEEDBACK]` セクションをプロンプト末尾に注入して修正を指示（→ §2.8参照）。 |

| 9 | **状態分類の非オオカミ少年化** | `state_classification.summary` は「大丈夫」の定型反復にしない。`QUIET / NORMAL` は短く、`WATCH / STRESS / BREAK` では原因・影響・確認姿勢を濃くする。 |
| 10 | **表示と保存の分離** | `display_context` は日次メール用に最小化し、`archive_context` は月次集計用に保持する。日次表示を削っても月次再蒸留の情報を削らない。 |

**Impact Hierarchy Logic**: Score = |Share(%) × Diff(%)| が最大の資産を「主因」として特定する。

### 2.7 マーケットデータフェッチ仕様

`MarketDataFetcher` (`src/infra/market_data.py`, Rev.2) が yfinance を使用して直近2営業日分（14日ウィンドウ + `dropna` + `tail(2)`）を取得し、前日比を計算する。

| ティッカー | 表示名 | 変化量の単位 |
| :--- | :--- | :--- |
| `^GSPC` | S&P500 | % |
| `^NDX` | NASDAQ100 | % |
| `^SOX` | SOX | % |
| `^TNX` | 米10年債 | pt（絶対値差） |
| `JPY=X` | USD/JPY | % |
| `^VIX` | VIX（恐怖指数） | pt（絶対値差） |

- VIXは出力フォーマット末尾に `VIX: {現在値:.2f} ({前日比:+.2f})` として付加される（生成ルール Rule 4 の閾値判定に使用）
- 取得失敗・データ不足時は `"(Market data unavailable)"` にフォールバック
- スタンドアロン確認: `python -m src.app.entrypoints.v4_daily_main --test-market`

### 2.8 AI Evidence Validation（サーキットブレーカー）

AI出力の Enum 型整合をシステム側で自律検証し、必要に応じて再生成を要求するサーキットブレーカー機構（`src/domain/curator.py`）。

**バリデーション対象フィールド**:

| フィールド | 検証内容 |
| :--- | :--- |
| `causality_vector` | `_VALID_CAUSALITY_VECTORS` Enum との一致確認 |
| `shield_status` | `_VALID_SHIELD_STATUSES` Enum との一致確認 |
| `portfolio_audit.core_thesis` | `_VALID_CORE_THESES` Enum との一致確認（月次 CHRONICLE） |
| `portfolio_audit.cash_buffer` | `_VALID_CASH_BUFFERS` Enum との一致確認（月次 CHRONICLE） |
| `portfolio_audit.stagnation_readiness` | `_VALID_STAGNATION_READINESS` Enum との一致確認（月次 CHRONICLE） |

> **設計意図**: `sys_tech_pct` / `sys_metal_pct` はシステム側で計算・注入するため、LLM 出力値との数値誤差検証（旧 `_EVIDENCE_TOLERANCE_PCT` ±3%）は廃止済み。バリデーションは純粋な型整合（Enum 一致）のみ実施する。

**リトライ戦略**:

- 最大 `_MAX_VALIDATION_RETRIES`（3）回まで再生成を試行
- Enum 不一致時はプロンプト末尾に `[VALIDATION_FEEDBACK]` セクションを注入し、AIに正しい Enum 値での再出力を指示
- 3回到達時も Enum 不一致が残る場合はCONTEXT生成をスキップする

**`_ledger_data` の埋め込み**:

- 検証完了後の `result` dict に `result["_ledger_data"] = id_data_map`（`asset_id → {name, share_pct, diff_pct, wtd}`）を付与
- `report_context.py` がこれを参照し、AI出力の `asset_id` キーで名称・統計を引き戻して表示する（IDベース不変契約）

---

## 3. CHRONICLE Prompt Design（月次レポート）

### 3.1 入力変数マップ

V4本流（`PROMPT_CHRONICLE_SYSTEM_V4` / `MonthlyCurator.generate_v4_chronicle()`）の入力一覧。

| 変数 | 供給元 | 内容 |
| :--- | :--- | :--- |
| `{year_month}` | `MonthlyEngine` | 対象月 (YYYY-MM) |
| `daily_metrics_summary` | `DailyMetricsRepository.load_month()` → `MonthlyCurator.generate_v4_chronicle()` | 対象月の `daily_metrics_YYYYMMDD.json` を圧縮した月次AIの主入力。15件未満の場合は既存月次Chronicleへフォールバック |
| `market_snapshot_summary` | `MarketSnapshotRepository.load_month()` → `MonthlyCurator.generate_v4_chronicle()` | 対象月の `market_snapshot_YYYYMMDD.json` を圧縮した市場観測入力。米国市場日付、休場、`market_summary` 原文、構造化した主要指数、米10年債、VIX、USD/JPY等を扱い、欠損・解析不能値は推測で補完しない |
| `{insight_stream}` | `KnowledgeManager.extract_monthly_insights()` | 対象月の日次Insightを時系列連結した補助テキスト |
| `daily_context_summary` | `MonthlyCurator.generate_v4_chronicle()` | 既存Knowledge Bankがある場合の補助構造ログ |

レガシー経路（`MONTHLY_CHRONICLE_REPORT` / `daily_metrics` 15件未満フォールバック）に注入される変数一覧。

| 変数 | 供給元 | 内容 |
| :--- | :--- | :--- |
| `{year_month}` | `MonthlyEngine` | 対象月 (YYYY-MM) |
| `{insight_stream}` | `KnowledgeManager.extract_monthly_insights()` | 対象月の日次Insightを時系列連結した補助テキスト |
| `{safe_ratio}` | `SummaryViewModel` | 前月末最終営業日時点の安全資産比率 |

### 3.2 Insight Stream アセンブリ

`MonthlyCurator.generate_v4_chronicle()` は `daily_metrics_summary` と `market_snapshot_summary` を主入力とし、`knowledge_bank.md` から抽出した日次Insightは補助入力として連結する。

- **抽出元**: `data/knowledge_bank.md`（`KnowledgeManager.extract_monthly_insights(year_month)` で対象月分のみ抽出）
- V4 では `daily_metrics_YYYYMMDD.json` の総資産推移、`MARKET_UNITS` / `ABSOLUTE_AMOUNT` 分離、欠損、top movers と、`market_snapshot_YYYYMMDD.json` の市場観測サマリを優先する。`market_snapshot_summary.daily_market_summaries[].market_summary` は原文を保持し、同じ日次要素の `market_observations` に `indices` / `us_10y_yield` / `usd_jpy` / `vix` の構造化観測値を併置する。`State / Archive / Archive Note` 行は存在する場合だけ補助構造ログとして集計する。
- **フォーマット**:

```
[YYYY-MM-DD]
{content}

[YYYY-MM-DD]
{content}

...
```

- **設計意図**: 日付ラベルを明示することで、AIが時系列的な構造変化を月次スケールで読み取れるようにする。

### 3.3 Generation Threshold（The Void）

対象月のInsight抽出件数が **10件未満** の場合、AI生成を物理的にスキップし空 dict `{}` を返す。

- **条件**: `len(insights) < 10`
- **UI表示**: `*Curator is silent due to insufficient records.*`
- **設計意図**: データの信憑性と歴史的文脈が不足する状態でAIに総括を強制させると、ハルシネーションや根拠なき断言が発生するリスクがある。最低10日分のInsightがあって初めて1ヶ月の「構造的変化」が語れるという品質基準。

### 3.4 出力JSONスキーマ（V4本流・マルチセクション）

V4本流の月次Chronicle（`OUTPUT_SCHEMA_CHRONICLE_V4` / `PROMPT_CHRONICLE_SYSTEM_V4`、`src/config/prompts.py`）は、JSON Schema形の返却フォーマット契約を `<output_schema>` としてUser payloadへ埋め込む。外部APIの構造化出力強制は前提にせず、`MonthlyCurator.generate_v4_chronicle()` は `LlmTransporter.request_intelligence(prompt)` からの受信後にトップレベル、必須フィールド、基本型を検証してから `MonthlyRenderer.render_v4()` が `v4_chronicle.html` にレンダリングする。

```json
{
  "chronicle": {
    "title": "この一ヶ月を一言で表す歴史的表題（短い見出し）",
    "monthly_summary": "①今月の結論",
    "market_causality": "①結論を支える最大の市場要因（monthly_summaryと合計≤150字）",
    "phase_analysis": ["②明確な局面変化がある場合だけ列挙"],
    "asset_contribution": ["②資産寄与（phase_analysisと合わせて最大3項目・合計≤250字）"],
    "portfolio_audit": "③方針判定",
    "next_month_watch": ["③翌月の注視点（最大2点。portfolio_auditと合計≤200字）"]
  },
  "meta": {
    "dominant_regime": "月間の主要レジーム",
    "primary_causality": "月間主因",
    "fx_impact": "為替影響",
    "risk_temperature": "月間リスク温度",
    "data_quality": "欠損・休場・未確定データの扱い（監査ログ専用。メールには表示しない）"
  }
}
```

**フィールド定義**:

| フィールド | 型 | 制約 | 内容 |
| :--- | :--- | :--- | :--- |
| `chronicle.title` | string | 短い見出し（600字カウント枠外） | この一ヶ月を一言で表す歴史的表題。体言止め可。 |
| `chronicle.monthly_summary` | string | ①合計≤150字 | ①今月の結論。月初月末・総資産推移・主要な変化を結論先行で示す。 |
| `chronicle.market_causality` | string | ①合計≤150字 | ①結論を支える最大の市場要因。MARKET_UNITSに限定し、`monthly_summary`と同じ事実を繰り返さない。 |
| `chronicle.phase_analysis` | string[] | ②合計≤250字 | ②資産への影響。明確な月内転換がある場合だけ、その転換点と根拠を列挙する。明確な転換がなければ空配列とする。 |
| `chronicle.asset_contribution` | string[] | ②合計≤250字 | ②資産への影響。寄与上位または足を引っ張った資産に絞る。`phase_analysis`と合わせて最大3項目。 |
| `chronicle.portfolio_audit` | string | ③合計≤200字 | ③方針と注視点。「方針維持」または「再確認が必要」の判定を先に置き、集中度・比率変化・方針の妥当性を示す。 |
| `chronicle.next_month_watch` | string[] | 最大2点・③合計≤200字 | ③方針と注視点。対象月データから継続観測すべき事実ベースの論点に限定し、未来予測や不確実な示唆を書かない。 |
| `meta.data_quality` | string | メール非表示 | TSMC fx_rate乖離・HOLIDAY_GUARD・daily_insights部分ログ等の監査ログ専用項目。値は生成・保持するが、メールのヘッダおよび本文には表示しない。 |

表示は `Monthly Conclusion`、`Portfolio Impact`、`Policy & Watch` の3ブロックに統合する。既存キャッシュの表示も、影響項目は最大3件、資産クラス推移は変動額上位3件、翌月の注視点は最大2件に制限する。

**実行時検証**:

- `OUTPUT_SCHEMA_CHRONICLE_V4` はJSON Schema形で `<output_schema>` に埋め込み、`PROMPT_CHRONICLE_SYSTEM_V4` とUser payloadを結合した単一promptとして `LlmTransporter.request_intelligence(prompt)` へ委譲する。
- 外部API側の structured outputs 強制は前提にせず、`MonthlyCurator.generate_v4_chronicle()` が受信後に `chronicle` / `meta` の存在、必須フィールド、`string` / `array<string>` の基本型を検証する。
- 検証失敗時は `V4ChronicleSchemaViolation`、禁止語検出時は `V4ChronicleBannedWordsViolation` とし、月次V4の不完全な本文をレンダリングしない。どちらも `RuntimeError` 派生だが、`MonthlyEngine.run()` は alert code を `V4_SCHEMA_VIOLATION_MONTHLY` / `V4_BANNED_WORD_MONTHLY` として一般 `OPERATIONAL_LIMIT_MONTHLY` から分離する。

#### 字数制約（titleを除く3ブロック合計 ≤600字）

「結論+リスク重視」の簡潔版を採用し、短縮分への加筆（余白の埋め戻し）はしない。titleは600字カウントの枠外とし、3ブロックの可読日本語テキスト合計を **600字以内** に収める。各ブロックの配分は以下のとおり。

| セクション | フィールド | 配分上限 |
| :--- | :--- | :--- |
| タイトル | `title` | 短い見出し（600字カウント枠外） |
| ①今月の結論 | `monthly_summary` + `market_causality` | ≤150字 |
| ②資産への影響 | `asset_contribution` + `phase_analysis`（最大3項目） | ≤250字 |
| ③方針と注視点 | `portfolio_audit` + `next_month_watch`（最大2点） | ≤200字 |

- **重複排除**: 同一の事実（例: +8.05% / テック主導 / ABSOLUTE_AMOUNT不変 / VIX17台）を複数セクションで繰り返さない。
- **金額丸め可**: 桁の冗長な羅列を避け、可読性を優先する。
- **局面変化の条件表示**: `phase_analysis` は明確な月内転換がある場合だけ生成・表示する。
- **資産クラス上限**: メールに表示する資産クラス推移は変動額の絶対値が大きい上位3件に限定する。
- **data_qualityメール除外**: `meta.data_quality` は監査ログ専用とし、メールのヘッダおよび本文には表示しない。
- **埋め戻し禁止**: 短縮して余白が生じても加筆しない。

#### 600字カウント定義

字数はtitleを除く3ブロックの **可読日本語テキスト** に対して、以下の規則で数える。

- 対象: ①`monthly_summary` + `market_causality` / ②`asset_contribution` + `phase_analysis` / ③`portfolio_audit` + `next_month_watch`。
- `title` は短い見出しであり、600字カウントの **枠外**（対象外）。
- KPI（Safe Ratioや資産クラス推移等のメタ数値）とフッタは **対象外**。
- `MonthlyRenderer.__html_text` / `__render_v4_list` で生成されるHTMLからタグ（`<br>` 等）を **除去** したテキストを対象とする。
- 改行・空白、および `__render_v4_list` の区切り文字 `" / "` は **数えない**。
- `meta.data_quality` 等のメタ項目は本文ではないため対象外。

> 字数はプロンプト/スキーマの指示で担保し、`tests/unit/test_v4_monthly_curator.py` の字数検証テストで上記カウント定義に従って検証する。コード側での自動切り詰め・実行時の自動再生成・送信中止は行わない。

#### レガシー3フィールド版（旧スキーマ）

旧レガシー経路（`MONTHLY_CHRONICLE_REPORT`、`daily_metrics` 15件未満フォールバック）では、以下の3フィールド・350字制約スキーマを用いる。V4本流とは別系統であり、本節の600字制約は適用されない。

```json
{
  "theme_title": "この1ヶ月を象徴する25文字以内の日本語タイトル",
  "chronicle_headline": "月間の最大の構造的変化を断言する40文字以内の短評",
  "chronicle_body": "①蒸留（日次Insightから補強候補セクター/スタイルを抽出）→②戦略的序列（どの外部アセットがボラティリティ緩和に最も貢献したかを断定）の2段階で350文字以内で記述",
}
```

| フィールド | 型 | 制約 | 内容 |
| :--- | :--- | :--- | :--- |
| `theme_title` | string | 最大25文字 | 1ヶ月を象徴する日本語タイトル。事実に基づく知的な表現。 |
| `chronicle_headline` | string | 最大40文字 | 月間の最大の構造的変化またはパラダイム移行を断言。体言止め。 |
| `chronicle_body` | string | 最大350文字 | 丁寧語。①蒸留（日次Insightから補強候補セクター/スタイルを抽出）②戦略的序列（外部アセットのボラティリティ緩和への貢献を断定）の2段階構成。 |

### 3.5 生成ルール（月次固有）

| ルール | 内容 |
| :--- | :--- |
| **日次ノイズ排除** | 1日の騰落という些末なノイズを無視し、1ヶ月を通した「金利・価格・為替」の合力の推移を俯瞰する。 |
| **未来予測禁止** | 未来への予測・不確実な示唆を一切禁ずる。 |
| **ハルシネーション禁止** | `insight_stream` のテキスト内に明示的に存在しない歴史的事件・外部ニュース・過去の市場ショックの補完を完全に禁ずる。 |
| **思考停止ワードの排除** | 共通 `CURATOR_BANNED_WORDS`（8語）に、V4月次専用の `MONTHLY_CHRONICLE_BANNED_WORDS` では `検討` を加えた9語を `chronicle` 本文フィールドへ適用（→ §4.2参照）。 |

---

## 4. 共通メカニズム

### 4.1 JSONパース方式

LLMレスポンスからのJSON抽出は以下の優先順位で処理する（`src/domain/curator.py` / `src/domain/monthly_curator.py`）。

| 優先順位 | 方式 | 条件 |
| :--- | :--- | :--- |
| 1 | `[JSON_START]...[JSON_END]` タグ抽出 | タグが存在する場合 |
| 2 | コードブロック除去（` ```json ``` `） | タグなし・コードブロック形式の場合 |
| 3 | rawレスポンスをそのままパース | 上記いずれにも該当しない場合 |

- パース前に制御文字（`[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]`）を正規表現で除去
- `JSONDecodeError` 発生時はフォールバックレスポンスを採用

### 4.2 禁止語強制（CURATOR_BANNED_WORDS / MONTHLY_CHRONICLE_BANNED_WORDS）

共通 `CURATOR_BANNED_WORDS` は以下の8語を「思考停止ワード（分析の放棄）」として定義し、AI出力のパース後・返却前に強制検査する。

| # | 禁止語 | 禁止の理由 |
| :--- | :--- | :--- |
| 1 | 静観 | 分析の放棄 |
| 2 | 様子見 | 分析の放棄 |
| 3 | 一旦 | 判断の先送り |
| 4 | と思われる | 断言の回避 |
| 5 | 一喜一憂 | 無内容な定型句 |
| 6 | 見守り | 分析の放棄 |
| 7 | ホールド | 判断の先送り |
| 8 | 距離を置く | 分析の放棄 |

V4月次専用 `MONTHLY_CHRONICLE_BANNED_WORDS` は、共通8語に `検討` を加えた9語とする。これは `MonthlyCurator.generate_v4_chronicle()` のV4検証だけで使い、日次CONTEXT、週次Chronicle、レガシー月次Chronicleの共通禁止語契約には波及させない。

- 検出時（CONTEXT / CHRONICLE legacy）: 共通禁止語契約の `RuntimeError` として扱い、呼び出し元の例外ハンドラでフォールバック処理
- 検出時（CHRONICLE V4 / `MONTHLY_CHRONICLE_BANNED_WORDS`）: `V4ChronicleBannedWordsViolation` を発生させ、`MonthlyEngine.run()` の alert code は `V4_BANNED_WORD_MONTHLY` として一般 `OPERATIONAL_LIMIT_MONTHLY` から分離する
- 適用範囲（CONTEXT）: `theme_title` / `statement_headline` / `statement_body` / `insight` / `featured_assets[].caption` / `shield_evaluation` の全フィールド
- 適用範囲（CHRONICLE legacy）: `theme_title` / `chronicle_headline` / `chronicle_body`
- 適用範囲（CHRONICLE V4 / `MONTHLY_CHRONICLE_BANNED_WORDS`）: `chronicle.title` / `chronicle.monthly_summary` / `chronicle.market_causality` / `chronicle.phase_analysis[]` / `chronicle.asset_contribution[]` / `chronicle.portfolio_audit` / `chronicle.next_month_watch[]`

### 4.3 LLMプロバイダ委譲

プロンプト実行は `LlmTransporter.request_intelligence(prompt: str) -> str` への単一委譲で行う。

- リトライ戦略・バックオフ・プロバイダ優先順位の詳細は `system.md §4` を参照
- トレースログ: `logs/llm_trace.log`（LLM transporter の運用ログ + フルプロンプト/レスポンス記録）

---

## 5. 関連ドキュメント

| ドキュメント | 参照内容 |
| :--- | :--- |
| `logic.md §5` | `TimelineController.get_us_market_context()` API仕様（休場判定の実装詳細） |
| `system.md §4` | LLMプロバイダ設定・リトライ戦略・バックオフ詳細 |
| `src/config/prompts.py` | 全プロンプトテンプレートの正本（`CURATOR_EXHIBITION_REPORT` / `MONTHLY_CHRONICLE_REPORT` / `CURATOR_BANNED_WORDS` / `MONTHLY_CHRONICLE_BANNED_WORDS` / `EXHIBITION_THEMES`） |

---
