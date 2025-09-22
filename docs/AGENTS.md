# Agent Policy for this repo

## Session bootstrap
Perform these steps at the start of every new Gemini CLI or Codex CLI session before making changes:

1. **起動確認:** Docker コンテナ `pdf_score_dev_gpu` を稼働させる。
   ```bash
   docker start pdf_score_dev_gpu
   ```
   開発コマンドをホストから実行する場合は、`docker exec pdf_score_dev_gpu <command>` を用い、コンテナ内 `/workspace` パスを前提とする。

2. **Serena 初期化（任意）:** CLI からプロジェクト情報を参照できるようにする。
   エージェント自身がserena mcpサーバーを起動できる場合は不要
   ```bash
   bash setup_scripts/setup.sh
   ```
   スクリプトは Serena のプロジェクトインデックス作成と SSE MCP サーバー (port 9121) の起動を行う。

## Docker maintenance
- 依存関係を更新したら最新のイメージをビルドする。
  ```bash
  docker build -t pdf_score_dev_gpu .
  ```
- 古いコンテナを入れ替える際は stop/remove → create の順に実行する。
  ```bash
  docker rm -f pdf_score_dev_gpu
  docker run -dit --name pdf_score_dev_gpu --gpus all \
    -v /home/masaki_muramatsu/ws_PDFScoreBar:/workspace \
    -v /home/masaki_muramatsu/.ssh:/root/.ssh:ro \
    -w /workspace pdf_score_dev_gpu tail -f /dev/null
  ```
  `tail -f /dev/null` を指定することで常時起動状態を維持し、`docker exec -it pdf_score_dev_gpu bash` での作業がすぐ行える。

## Execution style
- コマンド実行前に目的を簡潔に共有し、必要最小限のツールで情報を取得する（`rg`・`ls`・`sed` 等）。
- 変更後は関連テストやスクリプト（`pytest -q` など）をコンテナ内で実行し、結果を報告する。
- 作業終了時には差分と未完了事項を要約する。

## End-of-session docs
ユーザーと合意の上で以下の Markdown を更新する：
- `docs/DEVELOPMENT_LOG.md` – 主要な作業内容と意思決定
- `docs/NEXT_SESSION_NOTES.md` – 次回タスクや未解決事項
- `README.md` – プロジェクト全体のセットアップや利用方法の変更があった場合のみ

## Project context quick links
- プロジェクト概要・利用方法: `README.md`
- 開発履歴と意思決定: `docs/DEVELOPMENT_LOG.md`
- 現在の計画やメモ: `docs/NEXT_SESSION_NOTES.md`
- エージェント運用ガイド: `docs/AGENTS.md`
