# Agent Policy for this repo

## Session bootstrap
Perform these steps at the start of every new Gemini CLI or Codex CLI session before making changes:

1. **起動確認:** Docker コンテナ `pdf_score_dev_gpu` を稼働させる。
   ```bash
   docker start pdf_score_dev_gpu
   ```
   開発コマンドをホストから実行する場合は、`docker exec pdf_score_dev_gpu <command>` を用い、コンテナ内 `/workspace` パスを前提とする。

2. **Serena 初期化（任意だが推奨）:** CLI からプロジェクト情報を参照できるようにする。
   ```bash
   bash setup_scripts/setup.sh
   ```
   スクリプトは Serena のプロジェクトインデックス作成と SSE MCP サーバー (port 9121) の起動を行う。

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
