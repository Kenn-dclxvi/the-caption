# 架空の入力元で数量取込を試す

[取込契約](../reference/quantity-import-api.md)と[OpenAPI](../reference/openapi-import-v1.json)に対応する手順。まず隔離したテスト用CSV・資格情報で実施する。実データへの入力元登録は、対象と単位を所有者が確認してから行う。

1. [既存の起動・資格情報手順](market-units-api.md)に従ってAPIを起動する。所有者tokenと、`imports:read`・`imports:preview`・`imports:commit`だけを持つ専用tokenを分ける。以下の入力元subjectと専用tokenのsubjectを一致させる。
2. 所有者のMarket Units GETで、取込先のasset_idと現在の数量を確認する。名称から推測してIDを作らない。
3. 所有者がPOST `/api/v1/input-sources`へ次の形で登録する。UUIDと外部レコード名は説明用の架空値なので実際の確認済みIDへ置き換える。Idempotency-Keyには要求ごとのUUIDを使用する。

```json
{
  "name": "Fictional positions",
  "subject": "fictional-importer",
  "enabled": true,
  "max_age_seconds": 3600,
  "allow_unknown_as_of": false,
  "targets": [{
    "asset_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "quantity_unit": "share",
    "external_record_ids": ["fictional-record-a"]
  }]
}
```

4. 専用tokenでGET `/api/v1/input-sources/{source_id}/positions`を呼び、base_revisionを取得する。
5. POST `/api/v1/import-batches`へ全設定対象の絶対数量を送る。quantity_unitとexternal_record_idsは所有者設定と一致させる。source_run_idは取得処理ごとの一意なID、sequenceは入力元内で単調増加する整数。collected_atとas_ofには実際に根拠のある日時を使う。

```json
{
  "source_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  "source_run_id": "fictional-run-1",
  "mapping_version": "1",
  "base_revision": "GETで取得した値",
  "sequence": 1,
  "collected_at": "2026-09-10T12:00:00+09:00",
  "as_of": "2026-09-10T11:59:00+09:00",
  "enumeration_complete": true,
  "items": [{
    "asset_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "quantity": "123",
    "quantity_unit": "share",
    "external_record_ids": ["fictional-record-a"]
  }]
}
```

6. 返却diffのbefore/afterを確認する。ここではCSVは未変更。反映するならPOST `/api/v1/import-batches/{batch_id}/commit`へ `{"diff_hash":"previewのdiff_hash"}` を送る。取り消すなら同じbodyでcancelへ送る。
7. 応答を失ったら同じIdempotency-Key・bodyで再送する。新runで自動的に上書きし直さない。期限切れ時はバッチGETで確定結果を照合する。
8. GET positionsとGET batchesで結果を確認する。手入力で数量を変更するとmanual_overrideへ移る。所有者は現在の入力元GETのrevisionを指定し、PUTでconfigと明示的なresume_idsを送る。解除後に新しいpreviewを作る。

鮮度・対象・単位のエラーを0に置き換えない。412では最新入力と設定を再取得し、新しい取得runとしてpreviewをやり直す。元入力が古いままcollected_atだけを現在時刻へ付け替えない。


## WebUIで管理する

ヘッダーの「入力元・取込」を開く。所有者sessionにはinput-sources:manage、market-units:read、imports:readを必要とし、反映・取消にはimports:commitも必要となる。個人用モードの所有者にはこれらの権限がある。

「入力元を登録」で名前、専用tokenのsubject、鮮度上限、対象資産、数量単位、外部レコード集合を設定する。初期状態は無効であり、対象と単位を確認して有効にする。tokenそのものやMonex資格情報は入力しない。

入力元を選択すると対象と休止状態、取込履歴のbefore/afterを確認できる。未反映バッチの反映・取消は確認ダイアログ後にAPIへ送る。preview作成は取込クライアント側で行う。休止解除は「設定を編集・休止を解除」で、確認した対象を明示選択して保存する。

「最新状態を取得」は編集中フォームを保持する。元設定の版が変わっていたら、その古いフォームをそのまま保存せず、編集を控えて最新設定からやり直す。通信断では元の要求を保持し、同じ要求を再送して結果を確認する。結果の期限切れ、または再送時の権限不足（403）では、元の操作が完了している可能性があるため、照合が終わるまで再送・新規保存を止める。「現在の権限を再取得」または「別の資格情報で再認証」から復帰でき、元の要求は保持される。バッチ操作では、表示された元の入力元・バッチID・操作を確認して「元の要求を照合」を押す。imports:readが残っていれば、反映権限がなくても元バッチを取得できる。別の入力元の履歴を表示しただけでは照合完了にならず、元バッチの取得失敗・ID不一致時も確定できない。取得した反映状態を明示確認後に、元の要求と未送信編集を破棄して再開する。入力元設定の操作は最新設定を取得して照合する。自動的に新キーで保存し直すことはない。
