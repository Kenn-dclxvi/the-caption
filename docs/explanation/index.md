# Part 4: Explanation

## 1. Project Philosophy (基本理念)

### 1.1 The Caption Concept ("The Governed Evolution")
**「騒がしい市場の中で、静かに自分の資産を俯瞰する」**

THE CAPTION は、資産の動きを「美術館のキャプション」のような静謐なレポートへと変換するアーカイブシステムです。 単なる集計を超え、数値の裏側にある因果を AI が鑑定し、知的で落ち着いた資産管理体験を提供します。個人投資家にとって最大の敵は、暴落そのものではなく、日々の値動きに翻弄されて「市場から降りてしまう心」です。 長く市場に居続けるためには、過剰な通知と数字の洪水から、自身の精神を守り抜く必要があります。
その根底には、市場という荒波の中で**投資家としての寿命を延ばす**ための、4つの生存戦略が存在します。

1. **解析の委譲 (Delegation of Analysis)** 現代の市場において、情報の量は一人の人間が処理できる限界を超えています。 不完全な情報収集は、誤った判断（ノイズへの過剰反応）の元凶です。 本システムは、膨大な因果関係の処理を AI に完遂させることで、人間の能力では不可能な**「網羅的な情報の選別」**を実現し、判断の精度を担保します。

2. **ノイズからの絶縁 (Insulation from Noise)** 絶え間なく流れるニュースや扇動的な見出しは、私たちの平穏を静かに侵食します。 私たちは情報の取得と分析をシステムへ委任することで、自身の生活空間から「市場の喧騒」を物理的に切り離します。 必要なのは感情的な物語ではなく、自身のポートフォリオに基づいた客観的な鑑定書（THE CONTEXT）だけです。

3. **主権の回復 (Reclaiming Sovereignty)** 「世界がどう動いたか」を知るために、あなたの朝を費やす必要はありません。 投資は人生を豊かにするための手段であり、そのために人生の時間を差し出すのは本末転倒です。 複雑な解析をアウトソースし、空いた時間を「知るため」ではなく「生きるため」に使うこと。 それが、市場と長く付き合うための唯一の持続可能な姿勢です。

4. **支配による平穏 (Serenity through Dominance)** 「防御」とは、攻撃に耐えることではありません。 攻撃が届かない場所に身を置くことです。 本システムは、リスク資産（Exposure）と安全資産（Iron Bank）を統合管理し、市場変動の影響を数学的に減衰（Damping）させます。 「資産の半分は無傷である」という物理的な事実を毎日確認すること。 それこそが、感情を市場から切り離し、真の平穏を手にするための唯一の解です。

### 1.2 Design Philosophy ("Cushioned Fortress")  
v2.0では、市場のボラティリティから投資家の精神的平穏（Serenity）を守るため、
**「Cognitive Flow（認知フロー）」** に基づいたUI設計 "Cushioned Fortress" を採用しています。
**Visual Hierarchy (視覚的階層)**情報の提示順序と視覚的重み（コントラスト・サイズ）を操作し、視点を「超長期（真実）」から「短期（ノイズ）」へと段階的に誘導することで、感情の振幅を抑制します。

1. **Zone 1: The Foundation (基盤)**
    * **Safe Ratio**: 資産全体の安全性（Iron Bank比率）を最上部に配置。
    * **Total Return**: 画面右上に「通算の累積利益」をゴールド色で表示。 日々の変動に対する最強の精神的防壁（Shield）として機能します。
2. **Zone 2: Frontline (現実)**
    * **Net Assets**: リスク資産の現在地を最大フォントで提示。
    * **The Cushion (YTD/MTD)**: その直下に「年初来/月初来トレンド」を配置し、視覚的に強調。 短期的な変動を見る前に「長期的な順順調さ」を認識させます。
    * **The Fact (Day Diff)**: 前日比（ノイズ）は、最下段に薄いグレーで小さく配置。 情報の優先度を意図的に下げています。

---

## 2. Architecture Concepts (アーキテクチャ概論)

### 2.1 Collection-Primary Sovereign Ledger (v4.2)

v4.2 では、資産データの主従関係を反転した。旧来の証券会社サイトのスクレイピングは「日次レポートを動かすための必須入力」ではなく、正規台帳を監査するための従系である。

「正典」は計算元（評価の入力として何を信じるか）、「正本」は出力（確定した状態をどこが保持するか）を指す。両者は別レイヤーである（[ADR-0004](../adr/ADR-0004-collection-primary-v4.md) / [ADR-0002](../adr/ADR-0002-ledger-native-ssot.md)）。

* **SSOT A — Market Units（計算元の正典）**: `data/collection/market_units.csv`。株式、投資信託、コモディティ等の保有数を正典とする。
* **SSOT B — Absolute Amounts（計算元の正典）**: `data/external_assets.json`。現金、企業型DC、その他外部資産の絶対額を正典とする。
* **統合結果**: `UniversalIngester` が両正典を統合し、`ShadowLedger` (`data/v4_shadow_ledger.json`) を生成する。同一実行内では下流（`daily_metrics` / 表示 / 配信）がこれを入力とする。
* **Canonical Ledger（出力の正本）**: 日次で確定して保存する `data/current/ledger_YYYYMMDD.json`。週次/月次の参照先であり、翌営業日以降の `DAY` 比較の基準となる。
* **Audit, not Dependency**: 監査層は外部総額との差分を観測するだけであり、取得失敗は `[AUDIT]` 警告として縮退する。

この設計により、外部サイトのログイン失敗、メンテナンス、CSV仕様変更、画面DOM変更が 20:00 の日次配信を止める構造的リスクを排除する。

### 2.2 Sovereign Ledger Concept   (脱・CSV依存 / Legacy)
本システムは、外部ソース（証券会社が提供するCSV）への依存を最小限に留め、システムが自律的に生成・管理する JSON データ (`Ledger`) を「正」とするアーキテクチャ (**Ledger Native**) へ移行しました。

* **旧アーキテクチャ (Legacy CSV-Dependency)**:
    * データ源泉: 毎回、過去の大量の CSV ファイルを走査して履歴を構築。
    * 課題: 外部データの不整合（合計が合わない、前日比が欠損している等）の影響を直接受ける。
* **新アーキテクチャ (Sovereign Ledger)**:
    * データ源泉: 当日の CSV から生成した `current/ledger_YYYYMMDD.json` が唯一の正典。
    * メリット: 外部データの不整合を自律計算で排除し、巨大な CSV アーカイブを再読み込みする必要がないため高速。

### 2.3 System Architecture Overview (Trinity Architecture)
システム全体を「三位一体の分離（The Trinity Separation）」の思想に基づき、以下の3層に厳密に分離し、責務を疎結合化しています。
* **Logic (頭脳)**: `V4PortfolioEngine`, `UniversalIngester`, `PortfolioEngine`, `LedgerManager`, `LedgerFactory`, `DispatchController`, `MarketCurator`, `KnowledgeManager` 等。 純粋なビジネスロジックと計算、ドメイン知識に基づくオブジェクトの生成に専念する。
* **Infrastructure (運搬)**: `Notifier`, `LedgerRepository`, `MarketDataFetcher`, `LlmTransporter`, `ContextRepository`, `ChronicleRepository` 等。 ファイルI/O、文字列解析（正規表現パース）、ネットワーク通信、外部APIとの物理的な接続、および鑑定結果の永続化を担う。
* **View (描画)**: `V4ContentRenderer`, `ContentRenderer`, `ViewModel`, `AlertRenderer`（システムアラート用）等。 データの視覚表現へのマッピングのみを行い、ロジック演算を排除した「愚直なるビュー（Dumb View）」として振る舞う。

### 2.3.1 COLLECTION Domain (v4.2 Primary / Legacy Standalone)
v4.2 では **COLLECTION** は証券会社ドメインと並列の独立ドメインではなく、日次正規台帳の主要入力へ昇格した。単独レポート経路は本リポジトリに含まない。

* **主系の原則**: `data/collection/market_units.csv` は `UniversalIngester` の SSOT A であり、ブラウザ自動化による外部取得に依存しない。
* **共有リソース**: BaseRenderer（Slate Symphony カラーパレット）、MailSender、src/lib/ ユーティリティのみを共有する。
* **データストア**: `data/collection/market_units.csv`（ファンド定義）と `data/collection/history/`（基準価額履歴）を独立管理する。
* **採用背景**: 外部ファンド（MUFG 等）は証券会社側の CSV 取得・鮮度判定の仕組みが適用できないため、保有数とローカル履歴に基づく自律評価を選択した。

### 2.4 Pipeline Strategy (V4 vs Legacy)
システムは2つの異なる集計パイプラインを持ち、目的に応じて使い分けます。
* **V4 Collection-Primary Pipeline**: `market_units.csv` + `external_assets.json` から `ShadowLedger` を生成し、AI鑑定と単一HTMLメールへ進む標準日次経路。
* **Fortress Pipeline (v2.0)**: 外部資産（Iron Bank）を統合した「要塞」としての集計。
    * **Total Definition**: `Exposure (Risk Assets)` + `Iron Bank (Safe Assets)`
    * **Damper Effect**: 外部資産のバッファにより、市場変動の衝撃を数値的に緩和して認識させます。

### 2.5 Caching Strategy (鑑定結果と総括の永続化)
AI による日次の因果鑑定および月次の歴史的総括は計算コスト（トークンおよび時間）が高いため、一度生成された結果はそれぞれ `data/current/context_YYYYMMDD.json` および `data/current/chronicle_YYYYMM.json` として永続化されます。

* **運用上の利点**:
    * **コスト最適化**: `-u` オプションを使用することで、一度作成したレポートの再送時に AI API を呼び出さず、既存の結果を再利用できます。
    * **一貫性の保持**: 同じ日付や月のレポートを複数回送信する場合でも、 AI の確率的な出力変動を排除し、常に同一の「鑑定文・総括文」を提供し続けることが可能です。
    * **オフライン耐性**: ネットワーク遮断時でも、過去に生成済みの結果であれば配信プロセスの継続を許可します。

### 2.6 Knowledge Banking Strategy (知見の蓄積と永続化)
日々の AI による鑑定結果（Insight）は、単なる一過性の通知として消費されるだけでなく、`data/knowledge_bank.md` へ自律的に追記・蓄積されるアーキテクチャを採用しています。

* **運用上の利点**:
    * **歴史的文脈の形成**: 日々のテーマ（Theme）、概要（Overview）、推察（Insight）、および防壁の評価（Shield）が時系列順に並ぶことで、ポートフォリオの変動という「点」が、市場の歴史という「線」として可視化されます。
    * **自律的記録**: `DispatchController` がレポート配信と同時に `KnowledgeManager` を呼び出すことで、開発者の手を煩わせることなく完全自動でナレッジが構築され続けます。

### 2.7 Monthly Chronicle Orchestration (v3.0 拡張)
月間の構造的変化を総括する「Monthly Chronicle」は、日次の「点」の分析を「線」へと統合するオーケストレーション層である。

* **指揮系統の分離**: 日次処理と月次処理（`src/app/entrypoints/monthly_main.py`）のエンジンを完全に分離。 日次のノイズに左右されず、月次基準での純粋な歴史的総括を行う。
* **Lazy Polling による確定待ち**: 月初の特定時刻に強制実行するのではなく、前月末データが `VERIFIED`（確定）状態になるまで自律的に待機し、条件が整った瞬間に一度だけ配信を行う（`MonthlyGuardRail`）。
* **Knowledge Base の再蒸留**: `KnowledgeManager` に蓄積された 1 ヶ月分の日次 Insight を入力ソースとし、AI がそれらを構造的に再解釈（Re-distillation）することで、単なる統計値以上の「月間の文脈」を自律生成する。

---

## 3. The Curator Engine (鑑定・推論エンジン)

### 3.1 Context Engine & Exhibition Protocol (展示の概念)
日次レポートを単なる「資産状況の通知」から、**「市場という事象を読み解くための展示会（Exhibition）」** へと昇華させます。

* **Role**: AIは「分析官」ではなく、美術館の **「チーフ・キュレーター（学芸員）」** として振る舞う。
* **Tone**: 数字の羅列（Indexの役割）を排除し、**「言葉による文脈（Context）」** を主役とする。
* **運用哲学**: "Open Daily" (継続性の絶対優先)。 AIの出力が文字数制限を多少超過しても、エラーやリトライ（再生成）で配信を止めてはならない。 「完璧だが閉まっている美術館」より、**「多少不恰好でも毎日開いている美術館」** の方が価値が高い。

### 3.2 Causality & Market Mechanics (金利感応度・ベクトル解析モデル)
資産変動を以下の3つのベクトルの合成として解析し、その「合力」を結論とします。

1. **External Pressure (金利要因)**: 米10年債利回り等の騰落が、価格と為替をどの方向に押し出したか。
   * 上昇：バリュエーションに対する「重力」および、ドル買い（円安）の「圧力」として機能する。
2. **Price Vector (価格要因)**: 金利感応度や個別決算による、現地通貨建てでの純粋な資産価格変動。
   * 金利上昇局面では、将来キャッシュフローの現在価値割引により、ハイテク株に強い下落ベクトル（バリュエーション調整）が発生する。
3. **Currency Vector (為替要因)**: 日米金利差等による為替差損益が、円建て評価額に与えた物理的影響。

**解釈パターン**:
* **相殺 (Offsetting)**: `|Price Down| ≒ |Currency Up|`。 現地価格は下げたが、円安がそれを補った状態。 ポートフォリオ全体は「横ばい（Rotation）」と解釈する。
* **増幅 (Amplification)**: `|Price Down| > |Currency Up|`。 ハイテク株の調整幅が円安の恩恵を上回る状態。 **「防御機能の不奏功」**として冷徹に評価する。

### 3.3 US Market Holiday Causality Model (米国市場休場日の因果モデル)

**背景**:
JP基準日の前日が米国市場の休場日（連邦祝日・週末）であるケースでは、新規の米国市場データが存在しない。この場合、日本の投資信託の基準価額は「前日の米国株終値」ではなく「為替（USD/JPY）の変動」を主因として更新される。

**問題**:
`determine_us_market_date()` が「直近取引日」のみを返す設計では、AIが「存在しない市場（休場日）」を参照してしまう構造的な誤謬（Logical Fallacy）が生じる。具体的には「2/16（Presidents' Day）の米国市場が動いた」という事実に反する因果推論が生成されるリスクがある。

**解決策（v2.4実装）**:
`TimelineController.get_us_market_context()` により、AI への因果推論指示を以下の2ルートに分岐させる。

| ケース | `is_holiday` | AIへの指示方針 |
| :--- | :--- | :--- |
| 通常取引日 | `False` | 前日の NYSE 終値を参照してベクトル解析を行う |
| 米国市場休場日 | `True` | 「当日は休場. 基準価額変動の主因は為替のみ. 参照は直近取引日（`trading_date`）を使用」を明示注入 |

### 3.4 The Insight & Shield Paradigm (死角と防壁の鑑定)

単なる資産推移の要約を超え、システムはAIに対して「高度な金融インテリジェンス」としての役割を強制します。`src/config/prompts.py` に定義された出力スキーマにより、以下の高度な鑑定を日々の推論に組み込んでいます。

* **Insight (死角分析)**: 保有資産（内部）の解説を厳禁とし、ポートフォリオ「外」の市場トレンドや逆相関セクターを自律的に特定させることで、投資家の視野狭窄を防ぎます。
* **Portfolio Audit (方針監査 / v3.5)**: コア方針、現金比率、3〜5年停滞耐性を月次 CHRONICLE で監査します。日次 CONTEXT では扱わず、コモディティの防壁性能とも分離して、投資方針の維持・観測・再検証の切り分けに限定します。
* **Shield Evaluation (ヘッジ機能の相対評価)**: 金・銀・プラチナなどのコモディティ資産を「独立監視枠」として設定。グロース株（ハイテク等）の下落圧力に対して、どの貴金属が最も有効な非相関資産として機能したかを冷徹に比較・特定させます。
* **Evidence Validation (AI出力の型検証)**: AI が出力した `causality_vector` / `shield_status` / `portfolio_audit.*` の Enum を検証し、不一致時は `[VALIDATION_FEEDBACK]` をプロンプト末尾に注入して最大3回の再生成を要求します。
* **Statistical Reasoning Sandbox (純粋推論の実験場)**: 本推論エンジンは、個別ニュース等の外部定性情報（ノイズ）を意図的かつ完全に遮断する設計である。LLMに提供するのは `S&P500 / NASDAQ100 / SOX / 米10年債 / USD/JPY / VIX` の**6指標のみ**であり、そこからミクロなセクター動向（Insight）を導き出させる行為は、LLMが持つ「学習済みの市場構造（Market Mechanics）」に基づく**統計的推論能力を検証するための意図的な実験場（Sandbox）**として位置付けられている。

---

## 4. Implementation Standards (実装基準)

### 4.1 Sovereign Ledger Protocol (データ主権の確立)
外部依存を断切、システム自身が正解を持つアーキテクチャ **(SSOT: Single Source of Truth)** を徹底します。

1. **V4 Ledger Native Requirement**
    * **Rule**: 出力の正本は日次で確定保存する `data/current/ledger_YYYYMMDD.json` とする。確定後の状態判定と期間比較はこの正本を基準に行う（[ADR-0002](../adr/ADR-0002-ledger-native-ssot.md)）。
    * **Boundary**: `data/v4_shadow_ledger.json` は同一実行内で両正典を統合した結果であり、下流処理の入力として使う。日をまたぐ基準には使わない。
    * **Immutability**: `integrity_status = VERIFIED` へ到達した正本は後続実行で書き換えない。`STAGNANT` の間は暫定として更新してよい。

2. **The Fortress Equation (要塞の演算式)**
    * **Logic**: 総資産（Total Assets）は、常に以下の式で算出されなければならない。
     $$Total = Exposure(RiskAssets) + IronBank(SafeAssets)$$
    * **Constraint**: `Iron Bank` は市場変動係数 `0.0` の定数として扱い、外部資産定義ファイル（`data/external_assets.json`）からのインジェクションのみを許可する。

3. **The Audit Engine (外部取得への非依存化)**
    * **Behavior**: v4標準日次では外部取得の可否を配信可否に使わない。外部側で例外・未到達・CSV不整合が発生しても監査層が Warning を返し、配信フローは `ShadowLedger` の状態を基準に継続する。

### 4.2 The Curator Protocol (人格と対話の定義)
ユーザーの金融資産状況を評価するAIは以下の制約を定義します。

1. **Output Contract**:
    * トーン: 客観的
    * スタイル: 名詞句（Noun phrases）を使うこと。 評価語・感情語を使用しない。 比喩表現を使用しない
    * コンテンツ: 事実・因果・不足情報のみを記述する
    * 出力: 体言止めを優先する

2. **Vector Analysis Strategy (推論の全委譲)**
    * **Requirement**: プロンプトには**基準日と参照市場の日付・文脈（`us_market_context`）**を渡し、市場を構成する3つのベクトル（`External Pressure`, `Price Vector`, `Currency Vector`）の特定と合成（合力）の推論は、AI自身の知識ベースに完全に委ねる。
    * **Intent**: これは「Logic as a Prompt（コードではなくAIにロジックを肩代わりさせる）」アプローチの極致であり、システム側で複雑な経済指標を取得・計算するコストを排除する。

3. **Action Ban (思考停止の物理的断罪)**
    * **Validation**: 出力テキストに「様子見」「静観」「一旦」「〜と思われる」等の曖昧な表現が含まれる場合、それを `RuntimeError` として物理的に検閲・断罪し、システムアラート（ENGINE_RUNTIME）を通じてプロンプトエンジニアリングの改善を促す。

4. **Graceful Degradation (適切な沈黙)**
    * **Silent Skip**: AIのバリデーションが規定回数（`_MAX_VALIDATION_RETRIES`）失敗した場合、またはJSONパースエラー等の論理破綻が発生した場合は、エラーログのみを記録し `None` を返却してレポート配信を静かにスキップする。 ダミー文字列（定型文フォールバック）による偽のコンテンツ配信は完全に禁止する。
    * **Fatal Alert**: LLMプロバイダが全滅した場合など致命的な `RuntimeError` は Curator内で握りつぶさず上位層へ伝播させ、`PortfolioEngine` または `MonthlyEngine` の例外ハンドラが `OPERATIONAL_LIMIT` / `SYSTEM_CRASH` アラートを発火させる。
    * **V4 Rendering Guarantee**: v4日次フローでは AI鑑定文が空でも、`V4ContentRenderer` が Canonical Ledger を含む単一HTMLメールを生成できる。事実の伝達は `ShadowLedger` によって担保される。
    * **[ACCEPT_FAILOVER_FRAGILITY] — フェイルオーバー脆弱性の受容宣言**: プロンプトの制約（符号の絶対整合 `SIGN LOCK` / 禁止語の検閲 `BANNED_WORDS` / Enum厳格バリデーション）が極めて高度であるため、Primary LLM（Claude）から Secondary（Gemini等）へフェイルオーバーした際にバリデーションエラーによる配信スキップ率が高まる **Failover Fragility（フェイルオーバー脆弱性）** を内在している。しかし、ノイズが混じった妥協的な出力を許容するくらいならば、潔く**「沈黙（Skip）」** を選ぶという美学に基づき、このピーキーなプロンプト設計を正式な **Risk Acceptance（リスク受容）** として採択する。

### 4.3 Cushioned Fortress UI (視覚的防衛の実装)
UIは情報の伝達ではなく、**「心理的影響の減衰（Damping）」** を目的として構築されます。

1. **Zone 1**:
    * **Visual Priority**: 画面最上部には「Safe Ratio（Iron Bank比率）」を配置する。 「Total Return（累積利益）」は プラスの場合は、**Gold (`#c5a059`)** かつ **`font-weight: 200`** で表示する。 マイナスの場合は `#1e293b` (Ink) で表示する。

2. **Zone 2**:

    * **Emphasis**: 「Exposure（リスク資産総額）」を画面内最大フォント（目安 `60px` 以上）とする。 「YTD/MTD（トレンド）」の配色は **薄いグレー (`#64748b`)** を指定し、背景とのコントラスト比を意図的に下げることで、認識の優先度を物理的に落とす。

3. **Zone 3**:
    * **De-emphasis**: 「Day Diff（前日比）」は画面最下部に配置し、フォントサイズは `Zone 2` の **50%以下** とする。 配色は **薄いグレー (`#64748b`)** を指定し、背景とのコントラスト比を意図的に下げることで、認識の優先度を物理的に落とす。

### 4.4 Technical Constraints (技術的制約)

1. **The Trinity Separation (三位一体の分離と指揮系統・データ管理の純化)**
    * **Structure**: コードベースは Logic, View, Infrastructure の3層に厳密に分離する。
    * **Logic Purification (データ管理と生成の純化)**:
        * データ管理の司令塔（`LedgerManager`）から、物理的なファイルI/Oの責務を専用の `LedgerRepository` (Infra層) へ委譲する。
        * CSVからの文字列抽出（正規表現処理）を CSVパーサ (Infra層) へ委譲し、抽出された純粋なデータから要塞メトリクス（Safe Ratio等）を計算・構築する責務を `LedgerFactory` (Logic層) に分離する。
        * UI表示用ラベルの知識（"MUTUAL FUNDS"等）を `ViewModel` (View層) へ委譲し、Logic層を純粋な計算とドメイン知識のみに専念させる。
    * **Delegation (指揮系統 of Command)**: 指揮官である `PortfolioEngine` には条件分岐（If/Else）の記述を極力許さず、実行可否の判定は独立した憲兵モジュール（`GuardRail`）へ、配信の制御は `DispatchController` へ完全に委譲し、見通しの良い純粋なオーケストレーターとして振る舞うこと。

2. **AI-Native Logic Strategy**
    * **Methodology**: 米国祝日判定（Market Holiday Check）や因果関係の特定など、複雑な分岐条件を持つロジックはハードコードせず、LLMへの問い合わせ関数（Logic as a Prompt）を経由して解決する。

3. **Scraping Fragility Limits (スクレイピングの脆さの受容と運用方針)**

旧構成では、証券会社の Web UI をブラウザ操作で自動取得していた。**本公開リポジトリはこの取得層の実装を含まないが、設計原則として記録する。**
    このアプローチは DOM 構造への構造依存を内在しており、以下の方針でその脆さを **システムの限界（System Limit）** として明文化する。

    * **[ACCEPT_FRAGILITY] — 受容リスクの宣言**
        * 証券会社側の UI リニューアル・予期せぬモーダル出現・ページ構造変更によってスクレイピングパイプラインが停止するリスクは、**「解決すべきバグ」ではなく「運用上の受容リスク（Risk Acceptance）」** として扱う。
        * UI 変更の頻度は低く、インシデント発生時の手動セレクタ修正（定数の書き換え）コストは、複雑な自動修復ロジックの維持・保守コストを圧倒的に下回る。この非対称性を根拠に、リスク受容を正式な設計決定として採択する。

    * **[NO_AUTO_HEAL] — 自己修復ロジックの禁止（アンチパターン）**
        * セレクタの自動追従（Dynamic Selector Resolution）、複雑な DOM 探索ツリーの構築、要素検出リトライループなど、DOM 変化への自律的な適応を試みるエンジニアリングは **過剰設計（Over-engineering）のアンチパターン** として固く禁ずる。
        * 修復ロジックは将来の UI 変更時に二重の保守負債（修復ロジック自体の修正 + セレクタ修正）を生じさせるため、実装してはならない。

    * **[FAIL_FAST] — 速やかな失敗伝播の義務**
        * DOM 要素が取得できない場合、ブラウザ操作層（Infra 層）は下手に延命・リカバリを試みず、`SELECTOR_TIMEOUT` 等の具体的なエラーを **即座に上位層へ伝播させる** こと。
        * 伝播されたエラーは `PortfolioEngine` の例外ハンドラを経由し、既存の `SYSTEM_CRASH` アラートを正常に発火させることで、オペレーターへの迅速な通知を保証する。
        * 「動作しているように見せる」ための沈黙（例外の握りつぶし・デフォルト値での継続）は § 4.2.4 の Graceful Degradation 原則に反し、禁止する。

    | 制約 | 内容 | 分類 |
    | :--- | :--- | :--- |
    | `[ACCEPT_FRAGILITY]` | UI変更によるパイプライン停止を受容リスクとして宣言 | Risk Acceptance |
    | `[NO_AUTO_HEAL]` | セレクタ自動追従・DOM修復ロジックの実装を禁止 | Anti-pattern |
    | `[FAIL_FAST]` | DOM取得失敗時は即座にエラー伝播し SYSTEM_CRASH を発火 | Operational Policy |

4. **External Authentication Dependency Acceptance（外部認証依存の受容）**

旧構成では、証券会社へのログイン認証プロセスにおいてメール経由での OTP（ワンタイムパスワード）取得に依存していた。
    このアプローチは外部仕様への構造依存を内在しており、以下の方針でその脆さを **システムの限界（System Limit）** として明文化した。**本公開リポジトリはこの認証層の実装を含まないが、設計原則として記録する。**

    * **[ACCEPT_EXT_AUTH] — 外部認証依存リスクの宣言**
        * メールプロバイダのセキュリティポリシー変更・OTP メール文面フォーマット変更・証券会社の MFA フロー変更によって OTP 取得パイプラインが停止するリスクは、**「解決すべきバグ」ではなく「運用上の受容リスク（Risk Acceptance）」** として扱う。
        * これらの変更頻度は低く、インシデント発生時の手動定数修正（正規表現・設定値の書き換え）コストは、複雑な自動追従ロジックの維持・保守コストを圧倒的に下回る。この非対称性を根拠に、リスク受容を正式な設計決定として採択する。

    * **[NO_AUTO_HEAL_AUTH] — 自己修復ロジックの禁止（アンチパターン）**
        * OTP メール文面の自動解析（ヒューリスティックパース）、認証方式の自動フォールバック、MFA フロー変更への自律的な適応を試みるエンジニアリングは **過剰設計（Over-engineering）のアンチパターン** として固く禁ずる。
        * 修復ロジックは将来の仕様変更時に二重の保守負債（修復ロジック自体の修正 + 定数修正）を生じさせるため、実装してはならない。

    * **[FAIL_FAST_AUTH] — 速やかな失敗伝播の義務**
        * OTP 取得失敗・メール接続失敗・正規表現マッチ失敗が発生した場合、認証レイヤー（Infra 層）は下手に延命・リカバリを試みず、`MFA_FAILURE` 等の具体的なエラーを **即座に上位層へ伝播させる** こと。
        * 「認証済みのように見せる」ための沈黙（例外の握りつぶし・デフォルト値での継続）は § 4.2.4 の Graceful Degradation 原則に反し、禁止する。

    | 制約 | 内容 | 分類 |
    | :--- | :--- | :--- |
    | `[ACCEPT_EXT_AUTH]` | メール / OTP / MFA フロー変更によるパイプライン停止を受容リスクとして宣言 | Risk Acceptance |
    | `[NO_AUTO_HEAL_AUTH]` | 認証フロー自動追従・OTPパース自動修復ロジックの実装を禁止 | Anti-pattern |
    | `[FAIL_FAST_AUTH]` | OTP取得失敗時は即座にエラー伝播し MFA_FAILURE を発火 | Operational Policy |
