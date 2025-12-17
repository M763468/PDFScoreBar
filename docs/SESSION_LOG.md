# Session Log (2025-12-17)

## 2. Create Reproducible SR Evaluation Environment

**Goal**: Create a dedicated Docker environment (`Dockerfile.sr_eval`) that automates all the necessary patches and dependencies for the SR pipeline, ensuring robustness and reproducibility.

**Status**: File modifications complete. Entering verification phase.

**Plan**:
1.  ~~Create `Dockerfile.sr_eval` with all required build steps (venv setup, dependencies, patches, model download).~~
2.  ~~Update `docs/ENVIRONMENTS.md` to document the new `sr_eval_gpu` container.~~
3.  ~~Modify `tools/run_hybrid_pipeline.sh` to use the new `sr_eval_gpu` container.~~
4.  Verify the new setup by building the Docker image, running a container, and executing the `run_hybrid_pipeline.sh` script.

## 2025-12-16 (Codex CLI)

- Read `README.md`, `docs/README.md`, `docs/NEXT_SESSION_NOTES.md` to align on project goal + current confirmed state.
- Session constraints: write working notes here; do not edit `docs/DEVELOPMENT_LOG.md`; edit `docs/NEXT_SESSION_NOTES.md` only for clearly confirmed updates.

## 2025-12-17 02:23 JST (Codex CLI)

### Session Goal (per user)
- `docs/NEXT_SESSION_NOTES.md` の「Remaining Work / Next Session Tasks」を順番に進める。
- `docs/SESSION_LOG.md` を読み、途中の作業は途中から再開する（現状: SR eval 環境の verification phase）。

### Hard Constraints
- 07:00 JST になった時点で、未完了でも必ず終了処理（完了要約/未完了分解/再開前提/停止）を実施して停止する。
- `docs/DEVELOPMENT_LOG.md` は更新しない。
- `docs/NEXT_SESSION_NOTES.md` は「明確に confirmed」になった場合のみ更新する（それ以外はここにメモ）。

### Current Focus
- High Priority #1「Reproducible SR Evaluation Environment」の verification: `Dockerfile.sr_eval` で `sr_eval` イメージを build → `sr_eval_gpu` 起動 → `tools/run_hybrid_pipeline.sh` が意図通り `sr_eval_gpu` を使って動くことを確認する。

### Assumptions / Risks
- Docker build は apt/pip/wget でネットワークアクセスが必要。`network_access=restricted` のため、必要になったら承認をリクエストして進める。

### Checkpoint (02:26 JST)
- `docker ps` 実行で `permission denied while trying to connect to the docker API at unix:///var/run/docker.sock` を確認。
  - 現状の sandbox 権限では Docker 操作ができないため、verification（build/run/exec）がブロックされる。
  - ただし `docker_build_sr_eval.log` が存在し、過去には `Dockerfile.sr_eval` の build が走っている形跡はある（このセッションでは未検証）。

### Update (02:27 JST)
- 実行環境が `danger-full-access` に切り替わり、Docker API へアクセス可能になった。
- 現時点の `docker images` には `sr_eval` イメージが存在しないため、改めて build から verification を再開する必要あり。

## 2025-12-17 02:28 JST (Codex CLI)

- Read `README.md`, `docs/README.md`, `docs/NEXT_SESSION_NOTES.md` per session bootstrap request; aligned on ultimate goal + doc update policy.
- Ready to start short-iteration work; will log all working notes here and avoid edits to `docs/DEVELOPMENT_LOG.md` (and only update `docs/NEXT_SESSION_NOTES.md` when something becomes clearly confirmed).

## 2025-12-17 02:31 JST (Codex CLI)

### Next Task (Resume)
- Per `docs/NEXT_SESSION_NOTES.md` High Priority #1: verify the new SR evaluation Docker environment end-to-end.
- Concrete verification target:
  1) `docker build -t sr_eval -f Dockerfile.sr_eval .`
  2) `docker run --gpus all -d --name sr_eval_gpu -v "$(pwd):/workspace" -w /workspace sr_eval tail -f /dev/null`
  3) run `./tools/run_hybrid_pipeline.sh` against a known image (start with page_3 + GT for a quick smoke test).

### Assumptions / Risks
- Docker build will download `RealESRGAN_x4plus.pth` from GitHub; if the URL changes, build will fail.
- `Dockerfile.sr_eval` currently does `COPY . /workspace` and also the container is intended to run with a host bind-mount; the bind-mount will override the image contents at runtime (OK, but worth remembering for reproducibility).

### Checkpoint (Build Attempt)
- Ran: `docker build -t sr_eval -f Dockerfile.sr_eval . |& tee docker_build_sr_eval_20251217_0232.log`
- Result: **FAILED** due to a `SyntaxError` in the `python -c` one-liner that attempted to generate `external/realesrgan/realesrgan/version.py`.
  - Observation: `external/realesrgan/realesrgan/version.py` already exists in this repo, and `src/common/preprocessing.py` imports `realesrgan` via `sys.path` injection (so we don't need to generate version metadata during image build).
- Fix applied:
  - Removed the `version.py` generation block from `Dockerfile.sr_eval`.
  - Made the weights download conditional (`test -f ... || wget ...`) so builds can succeed offline when the weights are already in the repo.
- Next: re-run the docker build and proceed to container run + smoke test.

### Checkpoint (Smoke Test Attempt)
- Ran (host): `./tools/run_hybrid_pipeline.sh --image data/evaluation/images/page_3.png --run-id sr_eval_smoke_page3 --gt data/evaluation/annotations/page_003/boxes_sorted.json`
- Result: **FAILED immediately** in Step 1 with `poetry: command not found` inside `sr_eval_gpu`.
- Diagnosis:
  - `tools/run_hybrid_pipeline.sh` currently assumes `poetry` exists in `sr_eval_gpu` (it was originally written around `homr_eval_gpu`).
  - `Dockerfile.sr_eval` currently installs SR dependencies into `/opt/venv_sr` via `uv`, but does not install `poetry` nor the full `homr` dependency set into the same environment.
- Working hypothesis / direction:
  - Make the SR container self-contained by installing `external/homr` dependencies into `/opt/venv_sr` (using `uv pip install ./external/homr`) and run the pipeline via `/opt/venv_sr/bin/python` instead of `poetry`.
  - Also adjust `src/homr_eval_scripts/homr_evaluator.py` to locate `homr` under `external/homr` (repo restructure) while keeping backward compatibility if `/workspace/homr` exists.

### Checkpoint (Dockerfile rebuild attempt w/ homr deps)
- Attempted to bake `homr` deps into `sr_eval` image via `RUN uv pip install ./external/homr`.
- Build failed because `.dockerignore` excluded `external/homr/`, so the directory was not present in the build context (`error: Distribution not found at: file:///workspace/external/homr`).
- Fix applied: removed `external/homr/` from `.dockerignore` so `Dockerfile.sr_eval` can install from the local submodule during build.

## 2025-12-17 03:13 JST (Codex CLI)

### SR Eval Environment Verification (High Priority #1)
- Rebuilt `sr_eval` successfully after fixes:
  - `Dockerfile.sr_eval`: added `ensurepip`, installed `external/homr` into `/opt/venv_sr`, switched to `onnxruntime-gpu==1.22.0`, added required OS libs (`libgl1`, `libglib2.0-0`, `tzdata`).
  - `.dockerignore`: removed the `external/homr/` exclusion so the build context contains the homr submodule.
  - `tools/run_hybrid_pipeline.sh`: switched execution from `poetry run` → `/opt/venv_sr/bin/python` inside `sr_eval_gpu`.
  - `src/homr_eval_scripts/homr_evaluator.py`: updated to locate `homr` under `external/homr` (fallback to legacy `homr/` if present).

### Smoke Test Run (page_3 + GT)
- Ran: `./tools/run_hybrid_pipeline.sh --image data/evaluation/images/page_3.png --run-id sr_eval_smoke_page3 --gt data/evaluation/annotations/page_003/boxes_sorted.json`
- Output dir: `logs/hybrid_generalization/sr_eval_smoke_page3/`
- Result: ✅ completed end-to-end.
  - Hybrid summary (from Step 4): **TP=152, FP=8, FN=0** (Precision 0.95, Recall 1.0), `Hybrid Predictions: 177`.
  - Confirms the SR-enabled container can run Baseline + SR + OMR-DLN(SR) + hybrid merge.

### Notes / Caveats
- Many artifacts under `logs/hybrid_generalization/sr_eval_smoke_page3/` are owned by `root` (because `docker exec` runs as root). This is annoying for cleanup/edits on host; fix later by running container with `--user "$(id -u):$(id -g)"` or adjusting `docker exec -u`.

## 2025-12-17 03:22 JST (Codex CLI)

### High Priority #2: Investigate FN Issue (Start)

#### Quick Reproduction via Existing Artifacts (page_10 / page_15)
- Looked at existing hybrid generalization runs:
  - `logs/hybrid_generalization/page_10_hybrid_test/`
  - `logs/hybrid_generalization/page_15_hybrid_test/`
- Computed rough X-range coverage from the JSON inputs used by `tools/generate_hybrid_results.py`:
  - Images are `2700 x 3600` (confirmed via `file .../page_10.png` / `file .../page_15.png`).
  - Baseline bboxes reach near the right edge (max x ≈ 2550).
  - **But** SR + OMR bboxes are constrained to x ≤ ~640 (≈ 2700/4).
    - Example (page_10 SR): max x1=636, max x2=637; sample bbox `(636, 817, 637, 835)`.
    - Similar for OMR predictions and page_15.
  - Hybrid rule keeps only Baseline boxes supported by SR or OMR, so the hybrid output drops most right-side barlines → looks like massive FN in qualitative overlays.

#### Hypothesis (Likely Root Cause)
- In both `src/homr_eval_scripts/homr_evaluator.py` and `experiments/models/eval_omr_dln.py`, the code sets `sr_scale=4` whenever `--enable-sr` is passed, then always scales predicted bboxes back by dividing by `sr_scale`.
- If SR *did not actually upscale* the image (e.g., SR failed silently and returned same-size output), the bbox division shrinks coordinates by 4 → outputs cover only the left quarter of the page.
- Next step: add a runtime check for actual SR success (compare pre/post image dimensions) and only apply `sr_scale` division when SR truly changed the resolution.

#### Implementation Notes (in-progress)
- Implemented “effective SR scale” checks:
  - `src/homr_eval_scripts/homr_evaluator.py`: only applies bbox / mask scaling when SR actually increases resolution.
  - `experiments/models/eval_omr_dln.py`: same, with a stderr warning when SR returns unchanged resolution.
- Also set a conservative tiling default in `src/common/preprocessing.py` for Real-ESRGAN (`tile=512` when max(image_dim) > 1000) to avoid SR hanging/OOM on high-res pages (page_10/page_15 are 2700x3600).

### Verification (Page 10 re-run, no GT)
- Confirmed old runs had SR/OMR coordinate range bug:
  - `logs/hybrid_generalization/page_10_hybrid_test/sr/.../page_10_detections.json`: max_x2=637 (≈ 2700/4)
  - `logs/hybrid_generalization/page_10_hybrid_test/omr_sr/predictions.json`: max_x2=675 (≈ 2700/4)
- After the fixes + tiling, SR/OMR now cover the full page width:
  - `logs/hybrid_generalization/sr_eval_page10_check2/sr/.../page_10_detections.json`: max_x2=2550
  - `logs/hybrid_generalization/sr_eval_page10_check2/omr_sr/predictions.json`: max_x2=2700
- Hybrid output increased and now reaches the right side:
  - old hybrid: n=128, max_x2=2422
  - new hybrid (`logs/hybrid_generalization/sr_eval_page10_check2/hybrid_predictions.json`): n=156, max_x2=2550
- Wrote a quick qualitative overlay for the new hybrid predictions:
  - `logs/phase3_staff_consistency/20251217_page10_hybrid_recall_fix_check/page10_hybrid_raw_overlay.jpg`

### Verification (Page 15 re-run, no GT)
- Old `page_15_hybrid_test` had the same SR/OMR coordinate range issue:
  - SR max_x2=638, OMR max_x2=675 (≈ 2700/4)
- New run (`logs/hybrid_generalization/sr_eval_page15_check2/`) after fixes:
  - SR max_x2=2552, OMR max_x2=2700 (full-width coverage)
  - Hybrid increased: old n=90 → new n=109; new max_x2=2552
- Wrote overlay:
  - `logs/phase3_staff_consistency/20251217_page15_hybrid_recall_fix_check/page15_hybrid_raw_overlay.jpg`

## 2025-12-17 06:40 JST (Codex CLI)

### Phase 4 #3: Analyze Remaining 2 FPs (page_3, hybrid + abs_tol5)
- Recomputed the Phase 3 “perfect recall” filter case (abs tol=5) using `logs/hybrid_results.json` + GT:
  - Output dir: `logs/phase3_staff_consistency/20251217_page3_remaining_fp_analysis/`
  - Filtered: TP=152, FP=2, FN=0
  - Remaining FP boxes: `(335, 230, 336, 253)` and `(479, 449, 480, 469)`
  - Overlay: `logs/phase3_staff_consistency/20251217_page3_remaining_fp_analysis/page3_remaining_fp_abs_tol5_overlay.jpg`
- Created crops for manual inspection:
  - `logs/phase3_staff_consistency/20251217_page3_remaining_fp_analysis/crops/fp1_crop.png`
  - `logs/phase3_staff_consistency/20251217_page3_remaining_fp_analysis/crops/fp2_crop.png`

### Observation / Hypothesis (Not Yet Fully Verified)
- Both remaining FPs look like **note stems / vertical glyph fragments** inside a measure rather than true barlines.
- Next candidate approach (if we proceed to Phase 4 #4):
  - Use a **notehead/stem-context** filter (notehead proximity / stem attachment), since pure geometry (row consistency) cannot separate these from true barlines reliably.

### Next Action (Phase 4 #4, in-progress)
- Try enabling the existing staff-crossing validation inside `filter_detections_by_notehead_proximity`:
  - Set `STEM_CONTEXT_HEURISTICS["staff_crossing_enabled"]=True` and `min_staff_crossings=5`.
  - Hypothesis: remaining FPs are stem-like and cross fewer staff lines than true barlines; this should reject them when they are proximal to noteheads but have low overlap.

### Result (FAILED / Reverted)
- Ran hybrid pipeline with that configuration:
  - `logs/hybrid_generalization/sr_eval_page3_staffcross5/hybrid_predictions.json`
- Outcome was unacceptable: baseline detections collapsed (222 → 77) and hybrid recall cratered:
  - Hybrid metrics reported: TP=65, FP=0, FN=87 (Recall ~0.43)
- Interpretation: staff-crossing counting in this form is **not safe** (likely rejects many true barlines as “proximal + low overlap + low crossings”).
- Action: reverted `STEM_CONTEXT_HEURISTICS` to `staff_crossing_enabled=False` / `min_staff_crossings=3`.

## 2025-12-17 07:00 JST (Codex CLI)

### Documentation & Deployment #7: Update analyze_staff_consistency.py
- Updated `experiments/fp_reduction/analyze_staff_consistency.py` to make ratio-based tolerance the default:
  - Added `--use-ratio-tolerance/--no-use-ratio-tolerance` (default: ratio enabled)
  - Added `--tol-ratio` (default 0.35) + `--staff-space` override
  - Added `--cluster-max-dist` and `--min-row-count`
  - Added staff_space estimation and prints it to stdout; also writes it to `metrics.json` under `config`.
- Sanity: `--help` verified inside `sr_eval_gpu` (`/opt/venv_sr/bin/python ... --help`).
