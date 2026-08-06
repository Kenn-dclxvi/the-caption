---
description: THE-CAPTION のプロジェクト固有観点で PR をレビューする
argument-hint: "[PR番号 または owner/repo/pull/N]"
allowed-tools: Bash(gh pr view:*), Bash(gh pr diff:*), Bash(gh api:*), Bash(gh pr comment:*), Read, Grep, Glob
---

# PRレビュー

対象: $ARGUMENTS

引数が空の場合は現在のブランチに対応する PR を対象とする。

## 手順

1. `gh pr view` と `gh pr diff` で対象 PR のメタ情報と差分を取得する。
2. 差分に含まれるパスから、下記の観点のうち該当するものだけを適用する。
3. 判定に必要な範囲で周辺ファイルを読む。差分に現れないファイルの改善提案はしない。
4. 指摘を分類して出力する。

## 観点1: Trinity レイヤー分離（`src/` の差分がある場合）

正本は `src/AGENTS.md`。差分に含まれていればそちらを優先し、記載がなければ以下で判定する。

- 各層の責務: `src/app`=オーケストレーション / `src/domain`=純粋なビジネスロジック / `src/infra`=外部 I/O / `src/lib`=ドメイン所有を持たない共有ユーティリティ。
- `src/domain` から `src/app` を import しない。
- ViewModel は View 層の型であり、domain の signature へ現れない。domain へ渡す値は `src/lib/models` の `Ledger` / `LedgerSummary` / `Position` を使う。
- domain が表示用の文字列を必要とする場合、View の整形結果を受け取らず domain 側で組む。View と同じ書式を使う箇所に、二重定義である旨のコメントがあるか確認する。
- domain が外部 I/O を必要とする場合、`src/infra` の具象を import せず `src/domain/ports.py` へ Protocol を宣言する。実装は `src/infra`、注入は `src/app`。
- `src/domain/ports.py` を変更した差分に `tests/unit/test_ports.py` の追従がなければ指摘する。
- 使っていない依存を Protocol へ包んだまま引数に残していないか。
- 検証・正規化と入出力を同一モジュールへ置かない。検証・正規化は `src/domain`、パス解決と読み書きは `src/infra` の repository。
- ファイルパス定数は `src/config/settings` に置く。domain と infra の双方から参照する定数を一方へ持たせない。
- `common/` / `config/` / `modules/` などのレガシー互換ルートやルートエントリポイント shim を再導入していないか。

`docs/adr/ADR-0001-trinity-separation.md` は **Status: Superseded** である。レイヤー判定の根拠に使わない。

## 観点2: 台帳・時系列データ（台帳 / 日付 / 価格 / FX に触れる差分がある場合）

正本は `docs/adr/ADR-0002-ledger-native-ssot.md` と `docs/adr/ADR-0005-target-date-us-market-date.md`。

- 「計算元の正典（SSOT A / SSOT B）」と「出力の正本（Canonical Ledger）」を区別しているか。用語を混同した記述・実装を指摘する。
- `integrity_status = VERIFIED` へ到達した確定台帳を後続実行で書き換えていないか。`STAGNANT` の間の更新は可。
- 日次の確定台帳は `data/current/ledger_YYYYMMDD.json`。
- `DAY` の基準は前営業日の確定台帳。取得元 CSV の末尾行を基準にしない。前日側は値段と為替の両方を正本の確定値で揃える。
- 数量は当日値のみを用いる。買い増しによる評価額増加を `DAY` へ混入させない。
- `us_market_date` は `target_date - 1日` 以前で直近の NYSE 実取引日。米国株・コモディティ・USD/JPY はすべて同じ `us_market_date` を採用上限とする。株価日と FX 日を分離しない。
- `trading_date`（対象セッションの日付）/ `source_date`（実際に採用した価格行の日付）/ 取得日時・後日更新日時 を同一視していないか。
- 値動きの大小・曜日・米国休場・日本休場だけを理由に配信または確定を止めていないか。
- 前営業日の正本からの確定値継承は、ADR-0002 Guardrails の3条件（正本が `PRICED` 記録 / 正本の対象日が期待日以降 / 取得元から算出した値段が正本と一致）をすべて満たす場合に限る。継承した事実が `warnings` と `source_date` に残るか。
- 期間騰落（`WTD` / `MTD` / `YTD`）は現時点で取得元 CSV の期間起点が基準。確定台帳基準へ移行済みであるかのような実装・記述を指摘する。

## 観点3: ドキュメント記載ルール（`*.md` の差分がある場合）

正本は `docs/AGENTS.md`。

- 正規の CLI パスのみを記載しているか。アプリケーションのエントリポイントは `python -m src.app.entrypoints.v4_daily_main` / `python -m src.app.entrypoints.monthly_main` / `python -m src.app.entrypoints.weekly_main`。
- `python -m src.app.entrypoints.daily_main` と `python -m src.app.entrypoints.collection_main` は本リポジトリに存在しない。記載があれば指摘する。
- `main.py` / `monthly_main.py` / `collection_main.py` などのルートエントリポイント shim を記載していないか。
- `python tools/...` を記載していないか。
- 開発者向けツールは `python scripts/dev/...` または `bash scripts/dev/...`。
- ローカルの配置ルールをドキュメントへ繰り返さず、最も近い `AGENTS.md` へのリンクを優先しているか。

既存の `docs-canonical-command-guard.yml` は `README.md` と `docs/how-to/index.md` の行頭 `python tools/` のみを検査する。**それ以外のファイル、および行頭以外の出現は CI で検査されない**。ガードが通ることを記載可の根拠にしない。

## 観点4: conftest の settings スタブ（`src/config/settings.py` の差分がある場合）

正本は `tests/AGENTS.md`。

- `src/config/settings.py` へ定数を追加した差分に、`tests/conftest.py` への同じ値の登録が伴っているか。
- 伴っていなければ**停止級の指摘**とする。`tests/conftest.py` は `sys.modules["src.config.settings"]` を MagicMock へ差し替えるため、未登録のパス定数が `open()` へ渡ると fd として解釈され、標準出力が閉じてテスト全体が `OSError: [Errno 9] Bad file descriptor` で落ちる。テスト失敗ではなく pytest のクラッシュとして現れ、原因が追いにくい。

## 観点5: 実行経路（`run.sh` の差分がある場合）

- 位置パラメータの補完を `case` の前で行っているか。既定値を `${1:-v4}` のようなパラメータ展開だけで与えると、`shift` が終了ステータス1を返し `set -euo pipefail` により停止する。
- 各モード分岐の `shift` が、引数なしの実行でも失敗しないか。
- モード対応は `v4`/`v`、`weekly`/`w`、`monthly`/`m`。`daily` / `collection` は廃止モードとしてエラー終了する。
- 多重起動防止（`logs/run.sh.lock` の `flock`）に関わる変更で、`python -m` を前提にしていないか。

## 観点6: 汎用

上記に該当しない差分にも、通常のレビュー観点を適用する。

- 正しさ: 境界条件、None / 空コレクション、例外経路、並行実行時の競合。
- エラーハンドリング: 握りつぶし、過度に広い `except`、ログのみで継続してよいかの妥当性。
- テスト: 変更した挙動に対応するテストがあるか。既存テストの期待値を、実装に合わせて根拠なく緩めていないか。
- 秘匿情報: 鍵・トークン・実口座情報・個人情報の混入。

## 出力

以下の分類で、GitHub の PR コメントとして投稿する。該当0件の分類は見出しごと省略する。

- **停止指摘**: マージ前に必ず解消すべきもの。契約違反、正本ルール違反、データ破損・クラッシュにつながるもの。
- **改善指摘**: 解消が望ましいが、マージを止めるほどではないもの。
- **補足**: 判断材料の提示。修正を求めないもの。

各指摘には `file:line` 形式の位置と、根拠となる正本（`src/AGENTS.md` / ADR番号 等）を添える。

指摘がすべて0件の場合は、確認した観点を列挙したうえでその旨だけを述べる。

## 禁止

- 差分に現れないファイルの改善提案。
- 正本に根拠のない様式・命名の好みの指摘。
- コードの変更・コミット・PR の承認 / クローズ。本コマンドは読み取りとコメント投稿のみを行う。
