# Plan: PIPELINE-HOMR-INPROCESS-93-FOLLOWUP

## Goal
Finish the in-process refactoring started in Issue #93 by migrating `omr-dln` inference and `pdf_to_images` output passing to run entirely within the main pipeline process, eliminating remaining subprocess dependencies. Verify accuracy metrics against the established baseline.

## Milestones

### 1. OMR-DLN In-Process Refactoring
- **Create `src/pipeline/detection/omr_dln.py`**:
  - Implement a `run_omr_dln_batch` function that loads the `YOLO` model via `ultralytics`.
  - Use module-level caching to persist the loaded model across batch runs.
  - Implement `infer_barlines_from_measures` within this module.
- **Update `src/pipeline/detection/hybrid.py`**:
  - Replace the subprocess call to `eval_omr_dln.py` with an in-process call to `run_omr_dln_batch`.
  - Remove the legacy `_get_python_cmd` logic for `omr_dln`.

### 2. In-Memory Image Passing (pdf_to_images)
- **Update `src/pdf_to_images.py`**:
  - Add a `render_pdf_to_memory` function (or modify `render_pdf`) to return a list of `numpy.ndarray` images along with their metadata (e.g., page index) instead of immediately writing to disk.
- **Update `src/pipeline/orchestrator.py`**:
  - If `pdf_to_images` step is active, store the rendered arrays in memory.
  - Optionally write to disk only if a debug flag or `output_dir` is explicitly required for persistence.
  - Update `collect_images` or how `images` are passed to `run_detection_step` to allow passing in-memory numpy arrays instead of just `Path` objects.
- **Update Downstream Steps**:
  - Ensure `hybrid.py`, `probe_scan`, and `cnn` can accept in-memory `numpy.ndarray` inputs where applicable, reducing disk I/O overhead. (If some tools strictly require paths, we will write temporary files or adapt them within reason).

### 3. Verification & Evaluation on Eval2 (68 pages)
- Ensure the pipeline can run end-to-end (`homr`, `omr-dln`, `pdf_to_images`) entirely in a single Python process.
- **Execution Command (SR x2, target FN=~1, FP=0)**:
  ```bash
  make run-pipeline CONFIG=configs/evaluation2_sr_x2.yaml
  ```
- **Evaluation Constraints**:
  - **Execution Time & Timeout**: The full `homr` process (SR x2) on 68 pages takes a significant amount of time (potentially several hours). When executing `make run-pipeline`, ensure it is run in the background (e.g., using `nohup`, `tmux`, or CLI background tasks) or manage tool timeouts appropriately to prevent cancellation.
  - **Milestone Validation**: You DO NOT need to run the full 68-page pipeline after M1 and M2. Intermediate verifications should be done on a smaller subset (e.g., 1-3 pages) to ensure structural correctness. The full 68-page evaluation is only required for the **Final Verification (Step 3)**.
  - **Log Management**: If `make` commands fail and you need to run `python` scripts directly, **ALWAYS** redirect output using `> artifacts/<filename>.log` to prevent context pollution, then inspect only the required parts.
  - **Evaluation Consistency**: Evaluate using **existing scripts only** (e.g., `tools/evaluate_and_visualize.py`). Do not write custom or temporary evaluation scripts. If the existing evaluation script fails because paths have changed, fix the path resolution logic inside the existing script.
  - **Regression Tracking**: Compare the generated metrics against Issue #25 benchmarks. If FP > 0 or FN increases unexpectedly, investigate the root cause by examining differences across recent commits and historical documents to pinpoint where the logic diverged.

### 4. Documentation
- Update `docs/long-horizon-tasks/PIPELINE-HOMR-INPROCESS-93-FOLLOWUP/Log.md` after each milestone execution.
- Record final metrics and reproducibility commands in `docs/long-horizon-tasks/PIPELINE-HOMR-INPROCESS-93-FOLLOWUP/Benchmarks.md`.
