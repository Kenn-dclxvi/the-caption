# THE CAPTION API v1 契約と WebUI 操作対応

**Status: Implemented（段階B：3画面のAPI・WebUI。実データ導入は未実施）**

契約版: `0.1.0` / 作成日: 2026-09-08

## 1. 目的

[ADR-0008](../adr/ADR-0008-caption-api-and-private-importer.md) の段階Aとして、3画面の全操作を API の入力・出力・権限・保存効果・失敗条件へ対応付ける。APIの実装状況と、実データ導入・運用状況は区別する。

2026-09-08の実装範囲は、3リソースのGET/PUT、input-schema、healthの全8操作と3画面のWebUI移行。External Assets / Portfolio Basisにも安定ID・競合検出・再送記録・journal復旧を実装し、日次readerも同じロックと復旧処理を使う。汎用数量取込は[別契約](quantity-import-api.md)で追加した。private連携・実データ導入は別段階である。[起動・認証・運用手順](../how-to/market-units-api.md)を参照する。

機械可読契約の正本は [OpenAPI 3.1.1](./openapi-v1.json)。本書は、JSON Schema だけでは表現しきれない状態遷移と操作対応を定める。OpenAPI の `x-common-rules` / `x-business-rules` / `x-ui-coverage` もこの契約の一部である。二つの文書が食い違う場合は実装前に修正し、都合のよい一方を採用しない。

## 2. 対象と境界

対象は Market Units、External Assets、Portfolio Basis の全読取り・追加・編集・削除・全体保存、および入力定義・稼働確認の **5 path / 8 operation** とする。

全置換は1リソース単位の操作である。3回の PUT を跨ぐ原子性は提供しない。段階Cの汎用 change-set / import-batch は別契約として追加し、既存の PUT を private importer の無制限書込み経路にしない。入力元管理、認証情報の発行・失効、Monex 接続、レポート実行をこの版に実装済みのように記述しない。

保存の効果は最新の入力の更新まで。日次 snapshot の固定、評価、レポート送信、過去日の再生成を暗黙に起動しない。[ADR-0006](../adr/ADR-0006-market-units-snapshot-capture.md) の既存 snapshot 不変契約を保持する。

## 3. API 操作と必要権限

base path は `/api/v1`。表の権限はすべて必要であり、複数候補から一つを選ぶ意味ではない。

| Method / path | operationId | 必須権限 |
| :--- | :--- | :--- |
| GET /market-units | `getMarketUnits` | `market-units:read` |
| PUT /market-units | `replaceMarketUnits` | `market-units:read`、`market-units:replace` |
| GET /external-assets | `getExternalAssets` | `external-assets:read` |
| PUT /external-assets | `replaceExternalAssets` | `external-assets:read`、`external-assets:replace` |
| GET /portfolio-basis | `getPortfolioBasis` | `portfolio-basis:read` |
| PUT /portfolio-basis | `replacePortfolioBasis` | `portfolio-basis:read`、`portfolio-basis:replace` |
| GET /input-schema | `getInputSchema` | `inputs:schema:read` |
| GET /health | `getHealth` | 認証不要。状態と版だけ |

PUT の結果に全入力を返すため read 権限も要求する。この版の読取り権限はリソース全体への権限であり、行単位の制限付きtokenに全件 GET を許可しない。制限付き importer 用の読書きは段階Cで別途定義する。

全消去には同じリソースの `:clear` 権限を追加要求する。`clear_all` は意図の明示であり、認可の代わりではない。Market Units は items が空、Portfolio Basis は months が空、External Assets は **全月の項目総数が0** のとき `clear_all=true` を必須とする。それ以外は false とする。空月keyだけを残して clear 権限を迂回できない。空→空の保存も同じ規則で検証する。

## 4. 入出力の形と識別子

GET は全入力に `revision` / `storage_state` / `updated_at` を添えて返す。Market Units は `items` 配列、ほかの2種類は `months` 辞書を持つ。PUT body は items または months と `clear_all` だけを持ち、GET metadata をそのまま送り返さない。成功時は `changed` / `change_id` / `resource` を返す。

- 各市場連動資産には不変の `asset_id`、外部資産と月別取得原価にはそれぞれ不変の `entry_id` を発行する。
- PUT の新規行はIDを明示的に null とする。既存行はGETで取得したIDを維持する。未知の非null ID、重複ID、別リソースのIDは422とする。
- 全置換から省略した既存IDは削除する。名称、月、表示順の変更は同じIDで表す。`asset_key` / `audit_match_key` はこの不変IDと混同しない。
- 新規IDはPUT応答に含む。APIが正規化した値も応答で確認できる。ただし次回更新用ETagは成功後のGETで取得する。
- 未知の入力property、欠けた必須field、null不可のfieldへのnullは422。JSON objectの重複keyはパース時点で400とし、後勝ちで取り込まない。

新規未初期化だけは、仮想的な空documentとETagを返す。`storage_state=uninitialized`、`updated_at=null` とし、初回保存でreadyへ遷移する。一度登録されたファイルの消失・不正・未登録変更を新規の空入力に見せない。その場合は503とする。

## 5. 項目、正規化、保持条件

### 5.1 Market Units

7編集項目は `name / asset_class / currency / units / source_symbol / audit_match_key / csv_url`。全項目をPUTに含め、未設定可能な3文字列は空文字で表す。name / asset_class / currency はtrim後に空を許可しない。asset_class / currency はuppercaseする。source_symbolが空ならnameを採用する。

既存の互換asset_key生成規則を維持し、正規化後に一意であることを検証する。価格履歴の対応が曖昧になる変更を不変IDの再発行で隠さない。非UIの既存metadata（将来互換のenabled等）はIDへ紐付けて保持し、全置換のたびに落とさない。enabledを「評価対象外」の意味に変更しない。

分類・通貨の現UIは自由値を含み得るため、候補一覧を閉じたenumにしない。分類を保存できることと、その分類を評価できることは別である。csv_urlは保存する設定値であり、このPUT自体は外部取得しない。既存取得経路ではMUTUAL_FUNDSがCSV URLを使う。新規・変更する非空URLはHTTPSと `CAPTION_API_PRICE_HOSTS` の正確なhostname許可を必要とし、既存行の未変更URLは保持する。

### 5.2 External Assets

category / amount / name と entry_id を持つ。categoryはtrim後に必須。amountは **JPYの非負の絶対額**。原通貨額や買付余力を代入しない。nameはdomainの既存契約に合わせ空文字も許可し、表示時はcategoryで補完する。

month keyはdefaultまたは実在する年月形式（年0001〜9999、月01〜12）。項目のmonth変更ではentry_idを保持する。月内配列順はPUTに指定した順序を保存する。

**月を省略することと、月を空にすることを区別する。** 月が存在しないとdefaultを採用できる。月が存在してitemsが空なら、その月には外部資産がないという明示入力であり、defaultを抑止する。APIは空月を一律に削除しない。現UIの「最後の項目をDelete」は月keyも除去する操作として対応付ける。

### 5.3 Portfolio Basis

月ごとにentry_idと `total_acquisition_cost_jpy` を持ち、値は **JPYの正の10進文字列**。未設定は0でなくエントリ省略/削除で表す。総取得原価は市場連動資産全体に対する既存入力であり、単一口座の一部金額で上書きしない。

同じ月の編集はIDを維持する。Add Newで既存月に保存する場合も既存IDを用いた値の置換とする。別月へ移動するときは移動元IDを維持し、旧月keyを省略する。既存の移動先を上書きする場合は移動先の旧IDもrequestから省略し、削除を明示する。JSONの重複月keyやサーバーによる暗黙の合算は使わない。

### 5.4 数値と文字列

数値はJSON numberでなく10進文字列。整数部18桁、小数部12桁までとし、負数・指数・符号・桁区切り・空白・NaN・Infinity・bool・nullを拒否する。ゼロは数量と外部資産で許可し、総取得原価では拒否する。超過値は丸めず422とする。

正規化は値を落とさず行う。数値の不要な末尾0は正確な10進演算で除去できるが、浮動小数経由で桁を失わない。文字列はtrim/uppercase後にもschemaの上限を再検証し、Unicode uppercaseで長くなった場合も切捨てず422にする。C0/C1制御文字を許可しない。

これらは新API案の制約であり、現UIの数値widgetの制約から推定した値ではない。段階Bで既存入力との適合を確認し、非適合入力は個別に扱う。API保存の10進精度と、既存評価計算がfloatを使う箇所の精度を同一の保証として扱わない。

## 6. 保存、競合、再送

GETは対象リソースの強いETagを返す。PUTではその値を `If-Match` に一つ指定する。欠落428、不一致412、弱いtag・`*`・複数tagは400。revisionはサーバーが自動生成する空でない不透明なIDであり、形式の解釈・手動採番・編集は不要。同一性の比較だけに使い、リソースごとに変更保存で更新し、無変更なら更新しない。新規生成は接頭辞なしUUIDとし、既存の`rev_`付きID・履歴・再送記録は書き換えず有効として扱う。画面には生のIDを表示せず、保存成功や後続更新の有無を表示する。手編集や管理metadataの変更も競合検出の対象とする。

PUTの正規化・新ID付与は入力表現の変換になるため、成功PUTにETagまたはLast-Modifiedを付けない。次の更新に必要なETagはGETから取得する。この扱いは [RFC 9110 §9.3.4](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.3.4) に従う。

全PUTには `Idempotency-Key` を必須とする。本契約は引用符なしUUIDを採用するAPI固有の規則であり、確定したIETF標準ヘッダー構文だとは扱わない。

1. bodyサイズ・media type・JSON構文・header構文、現在の認証と必須権限、sessionのCSRFを検証する。
2. 認証主体ID＋method＋正規path＋keyで記録を照合する。fingerprintはobject key順・JSON空白を正準化した本文とIf-Matchを含む。配列順、文字列、10進文字列の表記をfingerprint作成時に変更しない。
3. 同じkey・同じfingerprintの完了記録があれば、現在の権限を満たす場合だけ元のstatus/bodyを返す。この照合は通常のIf-Matchの比較より先に行う。
4. 同じkeyでfingerprintが異なれば409。処理中の同一requestも409とRetry-After。別tokenへ更新しても同じ認証主体なら同じkeyの記録を照合できる。
5. 新規requestでは、lock内でIf-Match、schema、正規化後の制約、ID参照、現在の認可を検証し、入力・metadata・変更履歴・再送結果をまとめて確定する。

構文・認証で受理前に拒否した要求はkeyを予約しない。受理後の412/422もそのfingerprintに対する完了結果として保存し、修正した新しい編集は新keyで行う。保存成功後の応答喪失や503は結果不明になり得るため、同じkey/requestで結果を確定する。

完了結果は30日以上保持する。その後も使用済みkeyのtombstoneを保持し、結果を再生できない場合は409 `idempotency_result_expired` とする。key再利用で新規書込みを起こさない。全保持情報は本体の実行時データであり、Gitへ保存しない。

成功時の `changed=false` は正規化後の入力・保存管理状態が同じことを表す。`change_id=null` とし新しい資産変更は作らない。再送は初回のchange_idを再利用する。新規未初期化からreadyへの遷移は変更として記録する。

## 7. 認証と機密情報

個人用WebUIでは、Tailscale内から利用するoriginを `CAPTION_PERSONAL_UI_ORIGINS` へ指定し、token入力なしでbrowserSessionを初期化できる。実接続元がloopbackで、HostとOriginが指定originに一致する要求だけを許可する。指定originへアクセスできる利用者をpersonal-ownerとして扱い、cookie・CSRF・競合制御は維持する。この設定を省略した環境はtokenログインを使う。外部API clientのBearer認証はどちらの構成でも維持する。

serviceTokenまたはbrowserSessionのどちらか一つを使用する。OpenAPIのsecurity配列はORであり、同時に送った場合は400とする。OAuth flowやJWT形式を仮定しない。THE CAPTIONの資格情報とMonexの資格情報を混同しない。

cookie方式のPUTは `X-CSRF-Token` を必須とする。OpenAPI上のparameterは任意表記だが、`x-required-with=browserSession` と共通規則に従う条件付き必須項目である。Bearerだけの場合は不要。sessionはHttpOnly、HTTPSではSecure、SameSite=Strictとする。tokenはローカル管理CLIで発行・失効し、digestだけを資格情報ファイルに保存する。ブラウザはBearerを `POST /api/session` で交換する。この認証bootstrapだけは古いcookieとBearerを受け入れてsessionを置き換える。業務APIの認証方式ORは変わらない。

資産GETとエラーはCache-Control: no-store。入力定義は静的候補のみとし、既存資産由来の候補を無権限で漏らさない。UIは自分が読めるGET結果から候補を足す。healthは状態と版だけを返し、内部ファイルpath・口座情報を返さない。

## 8. エラー契約

エラーは `application/problem+json`。typeはabout:blank、titleはHTTP statusの標準名称または同義の翻訳、statusは実際の応答コードと一致させる。機械判定にはcodeを使い、detailの日本語文章を解析しない。request単位のinstanceはURN、フィールド位置はRFC6901 JSON Pointerで返す。これらの必須化は本APIの方針である。[RFC 9457](https://www.rfc-editor.org/rfc/rfc9457.html#section-3)

| HTTP | 代表code | clientの扱い |
| :--- | :--- | :--- |
| 400 | invalid_request | JSON/認証方式/headerの形を修正。重複JSON keyを送らない |
| 401 | authentication_required | 再認証後、結果不明要求は同じkeyで照合 |
| 403 | permission_denied / csrf_invalid | 必要権限またはsessionを確認。自動再送し続けない |
| 409 | idempotency_key_reused / idempotency_in_progress / idempotency_result_expired | 内容違いは新しい編集として扱う。処理中だけRetry-Afterに従う。期限切れは結果照合へ戻す |
| 412 | revision_mismatch | 最新GETと下書きを比較し、明示的に再編集して新keyで保存 |
| 413 / 415 | payload_too_large / unsupported_media_type | サイズまたはmedia typeを修正 |
| 422 | invalid_input / normalized_value_invalid | errorsの位置を表示して修正。unknown_identifier等の詳細はfield code |
| 428 | precondition_required | 対象GETのETagを付ける |
| 429 | rate_limited | Retry-Afterに従う |
| 500 / 503 | internal_error / input_store_unavailable | 未保存と決めつけず、結果不明なら同じkeyで照合 |

422では duplicate_id / unknown_identifier / duplicate_asset_key / invalid_month / invalid_decimal / invalid_clear_intent / normalized_value_invalid 等をerrors[].codeに使用する。実入力・秘密情報・内部pathをdetailへ不用意に写さない。healthの503だけは資産エラーではなくHealth schemaを返す。

## 9. WebUI 操作対応表

根拠は [App.tsx](../../src/web/market_units_editor/src/App.tsx) と [server.ts](../../src/web/market_units_editor/server.ts)。設計時点の32操作を列挙する。表内の行番号は移行前の根拠を示し、現行行番号ではない。対応するv1契約の実装状況は第1節を参照する。Add/Edit/Deleteの欄のPUTは **Save to Serverで初めて発行する保存先** であり、各ボタンで即座にHTTP書込みする意味ではない。

| Coverage ID | UI操作 | API / データ依存 | 保存・表示の契約 | 現実装の根拠 |
| :--- | :--- | :--- | :--- | :--- |
| `UI-COM-01` | 初期表示で3リソースを読込む | `getMarketUnits` / `getExternalAssets` / `getPortfolioBasis` | 非表示タブも取得。リソースごとにETagを保持 | `App.tsx:154` |
| `UI-COM-02` | タブ切替・一覧へ戻る | 通信なし | 通信不要。各リソースの保存前下書きを維持 | `App.tsx:551` |
| `UI-COM-03` | 表示中リソースのRefresh | `getMarketUnits` / `getExternalAssets` / `getPortfolioBasis` | 対象GETのみ。編集中フォームの古いrevisionを無言で付け替えない | `App.tsx:154` |
| `UI-COM-04` | Cancel | 通信なし | 開いたフォームだけ破棄。既に一覧へ適用した下書きは巻き戻さない | `App.tsx:839` |
| `UI-COM-05` | 件数・保存状態・通知の表示 | `getMarketUnits` / `getExternalAssets` / `getPortfolioBasis` | GET内容と通信/下書き状態から表示。内部絶対pathをAPIへ要求しない | `App.tsx:507` |
| `UI-COM-06` | 月順・分類候補の表示 | `getMarketUnits` / `getExternalAssets` / `getPortfolioBasis` / `getInputSchema` | 月降順/default末尾。静的候補と読取り権限のある既存値を結合 | `App.tsx:68` |
| `UI-COM-07` | フォームを開いたままSave to Server | `replaceMarketUnits` / `replaceExternalAssets` / `replacePortfolioBasis` | 一覧の下書きだけ保存。未適用フォームを含めない | `App.tsx:608` |
| `UI-COM-08` | 読込/保存の成功・失敗表示 | `getMarketUnits` / `getExternalAssets` / `getPortfolioBasis` / `replaceMarketUnits` / `replaceExternalAssets` / `replacePortfolioBasis` | Problem Detailsで判定。保存成功後GET。結果不明と未保存を区別 | `App.tsx:254` |
| `UI-MU-01` | 一覧読込・Refresh・保存順表示 | `getMarketUnits` | items配列順を保持 | `App.tsx:154` |
| `UI-MU-02` | Add New → Save Entry | `replaceMarketUnits` | 7項目の下書きを末尾へ追加。新規asset_id=null | `App.tsx:217` |
| `UI-MU-03` | Edit → Save Entry | `replaceMarketUnits` | 同じ位置・同じasset_idで7項目を編集 | `App.tsx:229` |
| `UI-MU-04` | Delete | `replaceMarketUnits` | 対象IDを下書きから除去。残りの順序を維持 | `App.tsx:249` |
| `UI-MU-05` | Save to Server | `replaceMarketUnits` | items全体を条件付きPUT | `App.tsx:254` |
| `UI-MU-06` | 全行削除後の保存 | `replaceMarketUnits` | items=[]・clear_all=true・追加clear権限 | `server.ts:140` |
| `UI-MU-07` | フォーム表示・入力・Cancel・数量表示 | `getMarketUnits` / `getInputSchema` | 表示の丸め値で元の10進文字列を上書きしない。入力中は通信不要 | `App.tsx:697` |
| `UI-EA-01` | 全月/defaultの読込・一覧 | `getExternalAssets` | entry_idを識別子にする。month::indexを使わない | `App.tsx:106` |
| `UI-EA-02` | Add New → Save Entry | `replaceExternalAssets` / `getInputSchema` | 最新既存月、なければdefault。初期category=CASH_EXTERNAL。月末尾へ追加 | `App.tsx:275` |
| `UI-EA-03` | 同月内でEdit → Save Entry | `replaceExternalAssets` | 同じentry_idを除去後に末尾へ追加する現行順序を表現 | `App.tsx:329` |
| `UI-EA-04` | 他月/defaultへ移動 | `replaceExternalAssets` | 同じentry_idを移動先末尾へ。移動元の最後の行なら元月keyを除去 | `App.tsx:331` |
| `UI-EA-05` | Delete・最後の項目削除 | `replaceExternalAssets` | 対象IDを除去。空になった元月keyも除去するUI操作 | `App.tsx:365` |
| `UI-EA-06` | Save to Server | `replaceExternalAssets` | months全体を条件付きPUT | `App.tsx:391` |
| `UI-EA-07` | 全項目削除後の保存 | `replaceExternalAssets` | months={}・clear_all=true。空月だけ残す場合も総項目0ならclear権限が必要 | `App.tsx:365` |
| `UI-EA-08` | 既存の空月を表示・保持 | `getExternalAssets` / `replaceExternalAssets` | items=[]を維持。月の省略とは違いdefaultを抑止する | `server.ts:84` |
| `UI-EA-09` | フォーム表示・入力・Cancel・円表示 | `getExternalAssets` / `getInputSchema` | 入力中は通信不要。amountはJPYの10進文字列 | `App.tsx:918` |
| `UI-PB-01` | 全月/defaultの読込・一覧 | `getPortfolioBasis` | 月降順/default末尾、1月1値 | `App.tsx:124` |
| `UI-PB-02` | Add New・既存月への追加 | `replacePortfolioBasis` / `getInputSchema` | 最新既存月、なければdefault。既存月なら同じentry_idで値を置換 | `App.tsx:412` |
| `UI-PB-03` | Edit → Save Entry | `replacePortfolioBasis` | 同じentry_idを保持し総取得原価を更新 | `App.tsx:435` |
| `UI-PB-04` | 月キー変更・既存移動先の置換 | `replacePortfolioBasis` | 移動元IDを維持。旧月を省略し、置換される移動先IDも省略する | `App.tsx:454` |
| `UI-PB-05` | Delete | `replacePortfolioBasis` | 月keyとentry_idを下書きから除去 | `App.tsx:474` |
| `UI-PB-06` | Save to Server | `replacePortfolioBasis` | months全体を条件付きPUT | `App.tsx:486` |
| `UI-PB-07` | 全月削除後の保存 | `replacePortfolioBasis` | months={}・clear_all=true・追加clear権限 | `App.tsx:474` |
| `UI-PB-08` | フォーム表示・入力・Cancel・円表示 | `getPortfolioBasis` / `getInputSchema` | 入力中は通信不要。総取得原価は正の10進文字列 | `App.tsx:1035` |

共通Refreshの行に3GETを列挙しているのは選択可能な対象を示す。全件一斉再取得を要求しない。初期表示だけは現行どおり3GETを使用する。通信不要の2操作も `x-ui-coverage` に空operationIdsとして含め、欠落と区別する。

## 10. 下書きと保存後のUI移行

各リソースは、GET時のbase document/ETag、一覧に適用済みの下書き、開いている未適用フォームを分けて保持する。Cancelはフォームだけを閉じる。Save to Serverは一覧の下書きだけを送る。

保存中は対象リソースの一覧への変更・Refresh・重複Saveを抑止し、応答で新しい未保存編集を消さない。フォームが開いていればその内容を保持するが、保存/Refreshでbaseが変化した場合は古いフォームとして識別する。編集対象IDと元の値を再照合するまで、古いフォームを新ETagの下へ無言で適用しない。

PUT成功後は返却されたIDと保存結果を保持し、GETで最新documentとETagを取得する。GETが別clientのより新しい変更を返す可能性があるため、自分が保存したrevisionと最新revisionを区別する。GET失敗時は「保存済み・最新表示の取得失敗」とし、PUTまで失敗したと表示しない。次回編集はGET成功後に行う。

412では下書きを保持して比較を求める。通信切断でPUT結果が分からないときは「結果確認中」とし、同じkey/requestで照合する。単にREADYを表示して未保存変更がないと見せない。

## 11. 現行との差分と互換経路

| 現状 | 新契約と移行時の扱い |
| :--- | :--- |
| 3組のGET/POSTがCSV/JSONを直読み書き | WebUIは新GET/PUTへ移行。旧経路を使う間も同じ認証・検証・保存serviceへ委譲 |
| 配列index、month::index、月keyで編集対象を識別 | 不変IDを移行時に発行し、全置換で維持 |
| APIにより非数値・非正数を0へ変換 | 新APIでは明示422。既存不正データはGETで0へ偽装せず、移行の確認対象 |
| UIは月13等をregexで受理し得る | 月01〜12へ統一 |
| UIの外部資産は負額を受理し得る | domainに合わせ非負へ統一。実入力の符号を変更して移行しない |
| UIでは外部資産name必須、domainは空を許可 | domainに合わせ空を許可し、categoryで表示補完。案内と必須制約を分ける |
| 数値をJS Numberや表示丸めで扱う | API wireは10進文字列。正確な入力を表示値で上書きしない |
| 成功応答を取り込まず再GETしない | 保存済み結果と次回ETagを取得し、保存/再読込み失敗を区別 |

最終移行先として、旧GET /api/funds、/api/external-assets、/api/portfolio-basis はそれぞれ新GETへ対応する。旧POST3本は新PUTの共通serviceへ対応する。旧GET /api/healthは新getHealthへ対応する。

旧POSTの無条件書込みを互換性の名目で残さない。移行するWebUIはGETで版を取得し、旧adapterを残す場合も条件情報を渡す。情報を渡せない旧clientは428として更新を案内し、サーバーが最新revisionを勝手に補って上書きしない。

現在は旧GET3本も共通serviceへ委譲し、IDとrevisionを省いた互換形状を返す。旧POST3本は認証・書込み権限・sessionのCSRFを確認したうえで428 `client_upgrade_required` を返す。旧clientによる無条件上書きは行わない。金額・数量は旧GETでも正確な10進文字列として返す。

## 12. 実装時の受入条件

以下は段階B全体の完了条件である。

Market Units導入時の検証記録（今回の全体件数ではない）：2026-09-08の修正後全Pythonテストは1,049件成功・5件スキップ、TypeScript検査・production build・UI protocol 13件が成功した。Pythonテストには転送時の本文膨張も検証する実HTTP 12件、API service 63件、入力domain 140件、保存repository 23件が含まれる。資格情報CLIの作成・一覧・失効は一時ディレクトリで確認した。EA/PBの再認証時の下書き保持・CSRF回復も修正したが、その画面effect自体のブラウザ実行テストは未実施。これはMarket Units導入時のローカル検証記録であり、その時点では残り2リソースが未実装だった。

External Assets / Portfolio Basis移行では、実HTTP経由の保存・再起動後再送、月移動とID維持、数値精度、全消去権限、競合、登録済みファイルの欠落・手編集検出、journal各段階の停止からの日次読取り復旧を追加検証した。UI通信テストは2画面の下書き・再認証・結果不明・保存後GET失敗を含む。実ブラウザでは一時データでログイン不要の初期表示、月移動・既存月置換・保存後再読込み・未適用フォームの保護を確認した。実アーカイブを置かない分離worktreeではアーカイブ依存の8テストがスキップされる。実データ導入、Monex接続、定期運用は未実施。

| 検証ID | 条件 |
| :--- | :--- |
| API-A01 | 32行の操作対応をすべて再現でき、対象外操作を既存対応数へ含めない |
| API-A02 | 7項目全保存、ID維持、新ID付与、並び順、月移動、既存月置換が契約どおり |
| API-A03 | 空月によるdefault抑止と月削除によるfallbackを区別する |
| API-A04 | 3リソースの全消去に意図・clear権限が必要。空月による迂回がない |
| API-A05 | 未知/重複ID、重複asset_key、不正月、数値型・精度・符号、正規化後上限を共通側で拒否 |
| API-A06 | stale/weak/wildcard/multiple/missing ETagを規定の状態で拒否し、正規化PUTにETagを返さない |
| API-A07 | 同key再送・異内容・処理中・token更新・結果期限切れで二重反映しない。失効/権限縮小後の再送も拒否 |
| API-A08 | 各保存段階の停止から一貫した状態へ復旧し、再送記録と入力結果がずれない |
| API-A09 | フォーム未適用値を保存せず、古いフォームと新ETagを黙って組み合わせない |
| API-A10 | 500/503やGET失敗を空データ/未保存と誤表示しない。既存の日次snapshotを変更しない |
| API-A11 | cookie/Bearer/CSRF/必須権限が同じserviceを通り、旧経路で迂回できない |
| API-A12 | OpenAPI 3.1構造、全ref、request/response例、操作対応IDが検証できる |

## 13. 段階Bの方式と残作業

Market Unitsは既存ExpressをHTTP入口とし、private stdio接続のPython application serviceで認証・保存する。既存CSVに隣接する管理情報で安定ID、revision、履歴、再送結果を保持し、プロセス間lockと永続journalで停止から復旧する。日次readerも同じlockを使用する。token/sessionと価格URLの扱いは第5・7節およびhow-toに定めた。External Assets / Portfolio BasisはJSONに隣接する `.monthly_inputs_api/<JSONファイル名>/` にID・revision・履歴・再送結果を保持し、JSONと管理情報をjournalで復旧する。既存JSONの初回GETは元ファイルを書き換えず管理情報だけを登録する。保存時も金額は10進文字列を維持し、既存の日次domainが評価用数値へ変換する。外部資産の旧flat `items` 形式はdefault入力へ対応付け、空月は保持する。数量限定の段階Cは[汎用数量取込API](quantity-import-api.md)を参照する。実データ導入と対象拡張は後続である。

文字数・数値桁・件数・body上限は提案値であり、既存データへの事前適合検査を受入条件とする。合わない入力を切捨てたり、今回実口座データを調べて補ったりはしない。定期実行の成立条件はADR-0008の段階Eで扱う。

## 14. 関連仕様

- [OpenAPI 3.1.1公式仕様](https://spec.openapis.org/oas/v3.1.1.html)
- [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12/json-schema-validation)
- [RFC 9110 If-Match](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.1)
- [RFC 6585 428 Precondition Required](https://www.rfc-editor.org/rfc/rfc6585.html#section-3)
- [RFC 9457 Problem Details](https://www.rfc-editor.org/rfc/rfc9457.html)
- [ADR-0008](../adr/ADR-0008-caption-api-and-private-importer.md)

月別WebUIで `idempotency_result_expired` を受けた場合は照合待ちへ移る。元の要求・一覧の下書き・未適用フォームを保持し、Refreshは比較用の最新documentだけを取得する。新規PUTと同一キーの再送は停止する。利用者が内容を比較し、残したい編集を控えたうえで明示確認すると最新documentを編集の基準へ採用する。未適用フォームは古い版として保持し、再編集・保存は利用者が明示的に行う。期限切れは未保存を意味しない。
