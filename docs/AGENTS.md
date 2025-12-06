# Agent Policy for This Repo

## Agent Roles

### FP Reduction Agent (Completed Dec 2025)
- **Scope**: Reduce False Positives in barline detection.
- **Status**: Visual heuristics exhausted. Only "Safe Filter" enabled.
- **Reference**: `docs/fp_reduction/FINAL_SUMMARY.md`. Future agents working on GUI or Models should read this first.

### General Coding Agentpo

This guide captures the required bootstrapping steps and execution etiquette for assistants working in the PDF Score Measure Number project.

## Session Bootstrap Checklist
必ず最初に以下を確認・実行する。

1. **起動確認:** `docker ps --filter name=pdf_score_dev_gpu -a` で状態を確認し、停止中なら起動する。
   ```bash
   docker start pdf_score_dev_gpu
   ```
   ホストから開発コマンドを実行する場合は `docker exec pdf_score_dev_gpu <command>` を使い、コンテナ内 `/workspace` を前提とする。

2. **homr 評価が必要な場合:** `docker ps --filter name=homr_eval_gpu -a` で稼働確認し、停止中であれば起動する。
   ```bash
   docker start homr_eval_gpu
   ```
   `homr` リポジトリ直下でのコマンドは `docker exec homr_eval_gpu bash -lc '<command>'` を使う。参照前に `docs/ENVIRONMENTS.md` の「Runtime Containers」を読み、パラメータやマウント先を確認してから作業に入る。

3. **Serena 初期化（必要に応じて）:** リポジトリ構造に大きな変更が入った場合のみ実行する。
   ```bash
   bash setup_scripts/setup.sh
   ```
   スクリプトは Serena のプロジェクトインデックス作成と SSE MCP サーバー (port 9121) を起動する。すでにサーバーが稼働済みであれば省略可。

## Container Maintenance
- 依存関係を更新したら `docker build -t pdf_score_dev_gpu .` で最新イメージを作り直す。
- `homr` 関連の更新がある場合は `docker build -t homr_eval -f Dockerfile.homr .` で `homr_eval_gpu` 用イメージを再構築する。
- 不要になった旧イメージは `docker images` で確認し、`docker image prune -f` もしくは `docker rmi <image>` で早めに削除してストレージを空ける。
- コンテナ再作成時は stop/remove → create の順序を守る。
  ```bash
  docker rm -f pdf_score_dev_gpu
  docker run -dit --name pdf_score_dev_gpu --gpus all \
    -v /home/masaki_muramatsu/ws_PDFScoreBar:/workspace \
    -v /home/masaki_muramatsu/.ssh:/root/.ssh:ro \
    -w /workspace pdf_score_dev_gpu tail -f /dev/null
  ```
  `tail -f /dev/null` により常時起動を維持し、`docker exec -it pdf_score_dev_gpu bash` ですぐ作業できる。

## Execution Style Guidelines
- コマンド実行前に目的を共有し、`rg`・`ls`・`sed` など最小限のツールで情報を取得する。
- 変更後は関連テストやスクリプト（例: `pytest -q`）をコンテナ内で実行し、結果を報告する。
- 作業終了時には差分と未完了事項を要約する。

## Required Documentation Updates
セッション完了時はユーザーと合意の上で以下を更新する：
- `docs/DEVELOPMENT_LOG.md` – 主要な作業内容と意思決定
- `docs/NEXT_SESSION_NOTES.md` – 次回タスクや未解決事項
- `README.md` – プロジェクト全体のセットアップや利用方法に変更があった場合のみ

## Kickoff Checklist
- `docs/README.md` でドキュメントマップを確認し、続けて `docs/NEXT_SESSION_NOTES.md` の「現在の優先事項」を読む。
- 直近の環境変更は `docs/ENVIRONMENTS.md` の更新履歴を参照する。
- 着手前に既存の `logs/` やデータ出力先をざっと確認し、重複実験を避ける。

## Maintenance Notes
- 作業完了後は `docs/NEXT_SESSION_NOTES.md` の「最近の差分サマリ」を最新状態にし、詳細な出来事は `docs/DEVELOPMENT_LOG.md` の該当フェーズへ追記する。
- `prompt.txt` と `docs/README.md` の開始手順が乖離していないかを週次など定期的に確認し、差異があれば `docs/NEXT_SESSION_NOTES.md` へメモしたうえで調整する。
- ログ出力や artefact の命名規約（`logs/<pipeline>/<timestamp>/...` など）を守り、不要になった成果物は整理してからセッションを閉じる。

## Reference Map
全体像と関連ドキュメントの位置付けは `docs/README.md` を参照すること。
