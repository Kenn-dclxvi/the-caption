# SSOT A Market Units リネームおよび日付別 Units 入力固定仕様

## 1. 目的

本仕様書は、以下の変更を実装可能な粒度で定義する。

1. `data/collection/funds.csv` を `data/collection/market_units.csv` へ改名する。
2. `funds_editor` を `market_units_editor` へ改名し、UI 表示も Market Units に統一する。
3. 日次台帳の再計算時に、日付別 Units スナップショットを入力として固定できるようにする。
4. SSOT A の正本パスと、実際に採用した Units 入力元を ledger 上で分離して記録する。

この変更は単なるファイル名変更ではなく、v4 canonical ledger の入力契約変更として扱う。

---

## 2. スコープ

### 2.1 対象

1. SSOT A の既定パス変更。
2. エディタのディレクトリ名・表示名・参照パス変更。
3. `target_date` 単位の Units スナップショット参照ロジック追加。
4. `ShadowLedger` への Units 入力元メタデータ追加。
5. 既存 `collection_units_*.json` の参照パス補正・再生成方針定義。

### 2.2 対象外

1. 評価額計算式の変更（`price * units`、投信 NAV 換算、コモディティ換算）。
2. 月次 AI プロンプト契約の変更。
3. Legacy Broker 取得アーキテクチャの再設計。
4. runtime における旧 `data/collection/funds.csv` の互換読み込み。
5. 既存 ledger の金額完全再計算。

旧 `funds.csv` から新 `market_units.csv` へのコピーまたはリネームを行う移行補助スクリプトは許容する。ただし、日次実行時の暗黙フォールバックとして旧ファイルを読む処理は対象外とする。

---

## 3. 名称変更仕様

### 3.1 SSOT A（市場連動資産の保有数）

1. 旧: `data/collection/funds.csv`
2. 新: `data/collection/market_units.csv`
3. CSV カラムは変更しない。

```text
name,asset_class,currency,units,source_symbol,audit_match_key,csv_url
```

### 3.2 エディタ名称

1. 旧ディレクトリ名: `src/web/funds_editor`
2. 新ディレクトリ名: `src/web/market_units_editor`
3. UI 表示名:
   - `Master Ledger` -> `Market Units`
   - 保存通知・現在パス表示は `data/collection/market_units.csv` に統一する。
4. package 名:
   - `the-caption-funds-editor` -> `the-caption-market-units-editor`

### 3.3 API 名称

今回の移行では、エディタ API endpoint は互換性優先で維持する。

1. `GET /api/funds` は維持する。
2. `POST /api/funds` は維持する。
3. 内部参照先と UI 表示だけを Market Units に変更する。

`/api/market-units` の新設は今回のスコープ外とする。

### 3.4 実行時パス契約

SSOT A の正本パスは、すべて以下に統一する。

```text
data/collection/market_units.csv
```

対象:

1. `src/domain/universal_ingester.py`
2. `src/domain/collection_history_updater.py`
3. `src/app/collection_engine.py`
4. `src/web/market_units_editor/server.ts`
5. `run.sh`
6. 関連テスト fixture・期待値

`market_units.csv` が存在せず、旧 `funds.csv` だけが存在する場合、runtime は自動フォールバックしない。これは運用データ移行漏れとして扱う。

---

## 4. Units スナップショット仕様

### 4.1 ファイル仕様

1. 保存先:
   `data/current/collection_units_YYYYMMDD.json`
2. `schema_version`:
   `market_units_snapshot.v1`
3. `snapshot_type`:
   `FULL_SNAPSHOT`
4. `captured_at`:
   timezone 付き ISO 8601、JST で記録する。
   例: `2026-05-21T19:30:00+09:00`

### 4.2 必須トップレベル項目

1. `schema_version`
2. `snapshot_type`
3. `target_date`
4. `captured_at`
5. `source.ssot_a_path`
6. `source.ssot_a_sha256`
7. `items[]`

`source.ssot_a_path` は正本 SSOT A のパスを示す。値は原則 `data/collection/market_units.csv` とする。

### 4.3 必須 `items[]` 項目

1. `asset_key`
2. `name`
3. `asset_class`
4. `currency`
5. `units`
6. `source_symbol`
7. `audit_match_key`
8. `csv_url`

`units` は文字列で保存する。これは小数・桁数・CSV 上の表現を不用意に丸めないためである。

### 4.4 任意 `items[]` 項目

1. `enabled`

`enabled` は将来互換フィールドとする。CSV 生成時に付与する場合の既定値は `true` とする。v1 の ledger 計算では `enabled=false` を特別扱いせず、計算対象から除外しない。検証時も `enabled` の有無は必須条件にしない。

---

## 5. asset_key 生成仕様

`asset_key` は snapshot 内の安定識別子であり、重複判定と再計算時の資産対応に使う。

生成優先順:

1. `audit_match_key` が空でなければ `audit_match_key`
2. `source_symbol` が空でなければ `${asset_class}:${currency}:${source_symbol}`
3. それ以外は `${asset_class}:${currency}:${name}`

正規化ルール:

1. `asset_class` と `currency` は `trim` 後に uppercase する。
2. `name`、`source_symbol`、`audit_match_key` は `trim` のみ行う。
3. 空文字は未設定として扱う。
4. 重複判定は上記正規化後の `asset_key` で行う。

注意:

1. `name` を含む fallback key は、表示名変更で履歴が割れる可能性がある。
2. 安定性が必要な資産では `audit_match_key` を明示することを推奨する。
3. FX helper row、COMMODITIES、JP_STOCK、US_STOCK、MUTUAL_FUNDS は同一ルールで扱う。

---

## 6. Ledger 入力元記録仕様

### 6.1 `ssot_a_path` の意味

`ShadowLedger.ssot_a_path` は canonical SSOT A の正本パスを示す。

値は常に以下とする。

```text
data/collection/market_units.csv
```

`ssot_a_path` には、実際に採用した snapshot ファイルパスを入れない。

### 6.2 `units_source` の追加

実際に Units 入力として採用したソースは、`ShadowLedger` のトップレベルに新設する `units_source` へ記録する。

既存 ledger 読み込み互換のため、schema 上の `units_source` は Optional とする。ただし、新規生成する ledger では必須出力とする。

```json
{
  "ssot_a_path": "data/collection/market_units.csv",
  "units_source": {
    "type": "SNAPSHOT",
    "path": "data/current/collection_units_20260521.json",
    "snapshot_target_date": "2026-05-21"
  }
}
```

`units_source` フィールド:

1. `type`: `"SNAPSHOT"` または `"LIVE_CSV"`
2. `path`: 実際に読んだファイルパス
3. `snapshot_target_date`: snapshot 採用時のみ設定する

LIVE_CSV 採用時の例:

```json
{
  "ssot_a_path": "data/collection/market_units.csv",
  "units_source": {
    "type": "LIVE_CSV",
    "path": "data/collection/market_units.csv"
  }
}
```

---

## 7. Units 解決モード仕様

### 7.1 起動インターフェース

`UniversalIngester.build_shadow_ledger()` は `units_mode` を受け取る。

```python
build_shadow_ledger(target_date: Optional[str] = None, units_mode: str = "daily")
```

許容値:

1. `daily`
2. `strict`

`recompute`、`audit`、`backfill` 相当の処理は `strict` を指定する。CLI や専用スクリプトで別名を設ける場合も、domain 層では `strict` に正規化する。

### 7.2 daily mode

日次運用では可用性を優先する。

1. 対象日の snapshot が存在し、検証に通れば snapshot を採用する。
2. snapshot 欠損時は `market_units.csv` を採用する。
3. snapshot 不正時は `[Guard]` warning を出し、`market_units.csv` へフォールバックする。
4. フォールバックした場合も `units_source.type = "LIVE_CSV"` として記録する。

### 7.3 strict mode

再計算・監査・バックフィルでは `strict` を使い、再現性を優先する。

1. snapshot が存在し、検証に通れば snapshot を必ず採用する。
2. snapshot 不正時は blocking とし、live CSV へ黙って切り替えない。
3. snapshot 欠損時に live CSV を使うには、明示オプションを必要とする。
4. 明示オプションで live CSV を使った場合も、`units_source.type = "LIVE_CSV"` として記録する。

---

## 8. スナップショット検証ルール

有効判定条件:

1. `schema_version = "market_units_snapshot.v1"`
2. `snapshot_type = "FULL_SNAPSHOT"`
3. `target_date` が要求日付と一致する。
4. `items` が空でない。
5. 全 `items` の `units` が数値として解釈可能である。
6. 正規化後の `asset_key` が重複しない。
7. 必須項目が欠損していない。

検証失敗時の扱いはモードに従う。

---

## 9. バックフィル仕様

### 9.1 バックフィルの意味

バックフィルは、指定された Units 入力を指定日付の snapshot として固定する処理である。

過去時点の保有数を自動復元する処理ではない。

### 9.2 入力ソース

バックフィル実行時は、Units 入力元を明示する。

候補:

1. 現在の `data/collection/market_units.csv`
2. 日付別に用意した手動 CSV
3. Git 履歴またはバックアップから復元した CSV
4. 初回導入日以降に日次処理で自動生成された snapshot

現在の `market_units.csv` で過去期間を生成した場合、その snapshot は「現在の保有数を過去日付に固定したもの」であり、過去当時の保有数を保証しない。

### 9.3 再現性の保証範囲

再計算再現性の保証対象は、以下を満たす日付に限定する。

1. `collection_units_YYYYMMDD.json` が存在する。
2. snapshot 検証に通る。
3. その snapshot が意図した Units 入力元から生成されたことが運用上確認されている。

---

## 10. 参照データ補正仕様

### 10.1 補正対象

1. `data/current/collection_units_*.json`
2. `data/v4_shadow_ledger.json`
3. `ssot_a_path` または Units 入力元情報を保持する日次成果物

### 10.2 補正方針

1. 移行期間中のみ、過去生成物に旧パスが残ることを許容する。
2. 最終状態は以下へ統一する。
   - `source.ssot_a_path = "data/collection/market_units.csv"`
   - 新規生成 ledger の `ssot_a_path = "data/collection/market_units.csv"`
   - 新規生成 ledger の `units_source` に実入力元を記録する
3. スナップショット再生成時は同一日付キーの既存ファイルを上書きする。

`data/v4_shadow_ledger.json` は current canonical output として扱う。補正はパス文字列だけの直接編集ではなく、代表日で ledger を再生成して確認することを基本とする。既存 ledger 履歴の金額完全再計算は対象外とする。

---

## 11. data 配下の運用移行仕様

`data/` 配下は git 管理外であるため、コード変更と運用データ移行を分離する。

### 11.1 コード・ドキュメント変更

1. 既定参照先を `market_units.csv` に変更する。
2. テスト fixture・期待値を `market_units.csv` に変更する。
3. ドキュメントと canonical context を新名称へ更新する。

### 11.2 運用データ移行

1. ローカル・本番環境の `data/collection/funds.csv` を `data/collection/market_units.csv` へリネームする。
2. リネーム後、旧 `funds.csv` が残っていても runtime は参照しない。
3. `market_units.csv` 欠損時は設定不備として扱う。

---

## 12. 更新対象ドキュメント

最低限、以下を更新対象とする。

1. `docs/reference/project-contexts/the-caption.txt`
2. `docs/reference/logic.md`
3. `docs/reference/system.md`
4. `README.md`
5. `docs/adr/ADR-0004-collection-primary-v4.md`
6. `docs/how-to/` 配下で `funds.csv` または `funds_editor` に触れている文書
7. `docs/appendix/` および `docs/explanation/` 配下で SSOT A を説明している文書

特に `docs/reference/project-contexts/the-caption.txt` は実行時の静的コンテキストとして扱われるため、旧名称を残さない。

---

## 13. 移行手順（実施順）

1. `ShadowLedger` schema に `units_source` を追加する。
2. `UniversalIngester` に `daily` / `strict` の Units 解決モードを追加する。
3. SSOT A 既定パスを `market_units.csv` に変更する。
4. エディタディレクトリを `market_units_editor` へ改名し、`run.sh` 参照先を更新する。
5. エディタの表示名・保存通知・health 出力を更新する。
6. 運用データとして `funds.csv` を `market_units.csv` へリネームする。
7. 指定期間の `collection_units_*.json` を、明示した入力ソースで再生成する。
8. 代表日で ledger を再生成し、`ssot_a_path` と `units_source` を検証する。
9. テストとドキュメントを新名称・新挙動に追従させる。

---

## 14. 受け入れ条件

### 14.1 名称

1. runtime の既定入力パスとして `data/collection/funds.csv` の直接参照が残っていない。
2. UI の保存通知と health 出力が `market_units.csv` を示す。
3. `run.sh` が `src/web/market_units_editor` を起動できる。
4. `GET /api/funds` / `POST /api/funds` は維持され、新 CSV を read/write する。

### 14.2 日次実行

1. snapshot 存在時は snapshot Units を採用する。
2. snapshot 欠損・不正時は warning を出し、live CSV で処理完走する。
3. ledger には `ssot_a_path` と `units_source` がそれぞれ正しい意味で記録される。

### 14.3 再計算・監査

1. `strict` 指定時、snapshot が存在する日付では snapshot を必ず採用する。
2. snapshot 不正時に live CSV へ黙って切り替わらない。
3. live CSV を使う場合は明示オプションが必要である。
4. 同一 `target_date`・同一 snapshot 入力で deterministic な Units 入力になる。

### 14.4 参照データ補正

1. 指定期間の `collection_units_*.json` が揃っている。
2. 期間内ファイルの schema が `market_units_snapshot.v1` に統一されている。
3. 新規生成 ledger の `ssot_a_path` が新名称で記録される。
4. 新規生成 ledger の `units_source` が実入力元を記録している。

---

## 15. テスト要件

1. Unit テスト:
   - snapshot 採用パス
   - daily mode の snapshot 欠損 fallback
   - daily mode の snapshot 不正 fallback
   - strict mode の snapshot 不正 blocking
   - `asset_key` 生成・重複判定
   - `units_source` 記録
2. 既存テストのパス期待値を `market_units.csv` に更新する。
3. エディタ API スモーク:
   - `GET /api/funds` が新 CSV を読む
   - `POST /api/funds` が新 CSV へ書く
4. E2E ドライラン:
   `python -m src.app.entrypoints.v4_daily_main <date> -t`
