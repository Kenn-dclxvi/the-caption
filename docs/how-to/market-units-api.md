# 入力API（Market Units / External Assets / Portfolio Basis）の起動と利用

2026-09-08時点では、3リソースのGET/PUT、入力定義、health、WebUIのセッション認証を実装している。[汎用数量取込API](../reference/quantity-import-api.md)を追加した。証券会社固有の自動入力はprivate側のクライアントで行い、本リポジトリには置かない。[API契約](../reference/api-v1.md)と[分離設計](../adr/ADR-0008-caption-api-and-private-importer.md)を参照する。

## セットアップの順序と環境分離

1. 本番checkout（3001）と開発checkout（3101）の入力データ・資格情報ファイルを分ける。
2. API client用のBearer tokenを発行し、資格情報ファイルの絶対パスを起動環境へ設定する。
3. 個人用WebUIを使う場合だけ、アクセスするoriginを明示する。
4. 実際の起動元（手動shell / launchd）へ設定を反映し、再起動する。
5. WebUI、認証付きAPIの読取、認証なし要求の拒否を別々に確認する。
6. Importerは入力元とsubject・対象ID・権限を確認後に接続する。接続確認だけで定期実行や書込みを有効化しない。

| 設定 | 用途 | 本番 / 開発の分離 |
| --- | --- | --- |
| `CAPTION_API_CREDENTIALS_FILE` | tokenのdigest・主体・権限・期限を保存したJSONの絶対パス | 別ファイル・別tokenを使う |
| `CAPTION_PERSONAL_UI_ORIGINS` | ログイン不要にする個人用WebUIの正確なorigin | 3001 / 3101を明示し、必要な入口だけ許可 |
| `CAPTION_API_SESSION_NAMESPACE` | ブラウザcookieの名前空間 | `prd` / `dev`（起動プロファイルの既定） |
| `HOST` | HTTP待受アドレス | `127.0.0.1`を維持 |
| `CAPTION_DATA_DIR` | API入力ルートの検証用切替 | 日次処理の入力先は切り替わらない |

API tokenはSMTPのアプリパスワード、LLMのAPIキー、証券会社のログイン情報とは別物。個人用WebUIを有効にしても、API client用tokenの設定は省略できない。

## 個人利用：ログイン不要のWebUI

Tailscale Serveで公開する個人用WebUIは、`CAPTION_PERSONAL_UI_ORIGINS` に利用するoriginを正確に指定して起動する。例は `https://<自分のTailscale DNS名>:3101`。複数指定はカンマ区切り。WebUIを開くだけで利用でき、アクセストークンの入力は不要。通常のAPI clientは引き続きBearer tokenを利用する。

この設定は指定originにアクセスできる人を所有者として扱うため、個人のTailscale内で使用する。HTTP入口はloopbackにbindし、Tailscale Serveから中継する。自動初期化は実際のloopback接続・指定Host・同一originの要求に限る。ブラウザの保護用cookieとCSRFは内部で管理し、期限切れ時は自動更新する。資格情報ファイルがなくても個人用WebUIは利用できる。設定を省略した環境では従来のtokenログインを維持する。

## 1. API client用の資格情報の作成

リポジトリルートで仮想環境を有効にし、Git管理外の資格情報ファイルを指定する。

```bash
source .venv/bin/activate
python -m src.app.entrypoints.input_api_credentials create \
  --file "$HOME/.config/the-caption/api-credentials.json" \
  --subject local-owner
```

標準出力の `token` はこのときだけ表示する。ブラウザのログイン欄またはAPI clientへ渡し、共有ログやGitへ保存しない。ファイルにはSHA-256 digestとID、主体、権限、有効期限だけを保存する。CLIが作成するファイルの権限は0600。既定の有効期間は30日、`--days` で1〜365日を指定できる。

既定では3リソースの読取り・置換・全消去と入力定義の権限を持つ。読取り専用にする場合は作成コマンドに `--permissions market-units:read,inputs:schema:read` を追加する。Market Unitsの置換には `market-units:read,market-units:replace`、全消去にはさらに `market-units:clear` が必要。同じsubjectでtokenを更新すれば、過去の保存要求を同じkeyで照合できる。別の利用者・サービスに同じsubjectを流用しない。

## 2. WebUI の起動

開発用checkoutで次を実行する。起動コマンドの配置は既存の `run.sh` に従う。

```bash
export CAPTION_API_CREDENTIALS_FILE="$HOME/.config/the-caption/api-credentials.json"
./run.sh collection-web-dev
```

既定の開発URLは `http://127.0.0.1:3101`。アクセストークン欄でログインする。ブラウザはtokenをlocalStorage/sessionStorageへ保存せず、認証後はHttpOnly・SameSite=Strictのcookieを使う。HTTPSではSecureも付く。更新にはセッションごとのCSRF tokenを付ける。sessionの上限は8時間と元tokenの有効期限の短い方で、server再起動後は再ログインする。

認証ファイル未設定・破損時は503で停止する。HTTP入口は既存Express、認証・3リソースの保存はprivate stdio接続の常駐Python workerが担当する。workerを直接ネットワーク公開しない。Pythonはリポジトリの `.venv/bin/python` を優先し、`CAPTION_API_PYTHON` で明示指定できる。

`run.sh` はCookieの名前空間を起動プロファイルから設定する。未設定・空文字なら本番は `prd`、開発は `dev` となり、同じブラウザでもCookieが衝突しない。独自の名前空間は `CAPTION_API_SESSION_NAMESPACE` で明示できる。複数環境を併用するときは異なる値を使う。

新規・変更する非空の価格CSV URLにはHTTPSと許可hostnameが必要。取得先を確認したうえで `CAPTION_API_PRICE_HOSTS` にカンマ区切りの正確なhostnameを設定して起動する。未設定では非空URLの新規設定・変更を拒否する。空文字への変更と、既存行の未変更URLは許可する。API保存自体ではURLを取得しない。

`CAPTION_DATA_DIR` はAPI/WebUIの入力ルートを切り替える検証用設定で、未指定ならこのcheckoutの `data`。日次処理の入力先まで一括変更する設定ではない。

### 本番3001の起動例

本番checkoutのルートから、発行済みの資格情報ファイルを指定する。以下のDNS名は実環境の名前へ置き換える。開発の3101 originを本番へ流用しない。

```bash
export HOST=127.0.0.1
export CAPTION_API_CREDENTIALS_FILE="$HOME/.config/the-caption/prd/api-credentials.json"
export CAPTION_API_SESSION_NAMESPACE=prd
export CAPTION_PERSONAL_UI_ORIGINS="https://<自分のTailscale DNS名>:3001,http://127.0.0.1:3001,http://localhost:3001"
./run.sh collection-web-prd
```

個人用モードが不要なら `CAPTION_PERSONAL_UI_ORIGINS` を設定せず、tokenログインを使う。外部入口は個人用Tailscale Serveからloopbackへ中継し、公開インターネットへ無認証UIを露出させない。

### launchdなどの常駐起動

shellの `export` は既存の常駐プロセスへ反映されない。launchdではplistの `EnvironmentVariables` に上記の設定を記載し、`ProgramArguments` と `WorkingDirectory` を対象checkoutへ固定する。資格情報ファイルは絶対パスを使い、tokenそのものをplistへ書かない。plist内の `$HOME` はshellのように展開されない。設定変更後は対象サービスを再起動する。

入力APIの設定は起動プロセスの環境変数からPython workerへ渡される。日次処理用 `.env.enc` のSMTP/LLM設定を変更しただけで、この設定も反映されたと扱わない。既存のplistや資格情報を置き換える際は、他の設定を保持する。

### 起動後の読取確認

- `GET /api/v1/health` の200は起動確認。個人用モードでは資格情報ファイルなしでも200になり得るため、API clientの認証や書込権限の証明にはならない。
- 設定したoriginのWebUIを開き、個人用モードなら自動sessionと3画面の取得を確認する。未設定ならtokenログインを確認する。
- API clientのBearer tokenで `GET /api/v1/market-units` と、必要な月別入力・入力元を読み取れることを確認する。
- cookieもBearerもない業務API要求は401、権限不足は403となることを確認する。値・token・応答全体を共有ログへ出さない。
- WebUIが予期せず認証画面になる場合は、実際の起動元のorigin設定・ポート・再起動を確認する。APIの401ではtokenの期限・失効・接続先、503では資格情報ファイルのパス・権限・形式を確認する。

## 3. API client からの保存

1. `Authorization: Bearer <token>` で `GET /api/v1/market-units` を呼び、documentと強いETagを保持する。
2. 各行の `asset_id` と7編集項目から `{ "items": [...], "clear_all": false }` を作る。新規行のIDはnull、数量は10進文字列とする。GET専用metadataとasset_keyはPUTへ送らない。
3. PUTに `Content-Type: application/json`、読込み時の `If-Match`、新しいUUIDの `Idempotency-Key` を付ける。
4. 成功応答の `changed / change_id / resource` を確認し、GETで次回用ETagを取得する。PUT応答にETagは付かない。

Bearerとsession cookieを業務APIへ同時に送らない。ブラウザ初期化用 `POST /api/session` だけはBearerを新sessionへ交換し、古いcookieを置き換える。`GET /api/session` はsession/CSRF情報、CSRF付き `DELETE /api/session` はログアウトを扱う。

通信断・500・503では、保存結果が不明なら同じ本文・If-Match・keyで再送する。412は下書きを保持して最新値と比較し、新しい編集として新keyで保存する。保存成功後のGET失敗は保存失敗とは区別する。完了結果は30日保持し、期限後も使用済みkeyを再実行しない。

全件削除は `items=[]` と `clear_all=true` を指定する。WebUIも全消去を確認してから同じAPIへ送る。

### 月別入力の保存

External Assetsは `/api/v1/external-assets`、Portfolio Basisは `/api/v1/portfolio-basis` で同じGET→If-Match付きPUT→GETの手順を使う。PUT本文は `months` と `clear_all` のみ。新規行の `entry_id` はnull、既存行のIDは月移動でも保持し、金額は10進文字列とする。

- 外部資産の例: `{"months":{"default":{"items":[{"entry_id":null,"category":"CASH_EXTERNAL","amount":"100.25","name":""}]}},"clear_all":false}`。nameは空文字も可。既存の空月 `{"items":[]}` はdefaultを抑止するため、そのまま保持する。
- 取得原価の例: `{"months":{"2026-09":{"entry_id":null,"total_acquisition_cost_jpy":"1000.25"}},"clear_all":false}`。金額は正数。月の移動では移動元IDを保持し、置換される移動先のIDと旧月は本文から除く。
- 全消去は `clear_all=true` と各リソースの `:clear` 権限が必要。外部資産は空月だけを残した場合も全消去扱いになる。

WebUIは3画面とも同じAPIを使用する。Save Entryは一覧の下書きに反映し、Save to Serverで保存する。保存中・結果不明・保存後GET失敗の間は新しい保存を抑止する。競合時は下書きをコピーしてからRefreshし、結果不明時はRetry Same Requestを使う。再認証でも下書きと未適用フォームは維持する。Refreshや保存で古くなったフォームは、コピーしてCancel後に開き直す。

## 4. 既存入力と保存管理

既存の有効なCSVを最初に読む際、CSVを書き直さず安定IDと管理情報を登録する。既存CSVの追加列をIDに紐付けて保持する。新APIの制約に合わない既存入力は503とし、切捨てやゼロ化で移行しない。実データへの適合は導入時に確認する。

CSVと隣接する `.market_units_api/<CSVファイル名>/` には安定ID、revision、変更履歴、再送記録、復旧journalを保存する。CSVと管理情報を一組でバックアップする。APIと日次readerは同じプロセス間lockを使い、途中停止時はjournalから確定処理を完了してから読む。

登録後のCSV手編集、ファイル消失、管理情報破損は503で検出する。管理情報を削除して新規入力として再開せず、保持したCSV・管理情報・バックアップをもとに復旧する。手編集の再取込用管理コマンドはこの段階では未実装。

External Assets / Portfolio Basisは、各JSONに隣接する `.monthly_inputs_api/<JSONファイル名>/` に同様の管理情報を保持する。JSONと管理情報を一組でバックアップする。初回GETでは元JSONのbytesを変えずIDを登録し、以後の変更・欠落を検出する。金額はJSON内でも10進文字列として保存する。日次readerは同じロックとjournal復旧を通り、既存domainの数値変換・月選択の契約を維持する。不正な旧入力・未知の項目は503とし、黙って切捨てない。

保存は現在の入力を更新する。既存の日次snapshotの上書き、過去日の埋戻し、評価・レポート実行は起動しない。旧 `POST /api/funds`、`POST /api/external-assets`、`POST /api/portfolio-basis` は428となるため、古いWebUI/clientを更新する。各PUTは1リソース単位の保存であり、3回のPUTを跨ぐ原子性は提供しない。

## 5. 一覧・失効・更新

```bash
python -m src.app.entrypoints.input_api_credentials list \
  --file "$HOME/.config/the-caption/api-credentials.json"
python -m src.app.entrypoints.input_api_credentials revoke \
  --file "$HOME/.config/the-caption/api-credentials.json" --id <credential-id>
```

一覧は平文tokenとdigestを出力しない。各API requestで現行の有効期限・失効・権限を確認し、失効後は関連sessionと再送も拒否する。ローテーションは同じsubjectで新規作成し、利用先を切り替えて旧IDを失効する。

## 6. Importer用tokenの最小権限

入力元の作成・対象設定は所有者が行い、通常の数量Importerには所有者tokenを渡さない。専用subjectは入力元のsubjectと完全一致させる。

```bash
python -m src.app.entrypoints.input_api_credentials create \
  --file "$HOME/.config/the-caption/prd/api-credentials.json" \
  --subject fictional-importer \
  --permissions imports:read,imports:preview,imports:commit
```

3リソースを扱うクライアントには、契約に応じて `external-assets:read,external-assets:replace,portfolio-basis:read,portfolio-basis:replace` を追加する。所有者管理・全消去権限は通常の取込には不要。数量反映は汎用取込APIで行う。発行時に一度だけ表示されるtokenは保護したクライアント設定へ保存し、資格情報JSONのdigestをBearer tokenとして使わない。

入力元の登録・対象確認・preview・commit・読戻しは [数量取込手順](quantity-import.md)を参照する。認証ファイルやtokenをGit・PR・スクリーンショットへ含めない。期限前に同じsubjectで新tokenを発行し、クライアントの切替と読取成功を確認してから旧IDを失効する。
