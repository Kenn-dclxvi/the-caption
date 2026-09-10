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
