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

## CNN Classifier Environment (Host / uv)
- **Purpose**: Train the CNN classifier used to filter barline false positives.
- **Virtualenv**: `.venv_cnn_classifier` (copied from the current `.venv` contents).
- **Rebuild**:
  ```bash
  uv venv .venv_cnn_classifier
  uv pip sync experiments/cnn_classifier/requirements_cnn_classifier_venv.txt
  ```
- **Dataset**: `/mnt/d/datasets/cnn_classifier_v1` (override with `CNN_DATASET_ROOT` env var).
- **Dataset build**:
  ```bash
  .venv_cnn_classifier/bin/python tools/cnn_classifier/build_cnn_dataset.py
  ```
- **Training**:
  ```bash
  .venv_cnn_classifier/bin/python experiments/cnn_classifier/train.py
  ```

## Runtime Containers

### pdf_score_dev_gpu
- Purpose: primary development environment for the PDF Score Bar project.
- Image: built from `Dockerfile` (base `nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04`).
- Persistent container: `docker start pdf_score_dev_gpu` → attach with `docker exec -it pdf_score_dev_gpu bash` (workdir `/workspace`).
- Notes: hosts project source; continue using for `oemer`/ML detector workflows.
- 2025-10-07: Dockerfile updated and image rebuilt as `pdf_score_dev_gpu:20251007b`; container re-created with baked `.venv_pdf` dependencies (PyMuPDF 1.26.4, opencv-python-headless 4.12.0.88, onnxruntime-gpu 1.22.0, Pillow 11.3.0, SciPy 1.15.3, scikit-learn 1.7.2, matplotlib 3.10.6, coloredlogs 15.0.1) plus tzdata. Verified via `pip list` inside container.

### homr_eval_gpu (2024-06-14 → refreshed 2025-09-26)
- Purpose: isolate `homr` evaluation environment with separate dependencies.
- **Note**: This environment is NOT suitable for running Super-Resolution (SR) tasks with Real-ESRGAN, as it lacks the necessary dependencies and patches. Use `sr_eval_gpu` instead.
- Build image: `docker build -t homr_eval -f Dockerfile.homr .` (CUDA 12.1 runtime + cuDNN 9; Poetry installs `homr` with dev deps inside `/opt/poetry/venvs`).
- Container creation: `docker run --gpus all -d --name homr_eval_gpu -v "$(pwd):/workspace" -w /workspace homr_eval tail -f /dev/null`.
- Post-create steps: After creating the container, dependencies must be explicitly installed.
  - **Install Dependencies**: Run `docker exec homr_eval_gpu bash -c "cd /workspace/external/homr && poetry install"` to ensure all packages from `poetry.lock` are installed in the virtual environment. This is necessary to avoid `ModuleNotFoundError` for packages like `cv2`.
  - **GPU Sanity Check**: `docker exec homr_eval_gpu bash -lc 'cd /workspace/external/homr && poetry run python -c "import torch, onnxruntime as ort; print(torch.cuda.is_available()); print(ort.get_device())"'`
- Host mount directories:
  - Logs: `/workspace/logs/homr_eval`
  - Models/cache: `/workspace/models/homr`
- Usage: attach with `docker exec -it homr_eval_gpu bash`. `poetry` already manages the venv; run commands from `/workspace/homr` (e.g. `poetry run homr --debug ...`).
- 2025-10-07: Dockerfile.homr rebuilt as `homr_eval:20251007b` with `.venv_pdf` parity packages inside the Poetry venv (PyMuPDF 1.26.4, opencv-python-headless 4.12.0.88, onnxruntime-gpu 1.22.0, Pillow 11.3.0, SciPy 1.15.3, scikit-learn 1.7.2, matplotlib 3.10.6, coloredlogs 15.0.1) plus tzdata; `homr_eval_gpu` container recreated and packages verified via `poetry run python -m pip list`.
- 2025-09-27: `.dockerignore` を追加してビルドコンテキストを縮小（`logs/`, `homr/.venv/`, 大量画像などを除外）。ホスト権限の都合で `docker build` は未実施。必要に応じて権限付与後に再ビルドすること。

### sr_eval_gpu
- Purpose: Dedicated environment for Super-Resolution (SR) enabled barline detection experiments using Real-ESRGAN. This environment includes all necessary patches and dependencies for functional SR.
- Image: built from `Dockerfile.sr_eval` (base `nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04`).
- Build image: `docker build -t sr_eval -f Dockerfile.sr_eval .`
- Container creation: `docker run --gpus all -d --name sr_eval_gpu -v "$(pwd):/workspace" -w /workspace sr_eval tail -f /dev/null`.
- Usage: attach with `docker exec -it sr_eval_gpu bash`. All `uv` managed dependencies are in `/opt/venv_sr`.
    - To run scripts: `docker exec sr_eval_gpu bash -c "/opt/venv_sr/bin/python <script_path>"`
    - For example: `docker exec sr_eval_gpu bash -c "/opt/venv_sr/bin/python experiments/models/eval_omr_dln.py --enable-sr ..."`

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
- 修正点の共有には `tools/gt_relabel_gui` の GT エディタを優先利用する（ブラウザ上で拡大縮小・削除・追加が可能）。
- `tools/coordinate_annotator.py` は **LEGACY** として残している（ズーム/パンが弱く正確なGT作業に不向き）。

### GT Editor (browser, recommended)
Run the browser-based GT editor with a config file:
```bash
python3 tools/gt_relabel_gui/server.py \
  --mode gt \
  --config logs/phase6_detector_miss/gt_rebuild/gt_editor_config.json \
  --port 8010 \
  --host 0.0.0.0
```
Open in a browser: `http://127.0.0.1:8010`

The editor writes:
- `output_raw` (unsorted GT)
- `output_sorted` (sorted GT with measure_number)

#### GT Rebuild Config (2025-12-29)
The rebuilt GT session can be re-opened using the saved config:
```bash
python3 tools/gt_relabel_gui/server.py \
  --mode gt \
  --config logs/phase6_detector_miss/gt_rebuild/gt_editor_config.json \
  --port 8010 \
  --host 0.0.0.0
```
- Reuse point: `logs/phase6_detector_miss/gt_rebuild/gt_editor_config.json`
- Outputs (authoritative GT for rebuild): `logs/phase6_detector_miss/gt_rebuild/`

## homr Evaluation Workflow and Log Paths

This section defines the standardized procedure for running barline detection evaluations with the `homr` pipeline.

- **Container**: All `homr` evaluations must be run inside the `homr_eval_gpu` container.

- **Canonical Command**: The following command structure should be used for all evaluations. It ensures consistency in execution environment, paths, and logging.

  ```bash
  docker exec homr_eval_gpu bash -c "
      cd /workspace/external/homr &&
        poetry run python /workspace/src/homr_eval_scripts/homr_evaluator.py \
          --images /workspace/data/evaluation/images/page_3.png \
          --ground-truth page_3:/workspace/data/evaluation/annotations/page_003/boxes_sorted.json \
          --output-root /workspace/logs/homr_eval \
          --force-run-id <your_run_id>
    "  ```
  - `<your_run_id>` should be a descriptive identifier, e.g., `20251201T_homr_heuristic1`.

- **Log Output Paths**:
  - **Canonical Path**: With the standardized command, all evaluation artifacts (metrics, overlays, etc.) will appear on the host machine under:
    - `logs/homr_eval/<your_run_id>/`
    - Example: `logs/homr_eval/20251201T_homr_heuristic1/metrics.json`
  - **Historical Path**: Older runs (e.g., Phase 28 baseline, `20251130T185351JST`) used a different output root (`--output-root logs`). Their outputs are located directly under `logs/` on the host:
    - Example: `logs/archive/20251130T185351JST/metrics.json`
  - This difference is expected. The standardization on `/workspace/logs/homr_eval` aims to prevent future confusion. A temporary issue on 2025-12-01 where new logs were not immediately visible on the host was determined to be a transient environment/volume visibility problem, not a code bug.

### Model Experiments Environment (feature/barline_model_experiments)

This section documents the setup and usage of the virtual environments and key commands for the model-based barline detection experiments conducted in the `feature/barline_model_experiments` worktree.

-   **Worktree Location**: The current project worktree is located at `/home/masaki_muramatsu/ws_PDFScoreBar_model_exp`.
-   **Virtual Environments**:
    -   `.venv_yolo`: Used for YOLO-World experiments. Contains `ultralytics` and its dependencies.
    -   `.venv_omr_dln`: Used for OMR-DLN (dmgonzalez8/OMR) experiments. Contains `ultralytics`, `torch`, `torchvision`, `opencv-python-headless` and other dependencies.

-   **Key Commands**:

    ```bash
    # YOLO-World synthetic sanity test
    source .venv_yolo/bin/activate
    python tools/create_synthetic_image.py
    python experiments/models/eval_yolo_world.py \
        --image data/workbench/synthetic_barline_test.png \
        --gt data/workbench/dummy_gt.json \
        --output-dir logs/model_experiments/yolo_world/synth_test \
        --conf 0.05
    ```

    ```bash
    # OMR-DLN (measure-based) evaluation on page_3
    source .venv_omr_dln/bin/activate
    python experiments/models/eval_omr_dln.py \
        --image data/evaluation/images/page_3.png \
        --gt data/evaluation/annotations/page_003/boxes_sorted.json \
        --output-dir logs/model_experiments/omr_dln/run_001 \
        --conf 0.25
    ```

-   **Important Note**: These environments are strictly for **evaluation of existing pretrained models only**. They are not set up for training new models or for creating new annotated datasets.

### PDF Rendering Environment (.venv_pdf)

This environment is used for converting PDF scores into images using `src/pdf_to_images.py`.

-   **Creation**:
    ```bash
    uv venv .venv_pdf
    source .venv_pdf/bin/activate
    uv pip install pymupdf opencv-python-headless numpy
    ```

-   **Usage**:
    ```bash
    source .venv_pdf/bin/activate
    python src/pdf_to_images.py \
        --pdf data/evaluation/pdfs/target.pdf \
        --output-dir data/evaluation/images/target_subdir \
        --prefix page
    ```

## Advanced Super-Resolution & Hybrid Methodology (2025-12-13)

### 1. homr Evaluation with Real-ESRGAN
Run inside `homr_eval_gpu`. Requires `--enable-sr` flag.
```bash
cd /workspace/external/homr
poetry run python /workspace/src/homr_eval_scripts/homr_evaluator.py \
    --images /workspace/data/evaluation/images/page_3.png \
    --ground-truth page_3:/workspace/data/evaluation/annotations/page_003/boxes_sorted.json \
    --output-root /workspace/logs/homr_eval_sr \
    --enable-sr
```

### 2. OMR-DLN Evaluation with Real-ESRGAN
Run inside `homr_eval_gpu` (requires `ultralytics` installed via poetry).
```bash
cd /workspace/external/homr
poetry run python /workspace/experiments/models/eval_omr_dln.py \
    --image /workspace/data/evaluation/images/page_3.png \
    --gt /workspace/data/evaluation/annotations/page_003/boxes_sorted.json \
    --output-dir /workspace/logs/omr_dln_sr \
    --enable-sr
```

### 3. Hybrid Analysis & Result Generation
Combines results from Baseline (no SR), `homr` (SR), and `OMR-DLN` (SR).
```bash
# Analyze and Generate Final Results
poetry run python /workspace/tools/generate_hybrid_results.py \
    --baseline <path_to_baseline_json> \
    --sr <path_to_homr_sr_json> \
    --omr <path_to_omr_sr_json> \
    --gt <path_to_gt_json> \
    --output /workspace/logs/hybrid_results.json
```

### 4. Automated Hybrid Pipeline
The `run_hybrid_pipeline.sh` script automates steps 1-3 (Baseline -> SR -> OMR -> Hybrid).

```bash
# Run full pipeline (with GT for metrics)
./tools/run_hybrid_pipeline.sh --image data/training/images/page_10.png --run-id page_10_test --gt data/training/annotations/page_010/boxes_sorted.json

# Run inference only (no GT)
./tools/run_hybrid_pipeline.sh --image data/evaluation/images/new_score.png --run-id new_score_test

# Reuse a precomputed SR image to skip SR generation in Step 2
./tools/run_hybrid_pipeline.sh \
  --image data/evaluation/images/page_3.png \
  --run-id page_3_reuse_sr \
  --gt data/evaluation/annotations/page_003/boxes_sorted.json \
  --sr-image logs/hybrid_pipeline_bench/<run_id>/sr/page_3/page_3/page_3.png
```

### Optional Debug Logging
- **Segnet ORT provider logging** (for CUDA/CPU diagnostics):
  ```bash
  export HOMR_DEBUG_PROVIDERS=1
  ```

### 5. `sr_eval_gpu_opt` Container (2026-01-16)
Used for the optimized hybrid pipeline in the `ws_PDFScoreBar_training` worktree.
To resolve symlinks (e.g., `external/homr` pointing to the main repo) inside the container, the main repository path is also mounted.

- **Creation Command**:
  ```bash
  docker run -itd --gpus all \
    --name sr_eval_gpu_opt \
    -v /home/masaki_muramatsu/ws_PDFScoreBar_training:/workspace \
    -v /home/masaki_muramatsu/ws_PDFScoreBar_training/.serena:/root/.serena \
    -v /home/masaki_muramatsu/ws_PDFScoreBar:/home/masaki_muramatsu/ws_PDFScoreBar \
    sr_eval
  ```
- **Reason**: The worktree uses a symlink for `external/homr` that points to an absolute path in the main repo. Standard mounting of just the worktree breaks this link inside the container. Mounting both paths allows the symlink to resolve correctly.

---
## Reproducibility checks (required)
- Always record **commit hash + full command + output path** for any baseline/adopted result.
- Explicitly pin parameters that are easy to miss (`probe_row_filter_mode`, `probe_endpoint_x_scale`, `probe_endpoint_y_scale`).
- Before reruns, verify that `union_root`, GT, and mask paths point to the same dataset version used originally.

---
## Phase 4: Geometry Note-Context Filter (page_3 confirmed) (2025-12-18)

This section documents the environment/artifact assumptions for the Phase 4 “note-context” filter used to remove stem-like false barlines using `homr` semantic outputs.

### Required homr Artifacts
The geometry filter consumes `homr` note-related masks for the same page:
- Notehead mask: `page_3_debug_6_notehead.png`
- Stems/rest mask: `page_3_debug_5_stems_rest.png`

These are produced as part of `homr_evaluator.py` debug outputs and typically live under a run directory such as:
- `logs/homr_eval_baseline/<run_id>/page_3/` (host path)

### Alignment Assumptions
The geometry filter requires that:
- The barline candidate boxes (e.g., from `logs/hybrid_results.json`) are in the coordinate space of the evaluation image (e.g., `data/evaluation/images/page_3.png`).
- The `homr` mask images correspond to the same page and are aligned to the same coordinate system.

Implementation note: the Phase 4 code resizes masks to match `--image` resolution using nearest-neighbour interpolation when sizes differ, but the masks must still represent the same page content (no page mismatch).

### Running the Filter (page_3, confirmed configuration)
The Phase 4 geometry filter is implemented in:
- `experiments/fp_reduction/analyze_staff_consistency.py`

It is disabled by default and can be enabled with a `homr` context directory:
```bash
.venv_pdf/bin/python experiments/fp_reduction/analyze_staff_consistency.py \
  --json logs/hybrid_results.json \
  --image data/evaluation/images/page_3.png \
  --gt data/evaluation/annotations/page_003/boxes_sorted.json \
  --output logs/phase4_notehead_geom/<run_id>/ \
  --no-use-ratio-tolerance --tol-top-px 5 --tol-bottom-px 5 \
  --enable-geom-notehead-filter \
  --geom-notehead-mode page3_known_fp \
  --homr-context-dir logs/homr_eval_baseline/<run_id>/page_3
```

### Current Limitation (Important)
- The confirmed-safe geometry mode is **page_3-specific** (correctness-first) and is intended as a stable milestone before implementing and validating a general rule on additional pages.
