# 汎用数量取込API

2026-09-10実装。段階Cの最初の対象はMarket Unitsの登録済みIDに対する絶対数量の更新である。[OpenAPI](openapi-import-v1.json)を機械可読契約とし、既存の[API v1](api-v1.md)と同じ認証・HTTP gateway・保存lock・journalを使う。

## 対象と権限

所有者は `input-sources:manage` で入力元を登録する。入力元には認証主体 `subject`、書込み可能なasset_id、数量単位、合算対象の外部レコードID集合、有効状態、鮮度上限、基準時点不明の許容を明示する。1つのIDを複数入力元へ登録できない。FX行は対象外。

取込クライアントの資格情報には `imports:read`、`imports:preview`、`imports:commit` だけを付与する。credentialファイルのsubjectと入力元のsubjectが一致する範囲だけ操作でき、他の入力元や全件Market Unitsを読めない。既存のcredential管理手順で発行・失効する。所有者は自分の権限で全入力元を操作できる。

| 操作 | 用途 |
| --- | --- |
| GET/POST `/api/v1/input-sources` | 所有者が入力元を一覧・登録 |
| GET/PUT `/api/v1/input-sources/{source_id}` | 所有者が設定取得・条件付き更新・休止解除 |
| GET `/api/v1/input-sources/{source_id}/positions` | 許可されたIDの数量、base_revision、休止状態 |
| GET `/api/v1/input-sources/{source_id}/batches` | 入力元の変更予定・前後値・反映結果の履歴 |
| POST `/api/v1/import-batches` | 検証してpreviewを保存。資産入力は変更しない |
| GET `/api/v1/import-batches/{batch_id}` | バッチの照合 |
| POST `/api/v1/import-batches/{batch_id}/commit` | 確認済みdiffを原子的に反映 |
| POST `/api/v1/import-batches/{batch_id}/cancel` | 未反映バッチを取消。履歴は削除しない |

書込みはapplication/jsonとUUIDのIdempotency-Keyを必須とする。sessionの場合は既存のCSRF検証も適用される。PUTによる入力元設定変更にはbase_source_revisionを指定する。管理対象・認証主体・鮮度方針の変更や手入力休止は、過去のpreviewを無効にする。

## 数量と取得状態

取込要求はsource_id、source_run_id、mapping_version、base_revision、単調増加するsequence、collected_at、as_of、enumeration_complete=true、itemsを含む。全設定対象と全外部レコード集合を指定する。対象の一部省略・重複・未知ID・単位不一致は422で全体を拒否する。一覧から消えた銘柄を0や削除と解釈しない。明示された有効な0だけ数量0へ更新する。

quantityは最大整数18桁・小数12桁の非負10進文字列。値は合算済みの絶対数量であり、THE CAPTIONは外部の単位変換や商品対応を推測しない。外部レコード集合は所有者が許可した合算範囲の証拠であり、数値の正しい合算自体はクライアントの責務である。名称・分類・価格URL・他の行を更新しない。既存値と数値として同一ならCSV bytes・revision・資産変更履歴を維持し、バッチにはno-change結果を残す。

collected_atは取得時刻、as_ofは入力元の基準時点。両者を混同しない。現在より未来、鮮度上限を超える入力は拒否する。as_of=nullは所有者がallow_unknown_as_of=trueを明示した場合だけ許可する。その場合もsequenceで反映順序を制約し、厳密な同時点snapshotとは扱わない。既知のas_ofが直近反映時点と同じか古い場合は自動反映しない。訂正は所有者の照合対象とする。

## preview・commit・再送

previewでサーバーがbefore/afterとdiff_hashを保存する。commit/cancelはそのdiff_hashだけを指定し、別payloadへすり替えない。commit直前にlock内で資格情報、入力元subject・権限・設定版・休止状態、資産revision、鮮度、sequence/as_ofを再確認する。1バッチの対象は全件成功か全件未反映。複数リソースを跨ぐ原子性はこの契約に含めない。

数量、バッチ状態、変更履歴、再送結果はMarket Unitsの管理情報へ一緒に保存し、CSVと同じjournalで復旧する。日次readerも既存の同じlockと復旧経路を使用する。日次snapshotや過去の確定成果物は変更しない。

同じ認証主体・操作・keyの同一要求には30日間元の結果を返す。異なる内容は409。再送照合は数量revision・鮮度の再検証より先に行うが、現在の認証・権限・入力元設定制限を迂回しない。30日経過後は409 idempotency_result_expiredとし、バッチGETで照合する。別keyで同じ確定済みバッチのcommitを繰り返しても数量を再反映しない。source_run_idの再利用は同一payloadだけ許可し、異なる内容を拒否する。

現在の入力元から外れたIDを含む履歴は制限付きクライアントへ返さない。所有者は履歴を取得できる。設定版変更後のcommitは412とし、新しいpreviewを必要とする。

## 手入力休止と運用範囲

通常のMarket Units PUTで管理対象の数量変更・削除・FX化があった場合、manual_overrideへ登録して自動更新を休止する。所有者は現在の設定版を取得し、PUTのresume_idsへ解除するIDを明記する。解除後も旧previewは使用せず、新しいpreviewを確認する。無変更の保存は休止を発生させない。

入力元100件、バッチ10000件、取込再送記録10000件を上限とする。上限では503で新しい書込みを停止する。自動削除・履歴の圧縮は行わない。保存先はCSVに隣接する既存管理情報であり、CSVと一組でバックアップする。元データや管理情報を直接書き換えて上限を回避しない。

入力元管理UI、汎用の行追加・削除change-set、現金・取得原価の取込、日次の月別入力manifest、private Monexクライアント、定期実行は後続。今回の検証は架空の入力元と一時ファイルだけを使用する。
