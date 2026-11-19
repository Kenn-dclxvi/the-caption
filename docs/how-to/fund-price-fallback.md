# 投信価格の翌朝補完

通常取得に失敗した指定投信について、翌朝Monexから取得した基準日一致の価格で未確定計算を完了する機能。実装と架空データによる検証の対象であり、この文書の追加だけでは本番有効化しない。

## 処理

通常のdailyは価格取得を従来の時刻に実行する。指定した円建て投信がMISSING / STALEなら入力を凍結して価格要求を保存し、未確定結果を確定台帳や配信へ進めない。

private importerは翌朝09:05 JSTにMonex銘柄詳細を取得する。未更新・取得失敗は09:30に再確認する。土日祝も対象で、09:31以降は新規の自動取得を開始しない。本体は公開APIで日付・単位・入力版を検証し、importerは独立GETで保存価格とreceiptを照合する。

必要な候補が揃ったら元の数量snapshot・外部資産・原価・他価格・市場日付・前日比較入力から計算を再開する。翌朝の入力へ置換しない。確定台帳を保存・同期・再読取りして計算完了とする。メール等の外部配信はこの機能に含めない。

通常価格の復旧時は未採用の要求だけ通常価格で補完する。Monex採用後は自動置換しない。既存の確定結果や元の入力版と競合する場合は `correction_required` とし、上書きしない。

## 設定

本体のdailyとAPI workerに同じ絶対パスの `CAPTION_FUND_PRICE_FALLBACK_STATE_DIR` を指定する。親ディレクトリは事前作成し、専用stateを0700、内部ファイルを0600で保護する。dailyには `CAPTION_FUND_PRICE_FALLBACK_ASSETS` も指定する。値は公開Market Unitsで確認した対象asset_idのカンマ区切りとし、実銘柄名・対応表は文書へ転記しない。

未設定では従来のdaily動作を維持し、新APIは503 `fund_price_fallback_disabled` を返す。有効化時は全てのdaily実行とAPI workerで同じstateを共有し、正本保存の排他制御を統一する。API workerの台帳先は `--csv-path` のdataルート配下のcurrentとし、別環境の既定dataを使わない。

運用は従来の `./run.sh v4` を使う。開発時の正規入口は `python -m src.app.entrypoints.v4_daily_main`。価格待ちの既存日を再実行した場合も元の入力版を再利用し、通常ソースの復旧分だけ読み取る。

起動・Monex認証・Monexコードとasset_idの対応表はprivate importer側の設定とする。生成したlaunchd plistは配置・loadするまで起動されない。スリープや起動漏れで両枠を逃した要求は未解決として通知し、後日価格を元の日付へ転用しない。

## 公開契約と権限

正本は [OpenAPI](../reference/openapi-fund-prices-v1.json)。認証・CSRF・レート制限・本文上限は既存APIの共通処理に従う。

| 操作 | 必要権限 | 内容 |
| --- | --- | --- |
| GET `/api/v1/fund-price-requests` | `fund-prices:read` | 未採用要求一覧 |
| GET `/api/v1/fund-price-requests/{request_id}` | `fund-prices:read` | 対象日・入力digest・価格・receipt・計算状態の独立照合 |
| POST `…/{request_id}/candidate` | read + `fund-prices:adopt` | 固定要求版への価格採用。UUIDのIdempotency-Key必須 |
| POST `…/{request_id}/complete` | read + `fund-prices:complete` | 空JSONで保存入力の計算を完了。UUIDのIdempotency-Key必須 |

候補はJPYかつ本体の1万口単価へ正確に対応するものだけ受け入れる。同じキー・候補は同じreceiptを返し、変更は409。通常ソースが復旧済みなら `primary` とし、Monexのreceiptを作らない。

`adopted` は価格採用、`calculation_status=completed` は正本の保存・照合完了であり別状態。価格採用後の計算失敗は `calculation_failed` で再開できる。異なる確定結果が存在する場合は `correction_required` で止める。同期書込み後に応答が失われても、保存済みの同一documentと照合して再開できる。完了済み要求のGETでも台帳digestを検証し、台帳が消失・変更された状態を成功として返さない。

## 検証と導入境界

`tests/integration/test_fund_price_fallback.py` は架空の2投信で、凍結入力、部分採用、基準日不一致、通常ソース復旧、応答消失、確定履歴保護、公開schema適合を検証する。

本番の設定・認証確認、サービスの版更新、起動有効化、実データ登録・独立照合は導入段階として別に確認する。価格更新時刻と可用性を保証する機能ではない。
