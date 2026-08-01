# Contributing

本リポジトリは個人のポートフォリオ評価システムであると同時に、**AI駆動開発（Director-Led AI Development）の実証リポジトリ**です。そのため通常の OSS とは前提が異なります。

## このリポジトリの性格

- 実装の大半は AI エージェントが `AGENTS.md` の実行制御規約に従って生成しています
- 設計判断は `docs/adr/` の ADR に記録されます
- 運用者は 1 名であり、機能追加の要望に応える体制は取っていません

そのうえで、以下は歓迎します。

| 種別 | 対応 |
| :--- | :--- |
| バグ報告 | issue でお願いします。再現手順を添えてください |
| ドキュメントの誤り | issue または PR |
| 脆弱性 | issue ではなく [SECURITY.md](./SECURITY.md) の手順で非公開報告 |
| 機能追加の提案 | issue で歓迎しますが、取り込みは保証しません |
| AI駆動開発の手法についての議論 | Discussions / issue で歓迎します |

## PR を出す場合

1. `.github/PULL_REQUEST_TEMPLATE.md` のチェックリストを埋めてください
2. 変更はスコープ内に限定し、既存ロジックの意味を変えないでください
3. 実行した確認コマンドを PR 本文に記載してください

## 開発環境

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env   # 値を埋める
```

検証:

```bash
.venv/bin/pytest
```

## 規約ドキュメント

| ファイル | 内容 |
| :--- | :--- |
| [AGENTS.md](./AGENTS.md) | AI エージェントの実行制御規約（本リポジトリの中核） |
| [docs/orchestration-process.md](./docs/orchestration-process.md) | オーケストレーションの進め方 |
| [docs/prompt-guide.md](./docs/prompt-guide.md) | プロンプト設計指針 |
| [prompts/](./prompts/) | plan / implement / review / audit の各フェーズ用プロンプト |
| [docs/adr/](./docs/adr/) | 設計判断の記録 |

## 含まれないもの

本リポジトリには実データが一切含まれません。`data/` `logs/` `.env` `secret.key` はすべて `.gitignore` 済みです。また、特定金融機関へのログイン自動化・スクレイピング実装は公開範囲に含めていません（[ADR-0001](./docs/adr/ADR-0001-trinity-separation.md) 参照）。
