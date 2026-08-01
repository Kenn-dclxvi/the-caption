# Part 1: Tutorials

### Environment Setup & Installation

---

### 1.1 Setup Instructions (構築手順)

#### Phase 1: GitHub Desktop のインストール

まず、あなたのPC（Windows/Mac）にリポジトリ管理ツールをインストールします。

1. **GitHub Desktop**
   - https://desktop.github.com/ にアクセスし、インストーラーをダウンロードして起動
   - 画面の指示に従いインストールを完了する
   - 起動後、GitHubアカウントでサインイン（アカウントがない場合は「Create your free account」から作成）

---

#### Phase 2: リポジトリのクローン

GitHub Desktop を使って、ソースコードをあなたのPCに取得します。

1. GitHub Desktop を起動
2. メニューバー「File」→「Clone Repository...」を選択
3. 「URL」タブを選択
4. URL欄にリポジトリのURLを入力
5. 「Local Path」でクローン先フォルダを指定（例: `~/Projects/THE-CAPTION`）
6. 「Clone」ボタンをクリック
7. クローン完了後、指定した「Local Path」にフォルダが作成されたことを確認

> **💡 Tip**: クローン完了後、GitHub Desktop の上部メニュー「Repository」→「Open in Terminal」を使うと、クローン先フォルダをすでにカレントディレクトリとした状態でターミナルが起動して便利です。

---

#### Phase 3: 仮想環境（venv）の作成と依存パッケージのインストール

ターミナル（Mac: Terminal / Windows: PowerShell）で作業します。

**1. クローン先フォルダへ移動**

```bash
cd /path/to/THE-CAPTION
```

> GitHub Desktop の「Open in Terminal」を使った場合、このステップは不要です。

**2. venv の作成**

```bash
python3 -m venv .venv
```

**3. venv の有効化**

```bash
# Mac / Linux
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\activate
```

有効化に成功すると、ターミナルのプロンプト先頭に `(.venv)` と表示されます。

**4. 依存パッケージのインストール**

```bash
pip install -r requirements.txt
```

**主要な依存関係**:
- `playwright>=1.40.0` - ブラウザ自動化
- `pandas>=2.0.0` - データ分析
- `openai>=1.0.0` - OpenAI 互換 API（Google/DeepSeek）
- `anthropic>=0.40.0` - Claude API
- `python-dotenv>=1.0.0` - 環境変数管理
- `jpholiday>=0.1.0` - 日本祝日判定
- `pandas-market-calendars>=4.0.0` - 米国市場カレンダー
- `cryptography>=41.0.0` - 環境変数の暗号化ツール用
- `PyYAML>=6.0.1` - アセットカタログ生成ツール用

**5. Playwright ブラウザのインストール**

```bash
playwright install chromium
```

**成功の確認:**

```bash
python -m src.app.entrypoints.v4_daily_main -h
python -m src.app.entrypoints.weekly_main -h
python -m src.app.entrypoints.monthly_main -h
```

各コマンドのヘルプメッセージが表示されれば、環境構築は完了です。v4.2 の日次標準は `v4_daily_main` です。

---

#### Phase 4: 秘匿情報の配置

プロジェクトルートに `.env` ファイルを作成し、自身の認証情報を記述します。
**重要：スペースを含む値（アプリパスワード等）は必ずダブルクォート `"` で囲んでください。**

```bash
# ===== AI Provider (LLM) =====
# Claude API (Primary - 必須)
ANTHROPIC_API_KEY="sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# Google Gemini API (Secondary - フェイルオーバー用)
GOOGLE_API_KEY="AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"

# DeepSeek API (Emergency Backup - オプション)
# DEEPSEEK_API_KEY="your_deepseek_api_key_here"

# ===== メール設定 =====
SMTP_USER="report_bot@domain.com"
SMTP_PASS="yyyy yyyy yyyy yyyy"
SMTP_TO="your_main_email@domain.com"
```

**API キーの取得方法**:

1. **Claude API (Anthropic)** - Primary Provider
   - https://console.anthropic.com/ にアクセス
   - 左メニュー「API Keys」→「Create Key」
   - 生成されたキー（`sk-ant-api03-...`）をコピー
   - **推奨モデル**: `claude-sonnet-4-6`（高品質・コスパ良好）
   - **レート制限**: 50リクエスト/分（Google の 2500倍）
   - **月額コスト**: 約 $0.40（1日1回実行の場合）

2. **Google Gemini API** - Secondary Provider（フェイルオーバー用）
   - https://ai.google.dev/ にアクセス
   - 「Get API Key」から無料キーを取得
   - 無料枠: 20リクエスト/日

3. **DeepSeek API** - Emergency Backup（オプション）
   - 設定のみ保持。通常は未使用。

---

#### Phase 5: Claude Code インストール・初期設定

このフェーズでは、AI-powered CLI ツール **Claude Code** をセットアップし、開発ワークフロー内で即座に使用できるように準備します。既に Phase 4 で設定した `ANTHROPIC_API_KEY` が自動的に認識されます。

---

##### 5.1 Claude Code CLI のインストール

**macOS:**

Homebrew を使用してインストールします。

```bash
brew tap anthropic/claude-code
brew install claude-code
```

インストール完了後、バージョン確認：

```bash
claude code --version
```

**Windows:**

Windows は以下いずれかの方法でインストール可能です。

**方法1: Homebrew（推奨）**

Windows 用 Homebrew（`scoop` または `chocolatey`）がある場合：

```bash
choco install claude-code
```

または

```bash
scoop install claude-code
```

**方法2: NPM（Node.js が必要）**

```bash
npm install -g @anthropic-ai/claude-code
```

インストール完了後、バージョン確認：

```bash
claude code --version
```

**方法3: 公式ドキュメント**

手動インストールやその他の方法については、以下をご参照ください：
- https://github.com/anthropics/claude-code

---

##### 5.2 Anthropic API 認証の連携

Claude Code は環境変数から自動的に `ANTHROPIC_API_KEY` を検出します。

**確認方法:**

ターミナルで以下を実行し、環境変数が正しく認識されているか確認します：

```bash
echo $ANTHROPIC_API_KEY
```

（Windows PowerShell の場合）

```powershell
$env:ANTHROPIC_API_KEY
```

環境変数が表示されれば、認証は自動的に確立されます。

**トラブルシューティング: API キーが認識されない場合**

以下のいずれかで手動設定可能です：

1. **ターミナルで直接設定（一時的）:**

```bash
# Mac / Linux
export ANTHROPIC_API_KEY="sk-ant-api03-..."

# Windows PowerShell
$env:ANTHROPIC_API_KEY="sk-ant-api03-..."
```

2. **システム環境変数に追加（永続的）:**

- **macOS**: `~/.zshrc` または `~/.bash_profile` に以下を追加
  ```bash
  export ANTHROPIC_API_KEY="sk-ant-api03-..."
  ```
  その後、`source ~/.zshrc` で再読み込み

- **Windows**: システム設定 → 環境変数 → ユーザー環境変数で `ANTHROPIC_API_KEY` を追加

---

##### 5.3 プロジェクト内での Claude Code 使用準備

**基本的な使用方法:**

THE-CAPTION プロジェクトのルートディレクトリで以下を実行：

```bash
claude code .
```

これにより、Claude Code がカレントディレクトリ（プロジェクトルート）で起動し、コードベース内のすべてのファイルにアクセス可能な状態で使用できます。

**よく使うコマンド:**

| コマンド | 説明 |
| :--- | :--- |
| `claude code .` | 現在のプロジェクトで起動 |
| `claude code --help` | ヘルプメッセージを表示 |
| `claude code --version` | Claude Code のバージョン確認 |
| `claude code auth` | API 認証状態の確認・再設定 |

**プロジェクト固有設定（オプション）:**

プロジェクトルートに `.claude.json` を作成することで、プロジェクト固有の設定を指定できます：

```json
{
  "model": "claude-sonnet-4-6",
  "temperature": 0.7,
  "context_window": "auto"
}
```

詳細は公式ドキュメントを参照してください。

---

##### 5.4 Troubleshooting

**問題: `command not found: claude code`**

- `claude code --version` で確認してからパスを確認してください
- **macOS**: `brew reinstall claude-code`
- **Windows**: PATH に Claude Code のインストール先が含まれているか確認

**問題: API キー認証エラー**

- `.env` ファイルが正しく配置されているか確認
- Phase 4 で記載した `ANTHROPIC_API_KEY` の値が正しいか確認
- ターミナルを再起動し、環境変数を再読み込みしてください

**問題: Claude Code 起動後にプロジェクト内容が見えない**

- プロジェクトルートディレクトリで `claude code .` を実行しているか確認
- `.claude.json` に不正な JSON 構文がないか確認

---

##### 5.5 THE-CAPTION Shell Setup

THE-CAPTION では、`zsh` 起動時にプロジェクト専用の補助関数を読み込めるようにしています。
この設定はリポジトリ内の原本を使い、`~/.zshenv` には最小限のブートストラップだけを書き込みます。

**1. ブートストラップの導入**

プロジェクトルートで以下を実行します。

```bash
python scripts/dev/install_the_caption_zshenv.py
```

このスクリプトは次の処理を行います。

- `configs/zsh/the-caption.zsh` を正本として参照する
- `~/.zshenv` に THE-CAPTION 用のブロックを追加または更新する
- repo 外で起動した `zsh` でも、`cd` して THE-CAPTION に入った時点でその worktree の `.venv/bin/activate` を有効化できるようにする
- 複数の THE-CAPTION クローン先でも、入った先の worktree 直下にある `.venv` を優先して有効化する

**2. 反映の確認**

新しいシェルを開くか、既存シェルで `~/.zshenv` を再読み込みします。

```bash
source ~/.zshenv
```

**3. 使えるようになる挙動**

THE-CAPTION の作業ディレクトリ内では、以下がプロジェクト内の `.venv` を優先して参照します。

- `python`
- `pip`
- `pytest`

また、`cd` で repo に入ると `source .venv/bin/activate` が走り、repo を外れると `deactivate` されます。

**注意**

- この設定は THE-CAPTION の git worktree 内でのみ有効です
- `.zshenv` に既存の設定がある場合でも、ブートストラップ以外は保持されます

#### Phase 6: pre-commit フックのセットアップ

別PCにクローンした際は、テストの自動実行フックを手動でセットアップしてください。これにより、コミット前に自動でテストが実行され、失敗した場合はコミットがブロックされます。

---

##### 6.1 フックファイルの作成

プロジェクトルートで以下を実行します：

**Mac / Linux:**

```bash
cat > .git/hooks/pre-commit << 'EOF'
#!/bin/bash
python -m pytest tests/ --tb=short -q
if [ $? -ne 0 ]; then
    echo ""
    echo "[pre-commit] Tests failed. Commit aborted."
    exit 1
fi
EOF
```

**Windows (PowerShell):**

```powershell
@'
#!/bin/bash
python -m pytest tests/ --tb=short -q
if [ $? -ne 0 ]; then
    echo ""
    echo "[pre-commit] Tests failed. Commit aborted."
    exit 1
fi
'@ | Out-File -FilePath .git\hooks\pre-commit -Encoding utf8
```

---

##### 6.2 実行権限の付与

**Mac / Linux のみ（Windows は不要）:**

```bash
chmod +x .git/hooks/pre-commit
```

---

##### 6.3 動作確認

フックを直接実行して、テストが通過するか確認します：

**Mac / Linux:**

```bash
.git/hooks/pre-commit
```

**Windows (Git Bash):**

```bash
bash .git/hooks/pre-commit
```

以下のように全テストが `passed` と表示されれば設定完了です：

```
.................................................   [100%]
49 passed in 0.16s
```

> **💡 Tip**: 以降はコミット操作のたびにテストが自動実行されます。テストが失敗した場合はコミットがブロックされるので、先にテストを修正してください。

---
