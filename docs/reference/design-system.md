# THE CAPTION : デザイン・スペック (Design Specification)

## 1. デザイン哲学 (Design Philosophy)

### 1.1. 鑑賞としての資産管理
本システムは、情報の提示を「通知」ではなく「鑑賞」と捉える。資産の増減を一喜一憂する数字としてではなく、静謐な事実として提示するため、独自の表現規律（Aesthetic Sovereignty）を絶対的な表現の原点（Origin）とする。

### 1.2. 感情のフラット化
資産の騰落に対し、色彩による心理的バイアス（赤・緑による扇動）を排し、Slate 系の無彩色のみで構成する。これにより、投資家が市場の変動という事実を「凪」の心境で冷静に受け止めるための空間を提供する。

### 1.3. ノイズからの絶縁 (Insulation from Noise)
情報の取得をシステムに委任した以上、アウトプット自体が新たなノイズになってはならない。したがって、感情を煽る装飾を徹底的に排し、事実のみを伝える『鑑定書』としての静寂さをデザインの最優先事項とする。

### 1.4 実装の集約 (Implementation Sovereignty)
本ドキュメントで定義される全てのデザイン規律（カラーパレット、タイポグラフィ、余白設定）は、src/app/renderer/ パッケージ 配下のクラス群に集約され、唯一の正解として管理される。

* **Design Tokens (BaseRenderer)**: カラーパレットや共通定数は src/app/renderer/base.py 内の BaseRenderer クラスにて一元管理される。
* **Layout Logic (Specific Renderers)**: V4ContentRenderer (Monolithic Scroll)、ContextRenderer (Exhibition)、FortressRenderer (Index)、MonthlyRenderer (Chronicle)、および CollectionRenderer (Collection) 等の各クラスが、共通トークンを継承して具体的なレイアウトを描画する。
* **Facade Access**: 外部モジュール（Notifier等）は、これらを統括する ContentRenderer ファサード を通じてのみ描画機能にアクセスする。

---

## 2. カラーパレット：階層化された無彩色 (The Slate Symphony)

色彩は単なる色記号ではなく、朝の覚醒に寄り添う「光と影」である。

| 色名 / Hex | 役割 | 情緒的設計意図 (Narrative) |
| :--- | :--- | :--- |
| **#ffffff** | 背景 (The Canvas) | **「夜明けの静寂」**。雑味を削ぎ落とした白は、これから描かれる一日の事実を曇りなく受け止めるための、汚れなきキャンバス。 |
| **#1e293b** | 本文 (The Ink/Slate-800) | **「深海への沈潜」**。漆黒を避けた深い紺は、知性を象徴するインク。朝の光の中で文字が浮かび上がり、思考を深く沈ませる。 |
| **#64748b** | 見出し (The Mist/Slate-500) | **「朝霧の境界」**。彩度を抑えた灰青は、主張しすぎない道標。事実を包み込み、情報の重要度を優しく解きほぐす。 |
| **#cbd5e1** | 境界線 (The Echo/Slate-300) | **「静かな残響」**。思考を断絶するのではなく、文脈をそっと支える極細の線。そこにあるかのように、ないかのように。 |
| **#c5a059** | 増加 (The Hallmark/Gold) | **「収穫の刻印」**。INDEXおよびCHRONICLEのみに許された、資産増加時の一筋の光。成功を喧伝する「緑」ではなく、価値が積み上がった事実を静かに祝う、品位ある金。 |
| **#f8fafc** | フッター (The Dawn/Slate-50) | **「消えゆく余韻」**。存在を消すほどに薄いグレー。情報の終わりを告げ、日常への滑らかな回帰を促す。 |

---

## 3. タイポグラフィ・システム：規律と静寂

### 3.1. ウェイトの設定ルール (Weight Sovereignty)
情報の重要度を「太さ」ではなく「サイズ比率」と「空間」で表現する。
* **font-weight: 300 (Light) の絶対遵守**: 
    * 全文を通じて `300` を固定使用。太字（Bold）による視覚的な「叫び」を禁止する。これは朝の覚醒しきっていない眼に過度な刺激を与えず、冷静な「鑑定書」としての品格を保つための配慮である。
* **font-weight: 100 / 200**:
    * INDEX および CHRONICLE の生データにおいて、数値の冷徹さと繊細さを強調するために補助的に使用を許可する。
    * `100` (Thin): Hero 数値（Safe Ratio 60px / Exposure 60px / Asset Value 40px 等の大サイズ数値）に適用。
    * `200` (ExtraLight): Zone A Tertiary Row（Exposure / Iron Bank / Total Return の 20px 補助数値行）に適用。**[Absolute Rule]** この行の Weight は `200` で固定し、`300` や `400` への変更を禁止する。Hero 数値（W100）と Label/Body テキスト（W300）の中間に位置し、「事実としての静けさ」を数値に与える。

### 3.2. 文字の倍率ルール (The Scaling Ratio)
Exhibition Mode（CONTEXT）および Chronicle Mode（CHRONICLE）においては、Base Body を基準とした微細なデシマル・スケールを適用し、鑑賞のための視覚的重力を定義する。

* **Theme Title (1.600倍 / 24px)**: 
    * レポートの魂となる詩的タイトル。24px の圧倒的なサイズ stumbling と 0.1em の浮遊感（字間）により、鑑賞のスイッチを入れる。
* **Hero Label (1.200倍 / 18px)**: 
    * INDEXのNet Assets等、情報の起点を司る権威あるラベル。
* **Base Body (1.000倍 / 15px)**: 
    * 思考の中心。長文を最も快適に「鑑賞」できるサイズ。16pxから15pxへ微調整し、余白との比率を高めた。
* **Asset Name (0.867倍 / 13px)**: 
    * 固有名詞。本文より一段階落としつつ、Regular (400) ウェイトではなく `13px` サイズで識別性を確保する。
* **Sub Label (0.733倍 / 11px)**: 
    * 補助概念。主役を邪魔しない、囁きのような情報。

---

## 4. 統合デザインマトリクス (Unified Design Matrix)

### 4.1 設計思想の相違点 (Conceptual Differences)
v4.2 の日次メールは Monolithic Scroll を標準とする。INDEX（帳簿）、CONTEXT（展示）、COLLECTION（比較）は分割メールではなく、単一の鑑定書内のフェーズとして統合される。旧 INDEX / CONTEXT / CHRONICLE / COLLECTION の設計思想は、レガシー経路と月次・週次で維持する。

| 比較項目 | INDEX (Fortress) | CONTEXT (Exhibition) | CHRONICLE (Chronicle) | COLLECTION (Collection) | 設計意図 (Intent) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **主目的** | **一目での把握 (Efficiency)**  | **深い咀嚼 (Narrative)**  | **構造的変化の俯瞰 (Historical Perspective)**  | **純粋な比較 (Purity)**  | v4 Monolithic Scroll では「一通の鑑定書」に統合する。 |
| **情報の性質** | 構造化された生データ  | AIによる因果関係の鑑定 | 蓄積された知見の再蒸留 | 外部ファンドの基準価額 | 脳の「計算」「解釈」「構造化」「比較」モードのスイッチング。 |

### 4.2 実装仕様マトリクス (Implementation Specs)
本セクションの定義値は絶対的なものであり、コード（Renderer）はこれを 1px たりとも狂わせずに実装しなければならない。

#### A. タイポグラフィ階層定義 (Typographic Hierarchy)
「数値サイズ × 0.4」の空間規律（§5.1）を全ての土台マージンに適用する。

| 役割 (Role) | 項目 | INDEX / CHRONICLE (数値の秩序) | CONTEXT (読解の静寂) | 規律の理由 |
| :--- | :--- | :--- | :--- | :--- |
| **Hero / Title** | **Size** | **60px** (Value) | **24px** (Title) | INDEXは「数値」を、CONTEXTは「主題」を主役に据える。 |
| | **Anchor Margin** | **24px** (60 * 0.4) | **10px** (24 * 0.4) | **[Proportional Rule]** 数値の質量に比例した静寂を確保する。 |
| | **Weight** | **100** (Thin) | **300** (Light) | 数値は極限まで削ぎ落とし、言葉は優美さを保つ。 |
| **Tertiary Row** | **Size** | **20px** | - | Hero(60px)とLabel(18px)の中間に位置し、事実を添える。 |
| | **Weight** | **200** (ExtraLight) | - | **[Absolute Rule]** W100(Hero)とW300(Text)の中間値。 |
| **Label / Body** | **Size** | **18px** (Label) | **15px** (Body) | INDEXは視認性、CONTEXTは没入重視。 |

#### B. ゾーン別レイアウト定義 (Zone Layouts)
余白は原則として「上から下への押し出し（margin-bottom）」で制御し、ネストによる重複を禁止する。

| ゾーン | 要素 | INDEX / CHRONICLE / COLLECTION | CONTEXT (Exhibition) | 共通ルール / 意図 |
| :--- | :--- | :--- | :--- | :--- |
| **Zone A** (Hero) | **Spacing** | Bottom **24px** (Anchor) | Bottom **10px** (Anchor) | **[The Monolith]** 巨大数値と土台の距離を比例固定する。 |
| | **Section Gap** | Bottom **60px** | Bottom **40px** | 導入部直下の「沈黙」。 |
| **Zone B** (Body) | **Structure** | Border-Left: 1px / Pad-Left: 32px | Border-Left: 1px / Pad-Left: 20px | **[The Partition]** インデントで独立性を強調。 |
| | **Margin Top** | **0px** | - | **[Spatial Sovereignty]** Zone A の Section Gap（60px）のみで制御し、重複余白を排除する。 |
| **Zone C** (List) | **Item Value** | Size **40px** | - | リスト内の数値も Monolith 規律を維持。 |
| | **Item Gap** | Bottom **60px** | - | **[Spatial Sovereignty]** Section Gap と同値に統一し、全ゾーンの余白を 60px に収束させる。 |
| | **Spacing** | Bottom **16px** (40 * 0.4) | - | **[The Scaling]** リスト内の数値質量に合わせた比例余白。 |
| | **Item Meta** | Size 12px / c_slate | Size 12px / c_slate | 補助情報はサイズと色を完全統一。 |
---

## 5. V4 Monolithic Scroll：統合鑑定書

v4.2 の標準日次メールは `src/app/renderer/templates/v4_monolithic.html` を正本とする。目的は INDEX / CONTEXT / COLLECTION を別々の通知として送ることではなく、20:00 の単一HTMLメールで資産全体を静かに鑑賞できる縦長の流れを作ることである。

### 5.1 Phase Structure

| Phase | 名称 | 表示内容 | 規律 |
| :--- | :--- | :--- | :--- |
| **1** | The Evening Anchor (Conditional) | Theme Title、State / Primary | State Classification は表示名を露出させず、`WATCH / NYFANG` のような短い計器行として扱う。Market Context 長文は前面に出さない |
| **2** | The Defensive Monolith | Safe Ratio、Defense Bar、Exposure / Iron Bank / Total Return、Total Net Assets | Safe Ratio を 60px の防衛ヒーローとして維持し、Exposure / Iron Bank / Total Return を経て、Total Net Assets を 40px の帳簿ブロックとして提示する |
| **3** | The Unified Ledger | Exposure（市場資産）、Iron Bank（静的資産） | Exposure と Iron Bank を分離し、同一タイポグラフィでフラットに並べる |
| **4** | The Shield | Shield Evaluation | 結びの防壁評価。補助情報として 13px 系統で描画 |

### 5.1.1 State Classification Rules

V4 Monolithic Scroll は、毎日同じ「大丈夫」という安心文を繰り返さない。冒頭では行動指示ではなく、当日の観測温度を分類する。

| 状態 | 意味 | 表示密度 |
| :--- | :--- | :--- |
| **QUIET** | 構造変化がほぼない | 最小限 |
| **NORMAL** | 通常の揺れの範囲 | 短文 |
| **WATCH** | 偏りやデータ未着など確認対象がある | 主因を明示 |
| **STRESS** | 防衛状態への圧力がある | 原因と確認姿勢を濃くする |
| **BREAK** | 方針再確認が必要な変動 | 最も高い密度で提示 |

分類は `total_diff_pct`、Safe Ratio、pricing_status、`Share × Diff` の影響度を材料にする。`QUIET / NORMAL` は「何もしなくてよい」と長々語らず、レポート自体を静かに保つ。

### 5.1.2 Display / Archive Separation

日次メールは表示密度を抑え、文章よりも計器値を優先する。`display_context` はメール表示専用で、State / Primary の最小行だけを担う。`archive_context` は月次再蒸留専用で、causal_vector、market_regime、fx_effect、vix_band、monthly_tags、short_note を保存する。表示から削った因果情報は失わず、月次CHRONICLEで集計する。

### 5.1.3 Appraisal Visibility Gate

`DAILY PORTFOLIO APPRAISAL`（Phase 1）は常設表示ではない。
以下の 2 条件を同時に満たす場合のみ表示する。

1. `total_return_jpy < 0`
2. `last_displayed_date` から対象日までの経過日数が 7 日以上

いずれかを満たさない場合は、Phase 1 を表示しない。
`last_displayed_date` は `data/runtime/v4_appraisal_state.json` で管理する。

### 5.2 Unified Ledger Rules

Unified Ledger は `ShadowLedger.assets` のフラットなリストをそのまま ViewModel 化する。旧 COLLECTION ドメインのファンド群、株式、コモディティ、現金、企業型DC、その他外部資産は同列に並ぶ。

| ルール | 内容 |
| :--- | :--- |
| **The Truncation Guard** | 銘柄名は `white-space: nowrap; overflow: hidden; text-overflow: ellipsis;` を適用し、1行省略を強制する |
| **Metric Capsule** | Exposure 側の補助指標は `UNITS / PRICE` のみを表示し、不要ラベルは排除する |
| **Source Neutrality** | `MARKET_UNITS` と `ABSOLUTE_AMOUNT` は見た目の序列を作らず、評価額順で並べる |
| **60px Silence** | フェーズ間と主要行間には 60px の押し出し余白を置く |

### 5.3 Renderer Boundary

v4.2 の描画ファイルは既存レンダラーから独立している。

| ファイル | 責務 |
| :--- | :--- |
| `src/app/renderer/v4_view_models.py` | `ShadowLedger` と AI 鑑定結果から `V4MonolithicViewModel` を構築 |
| `src/app/renderer/v4_content_renderer.py` | Jinja2 テンプレートへ ViewModel を流し込み HTML を返す |
| `src/app/renderer/templates/v4_monolithic.html` | Monolithic Scroll のインラインCSSテンプレート |

---

## 6. INDEX & CHRONICLE：事実の集約と秩序 (Data Density Logic)

### 5.1. デシマル・スケーリング則 (Decimal Scaling Rule)
金額を頂点とした情報の「重み」を比率で定義する。
* **金額 (1.0)** / **前日比 (0.4)** / **タイトル (0.3)** / **アンカー (0.25)** の比率を維持。
* **空間の黄金律 (Anchor Margin)**: 巨大な数値（Value）とその直下を支える土台（Anchor/Bar/Metrics）の間の距離は、常に **Valueサイズ × 0.4** で算出する（例: 60pxなら24px、40pxなら16px）。
* 評価損益（アンカー）は、金額に対して控えめでありつつ、前日比よりも「静的な重み」を持つサイズとする。

### 5.2. 帳簿の美学 (The Floating Ledger)
INDEX および CHRONICLE における数値表現は、会計帳簿（Ledger）のような絶対的な秩序を美の基準とする。
* **右揃えの絶対性**: 「評価額（Value）」と「評価損益（Return）」は、一の位の桁を物理的に完全に一致させる。これにより、「計算の正しさ」を視覚的に保証する。
* **単位の排除**: 桁揃えの美しさを最大化するため、**「JPY」等の単位表記を数値ブロックから完全に排除する**。文脈により通貨は自明であるため、ノイズとなる文字情報は不要とする。
* **ハイブリッド配置 (Internal Right / External Left)**:
    * 数値ブロック内部は「右揃え」とするが、ブロック自体は画面の「左側」に配置する。
    * これにより、左側の見出し（Label）から右側の数値（Value）へ、そして左下の変動（Change）へと流れる「Z型」の視線誘導を構築する。
* **凝縮と拡散の呼吸 (Compression & Expansion)**:
    * **数値 (Values)**: **`-0.02em`** のマイナスカーニングを適用。数字を「散漫な記号の列」ではなく「鉄の塊」として視認させる。
    * **見出し (Labels)**: **`0.15em`** の広範な余白を与え、大文字（UPPERCASE）の風格を漂わせる。
    * **詳細 (Sub-Info)**: **`0.05em`** の微細な呼吸を与え、可読性を担保する。

### 5.3. 認知のアンカー (The Cognitive Anchor)
日々の変動（ノイズ）による精神的摩耗を防ぐため、「評価損益」をアンカーとして配置する。
* **配置**: 評価額（Value）の直下、かつ前日比（Daily Change）の手前（上部）に配置する。
* **役割**: 「今日の増減」を見る前に「積み上げられた実績」を視認させることで、短期的な変動に対する精神的なバッファ（凪）を形成する。
* **表現**: ラベルや装飾を排し、純粋な数値として評価額に寄り添わせることで、静謐な事実として扱う。

### 5.4. 収穫のアクセント と Return Color Rule
資産が増加した場合に限り、前日比等の要素に **#c5a059 (Gold)** を適用する。これは「上昇」という動態の強調ではなく、その時点での「資産の質」に対する鑑定としての刻印である。

* **アンカーへの適用除外**: 評価損益（Return）は「静的な事実」であるため、プラスであっても Gold を適用せず、常に **#64748b (Slate)** または **#1e293b (Ink)** で描画し、前日比（動的要素）と明確に区別する。

* **Total Return Color Rule (Zone A Tertiary Row)**:
    * `Total Return`（通算損益）の表示色は、ViewModel（`SummaryViewModel.total_pl_color`）が動的に供給する。
    * **プラス（利益）**: **#c5a059 (Gold)** を適用する。累積利益は「収穫の刻印」として Gold での描画を許可する唯一の静的要素である。
    * **マイナス（損失）またはゼロ**: **#1e293b (Ink)** を適用する。損失を赤で強調することは感情のフラット化原則に反するため、無彩色のみとする。
    * **[Prohibition]**: `#dc2626` (Red) / `#059669` (Emerald) 等の感情的色彩の使用を厳禁とする。

### 5.5. 時間軸の表記統一 (Temporal Sovereignty)
時間軸を表すラベルは、全て **大文字 (UPPERCASE)** に統一し、視覚的な高さと密度を揃える。
* **YTD** (Year-to-Date)
* **MTD** (Month-to-Date)
* **WTD** (Week-to-Date)
* **DAY** (Daily Change)
これにより、YTD/MTD/WTD を1行、DAY を別行にした際の幾何学的な整合性を担保する。
* INDEX の各アセットクラス行でも、日次変動の補助ラベルとして **DAY** を独立行で表示し、`+金額 / +率` の形で描画する。
* COLLECTION の各ファンド行でも、日次変動の補助ラベルとして **DAY** を独立行で表示し、`+金額 / +率` を同一行で描画する。DAY の変動色はプラス時 `Gold`、マイナス時 `Slate` に統一する。

---

## 7. CONTEXT：文脈の鑑定と読解 (Narrative Flow)

### 6.1. 言語主権 (Language Sovereignty)
* **Plain Language Protocol**: 専門用語（Jargon）の使用を厳禁とする。
* **Tone & Manner**: ユーザーの不安に寄り添う「老練な執事」や「賢明な助言者」のようなトーン。

### 6.2. 読解のための静寂 (The Serenity Logic)
CONTEXT は「文字を読むこと」に特化し、以下の数値を厳守する。
* **Font Weight**: 文章においては **W300 (Light)** を絶対基準とする。
* **Letter Spacing**: **0.1em**。読む速度を意図的に落とし、情報を「鑑賞」させる。
* **Line Height**: **2.0**。視線移動のインターバルを最大化し、情報の「上書き」を避ける。

### 6.3. 呼吸する垂直余白 (Spatial Silence)
* **Section Gap (60px)**: Overview 読了後の「沈黙」。
* **Subsection Gap (40px)**: 要因から結論へ至る前の精神的インターバル。

### 6.4. 方針監査の月次移管 (Portfolio Audit Migration)

`Portfolio Audit` は日次（V4 Monolithic）では廃止し、月次（Chronicle）へ移管する。
日次メールは State / Primary と帳簿指標の提示に限定し、方針監査の記述は表示しない。
月次では、対象月の記録を再蒸留した監査結果として `Portfolio Audit` を表示し、投資方針の維持・再検証を扱う。

### 6.5. SHIELD パネルのタイポグラフィ規律 (SHIELD Panel Typography)

CONTEXT（日次）の SHIELD EVALUATION および CHRONICLE（月次）の SHIELD REVIEW は、以下の規律を絶対的な正典とする。

| 要素 | SHIELD EVALUATION (日次) | SHIELD REVIEW (月次) |
| :--- | :--- | :--- |
| **区切り線** | `border-top: 1px solid {c_silver}` | 同左 |
| **ラベル** | `font-size: 11px; letter-spacing: 0.1em` | 同左 |
| **本文** | `font-size: 13px; font-weight: 300; line-height: 1.6; letter-spacing: 0.05em` | 同左 |

**`letter-spacing: 0.05em` の根拠**: §5.2「詳細 (Sub-Info)」の Sub-Info 規律（0.05em）の適用領域として定義する。メイン本文（0.1em）より抑制することで、補足パネルとしての視覚的格差を保つ。

---

## 8. 技術的制約と一貫性

### 7.1. 物理的防御
* **Max-width: 440px**: スマートフォンの画面幅において、視線の横移動距離を抑え、読解ストレスを最小化する。
* **Inline CSS**: 全ての美学をメールソフトへ 100% 欠損なく届けるため、全ての HTML タグに直接スタイルを記述する。
* **Zero Decoration**: シャドウ、グラデーション、角丸、アイコンを一切禁止する。

### 7.2. レイアウト防壁 (CSS Guard)
証券会社の長大な銘柄名や、狭い画面幅による予期せぬ改行（レイアウト崩れ）を物理的に封殺するため、以下のCSS防御を絶対的な規律として適用する。
* **The Truncation Guard (1行省略強制)**:
    * INDEXレポートおよび v4 Unified Ledger の銘柄名要素には `white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block; width: 100%;` を適用する。
    * いかなる長い文字列であっても2行への折り返しを許さず、末尾を省略（...）させることで「The Monolith」としての縦のレイアウトを死守する。
* **The Metric Capsule (指標の絶対結合)**:
    * `YTD +1.0%` のようなラベルと数値のペア、および `Share: XX.X% | Diff: +X.XX%` などの不可分なメタ情報は、それぞれ `<span style="white-space: nowrap;">` でカプセル化する。
    * 空白（`&nbsp;`）が作り出す「絶対的な空間の広がり」を維持しつつ、中途半端な位置での段落落ち（文字割れ）を物理的に不可能にする。
