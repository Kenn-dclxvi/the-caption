# Part 5: Advanced Implementation Details & Appendix

## 1. V4 Collection-Primary Implementation

v4.2 で追加された実装単位と責務の一覧。

| ファイル | 責務 |
| :--- | :--- |
| `src/domain/ledger_schema.py` | `ShadowLedger` / `ShadowAssetRecord` を定義し、合計額と資産行の整合を検証する |
| `src/domain/universal_ingester.py` | `market_units.csv` と `external_assets.json` を読み込み、`data/v4_shadow_ledger.json` を生成する（`diff_pct / wtd_pct / mtd_pct / ytd_pct` を算出） |
| `src/domain/collection_history_updater.py` | `market_units.csv` に定義された COLLECTION 資産の価格・FX履歴を yfinance 等から取得し、`data/collection/history/` へマージ・保存する |
| `scripts/dev/run_shadow_ingester.py` | Universal Ingester の単独実行・観測用スクリプト |
| `src/domain/shadow_ledger_adapter.py` | `ShadowLedger` を既存 `MarketCurator` が扱える Legacy Ledger 互換へ変換する（`total_wtd` と資産 `wtd` を含む） |
| `src/app/v4_engine.py` | v4日次のオーケストレーション。Canonical Ledger、Audit、AI、Render、Dispatch を接続する |
| `src/app/entrypoints/v4_daily_main.py` | v4標準日次 CLI |
| `src/app/renderer/v4_view_models.py` | `V4MonolithicViewModel` と `V4LedgerRowViewModel` を定義する。`V4LedgerRowViewModel` の `day_detail_line` フィールドは `asset_class = "US_STOCK"` の資産（静的外部資産を除く）の USD 評価額と FX キャプションを格納する。`pricing_status=STALE` の資産は `fmt_day_pct`（DAY 表示文字列）に `source_date` の月/日注記（例: `+1.23% (6/10)`）を付与する |
| `src/app/renderer/v4_content_renderer.py` | `v4_monolithic.html` をレンダリングするファサード |
| `src/app/renderer/templates/v4_monolithic.html` | Monolithic Scroll テンプレート（Appraisal は条件表示） |

### 1.1 Universal Ingester Calculation Rules

| 入力 | 対象 | 評価額計算 |
| :--- | :--- | :--- |
| `market_units.csv` | 投資信託 (`MUTUAL_FUNDS`) | `基準価額 / 10000 * units` |
| `market_units.csv` | 株式等 | `price * units * fx_rate` |
| `market_units.csv` | コモディティ | `oz建て価格 * fx_rate / 31.1034768 * units` |
| `market_units.csv` | FX helper row | 評価資産としては出力せず、USD建て換算の補助に使う |
| `external_assets.json` | 現金・外部資産 | `amount` をそのまま `current_value_jpy` にする |

`external_assets.json` は対象月 `YYYY-MM` のキーを優先し、存在しない場合は `default` キーへフォールバックする。`items` 配列以外は空配列として扱い、壊れた値は0へ安全化する。

### 1.2 V4 Test Coverage

v4.2 追加範囲は次のユニットテストで観測する。

| テスト | 対象 |
| :--- | :--- |
| `tests/unit/test_universal_ingester.py` | Dual Input SSOT、価格計算、外部資産マージ |
| `tests/unit/test_ledger_schema.py` | `ShadowLedger` の合計検証 |
| `tests/unit/test_shadow_ledger_adapter.py` | Legacy Ledger 互換変換 |
| `tests/unit/test_v4_engine.py` | v4日次オーケストレーション |
| `tests/unit/test_v4_renderer.py` | Monolithic Renderer / ViewModel |

## 2. Data Normalization Rules (データ正規化ルール)

データ取り込み時の文字列処理ルールです。

**Normalization (Sanitization)**
1. **NFKC Normalization**: `unicodedata.normalize('NFKC')` を適用し、全角英数（例: `ｉＦｒｅｅ`）を半角（`iFree`）へ統一します。
2. **Brand Respect**: ただし、カタカナやブランド固有の大文字小文字（CamelCase）は破壊せずに維持します。
3. **Tag Cleaning**: `[NISA]` タグや `(特定)` 等の付帯情報を正規表現で除去し、純粋な銘柄名をキーとして抽出します。

---

## 3. Reporting Implementation (レポート実装詳細)

Fortress Card (Zone 1) を構築するための具体的な HTML/CSS 構造です。
```html
<div style="margin-bottom: 60px;">
    <div style="margin-bottom: 32px;">
        <div style="font-size: 12px; color: #64748b; letter-spacing: 0.15em; margin-bottom: 8px; text-transform: uppercase;">Safe Ratio</div>
        <div style="font-size: 60px; font-weight: 100; color: #1e293b; line-height: 0.9; letter-spacing: -0.04em; margin-left: -2px;">
            52.4<span style="font-size: 24px; font-weight: 200; margin-left: 4px; color: #64748b;">%</span>
        </div>
    </div>

    <div style="margin-bottom: 40px; width: 100%;">
        <div style="width: 100%; height: 12px; background-color: #f1f5f9; overflow: hidden; display: flex;">
            <div style="width: 47.6%; display: flex;">
                <div style="width: 96%; background-color: #64748b;"></div>
                <div style="width: 4%; background-color: #c5a059;"></div> </div>
            <div style="width: 2px; background-color: #ffffff;"></div>
            <div style="width: 52.4%; background-color: #cbd5e1;"></div>
        </div>
    </div>

    <table border="0" cellpadding="0" cellspacing="0" style="width: 100%;">
        <tr>
            <td style="width: 33%; vertical-align: top;">
                <div style="font-size: 11px; color: #94a3b8; letter-spacing: 0.05em; text-transform: uppercase;">Exposure</div>
                <div style="font-size: 20px; color: #1e293b; font-weight: 200; margin-top: 4px;">7.6M</div>
            </td>
            <td style="width: 34%; vertical-align: top; text-align: center;">
                <div style="font-size: 11px; color: #94a3b8; letter-spacing: 0.05em; text-transform: uppercase;">Iron Bank</div>
                <div style="font-size: 20px; color: #1e293b; font-weight: 200; margin-top: 4px;">8.1M</div>
            </td>
            <td style="width: 33%; vertical-align: top; text-align: right;">
                <div style="font-size: 11px; color: #94a3b8; letter-spacing: 0.05em; text-transform: uppercase;">Damper</div>
                <div style="font-size: 20px; color: #1e293b; font-weight: 200; margin-top: 4px;">0.48x</div>
            </td>
        </tr>
    </table>
</div>
```

---

## 4. COLLECTION Acquisition Logic (COLLECTIONデータ取得詳細)

COLLECTION ドメインのデータ取得フローです。ブラウザ自動化を用いず、GAS プロキシ経由のシンプルな HTTP リクエストを採用しています。

### 4.1 Fetch Flow (データ取得フロー)

| ステップ | モジュール | 内容 |
| :--- | :--- | :--- |
| **1. Config 読み込み** | CollectionEngine | `data/collection/market_units.csv` から name/units/csv_url を読み込む |
| **2. Direct Fetch** | CollectionEngine | 各 `fund["csv_url"]` へ `urllib.request.Request`（User-Agent: Mozilla/5.0、timeout: 30秒）で直接 HTTP GET（`-f` フラグ時のみ） |
| **3. CSV パース** | CollectionEngine | UTF-8 → Shift-JIS → CP932 の順でデコードを試行。`基準日`/`基準価額` 列を抽出する |
| **4. 履歴マージ** | CollectionEngine | `data/collection/history/{name}.csv` と連結し、日付重複を除去して保存する |
| **5. 指標計算** | CollectionEngine | 対象日以前の最新行から NAV を取得し、前日差・MTD・YTD を算出する |
| **6. ViewModel 構築** | CollectionEngine | `CollectionPositionViewModel` / `CollectionSummaryViewModel` を構築してレポートへ渡す |

### 4.2 CSV Encoding Strategy

MUFG・大和投資信託等の外部 CSV は Shift-JIS エンコードが多い。`CollectionEngine.__parse_nav_bytes()` は `utf-8 → shift-jis → cp932` の順にデコードを試み、各エンコードに対して `skiprows=[0, 1]` も組み合わせて試行する（CSV 先頭に余剰行がある場合に対応）。最初に成功したものを採用する。

日付フォーマットは `YYYYMMDD`（例: `20180131`）と `YYYY/MM/DD`（例: `2018/07/03`）の両方に対応し、いずれも `pd.to_datetime` でパースされる。

### 4.3 Metrics Calculation

| 指標 | 計算式 |
| :--- | :--- |
| **current_value** | `(NAV / 10000) × units` |
| **diff_pct (DAY)** | `(NAV - prev_NAV) / prev_NAV × 100` |
| **m_pct (MTD)** | `(NAV - 月初前最終NAV) / 月初前最終NAV × 100` |
| **y_pct (YTD)** | `(NAV - 前年末最終NAV) / 前年末最終NAV × 100`（前年末最終NAV = `df[df["基準日"] < 当年1月1日].iloc[-1]`） |

### 4.4 Fund Configuration Schema (market_units.csv スキーマ)

`data/collection/market_units.csv` の列定義。UTF-8 で保存し、`csv.DictReader` で読み込む。

| フィールド | 型 | 内容 | 必須 |
| :--- | :--- | :--- | :--- |
| **name** | str | ファンドの論理名。履歴ファイル名（`history/{name}.csv`）にも使用される | YES |
| **units** | int | 保有口数 | YES |
| **csv_url** | str | ファンド基準価額 CSV の直接 URL（`-f` フラグ時に HTTP GET する対象） | YES |

### 4.5 ViewModel Specifications (View 層定義)

#### CollectionSummaryViewModel

`CollectionEngine` がポートフォリオ全体の集計値から生成し、`CollectionRenderer` へ渡す。

| プロパティ | 型 | 内容 |
| :--- | :--- | :--- |
| `fmt_total_value` | str | 総評価額（カンマ区切り整数） |
| `fmt_total_diff` | str | 当日の総変動額（符号付きカンマ区切り整数） |
| `fmt_total_diff_pct` | str | 当日の総変動率（符号付き、小数点2桁 %） |
| `display_date` | str | レポート基準日（YYYY-MM-DD） |
| `total_diff_color` | str | `#c5a059`（プラス）/ `#64748b`（マイナス・ゼロ） |
| `day_color` | str | `#c5a059`（プラス）/ `#64748b`（マイナス・ゼロ）。COLLECTION の DAY 表示色に使用 |

**総変動率の計算式**: `total_diff_jpy / (total_value - total_diff_jpy) × 100`

#### CollectionPositionViewModel

ファンド 1 件ごとに生成される。

| プロパティ | 型 | 内容 |
| :--- | :--- | :--- |
| `name` | str | ファンド名（market_units.csv の `name`） |
| `fmt_value` | str | 評価額（カンマ区切り整数） |
| `fmt_diff_jpy` | str | 当日変動額（符号付きカンマ区切り整数） |
| `fmt_diff_pct` | str | 当日変動率（符号付き、小数点2桁 %） |
| `fmt_mtd` | str | MTD 変動率（符号付き、小数点2桁 %） |
| `fmt_ytd` | str | YTD 変動率（符号付き、小数点2桁 %） |
| `share_pct` | float | ポートフォリオ全体に占める比率（0〜100）。バーグラフの幅に使用 |
| `diff_color` | str | `#c5a059`（プラス）/ `#1e293b`（マイナス・ゼロ） |
| `day_color` | str | `#c5a059`（プラス）/ `#64748b`（マイナス・ゼロ）。COLLECTION の DAY 表示色に使用 |
| `day_is_positive` | bool | `diff_pct > 0` のとき True。テンプレート内で DAY ラベル色の分岐に使用 |

---

## 5. Historical Archives (歴史的アーカイブ)

初期プロトタイプ（MUFG/GAS連携）の要件です。

***[REQ-P-001] MUFG 基準価額の取得***: 三菱UFJアセットマネジメントの公開情報を参照し、特定のファンドの基準価額を取得すること。

***[REQ-P-002] GAS プロキシ利用***: 直接的なスクレイピング制限を回避するため、GAS URL を介したデータ取得をサポートすること。

***[REQ-P-006] プロト・トリニティ構造***: 後の「三位一体の分離」の原型となる、Config（設定）、Network（基盤）、Logic（計算）、Engine（執行）の分離を試行すること。

***[REQ-P-007] サンドボックス管理***: 本番データと隔離された `data/sandbox` ディレクトリで履歴（market_units.csv）を管理すること。

---

## 6. MarketDataFetcher — 市場データ取得ロジック

`src/infra/market_data.py` の `fetch_market_context(us_date_str)` が yfinance から市場コンテキストを取得する際の処理フロー（Rev. 5）。

### 6.1 Fetch & Normalization Pipeline

| ステップ | 処理 | 目的 |
| :--- | :--- | :--- |
| **1. Download** | `yf.download(tickers, start, end)` で14日分を一括取得 | S&P500 / NASDAQ100 / SOX / TNX / USD/JPY / VIX を同時取得 |
| **2. ffill()** | `raw["Close"].ffill()` | 非取引日（週末・祝日）の NaN を前営業日の終値で穴埋め |
| **3. dropna** | `.dropna(how="all")` | 全列が NaN のパディング行を除去 |
| **4. TZ 正規化** | `tz_convert(None)` → `normalize()` | tzaware インデックスを tz-naive の日付キー（00:00:00）に統一 |
| **5. 重複集約** | `groupby(index).last()` | 同一日付の複数行（FX のみ更新など）を最新行に集約 |
| **6. 未来日カット** | `close[index <= pd.to_datetime(us_date_str)]` | `us_date_str` より未来の先行データ行を強制除去 |

**Step 6 の必要性**: yfinance は為替（JPY=X）の最新足を `us_date_str` の翌日付で返すことがある。`ffill()` がこの翌日行に株価を伝播すると `curr == prev` となり、全銘柄の前日比が `0.00%` になるバグが発生する。ステップ 6 で当日超を強制カットすることで根絶する。

### 6.2 出力フォーマット

```
S&P500: +X.XX% | NASDAQ100: +X.XX% | SOX: +X.XX% | 米10年債: X.XX% (+X.XX) | USD/JPY: XXX.XX (+X.XX%) | VIX: XX.XX (+X.XX)
```

---

## 7. Monthly Chronicle Implementation (月次総括の実装詳細)

v3.0 より導入された、知見の蓄積からパラダイムシフトを読み解く月次総括エンジンの詳細仕様です。

### 7.1 Sequence Diagram: Monthly Execution Pipeline
```mermaid
sequenceDiagram
    participant Cron as Monthly Main
    participant Engine as MonthlyEngine
    participant Guard as MonthlyGuardRail
    participant Repo as LedgerRepository
    participant ChronoRepo as ChronicleRepository
    participant Knowledge as KnowledgeManager
    participant Curator as MonthlyCurator
    participant Notifier as Notifier

    Cron->>Engine: run(target_date, reuse_context)
    Engine->>Guard: should_proceed(target_date)
    
    Guard->>Repo: load(last_biz_day)
    Repo-->>Guard: Ledger (integrity_status)
    
    alt Status != "VERIFIED"
        Guard-->>Engine: False (Lazy Polling)
        Engine->>Engine: Termination
    else Status == "VERIFIED"
        Guard-->>Engine: True
        
        opt reuse_context == True
            Engine->>ChronoRepo: exists(year_month)
            ChronoRepo-->>Engine: True
            Engine->>ChronoRepo: load(year_month)
            ChronoRepo-->>Engine: narrative_data
        end
        
        opt narrative_data is None
            Engine->>Knowledge: extract_monthly_insights(year_month)
            Knowledge-->>Engine: insight_stream (Daily records)
            
            Engine->>Curator: generate_monthly_chronicle(insights)
            Curator->>LLM: Execute Prompt (Knowledge Re-distillation)
            LLM-->>Curator: JSON Chronicle Report
            Curator-->>Engine: narrative_data
            
            Engine->>ChronoRepo: save(narrative_data, year_month)
        end
        
        Engine->>Notifier: monthly_report(narrative_data, summary)
        Notifier-->>Engine: DISPATCHED
        
        Engine->>Engine: Update LAST_SENT_FILE_MONTHLY
    end
```

### 7.2 Knowledge Re-distillation (ナレッジの再蒸留)

日次レポートで AI が鑑定したインサイト（`knowledge_bank.md`）は、月次処理において以下のプロセスで再構成されます。

1. **Extraction**: `KnowledgeManager` が対象月の日次 Insight（Theme, Overview, Insight）を時系列順に抽出します。
2. **Contextualizing**: 抽出された Insight ストリームを `MonthlyCurator` が受け取り、月間騰落率（MTD）や安全資産比率と結合します。
3. **Refinement**: AI が一ヶ月間のノイズを排し、構造的変化（パラダイムシフト）のみを歴史的観点から抽出。日次の「点」を繋ぎ、投資家が振り返るべき「線」の物語へと昇華させます。
