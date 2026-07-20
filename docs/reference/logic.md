# Part 3 (Logic): Logic Reference

## 1. V4 Canonical Ledger Guard (Collection-Primary)

v4.3 の日次処理は、Broker CSV の鮮度ではなく `ShadowLedger` の評価可能性を基準に配信可否を判定する。

| 判定対象 | ルール | 結果 |
| :--- | :--- | :--- |
| `ShadowLedger.assets` | 1件以上存在すること | 0件なら配信不可 |
| `ShadowLedger.total_value_jpy` | 0より大きいこと | 0以下なら配信不可 |
| `pricing_status` | `PRICED` / `STATIC` は正常 | 配信可 |
| `pricing_status` | `MISSING` は警告扱い | `allow_missing=True` の場合は縮退配信可 |

この判定は `GuardRail.should_dispatch_shadow_ledger()` が担当する。v4.3 の CompletionLock は旧日次と同じロックファイルを使うが、Broker の `VERIFIED/STAGNANT` 判定には依存しない。

## 2. Freshness Guard (Legacy Broker)
最新のスナップショットにおいて、主要アセットクラスのデータが全て更新されているかを厳格に判定する。

1. **個別変動検知 (Individual State Validation)**:
   - 対象クラス: MUTUAL_FUNDS (投資信託) および US_STOCK (米国株式)
   - 判定基準: 各アセットクラスの日本円建て評価額（JPY）が、個別に前日の台帳（Ledger）データから **10円以上** 変動していること。
   - ※従来は両者の「合算値」で判定していたが、一方の更新遅延を見逃すリスク（片肺状態）を排除するため個別判定に移行した。

2. **片肺状態の降格 (One-Lung State Degradation)**:
   - 上記の対象クラスのうち、保有額が0より大きいにもかかわらず、変動幅が10円未満（不感帯）のアセットが一つでも存在する場合、データ全体のステータスを STAGNANT（停滞/未確定）に降格させる。

3. **ドメイン知識の統合 (Sovereign Validation)**:
   - 米国市場の休場日（祝日等）であっても、証券会社は日々の為替レート（USD/JPY）の変動を適用して円建て評価額を更新する。
   - この特性を利用し、外部の市場カレンダー（TimelineController等）に依存せず、純粋に「JPY評価額が10円以上動いたか」という内部状態（State）のみでデータの鮮度を自己証明するアーキテクチャとしている。

## 3. System Flow & CompletionLock
執行エンジンはデータの状態のみに基づく「ステートレス・フロー」を採用する。

**V4 Daily Execution Flow (Collection-Primary 日次パイプライン)**

| フェーズ | 状態チェック | アクション |
| :--- | :--- | :--- |
| **1. Guard** | 本日の CompletionLock が存在するか？ | **YES**: 即時終了。`-F` または `-t` では通過<br>**NO**: 次へ進む |
| **2. Universal Ingester** | `market_units.csv` と `external_assets.json` を読めるか？ | 市場連動資産と絶対額資産を `ShadowLedger` へ統合し、`data/v4_shadow_ledger.json` へ保存 |
| **3. ShadowLedger Gate** | 合計額が正で、資産行が存在するか？ | **YES**: 次へ進む<br>**NO**: 送信不可 |
| **4. Daily Inputs** | `ShadowLedger` から月次入力を作れるか？ | `daily_metrics_YYYYMMDD.json` と `market_snapshot_YYYYMMDD.json` を保存 |
| **5. Daily Context** | `-t` / `-u` のどれか？ | `-t` は固定コンテキスト、`-u` は既存キャッシュ、通常は確定論的コンテキスト（日次LLM呼び出しなし） |
| **6. Render** | `V4MonolithicViewModel` を構築できるか？ | `ShadowLedger` と `SummaryViewModel` / `PositionViewModel` から単一HTMLメールを生成 |
| **7. Dispatch** | Format Test か？ / `MISSING` または `STALE` があるか？ | `-t` は送信しない。通常は `MailSender` で送信。`MISSING`/`STALE` がある場合は `CAPTION [YYYY-MM-DD]○`（暫定）として送信し、ロックは更新しない。全件確定時は `CAPTION [YYYY-MM-DD]` で送信し、ロックを更新する。 |

V4 の日次コンテキストは常に確定論的に生成する。LLM 呼び出しは日次フローから廃止された（`#267`）。`-u` フラグで既存キャッシュを再利用する場合を除き、毎回 `build_deterministic_daily_context()` が呼ばれる。

V4 Monolithic UI は v3 Fortress / Collection の主要メトリクスを復元する。防衛ブロックでは `Safe Ratio` の後に `Exposure / Iron Bank / Total Return` を置き、その下に `Total Net Assets` と `YTD / MTD / WTD` を1行、`DAY` を別行で表示する。Unified Ledger の各資産行は `YTD / MTD / WTD` を1行、`DAY` を別行で表示し、Exposure 側の補助指標は `UNITS / PRICE` のみを表示する。

### V4 Total WTD/MTD/YTD Aggregation

v4 の個別資産 `WTD` / `MTD` / `YTD` は、`UniversalIngester` が市場履歴の期間基準価格と現在価格から算出する。全体値は `ShadowLedgerAdapter._weighted_period_pct()` が、個別収益率を **期間開始時点相当額** で加重平均する。

資産 `i` の現在評価額を `V_i`、個別期間収益率を小数表記で `r_i` とすると、期間開始時点相当額 `B_i` と全体収益率 `R` は次の式になる。

```text
B_i = V_i / (1 + r_i)
R   = Σ(B_i × r_i) / ΣB_i
```

この変更の目的は、値上がり後に大きくなった現在評価額で同じ値上がり率を再び重く評価し、値下がり後に小さくなった現在評価額で同じ値下がり率を軽く評価する、現在評価額加重の上方偏りを除くことである。導入判断時のローカル保存データ（`target_date=2026-06-10`）では、メール表示上の YTD が旧式 `+19.58%`、本式 `+17.55%` となり、丸め前の式だけで `2.025` ポイントの差が生じた。一方、同じ比較日の WTD 差は `0.004` ポイント、MTD 差は `0.039` ポイントであり、主な改善対象は長期間に資産間の騰落差が広がる場合である。

この全体値は、現在の保有数量を期間開始時にも保有していたとみなす **概算の市場収益率** であり、厳密な時間加重収益率（TWRR）ではない。期間中の入出金、売買時点、過去の保有数量は復元しない。`Portfolio Basis` は累積取得原価と `Total Return` の正典として維持し、本計算には使用しない。`ABSOLUTE_AMOUNT` と現金カテゴリは集計対象外とする。個別期間収益率が `---` の市場資産は、従来どおり分子への寄与を0とし、現在評価額を分母へ残す。

本式は変更後に新しく生成するレポートへ前方適用する。送信済みメール、過去の台帳、`daily_metrics_YYYYMMDD.json` は再生成しない。過去の保有数量スナップショットが全日分揃っていないため、一括再生成は正確性を高めず、現在の保有数量を過去へ誤適用する可能性がある。

この集計式の変更は、米国株の `trading_date` / `source_date`、市場終了判定、FX 基準日を変更しない。米国市場日付は独立した仕様・実装対象として扱う。

`Portfolio Audit` は日次フローから廃止した。`generate_v4_insight()` の日次表示契約では `portfolio_audit` を表示対象に含めず、方針監査は月次フローで扱う。

`DAILY PORTFOLIO APPRAISAL` は常時表示ではない。`total_return_jpy < 0` を満たし、かつ前回表示日から 7 日以上経過した場合のみ表示する。表示判定は `V4PortfolioEngine.__should_show_appraisal()` が行い、状態は `data/runtime/v4_appraisal_state.json` の `last_displayed_date` に記録する。これは表示制御であり、日次AI実行条件とは分離する。

### 3.1 V4 Ledger Finalization

v4 のメール表示は `ShadowLedger` をそのまま描画するのではなく、**確定処理済みの `ShadowLedger`** を入力にする。

**確定順序**

```text
ShadowLedger生成
  -> Provisional判定
  -> Finalization Gate
  -> Finalized ShadowLedger
  -> Render / Dispatch
```

**確定ロジックの原則**

- `DAY` は履歴 CSV の直近2点差分を直接使わない。
- `DAY` は確定処理済み台帳内で freeze した差分を使う。
- 休日の国内資産は `DAY +0 / +0.00%` として freeze する。
- `ABSOLUTE_AMOUNT` は常に `DAY +0 / +0.00%` とする。
- renderer は履歴 CSV や市場履歴を再計算しない。

**市場別の確定方針**

| 資産種別 | 確定方針 | 実装状態 |
| :--- | :--- | :--- |
| `JP` | 日本休場日は `DAY 0` で freeze。営業日は直近営業日差分を採用。 | **実装済み** |
| `STATIC` | 常に `DAY 0`。 | **実装済み** |
| `US` | US 取引日を基準に freeze。日本休場日でも US 取引日なら `DAY` を維持する。 | **対象外**（現行スコープ外） |
| `FX` / `COMMODITIES` | 各市場の取引可否を基準に freeze。市場休場なら `DAY 0`。 | **対象外**（現行スコープ外） |

現時点の確定範囲は、JP 休場日における国内資産の `DAY` freeze と `ABSOLUTE_AMOUNT` の 0 確定までとする。
`WTD` / `MTD` / `YTD` の追加確定や専用 Mail Dataset は後続の拡張対象であり、renderer は引き続き確定処理済み `ShadowLedger` を参照する。

**Legacy Daily Execution Flow (旧Broker主系パイプライン)**
| フェーズ | 状態チェック | アクション |
| :--- | :--- | :--- |
| **1. Guard** | 本日の CompletionLock が存在するか？ |**YES**: 即時終了 (TERMINATE)<br>**NO**: 次へ進む |
| **2. Local Check** | ローカルに当日のデータが存在するか？ |**YES**: 中身を鑑定 (Step 3へ)<br>**NO**: 取得へ (Step 4へ) |
| **3. Freshness** | ローカルデータは VERIFIED か？ |**VERIFIED**: 取得スキップ、配信へ<br>**STAGNANT**: **再取得 (Force Fetch)** を決断 |

**Holiday Guard (日次 GuardRail の休日判定)**

GuardRail は `target_date` が `is_holiday()` = `True` の場合、以下のロジックで処理する。

| 条件 | アクション |
| :--- | :--- |
| `LAST_ACCESS_FILE` が本日付と一致 | 即時終了 (TERMINATE) |
| 本日初回アクセス | `LAST_ACCESS_FILE` に本日付を書き込み、処理を続行 |

`TimelineController.get_target_date()` (Rev. 11) は非休日を自動選択するため、通常フローではこのパスに到達しない。`manual_date` で休日を明示指定した場合のみ発動する。

**Monthly Execution Flow (月次パイプライン)**
| フェーズ | 状態チェック | アクション |
| :--- | :--- | :--- |
| **1. Lock Check** | 対象月 (YYYY-MM) の `last_sent_monthly.txt` が存在するか？ | **YES**: 即時終了 (TERMINATE)<br>**NO**: 次へ進む |
| **2. Monthly Dataset** | 対象月の `daily_metrics` が15件以上あるか？ | 15件以上なら確定論的な月次入力として優先。15件未満なら既存月次Chronicleへフォールバック |
| **3. Chronicle AI** | 月次入力を構築できるか？ | `daily_metrics` が15件以上ある場合は `MonthlyCurator.generate_v4_chronicle()`、未満なら `generate_monthly_chronicle()` で総括を生成 |

月次フローは前月末台帳の `VERIFIED` を前提としない。`MonthlyGuardRail.should_proceed()`（Rev. 3）はロックファイル（`last_sent_monthly.txt`）のみで送信可否を判定し、台帳未確定による持ち越しゲートは廃止された。

**V4 Monthly Chronicle (ShadowLedger 月次総括)**

`MonthlyCurator.generate_v4_chronicle()` は v4.3 の月次ロジックであり、`daily_metrics` が15件以上存在する月に使用する。対象月の `ShadowLedger` 履歴を日付順に読み、先頭日と末尾日の資産クラス別評価額を `source + asset_class` 単位で比較する。加えて、`daily_metrics_YYYYMMDD.json` と `market_snapshot_YYYYMMDD.json` を集約して、月間総資産推移、寄与上位、欠損日、転換点候補、市場観測サマリ原文、主要指数・米10年債・USD/JPY・VIXの構造化観測値を月次AIへ渡す。

月次 CHRONICLE の `render_v4` はメール先頭に `Safe Ratio` セクションを表示する（描画は `MonthlyRenderer.__render_v4_safe_ratio()`）。旧 `Shield Review`（金・銀・プラチナの防壁評価）セクションは月次v4から削除された（#281）。

本文は `Monthly Conclusion`（今月の結論）、`Portfolio Impact`（資産への影響）、`Policy & Watch`（方針と注視点）の3ブロックで表示する。本文はtitleを除いて合計600字以内とする。既存キャッシュを再利用する場合も、影響項目は最大3件、資産クラス推移は変動額上位3件、翌月の注視点は最大2件に制限する。

| 入力 | 取り扱い |
| :--- | :--- |
| `MARKET_UNITS` | 市場環境に由来する動的資産の月次潮流として扱う |
| `ABSOLUTE_AMOUNT` | 現金・外部資産の静的事実として扱い、市場因果とは切り離す |
| Daily Metrics | `data/current/daily_metrics_YYYYMMDD.json` を月次AIの主入力として扱う |
| Market Snapshot | `data/current/market_snapshot_YYYYMMDD.json` を月次AIの主入力として扱う。米国市場日付、休場、`market_summary` 原文、主要指数、米10年債、VIX、USD/JPY等の構造化観測値を渡し、欠損・解析不能値は推測で補完しない |
| Daily Insights | `KnowledgeManager.extract_monthly_insights()` から対象月の鑑定記録を束ねる。補助入力であり必須ではない |

LLM には `PROMPT_CHRONICLE_SYSTEM_V4` と、`<output_schema>` に埋め込んだJSON Schema形の `OUTPUT_SCHEMA_CHRONICLE_V4` を含む単一promptを `LlmTransporter.request_intelligence()` で渡す。戻り値は `{"chronicle": ..., "meta": ...}` の形で V4 月次テンプレートへ接続できる。`MonthlyCurator.generate_v4_chronicle()` は受信後にトップレベル、必須フィールド、基本型を検証し、不一致の場合は月次V4本文として採用しない。schema violation と banned words violation は V4 専用例外として `MonthlyEngine.run()` に伝搬し、alert code を `V4_SCHEMA_VIOLATION_MONTHLY` / `V4_BANNED_WORD_MONTHLY` に分離する。
月次の User データも `<daily_metrics_summary>`, `<market_snapshot_summary>`, `<daily_insights>`, `<monthly_trend_data>`, `<output_schema>` に分離し、`ABSOLUTE_AMOUNT` の増減は家計・運用の構造変化として扱う。
方針監査（`portfolio_audit`）は `Policy & Watch` ブロックで表示・解釈する。

**COLLECTION Execution Flow (Legacy Standalone COLLECTIONパイプライン)**

v4.3 では `data/collection/market_units.csv` は Canonical Ledger の SSOT A として昇格した。以下の `collection_main` フローは、単独の COLLECTION レポートを配信するレガシー/補助経路として維持する。

Freshness Guard・Broker CSVダウンロード・CompletionLock（Broker）とは完全に独立したフローを持つ。
祝日判定・市場カレンダーへの依存を持たず、実行可否はクーロンスケジューラ側で制御する。ファンドごとのデータ更新タイミングのバラつきを吸収するため、「指定日（target_date）」を絶対の基準とするプログレッシブ配信（段階的送信）ロジックを採用する。

| フェーズ | 状態チェック | アクション |
| :--- | :--- | :--- |
| **1. Guard** | `last_sent_collection.txt` に本日付と更新件数（`YYYY-MM-DD,COUNT`）が記録されているか？ | **YES (全件完了済み)**: 即時終了 (TERMINATE)<br>**NO**: 次へ進む |
| **2. Fund Config** | `data/collection/market_units.csv` が存在するか？ | **NO**: アラート送信 → 終了<br>**YES**: 次へ進む |
| **3. Fetch (opt)** | `-f` フラグが有効か？ | **YES**: 各 `csv_url` へ直接 HTTP GET → 履歴へ追記<br>**NO**: スキップ |
| **4. Metrics** | 各ファンドの履歴ファイルから指定日と一致する最新レコードの有無を判定し、更新件数（`updated_count`）を計数する | **0件**: 更新未達として静かに終了 (SILENCE)<br>**1件以上**: 次へ進む |
| **5. Dispatch** | 更新件数と過去の送信状態を比較 | **NEW DAY**: 初回検知として仮送信 (Provisional) `[date]○`<br>**COMPLETION**: 全件確定として送信 `[date]`<br>**SILENCE**: 進捗なしとしてスキップ |

`data/collection/market_units.csv` は COLLECTION フローの設定源であり、手編集または `./run.sh collection-web-prd` / `./run.sh collection-web-dev` から更新できる。いずれの更新経路でも、実行時の参照先は同一ファイルである。

> Curator プロンプト設計の詳細（出力スキーマ・生成ルール・バリデーション機構）は [prompts.md](./prompts.md) を参照。

## 4. Capital Flow Noise Suppression（資金移動ノイズ排除ガード）

`LedgerManager.enrich_assets()` が WTD/MTD/YTD を付与する前段階で実行される元本変動検知ロジック。

**目的**: 資金の追加投入・引き出しによって `acquisition_price`（取得元本）が変動した日は、当日の `prev_day_diff_pct`（前日比騰落率）を **市場変動ではなく資金移動が原因** とみなし、加重平均の分子への寄与をゼロに抑制する。ただし **買い増し（既存ポジションへの追加）** は元本増分を除去した真の市場差分を復元する。

**前処理 (Lookup Dict 構築)**:

前日元帳 (`__get_ledger_data(prev_date)`) を一度ロードし、以下の2つの lookup dict を並列構築する。

| dict | キー | 値 |
| :--- | :--- | :--- |
| `prev_acq_map` | `asset_id` | 前日 `acquisition_price`（元本） |
| `prev_val_map` | `asset_id` | 前日 `value_jpy`（評価額） |

**判定フロー**:

`abs(curr_acq - prev_acq) >= 100`（100円以上の元本乖離）を検知した場合に以下の3分岐を適用する。閾値通過直後に `diff_jpy = acquisition_price − prev_acq` を計算し、ログへ元本変動額を明記する（符号付き整数）。

| ケース | 条件 | 処理 | ログ |
| :--- | :--- | :--- | :--- |
| **A: 買い増し** | `curr_acq > prev_acq` かつ `prev_val > 0` | `real_diff_pct = (value_diff − principal_diff) / prev_val × 100` を復元。`prev_day_diff_jpy` も同時更新 | `[Guard] Buy flow detected … (Acq Diff: X,XXX JPY). Restored diff: +X.XX%` (INFO) |
| **B: 新規購入** | `curr_acq > prev_acq` かつ `prev_val == 0` | `prev_day_diff_pct` を `0.0` にミュート | `[Guard] Initial buy detected … (Acq Diff: X,XXX JPY). Suppressing to 0.0%` (WARNING) |
| **C: 一部売却** | `curr_acq < prev_acq` | `prev_day_diff_pct` を `0.0` にミュート | `[Guard] Sell flow detected … (Acq Diff: -X,XXX JPY). Suppressing to 0.0%` (WARNING) |

**閾値選定根拠（Dead-zone Rationale）**:

証券会社側のシステムは、売買を行っていないにもかかわらず `acquisition_price`（取得元本）が数円〜数十円単位で前日比変動する「端数調整」を日常的に実施する。

- **観測実績（2026-02-27）**: FANG+インデックス `-17円`、全世界半導体株インデックス `-44円`
- **設計判断**: 100円を不感帯上限として設定することで、これらの端数調整を誤って「資金移動イベント」として検知し、`prev_day_diff_pct` を `0.0%` に誤ミュートする偽陽性を構造的に排除する。
- **受容リスク（Known Limitation）**: 100円単位の真の積立購入（ワンコイン投資等）を初回設定した場合、その取得元本変動が不感帯内に収まり、ガードロジックがスルーする可能性がある。当該運用を開始する際は、実態に合わせて本閾値を再評価すること。

**保守的評価の担保**:

- ケース B・C でミュートされたアセットは、加重平均の **分母（total_value）には含まれる** が、**分子（変動量）には寄与しない**。
- ケース A は元本増分を控除した純粋な市場変動率を復元するため、加重平均の歪みを排除する。
- 非対象条件: 前日元帳が存在しない場合、または前日に同一 `asset_id` のレコードが存在しない場合は `prev_day_diff_pct` を変更しない。

**処理順序**:

`LedgerManager.__process_date()` は `enrich_assets()` → `enrich_summary()` の順で実行する。前者のノイズ排除（ミュート／復元）が完了した状態で後者が動作することを保証している。

**ポートフォリオ全体騰落率への連鎖 (total_diff_jpy / total_diff_pct)**:

`enrich_summary()` は総額の単純な差分ではなく、CASH カテゴリを除く全資産の `prev_day_diff_jpy` を積み上げた `pure_market_diff_jpy` を `total_diff_jpy` として採用する。

| フィールド | 計算式 |
| :--- | :--- |
| `total_diff_jpy` | `sum(a.prev_day_diff_jpy for a in assets if a.category != "CASH")` |
| `total_diff_pct` | `pure_market_diff_jpy / prev_fortress_total × 100`（`prev_fortress_total == 0` の場合は `0.0`） |

これにより、入金・新規購入などの資金移動イベントが「市場の利益」として誤検知され、AI の因果推論にハルシネーションを引き起こす問題を構造的に排除する。

**Curator への連鎖効果**:

- `MarketCurator.__compute_actual_evidence()` はこのミュート済みの `prev_day_diff_pct` を参照して `actual_tech_pct` / `actual_metal_pct` を計算する。
- 結果として LLM プロンプトへの `sys_tech_pct` / `sys_metal_pct` 注入値が資金移動ノイズを含まないシステム計算値となる。

## 5. Legacy WTD/MTD/YTD — 時間加重収益率（TWRR）計算

この節は legacy `LedgerManager` 経路だけを定義する。v4 `ShadowLedgerAdapter` の全体集計は「V4 Total WTD/MTD/YTD Aggregation」を正とする。

`LedgerManager` は期間パフォーマンス指標（WTD/MTD/YTD）の算出に **時間加重収益率（Time-Weighted Rate of Return: TWRR）** を採用する。資金移動（入出金）による評価額の跳ねを排除し、純粋な市場変動の幾何連結を保証する。

### 4.1 計算メソッド: `__calc_twrr`（O(1) 漸化式）

**シグネチャ**:

```python
def __calc_twrr(self, current_date_str: str, mode: str, daily_pct: float, prev_twrr_str: str) -> str:
```

**パラメータ**:

| 引数 | 型 | 内容 |
| :--- | :--- | :--- |
| `current_date_str` | str | 対象日（YYYY-MM-DD）。境界判定に使用 |
| `mode` | `"WEEK"` / `"MONTH"` / `"YEAR"` | 集計期間 |
| `daily_pct` | float | 当日の日次収益率（%）。呼び出し元が算出して注入する |
| `prev_twrr_str` | str | 前営業日の TWRR 文字列（`+X.XX%` または `---`）。前日 Ledger JSON から読み出す |

**出力**: `+X.XX%` 形式の符号付き文字列（符号・小数点以下2桁を保証）。

### 4.2 アルゴリズム（O(1) 漸化式）

旧実装（Rev. 52 以前）は期首から現在日まで全過去 Ledger JSON を走査する O(n) スキャンであった。Rev. 53 以降は **前日 TWRR を状態として引き継ぐ O(1) 漸化式** に置換されている。

1. `__is_first_ledger_of_period(current_date_str, mode)` で境界判定を行う。
   - その期間の最初に保存された ledger → `prev_twrr_float = 0.0`（期間リセット）
   - それ以外 → `prev_twrr_float = SystemUtils.parse_pct_str(prev_twrr_str)`（前日値を継承）
2. 漸化式: `result = ((1 + prev_twrr_float / 100) × (1 + daily_pct / 100) - 1) × 100`
3. `f"{result:+.2f}%"` で返す。

WTD / MTD / YTD はすべて同じ考え方で扱う。カレンダー上の固定日ではなく、「その期間で最初に保存された ledger」を起点にする。期間内の最初の ledger が休日や週末の翌営業日にずれ込んでも、その最初の保存日がリセット点になる。

> **[重要] WTD 週起点は日本時間 `target_date` を基準に算出する**
>
> `LedgerManager`（TWRR漸化式パス）・`UniversalIngester`（市場履歴CSVパス）のいずれにおいても、WTD の週起点（分母）は **日本時間の `target_date` の ISO week** で決定する。
>
> 米国株・コモディティは、米国市場の金曜引値が **日本時間の月曜朝** に初めてシステムに届く。この「JP月曜に観測される米国金曜終値」は当週の第1観測値（分子側）であり、WTD の起点（分母）ではない。正しい WTD 起点は、前週の JP 営業日（= 米国木曜引値）である。
>
> `UniversalIngester._period_base_value` は `week_origin=target_date`（JP処理日）を受け取り、`JP月曜 − 3日 = JP前週金曜` を排他上限として履歴 CSV から起点値を選出する（`Date < jp_prev_friday`）。これにより米国金曜が起点に混入することを防ぐ。

### 4.3 境界判定メソッド: `__is_period_boundary`

```python
def __is_period_boundary(self, current_date_str: str, mode: str) -> bool:
```

| `mode` | 境界条件 |
| :--- | :--- |
| `"WEEK"` | `その週の最初の保存済み ledger`（ISO week 基準。月曜が休みなら最初の営業日にリセット） |
| `"MONTH"` | `その月の最初の保存済み ledger`（1 日が休日・週末なら次の保存日にリセット） |
| `"YEAR"` | `その年の最初の保存済み ledger`（年初の休みがあれば最初の営業日にリセット） |

境界日は前期間の TWRR 累積を切り捨て、当日の `daily_pct` のみで集計をリスタートする。MTD だけの例外は存在しない。

### 4.4 `daily_pct` の注入元（呼び出し元責務）

`daily_pct` の算出責務は呼び出し元が担う。`__calc_twrr` は `daily_pct` 自体は再計算しないが、週・月・年の境界判定では直前の保存済み ledger を参照して、その期間の最初の保存日かどうかを判断する。

| 呼び出し元 | `daily_pct` の取得元 | `prev_twrr_str` の取得元 |
| :--- | :--- | :--- |
| `enrich_summary` | `ledger.summary.total_diff_pct`（`total_diff_pct` 計算後に呼び出す） | 前日 Ledger JSON の `summary["total_wtd/mtd/ytd"]` |
| `enrich_assets` | `asset.prev_day_diff_pct`（Capital Flow Suppression 適用済み） | 前日 Ledger JSON の `assets[id]["wtd/mtd/ytd"]` |
| `get_aggregated_positions` | CLASS TWRR は `asset.wtd/mtd/ytd` の `value_jpy` 加重平均で算出（`__calc_twrr` 不使用） | — |

### 4.5 インメモリキャッシュ（`__get_ledger_data`）

元帳 JSON の反復ディスク読み込み（I/O 爆発）を防止するため、`LedgerManager` は `__ledger_cache: Dict[str, Optional[Dict]]` を内包する。

```python
def __get_ledger_data(self, date_str: str) -> Optional[Dict]:
    if date_str not in self.__ledger_cache:
        self.__ledger_cache[date_str] = self.__repo.load(date_str)
    return self.__ledger_cache[date_str]
```

- 同一日付の元帳は 1 インスタンス内で 1 回のみ `LedgerRepository.load()` を呼び出す。
- `enrich_assets`・`enrich_summary`・`get_aggregated_positions`・`__scan_weekly_range`・`__check_freshness` の全アクセスが本メソッド経由に統一される。

### 4.6 呼び出しシグネチャ（3 メソッド）

| メソッド | WTD | MTD | YTD |
| :--- | :--- | :--- | :--- |
| `enrich_summary` | `__calc_twrr(date, "WEEK", total_diff_pct, prev_summary["total_wtd"])` | `__calc_twrr(date, "MONTH", total_diff_pct, prev_summary["total_mtd"])` | `__calc_twrr(date, "YEAR", total_diff_pct, prev_summary["total_ytd"])` |
| `enrich_assets` | `__calc_twrr(date, "WEEK", asset.prev_day_diff_pct, prev_twrr["wtd"])` | `__calc_twrr(date, "MONTH", asset.prev_day_diff_pct, prev_twrr["mtd"])` | `__calc_twrr(date, "YEAR", asset.prev_day_diff_pct, prev_twrr["ytd"])` |
| `get_aggregated_positions` | `value_jpy` 加重平均（`__calc_twrr` 不使用） | 同左 | 同左 |

---

## 6. TimelineController: Date Resolution & Holiday-Aware US Market Context

### get_target_date() — 最終取引日の自動決定 (Rev. 11)

`manual_date` 未指定時、前日から後方トラバースし `is_holiday()` が `False` となる最初の日付を返す。

| 実行日 | 起点 (前日) | 結果 |
| :--- | :--- | :--- |
| 日曜 (2026-03-01) | 土曜 (2/28) → **金曜 (2/27)** | 2026-02-27 |
| 月曜 (2026-03-02) | 日曜 (3/1) → 土曜 (2/28) → **金曜 (2/27)** | 2026-02-27 |
| 火曜 (通常日) | 月曜 (非休日) | 月曜の日付 |

`manual_date` 指定時はトラバースを省略し、そのまま返す。

### get_us_market_context() — Holiday-Aware US Market Context (Rev. 6)

**概要**:
src/lib/timeline_controller.py の get_us_market_context() メソッドは、JP基準日に対して米国市場の3つの文脈情報を返す。これにより、AI への因果推論指示の精度を構造的に保証する。

**メソッドシグネチャ**:
```python
def get_us_market_context(self, jp_target_date: str) -> Dict[str, object]:
```

**戻り値の定義**:

| キー | 型 | 内容 |
| :--- | :--- | :--- |
| trading_date | str (YYYY-MM-DD) | 直近の NYSE 実取引日。市場データ参照・AI指示に使用する。 |
| calendar_date | str (YYYY-MM-DD) | JP基準日の暦上の前日。米国カレンダー上の「対象日」。 |
| is_holiday | bool | trading_date != calendar_date の場合 True。NYSE 休場（祝日・週末）を示す。 |

**具体例（2026-02-17 JP基準日・Presidents' Day の場合）**:

| キー | 値 |
| :--- | :--- |
| trading_date | "2026-02-13" |
| calendar_date | "2026-02-16" |
| is_holiday | True |

**設計上の意図**:
以前の determine_us_market_date() は「直近取引日」のみを返していたため、米国市場が休場だった場合に AI が「存在しない市場データ」を参照する誤った因果推論を生む可能性があった。本メソッドはその問題を構造的に解決する。determine_us_market_date() は下位互換のため温存する。

### 日付概念 定義一覧

第三者引き継ぎ向けに、本システムで使用する日付概念を1枚にまとめる。

| 概念 | 定義 | 実装参照 |
| :--- | :--- | :--- |
| `target_date`（JP台帳対象日） | v4日次台帳に記録する日本時間基準の対象日。標準運用では 18:30 JST 以降に「当日」を対象にする。手動指定時は指定日をそのまま対象にする。旧 Broker 主系など legacy 経路の省略時前営業日解決とは分離する。 | `V4Engine.run()` / `UniversalIngester.build_shadow_ledger()` |
| `us_market_date`（US市場取引日） | `target_date - 1日` 以前で直近の NYSE 実取引日。通常は `target_date` の暦上の前日で、米国祝日・週末は前取引日にロールバックされる。標準実行帯の時刻によって再判定しない。 | `get_us_market_context()` の `trading_date` キー |
| `calendar_date`（US暦日） | `target_date` の暦上の前日（US側）。`trading_date` との差異が NYSE 休場の有無を示す。 | `get_us_market_context()` の `calendar_date` キー |
| 取引日と確定判定 | `trading_date` は対象セッションの日付、`source_date` は採用した原資産価格行の日付である。データの取得日時・更新日時とは分離する。必要な価格行と FX 行の期待日到達、および終値確認の結果は `pricing_status` で表す。 | `UniversalIngester._build_market_record()` |
| 米国休場日の扱い | 株価データは前取引日の値を引き継ぐ。AI プロンプトには `is_holiday=True` として注入され、存在しない市場変動へのハルシネーションを構造的に防止する。 | `get_us_market_context()` → `is_holiday` キー |
| 境界時刻（JST） | 標準実行帯は **18:30〜20:00 JST**。最初の実行は 18:30、その後は 18:45 / 19:00 / 19:15 / 19:30 / 20:00 に再実行する。 | `../how-to/index.md §1.2 Routine Schedule` |
| `manual_date` 指定時の注意 | 日本祝日を含む任意の日付を指定可能。v4 は legacy Freshness Guard の `STAGNANT` を使用しない。選択更新後も必要な価格または FX が期待日へ届かなければ `MISSING` / `STALE` の暫定配信とし、CompletionLock を記録しない。 | `V4Engine.run()` / `UniversalIngester.build_shadow_ledger()` |
| **WTD 週起点（JP基準）** | WTD の分母（起点）は `target_date`（JP処理日）の ISO week の月曜から3日前（JP前週金曜）を排他上限として選出した最後の履歴値。米国株・コモディティは米国金曜終値が JP 月曜朝に届くため、その値は起点ではなく当週の第1観測値（分子側）として扱う。`UniversalIngester._period_base_value` に `week_origin=target_date` を渡すことで日本時間基準を強制している。 | `UniversalIngester._period_base_value`（`week_origin` 引数）/ §5 WTD 注記 |

### アセットクラス別 価格基準日定義

システム標準実行帯（18:30〜20:00 JST）における各アセットクラスの「確定済み最新値」を定義する。
`target_date` を JP 処理日、`trading_date` を対応する直近 NYSE 実取引日とする。

| アセットクラス | 市場時間（JST） | 標準実行帯での確定状況 | 使用する yfinance Date | `yf.download` の `end`（exclusive） |
| :--- | :--- | :--- | :--- | :--- |
| **JP株**（`JP_STOCK`） | 9:00〜15:30 | ✅ `target_date` 当日引け確定 | `target_date` | `target_date + 1日` |
| **US株**（`US_STOCK`） | 翌23:30〜6:00 | ✅ `trading_date` 引け確定（当日セッション未開始） | `trading_date`（yfinance の expected date Close 欠落時のみ Alpha Vantage fallback で同日 Close を補完） | `trading_date + 1日` |
| **コモディティ**（`COMMODITIES`） | 翌22:30〜3:30 | ✅ `trading_date` 引け確定（当日セッション未開始） | `trading_date` | `trading_date + 1日` |
| **FX**（`USDJPY` 等） | 24時間（yfinance は 17:00 ET 基準） | ✅ `trading_date` の 17:00 ET 値確定（= 当日 06:00 JST） | `trading_date` | `trading_date + 1日` |
| **投資信託**（`MUTUAL_FUNDS`） | URL 取得（ファンド側管理） | `target_date` の基準価額があれば当日値。未公表なら `target_date` 以前の最新値を `STALE` として採用 | 適用外 | 適用外 |

`UniversalIngester` は台帳再計算時もこの採用上限を守る。ローカル履歴 CSV に `trading_date` より後の US株・コモディティ・FX 行が後から存在していても、その `target_date` の計算では `trading_date` 上限により除外する。

現行の `DAY` は、採用した直近米国セッションの原資産騰落率である。同じ `trading_date` を参照する複数の `target_date` では同じ値を繰り返し得る。FX も `trading_date` に固定し、純粋な FX 変動だけによる評価額差は `DAY` に含めない。米国株価日と FX 日を分離する代替案、確定ブロック境界、観測事例は [ADR-0005](../adr/ADR-0005-target-date-us-market-date.md) を正とする。

`CollectionHistoryUpdater` は yfinance を primary とする。US株（`US_STOCK`）で `trading_date` を expected date として取得した後、valid `Close` 履歴の最新日が `trading_date` より前、または `trading_date` 行に valid `Close` がない場合のみ、`ALPHA_VANTAGE_API_KEY` が設定されていれば Alpha Vantage `TIME_SERIES_DAILY` の `4. close` を optional fallback として同日行へ merge する。API key 未設定/空、Alpha Vantage の HTTP/JSON/API/parse error、または `US_STOCK` 以外では fallback しない。fallback 不成立時は補完せず、後段の鮮度判定で `STALE` になり得る。

> **実装上の注意（yfinance exclusive end）**  
> `yf.download` の `end` パラメータは exclusive（指定日を含まない）。  
> `trading_date` のデータを取得するには `end = trading_date + 1日` を渡す必要がある。  
> `CollectionHistoryUpdater._fetch_market_history` 内で `+1日` の変換を行っている。  
> JP株は `target_date` の当日終値を採用するため、`end = target_date + 1日` を適用する。  
> US株・コモディティ・FX は `trading_date` の確定値を採用するため、`end = trading_date + 1日` を適用する。
> US株のみ、yfinance 取得後に `trading_date` の valid `Close` が欠落している場合は、上記条件で Alpha Vantage `TIME_SERIES_DAILY` fallback による同日 Close 補完を試行する。

## 6. Prompt Injection Guard: サニタイズ & インテグリティ検証ロジック

### 6.1 攻撃対象面（Attack Surface）

| 汚染源 | 流入経路 | 注入先 |
| :--- | :--- | :--- |
| 外部市場データ | `MarketDataFetcher.fetch_market_context()` → `market_data_str` | `us_market_context` → プロンプト文字列 |
| アセット名 | Broker スクレイピング → `ledger.assets[].name` / `asset_vm.name` | `gallery_text` → プロンプト文字列 |

### 6.2 Layer 1: `MarketCurator.__sanitize_external(text)`

呼び出しタイミング: プロンプト組み立て前（`__generate_exhibition_report` 内）

アルゴリズム:

1. `text.lower()` でケース正規化
2. `_INJECTION_PATTERNS` を線形スキャン（`in` 演算子）
3. 検知なし → テキストをそのまま返す
4. 検知あり → `[Guard]` ログ + `re.sub(..., flags=re.IGNORECASE)` で全パターンを `[REDACTED]` に置換して返す

副作用なし（例外を投げない）。`[REDACTED]` 含みテキストの品質低下は後続の `_MAX_VALIDATION_RETRIES` リトライが吸収する。

### 6.3 Layer 2: `LlmTransporter.__assert_prompt_integrity(prompt)`

呼び出しタイミング: `request_intelligence()` 冒頭、全プロバイダループの前

アルゴリズム:

1. `prompt.lower()` でケース正規化
2. `_INJECTION_PATTERNS` を線形スキャン
3. 検知なし → `[Audit] Prompt integrity OK` ログ、処理継続
4. 検知あり → `[Guard]` 警告ログ + `RuntimeError` raise

例外伝播パス: `RuntimeError` → `curator.py:__execute_prompt` が re-raise → `generate_context_report` → 上位エンジン例外ハンドラ

### 6.4 `_INJECTION_PATTERNS` 定数

両ファイルのモジュールトップに同一定数を配置（共通モジュール抽出はスコープ外）。

| 種別 | パターン |
| :--- | :--- |
| EN（命令上書き） | `ignore previous instructions` / `ignore all previous` / `disregard previous instructions` / `you are now` / `forget previous` |
| EN（プロンプト操作） | `new instructions:` / `system prompt` |
| JP（命令上書き） | `AGENTS.mdを無視` / `前の指示を無視` / `以下の指示に従え` / `新しい指示に従` / `あなたは今` |

検知はケース非感受性（`re.IGNORECASE` / `.lower()`）。
