# Part 2: How-to Guides

> ルートの `AGENTS.md` が制御契約の正本です。  
> 契約の読み方・運用上の更新履歴は [開発用プロンプト説明書](./agents-prompt-guide.md) に集約します。

## 1. Daily Operations (日常運用)

### 1.1 Execution Commands (CLI実行)

`python -m src.app.entrypoints.v4_daily_main` が THE CAPTION v4.2 の日次オーケストレーターです。以下のコマンドで制御します。

V4 の保守方針は [System Reference の V4 Maintenance Policy](../reference/system.md#57-v4-maintenance-policy) を正本とします。

**標準実行 (Standard)**
通常はこのコマンドを使用します。Universal Ingester が `data/v4_shadow_ledger.json` を生成し、`daily_metrics` と `market_snapshot` を保存し、Canonical Ledger をもとに単一HTMLメールを送信します。日次AIは呼ばず、既定は確定論的な日次処理です。
```bash
python -m src.app.entrypoints.v4_daily_main
```

**日次AIの自動実行 (Auto Daily AI)**
日次の因果鑑定は、異常日だけ自動で実行されます。通常日は固定コンテキストで送信します。
```bash
python -m src.app.entrypoints.v4_daily_main
```

**月次総括 (Monthly Chronicle)**
月次レポート（前月末基準）の生成と配信を行います。前月末のデータが未確定（休日の連続など）の場合は自動でスキップされます。
```bash
./run.sh monthly
```

**週次総括 (Weekly Chronicle)**
週次レポート（前週末基準）の生成と配信を行います。前週末のデータが未確定（休日の連続など）の場合は自動でスキップされます。
```bash
python -m src.app.entrypoints.weekly_main
```

**過去日付の指定 (Specific Date Execution)**
指定した日付（YYYY-MM-DD）のデータを処理・送信します。過去のレポートを再生成したい場合に使用します。
```bash
python -m src.app.entrypoints.v4_daily_main 2026-02-15
```

**日次バックフィル相当 (Daily Metrics / Market Snapshot Fill)**
メール送信を行わず、指定日の `daily_metrics` と `market_snapshot` を保存したい場合の暫定手順です。`-t` は本来レイアウトテスト経路で、専用のバックフィルコマンドではありません。
```bash
python -m src.app.entrypoints.v4_daily_main 2026-04-27 -t -F
```

**過去月次の指定 (Specific Month Execution)**
指定した日付を起点とする前月分の月次レポートを生成します。
```bash
./run.sh monthly 2026-03-01
```

**過去週次の指定 (Specific Week Execution)**
指定した日付を起点とする前週分の週次レポートを生成します。
```bash
python -m src.app.entrypoints.weekly_main 2026-03-10
```

**AI鑑定の再利用 (Context Reuse)**
既存の AI 鑑定結果 (`context_YYYYMMDD.json`) が存在する場合、 AI プロバイダへの問い合わせをスキップしてレポートを生成します。対象日のキャッシュがない場合は通常生成へフォールバックします。
```bash
python -m src.app.entrypoints.v4_daily_main -u
```

**送信なしレイアウト確認 (Format Test)**
固定コンテキストで描画のみ確認します。AI問い合わせとメール送信は行いません。
```bash
python -m src.app.entrypoints.v4_daily_main -t
```

**トラブル時の再送 (Force Send)**
CompletionLock（送信済みフラグ）を無視して、強制的に日次レポートを再送信します。
```bash
python -m src.app.entrypoints.v4_daily_main -F
```

**月次レポートの強制再送 (Monthly Force Send)**
送信済みロックを無視して、強制的に月次レポートを再送信します。
```bash
./run.sh monthly -F
```

**週次レポートの強制再送 (Weekly Force Send)**
送信済みロックを無視して、強制的に週次レポートを再送信します。
```bash
python -m src.app.entrypoints.weekly_main -F
```

**月次レポートのキャッシュ利用再送 (Monthly Reuse)**
AI 鑑定コストを消費せず、既存の総括内容のまま月次レポートの配信のみをやり直したい場合に使用します。
```bash
./run.sh monthly -F -u
```

**週次レポートのキャッシュ利用再送 (Weekly Reuse)**
AI 鑑定コストを消費せず、既存の総括内容のまま週次レポートの配信のみをやり直したい場合に使用します。
```bash
python -m src.app.entrypoints.weekly_main -F -u
```

**AI鑑定のキャッシュ利用再送 (Force Send with Reuse)**
AI 鑑定コストを消費せず、既存の鑑定内容のままメールの配信のみをやり直したい場合に最適です。
```bash
python -m src.app.entrypoints.v4_daily_main -F -u
```

**市場データ取得テスト (Market Data Probe)**
`MarketDataFetcher` の単体動作確認を行います。yfinance を経由して S&P500 / NASDAQ100 / SOX / 米10年債 / USD/JPY / VIX を取得し、整形済み文字列をログ出力して終了します。各ティッカーが NaN / 欠損の場合は `"N/A"` を返し、クラッシュしません。PortfolioEngine は起動しません。
```bash
python -m src.app.entrypoints.v4_daily_main --test-market
```

**強制再送 (Force Resend / Compatibility Flags)**
v4標準では `-F` が再送の実効フラグです。`-o` は互換目的の no-op のため、付与してもしなくても挙動は同じです。
```bash
python -m src.app.entrypoints.v4_daily_main -o -F
```

**Shadow Ledger 単独生成 (V4 Probe)**
Universal Ingester の生成結果のみを確認します。出力先は `data/v4_shadow_ledger.json` です。
```bash
python scripts/dev/run_shadow_ingester.py
```

#### フラグ使い分けガイド

フラグの組み合わせに迷ったときの判断表です。

| やりたいこと | 推奨コマンド | 備考 |
| :--- | :--- | :--- |
| 毎日の通常実行 | `python -m src.app.entrypoints.v4_daily_main` | CompletionLock があればスキップして終了 |
| AIキャッシュを再利用して再送 | `python -m src.app.entrypoints.v4_daily_main -F -u` | `-u` 単独はロックに弾かれるため `-F` と組み合わせる |
| 強制再送（互換フラグ付き） | `python -m src.app.entrypoints.v4_daily_main -o -F` | 実効は `-F`。`-o` は互換 no-op |
| Shadow Ledger だけ確認 | `python scripts/dev/run_shadow_ingester.py` | メール送信なし |
| MarketDataFetcher の単体確認 | `python -m src.app.entrypoints.v4_daily_main --test-market` | **本番パイプライン非起動**（後述） |
> **テストフラグと本番経路の違い**
>
> - `--test-market` は `V4PortfolioEngine` を起動しない。Guard / Cache / CompletionLock をすべてバイパスし、市場データ取得のログのみ出力して終了する。本番の配信経路とは完全に別物。
> - **共通原則**: 「テストコマンドが通った ＝ 本番OK」ではない。本番経路の最終確認は必ず `python -m src.app.entrypoints.v4_daily_main`（標準実行）で行うこと。

---

### 1.2 Routine Schedule (運用スケジュール)

Production の v4 標準運用では、`./run.sh v4` を平日 18:30 / 18:45 / 19:00 / 19:15 / 19:30 / 20:00 に繰り返し実行します。これらの再実行は、投資信託の当日評価額が確定する時間帯に合わせること、その他の EOD 市場データはすでに確定済みであること、米国市場データは日本時間の当日夜時点では直近 NYSE 実取引日の確定データとして扱うことを前提にしています。

```bash
30 18 * * 1-5 cd <repo-root> && ./run.sh v4 > <repo-root>/logs/cron_panic_v4.log 2>&1
45 18 * * 1-5 cd <repo-root> && ./run.sh v4 >> <repo-root>/logs/cron_panic_v4.log 2>&1
00 19 * * 1-5 cd <repo-root> && ./run.sh v4 >> <repo-root>/logs/cron_panic_v4.log 2>&1
15 19 * * 1-5 cd <repo-root> && ./run.sh v4 >> <repo-root>/logs/cron_panic_v4.log 2>&1
30 19 * * 1-5 cd <repo-root> && ./run.sh v4 >> <repo-root>/logs/cron_panic_v4.log 2>&1
00 20 * * 1-5 cd <repo-root> && ./run.sh v4 >> <repo-root>/logs/cron_panic_v4.log 2>&1
```

#### 1.2.1 Weekly / Monthly Lazy Polling

週次レポート（`python -m src.app.entrypoints.weekly_main`）は、**毎日（日次バッチの直後）実行** するように `crontab` や `launchd` へ登録してください。週末が休日の場合、前週最終営業日の Ledger が `VERIFIED` になるまで自律的に待機し、確定した最初の実行でのみ送信します（`last_sent_weekly.txt` により重複送信を防止）。

月次レポート（`python -m src.app.entrypoints.monthly_main`）は、「毎月1日に1回だけ」ではなく、**「毎日（日次バッチの直後）実行」** するように `crontab` や `launchd` へ登録してください。
月末が休日の場合、月初の段階では最終データが確定（`VERIFIED`）していません。本システムは「前月末のデータが確定した最初の実行タイミング」を自律的に待ってから（Lazy Polling）一度だけレポートを送信し、以後は `last_sent_monthly.txt` のロックにより翌月まで沈黙するよう設計されています。

crontab 例:
```bash
10 20 * * * cd <repo-root> && python -m src.app.entrypoints.weekly_main >> <repo-root>/logs/cron_panic_v4.log 2>&1
10 20 * * * cd <repo-root> && ./run.sh monthly >> <repo-root>/logs/cron_panic_v4.log 2>&1
```

### 1.3 Remote Monitoring (リモート監視)

外出先から iPhone/iPad の「ファイル」アプリで実行結果を確認するため、`launchd` を使用してログを iCloud Drive へ自動転送します。

**設定手順:**
1. `~/Library/LaunchAgents/com.<username>.finance.logcopy.plist` を作成し、以下の内容を記述します。
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "[http://www.apple.com/DTDs/PropertyList-1.0.dtd](http://www.apple.com/DTDs/PropertyList-1.0.dtd)">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.<username>.finance.logcopy</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/sh</string>
        <string>-c</string>
        <string>if [ -f "${PROJECT_DIR}/logs/finance_report.log" ]; then cp "${PROJECT_DIR}/logs/finance_report.log" "${ICLOUD_LOG_DIR}/finance_report_$(date +%Y%m%d).log"; fi; if [ -f "${PROJECT_DIR}/logs/llm_trace.log" ]; then cp "${PROJECT_DIR}/logs/llm_trace.log" "${ICLOUD_LOG_DIR}/llm_trace_$(date +%Y%m%d).log"; fi</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>15</integer>
    </dict>
</dict>
</plist>
```

**管理コマンド:**
* **登録**: `launchctl load ~/Library/LaunchAgents/com.<username>.finance.logcopy.plist`
* **解除**: `launchctl unload ~/Library/LaunchAgents/com.<username>.finance.logcopy.plist`
* **即時実行テスト**: `launchctl start com.<username>.finance.logcopy`

**Alert Stage 登録（必須）**
監視ルール（メール振り分け/通知連携/ダッシュボード）には、少なくとも次の Stage を登録してください。

| ドメイン | 運用制限 | 致命障害 |
| :--- | :--- | :--- |
| Daily | `OPERATIONAL_LIMIT` | `SYSTEM_CRASH` |
| Weekly | `OPERATIONAL_LIMIT_WEEKLY` | `SYSTEM_CRASH_WEEKLY` |
| Monthly | `OPERATIONAL_LIMIT_MONTHLY` | `SYSTEM_CRASH_MONTHLY` |
| Collection | `COLLECTION_INIT`, `COLLECTION_DATA` | `SYSTEM_CRASH_COLLECTION` |

### 1.4 Weekly E2E Gate (出荷前)

週次の仕様変更を含む出荷前には、以下を必ず実施して証跡を残してください。

1. `./scripts/dev/weekly_e2e_gate.sh` を実行する（help/format-test/unit を一括確認）。
2. 検証用宛先を設定した環境で `./scripts/dev/weekly_e2e_gate.sh --live <target-date>` を実行し、`WEEKLY CHRONICLE [YYYY-Www]` の配信ログを確認する。

---

## 2. Development Workflow (開発フロー)

### 2.1 Twin-Tower Architecture Workflow
Windows (Satellite Dev) と Mac (Core) を切り替えながら開発するフローです。

**環境の切り替え (Win ⇄ Mac):**

1.  **Win**: 作業中のコードを `git push` する（WIPでOK）。
2.  **Mac**: `git pull` で最新コードを取得する。
3.  **Mac**: `docker-compose run ...` で即座に続きを実行。

**※注意**: `history.csv`（資産データ）だけは Git 管理外です。 最新データを持ち運ぶ場合は `data/` フォルダを同期してください。

### 2.2 Testing Procedures (テスト手順)

コード修正後は、必ず `pytest` でユニットテストを実行してからコミットしてください。

#### セットアップ（初回のみ）

```bash
pip install -r requirements-dev.txt
```

#### 実行コマンド

| コマンド | 用途 |
| :--- | :--- |
| `pytest tests/ -v` | 全テストを詳細出力で実行（標準） |
| `pytest tests/ --tb=short` | 失敗時のトレースバックを短縮表示 |
| `pytest tests/ --cov=src --cov-report=term-missing` | カバレッジ計測（未カバー行をターミナルに表示） |

#### テスト構成

| ファイル | 対象モジュール | テスト内容 |
| :--- | :--- | :--- |
| `tests/conftest.py` | `src/config/settings.py` (Fernet) | `src.config.settings` を `MagicMock` に差し替え。暗号化依存を全テストから切り離す共通フィクスチャ |
| `tests/unit/test_utils.py` | `src/lib/utils.py` | `SystemUtils.parse_pct_str` — 数値・文字列・`None` 等9パターンの境界値検証 |
| `tests/unit/test_view_models.py` | `src/app/renderer/view_models.py` | `PositionViewModel` / `SummaryViewModel` / `CollectionPositionViewModel` / `CollectionSummaryViewModel` の書式・色・状態計算 |
| `tests/unit/test_market_data.py` | `src/infra/market_data.py` | `MarketDataFetcher.fetch_market_context` — 正常系5（正負・変化なし・パイプ数・休場日ルックバック）+ フォールバック4（空df・1行・例外・全NaN）の計9パターン。yfinance を `sys.modules` でモック |

#### conftest 設計方針

`src/config/settings.py` は起動時に Fernet（AES-256）でキーファイルと暗号化 `.env` を読み込む。テスト環境ではこれらのファイルが存在しないため、`conftest.py` が `sys.modules` レベルで `src.config.settings` を `MagicMock` に差し替え、暗号化依存を完全に排除している。

#### pre-commit hook ポリシー

`.git/hooks/pre-commit` が自動的に `pytest tests/` を実行します。

| 結果 | 挙動 |
| :--- | :--- |
| **PASS** | コミット続行 |
| **FAIL** | コミットを強制中断。テストを修正してから再コミット |

---

## 3. Maintenance & Recovery (保守・復旧)

### 3.1 Backup Strategy (バックアップ戦略)

本システムは「本番環境 (Stable)」と「開発環境 (Dev)」の双方向でデータ保全を行います。 `backup_data.sh` 等を `launchd` に登録して自動実行します。

| 環境 | スクリプト名 | バックアップ対象 | 実行推奨時刻 |
| :--- | :--- | :--- | :--- |
| **Production** | `backup_data.sh` | `data/` (正典), `logs/` | **09:15** (月次レポート配信後) |
| **Development** | `backup_data_dev.sh` | `data/` (Dev用), `logs/` | **09:35** (開発作業前) |

**リストア手順:**
1. `tar xzf data_YYYYMMDD.tar.gz` を実行し、ディレクトリを展開する。
2. `history.csv` が破損した場合、直近のバックアップから復元する。

### 3.2 Troubleshooting (トラブルシューティング)

**ログの確認**
`logs/finance_report.log` を確認します。

| ログのキーワード | 意味 | ユーザーのアクション |
| :--- | :--- | :--- |
| **`[Outcome] DISPATCHED`** | 整合性立証。配信完了。 | 鑑賞のみ。 |
| **`[Guard] already sent`** | 本日分は既に送信済み。 | 何もしなくてよい。 |
| **`[Provisional]` / 件名末尾 `○`** | データ未完成につき暫定送信。ロック未確定のため再取得が継続する。 | 次の実行を待つ。 |
| **`Reusing existing context`** | 既存の鑑定結果を再利用。 | AIコストを節約。 |
| **`[System Crash]`** | システム例外または通信断絶。 | 必要に応じて手動リトライ。 |

**ERROR: All AI providers failed**
AI API（Claude/Gemini）のレート制限やトークン不足です。
* **対処**: 翌日のリセットを待つか、`-u` オプションで既存キャッシュを再利用してください。

**LLM プロンプト・レスポンスの確認 (llm_trace.log)**
ハルシネーションの再現やプロンプト改訂の効果検証が必要な場合は、LLM transporter の運用ログを含む専用ファイルを参照します。
```bash
tail -f logs/llm_trace.log
```

| 項目 | 内容 |
| :--- | :--- |
| **ファイル** | `logs/llm_trace.log` |
| **記録内容** | LLM transporter の運用ログ `[Acquisition]` / `[Outcome]` / `[Guard]` + 送信プロンプト全文 `[Acquisition]` + 生レスポンス全文 `[Parsing]` |
| **ローテーション** | 日次（30日分保持） |
| **注意** | 資産データを含む機密情報が記録されるため、`logs/` ディレクトリの `.gitignore` 管理を維持すること |

### 3.3 Curator Knowledge Update (鑑定エンジンの知識更新)

ポートフォリオの構成銘柄や投資セクターを大きく変更した場合、キーワード辞書をメンテナンスします。

1.  **対象ファイル**: `src/domain/curator.py` や `src/domain/monthly_curator.py`
2.  **修正箇所**: `MarketCurator` クラス内の分析ロジック。
3.  **更新内容**: 新規投資先のティッカーシンボルや銘柄名を追加する。これを行わないと、特化分析の対象外となる可能性があります。

---

## 4. Utility Tools (補助ツール運用)

日常的なメンテナンスやセキュリティ向上のためのツール群の使用方法です。

### 4.1 Asset Catalog Generation (YAML自動生成)
取得したRaw CSVから銘柄を抽出し、`config/assets.yaml` の雛形を生成します。

**実行コマンド**:
```bash
python scripts/dev/generate_asset_yaml.py
```
**手順**:
1. `data/raw/` に各資産クラスのCSVを配置する。
2. ツールを実行し、`config/assets.yaml` を出力させる。
3. 生成されたファイルを開き、`short_name` や `color` を手動でキュレーション（調整）する。

### 4.2 Environment Encryption (環境変数の暗号化)
`.env` ファイルを AES-256 (Fernet) で暗号化し、ソース共有時の安全性を確保します。

**暗号化の実行**:
```bash
python scripts/dev/encrypt_env.py
```
**挙動**:
1. `secret.key`（鍵）と `.env.enc`（暗号化済みファイル）が生成される。
2. **[重要]**: 暗号化成功後、元の `.env` は削除または安全な場所へ退避させる。
3. システム実行時、`src/config/settings.py` が自動的に鍵と暗号化ファイルを検知してメモリ上に展開する。

### 4.3 Chronicle Rewriter (知識の歴史再構築)
指定した期間の `ledger_YYYYMMDD.json` を読み込み、最新プロンプト（VIX取得対応版）で MarketCurator を叩き直して `context_YYYYMMDD.json` と `knowledge_bank.md` を上書き再構築するバッチツールです。メール送信は一切行いません。

**基本実行** (日付範囲を指定):
```bash
python scripts/dev/rebuild_knowledge.py --start 2026-01-01 --end 2026-01-31
```

**単一日付の再構築**:
```bash
python scripts/dev/rebuild_knowledge.py --start 2026-02-15 --end 2026-02-15
```

**レートリミット回避のディレイを調整** (デフォルト: 12秒):
```bash
python scripts/dev/rebuild_knowledge.py --start 2026-01-01 --end 2026-01-31 --delay 20
```

**引数一覧**:

| 引数 | 必須 | 説明 |
| :--- | :--- | :--- |
| `--start YYYY-MM-DD` | YES | 再構築開始日（inclusive） |
| `--end YYYY-MM-DD` | YES | 再構築終了日（inclusive） |
| `--delay N` | NO | API 呼び出し間のスリープ秒数（デフォルト: 12） |

**ユースケース**:
- プロンプト改訂後に過去の鑑定結果を最新ロジックで書き直したい場合。
- VIX取得対応など、Context スキーマが変更された後の一括リフレッシュ。
- `knowledge_bank.md` が破損・欠損した場合の再構築。

**挙動**:
1. `data/current/` をスキャンし、指定範囲内の `ledger_*.json` を日付昇順で処理する。
2. 各元帳を `Ledger` オブジェクトとして再構築し、`MarketCurator.generate_context_report()` を呼び出す。
3. 結果を `context_YYYYMMDD.json`（上書き）および `knowledge_bank.md`（該当日エントリ上書き）に保存する。
4. API 呼び出し間に `--delay` 秒の sleep を挟み、レートリミットを回避する。
5. 元帳が存在しない日付は警告ログを出力してスキップし、バッチ全体は止まらない。

### 4.4 Session Setup (初回ブラウザ認証)
Broker 証券へのログイン状態を手動で取得し、`auth/state.json` に保存します。本番の CSV 取得前に一度実行する想定です。

**実行コマンド**:
```bash
python scripts/dev/setup_auth.py
```
**手順**:
1. ブラウザが起動し、証券会社のログイン画面が開く。
2. 手動でログインし、二要素認証（メールやアプリのコード入力）まで完了させる。
3. 資産状況が見える画面まで進んだら、ターミナルに戻り Enter を押す。
4. セッション情報が `auth/state.json` に保存される。

### 4.5 SMTP Send Test (メール送信テスト)
`.env` の SMTP 設定（SMTP_USER / SMTP_PASS / SMTP_TO）を用いて、テストメールを送信し接続を確認します。

**実行コマンド**:
```bash
python scripts/dev/test_email.py
```
**前提**: `.env` に SMTP_USER, SMTP_PASS, SMTP_TO が設定されていること。

### 4.6 Gemini Model List (利用可能モデル一覧)
Google Gemini API に設定されたキーで、`generateContent` に対応したモデル一覧を表示します。Secondary LLM の確認用です。

**実行コマンド**:
```bash
python scripts/dev/check_models.py
```
**前提**: `.env` に GOOGLE_API_KEY が設定されていること。

### 4.7 LLM Cost Summary (トークン使用量・コスト概算)
`logs/llm_trace.log`（およびローテーション済みファイル）から `[Outcome] Token Usage` 行を解析し、指定月の LLM 呼び出し回数・入出力トークン・概算コストを集計します。

**実行コマンド**:
```bash
python scripts/dev/cost_summary.py
python scripts/dev/cost_summary.py --month 2026-02
```
| 引数 | 規定値 | 説明 |
| :--- | :--- | :--- |
| `--month YYYY-MM` | 当月 | 集計対象月 |

### 4.8 Project Merge (プロジェクト全文マージ)
ソースツリーをレイヤー別（LOGIC / INFRA / VIEW / DOC / TOOL）に走査し、`__REV` ベースのリビジョン情報と import 依存を 1 ファイルにマージします。開発・レビュー用です。ファイル末尾フッターは付与しません。

**実行コマンド**:
```bash
python scripts/dev/merge_project.py
```
**出力**: プロジェクトルートに `Project_Full_v{VERSION}_{timestamp}.txt` が生成される。`data` / `logs` / `auth` / `.env` 等は除外され、各ファイルの本文はそのまま収録される。

### 4.9 Batch CSV Fetch (全資産クラス一括取得)
Playwright で Broker View にログインし、国内株・米国株・投資信託・債券・REIT 等の全資産クラス CSV を `data/raw/` に一括ダウンロードします。開発・手動取得用です。

**実行コマンド**:
```bash
python scripts/dev/fetch_all_assets.py
```
**前提**: `.env` に BROKER_ID, BROKER_PASS が設定されていること。ブラウザは可視で起動する。

### 4.10 PoC Fetch Detail (投資信託取得デバッグ)
投資信託タブの CSV 取得フローを可視ブラウザで段階実行し、デバッグ用 CSV を出力する PoC ツールです。本番パイプラインには含まれません。

**実行コマンド**:
```bash
python scripts/dev/poc_fetch_detail.py
```
**用途**: セレクタ変更や Broker 画面変更時の動作確認。

### 4.11 Tools Shim Sunset (互換 shim 廃止)
`tools/` 互換 shim は **2026-03-05** に廃止済みです。以後は本ドキュメント内の module-based command guidance を正とします。

### 5. Legacy / v3 までの運用メモ

以下は v4 標準運用には含めない、旧 Collection / Broker / v3 系の運用メモです。
v3以前のコード・エントリポイント・スクリプトは `legacy/v3/` へ退避済みです。現行 v4 実行経路からは切り離されており、実行対象外です。
旧運用ドキュメントは `docs/archive/` を参照先として扱います。

旧運用手順の参照が必要な場合は `legacy/v3/` 配下を参照してください。そのまま復活させず、現行仕様に基づく新規変更として扱ってください。
