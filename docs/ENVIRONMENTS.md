# Environments

## pdf_score_dev_gpu (existing)
- Purpose: primary development environment for the PDF Score Bar project.
- Image: built from `Dockerfile` (base `nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04`).
- Persistent container: `docker start pdf_score_dev_gpu` → attach with `docker exec -it pdf_score_dev_gpu bash` (workdir `/workspace`).
- Notes: hosts project source; continue using for `oemer`/ML detector workflows.

## homr_eval_gpu (2024-06-14 → refreshed 2025-09-26)
- Purpose: isolate `homr` evaluation environment with separate dependencies.
- Build image: `docker build -t homr_eval -f Dockerfile.homr .` (CUDA 12.1 runtime + cuDNN 9; Poetry installs `homr` with dev deps inside `/opt/poetry/venvs`).
- Container creation: `docker run --gpus all -d --name homr_eval_gpu -v /home/masaki_muramatsu/ws_PDFScoreBar:/workspace -w /workspace homr_eval tail -f /dev/null`.
- Post-create steps: environment is ready immediately. Just run GPU sanity check if needed:
  - `docker exec homr_eval_gpu bash -lc 'cd /workspace/homr && poetry run python -c "import torch, onnxruntime as ort; print(torch.cuda.is_available()); print(ort.get_device())"'`
- Host mount directories:
  - Logs: `/workspace/logs/homr_eval`
  - Models/cache: `/workspace/models/homr`
- Usage: attach with `docker exec -it homr_eval_gpu bash`. `poetry` already manages the venv; run commands from `/workspace/homr` (e.g. `poetry run homr --debug ...`).
- 2025-09-27: `.dockerignore` を追加してビルドコンテキストを縮小（`logs/`, `homr/.venv/`, 大量画像などを除外）。ホスト権限の都合で `docker build` は未実施。必要に応じて権限付与後に再ビルドすること。

## Data directory layout (2024-06-14 年版)
- `data/README.md`: データ管理方針と命名規約のまとめ。更新時は必ずここにも反映する。
- `data/training/`
  - `pdfs/`: 学習用 PDF（例: IMSLP 由来のスコア）。
  - `images/`: 上記 PDF をページ単位で画像化したもの（`page_1.png` など）。
  - `annotations/`: ページごとの Ground Truth を `page_00x/` ディレクトリに整理。`raw_boxes.json` → 手動アノテーション直後、`boxes_sorted.json` → 小節番号順に整列済み。
- `data/evaluation/`
  - `pdfs/`: 検証対象の PDF（`おもちゃの交響曲_bass.pdf` 等）。
  - `images/`: 評価対象 PDF を画像化したもの。`page_1` は表紙、`page_2` は空白、`page_3` 以降が楽譜。
  - `annotations/`: 評価用 Ground Truth を `page_00x/` ごとに配置予定（例: `page_003/boxes_sorted.json`）。
- `data/workbench/`
  - `captures/`: 作業途中の切り出しや比較素材。
  - `drafts/`: 旧版 GT や一次データ（コミット前に棚卸しする）。

> メモ: 既存の `page_1.png` などゼロ埋めでないファイルは順次 `page_001.png` 形式へ移行する。リネーム時はコードとドキュメントの参照先を更新すること。

## Log and artifact policy (2025-09-27)
- 新規実験ログ・成果物は `logs/` 配下に統一（例: `logs/homr_eval/<timestamp>/`）。Git では `logs/` を一括で無視し、必要な指標は JSON/markdown にまとめてリポジトリに保存。
- 過去の OMR 実験に使用していた `debug_outputs/` はアーカイブ用途として残しているが、今後は `logs/` に一本化。既存スクリプト（`homr_evaluator.py` など）はすべて `logs/` を前提に出力する。
- hhmm 形式のタイムスタンプは JST（Asia/Tokyo）で生成される。`20250927T083500JST` のようにサフィックスでタイムゾーンを明示する。
