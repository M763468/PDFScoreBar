# Handoff: Issue #7 - Environment Consolidation

## 状態
- **ブランチ**: `task/env-consolidation` (ベース: `main`)
- **タスク**: `BAR-007` (Long-Horizon Task)

## これまでに完了したこと (Phase 1, 2, 3)
1. **Long-Horizon Taskの初期化**: `docs/long-horizon-tasks/BAR-007/` 配下に計画・ログを作成しました。
2. **要求の監査 (Audit)**:
    - 複数のDockerfileや仮想環境を監査しました。
    - `GroundingDINO` はメインパイプライン (`src/pipeline/main.py`) では使われていないため、今回の統合環境からは除外し、アーカイブする方針としました。
3. **統合要件の定義 (pyproject.toml)**:
    - `sr_eval_gpu` コンテナ内の `/opt/venv_sr` で使われていたライブラリ（`ultralytics`, `rapidocr-onnxruntime` など）と、ベースの要件（`PyMuPDF`, `onnxruntime-gpu`, `opencv-python-headless` など）を `pyproject.toml` の `dependencies` に集約しました。
4. **統合 Dockerfile (`Dockerfile.unified`) の作成**:
    - ベースイメージ: `nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04`
    - パッケージ管理: `uv`
    - 仮想環境のパス: `/opt/venv_pipeline`
    - `realesrgan` と `homr` を editable install する記述、および `basicsr` のパッチを含めました。
5. **Python環境の動的解決ロジック (`src/pipeline/core/python_env.py`) の更新**:
    - 新しい統合環境パス `/opt/venv_pipeline` と統合コンテナ名 `pdfscore_pipeline_gpu` を優先的に探索するよう更新しました（後方互換性のため `/opt/venv_sr` や `sr_eval_gpu` へのフォールバックも維持しています）。

ここまでの作業内容はコミット済みです（`f2de576`）。

## 現在発生している問題
`docker build -t pdfscore_pipeline_gpu -f Dockerfile.unified .` を実行した際、Dockerの認証エラー (`error getting credentials - err: exit status 1`) らしきものが発生し、ベースイメージのPullに失敗しました（WSL/Docker Desktop環境特有のエラーである可能性があります）。
そのため、ビルドと検証ステップが完了していません。

## 次のセッションでやること (Phase 4, 5)
1. **Dockerビルドの再試行・解決**:
    - Dockerの認証エラーを解消（`~/.docker/config.json` の `credsStore` の削除など）し、`Dockerfile.unified` のビルドを成功させます。
2. **動作検証 (Phase 4)**:
    - 構築したコンテナ内で `src/pipeline/main.py --config configs/evaluation2_e2e_verification_full.yaml` などを実行し、E2Eで動作することを確認します。
3. **クリーンアップとドキュメント更新 (Phase 5)**:
    - 不要になった `Dockerfile.homr`, `Dockerfile.sr_eval`, `Dockerfile.groundingdino` を削除（またはアーカイブディレクトリへ移動）。
    - `Dockerfile.unified` を `Dockerfile` にリネーム。
    - `docs/ENVIRONMENTS.md` を更新し、新しい統合環境 `pdfscore_pipeline_gpu` の使い方を記載します。
    - `docs/long-horizon-tasks/BAR-007/Log.md` を更新し、タスクをクローズします。

## 引き継ぎ時のコマンド例
```bash
git checkout task/env-consolidation
cat docs/long-horizon-tasks/BAR-007/Plan.md
```
