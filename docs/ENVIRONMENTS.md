# Environment & Tooling Guide

> [!NOTE]
> **Path Changes (Dec 2025)**: The repository has been restructured.
> - Tools previously in `src/tools/` are now in `tools/`.
> - `homr` and `oemer` repositories are now in `external/`.
> - Analysis scripts are in `experiments/`.
> If you see older paths in logs or docs, please adjust accordingly.

This document describes how to use the provided tools (now located in `tools/`) and Docker environments.

## GUI Helper Environment
- **Tool Location**: `tools/gui_helper/`
- **Execution**: Runs directly on the Host (WSL/Linux), **no Docker required**.
- **Dependencies**: Minimal. Requires `flask` and `Pillow`.
- **Display**: Served via HTTP (`localhost:5000`), allowing usage in any browser (no X11 forwarding needed).
- **Note**: Ensure `config.py` points to valid image/JSON paths on your host filesystem.

## Runtime Containers

### pdf_score_dev_gpu
- Purpose: primary development environment for the PDF Score Bar project.
- Image: built from `Dockerfile` (base `nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04`).
- Persistent container: `docker start pdf_score_dev_gpu` → attach with `docker exec -it pdf_score_dev_gpu bash` (workdir `/workspace`).
- Notes: hosts project source; continue using for `oemer`/ML detector workflows.
- 2025-10-07: Dockerfile updated and image rebuilt as `pdf_score_dev_gpu:20251007b`; container re-created with baked `.venv_pdf` dependencies (PyMuPDF 1.26.4, opencv-python-headless 4.12.0.88, onnxruntime-gpu 1.22.0, Pillow 11.3.0, SciPy 1.15.3, scikit-learn 1.7.2, matplotlib 3.10.6, coloredlogs 15.0.1) plus tzdata. Verified via `pip list` inside container.

### homr_eval_gpu (2024-06-14 → refreshed 2025-09-26)
- Purpose: isolate `homr` evaluation environment with separate dependencies.
- Build image: `docker build -t homr_eval -f Dockerfile.homr .` (CUDA 12.1 runtime + cuDNN 9; Poetry installs `homr` with dev deps inside `/opt/poetry/venvs`).
- Container creation: `docker run --gpus all -d --name homr_eval_gpu -v /home/masaki_muramatsu/ws_PDFScoreBar:/workspace -w /workspace homr_eval tail -f /dev/null`.
- Post-create steps: environment is ready immediately. Run GPU sanity check if needed:
  - `docker exec homr_eval_gpu bash -lc 'cd /workspace/homr && poetry run python -c "import torch, onnxruntime as ort; print(torch.cuda.is_available()); print(ort.get_device())"'`
- Host mount directories:
  - Logs: `/workspace/logs/homr_eval`
  - Models/cache: `/workspace/models/homr`
- Usage: attach with `docker exec -it homr_eval_gpu bash`. `poetry` already manages the venv; run commands from `/workspace/homr` (e.g. `poetry run homr --debug ...`).
- 2025-10-07: Dockerfile.homr rebuilt as `homr_eval:20251007b` with `.venv_pdf` parity packages inside the Poetry venv (PyMuPDF 1.26.4, opencv-python-headless 4.12.0.88, onnxruntime-gpu 1.22.0, Pillow 11.3.0, SciPy 1.15.3, scikit-learn 1.7.2, matplotlib 3.10.6, coloredlogs 15.0.1) plus tzdata; `homr_eval_gpu` container recreated and packages verified via `poetry run python -m pip list`.
- 2025-09-27: `.dockerignore` を追加してビルドコンテキストを縮小（`logs/`, `homr/.venv/`, 大量画像などを除外）。ホスト権限の都合で `docker build` は未実施。必要に応じて権限付与後に再ビルドすること。

## Data Directory Layout
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

## Log and Artifact Policy (2025-09-27)
- 新規実験ログ・成果物は `logs/` 配下に統一（例: `logs/homr_eval/<timestamp>/`）。Git では `logs/` を一括で無視し、必要な指標は JSON/markdown にまとめてリポジトリに保存。
- 過去の OMR 実験に使用していた `debug_outputs/` はアーカイブ用途として残しているが、今後は `logs/` に一本化。既存スクリプト（`homr_evaluator.py` など）はすべて `logs/` を前提に出力する。
- hhmm 形式のタイムスタンプは JST（Asia/Tokyo）で生成される。`20250927T083500JST` のようにサフィックスでタイムゾーンを明示する。

## Barline Review Workflow
- homr デバッグマスクの可視化: `tools/generate_barline_overlay.py --base data/evaluation/images/<page>.png --mask logs/.../page_<n>_debug_8_bar_line_img.png --output logs/.../<timestamp>_debug_overlay.png`
- JSON 由来の矩形確認: `tools/render_barline_boxes_overlay.py --base data/evaluation/images/<page>.png --boxes <path/to/boxes.json> --output logs/.../<timestamp>_boxes_overlay.png`
- いずれの画像も `logs/homr_eval/<run>/` 配下に保存し、レビュー時にはこの2種類のオーバーレイをセットで提示する。
- 修正点の共有には `src/tools/coordinate_annotator.py` を利用し、対象ページの `IMAGE_PATH` / `GROUND_TRUTH_OUTPUT_PATH` を切り替えて矩形を再指定する。保存後は `tools/render_barline_boxes_overlay.py` で差分確認を行う。

## homr Evaluation Workflow and Log Paths

This section defines the standardized procedure for running barline detection evaluations with the `homr` pipeline.

- **Container**: All `homr` evaluations must be run inside the `homr_eval_gpu` container.

- **Canonical Command**: The following command structure should be used for all evaluations. It ensures consistency in execution environment, paths, and logging.

  ```bash
  docker exec homr_eval_gpu bash -c "
    cd /workspace/homr &&
    poetry run python /workspace/src/homr/homr_evaluator.py \
      --images /workspace/data/evaluation/images/page_3.png \
      --ground-truth page_3:/workspace/data/evaluation/annotations/page_003/boxes_sorted.json \
      --output-root /workspace/logs/homr_eval \
      --force-run-id <your_run_id>
  "
  ```
  - `<your_run_id>` should be a descriptive identifier, e.g., `20251201T_homr_heuristic1`.

- **Log Output Paths**:
  - **Canonical Path**: With the standardized command, all evaluation artifacts (metrics, overlays, etc.) will appear on the host machine under:
    - `logs/homr_eval/<your_run_id>/`
    - Example: `logs/homr_eval/20251201T_homr_heuristic1/metrics.json`
  - **Historical Path**: Older runs (e.g., Phase 28 baseline, `20251130T185351JST`) used a different output root (`--output-root logs`). Their outputs are located directly under `logs/` on the host:
    - Example: `logs/20251130T185351JST/metrics.json`
  - This difference is expected. The standardization on `/workspace/logs/homr_eval` aims to prevent future confusion. A temporary issue on 2025-12-01 where new logs were not immediately visible on the host was determined to be a transient environment/volume visibility problem, not a code bug.

