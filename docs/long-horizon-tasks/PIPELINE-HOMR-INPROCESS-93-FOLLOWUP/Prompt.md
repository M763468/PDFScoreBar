# Prompt: PIPELINE-HOMR-INPROCESS-93-FOLLOWUP

## Goal
Finish the in-process refactoring started in Issue #93 by migrating `omr-dln` inference and `pdf_to_images` output passing to run entirely within the main pipeline process, eliminating remaining subprocess dependencies. Verify accuracy metrics against the established baseline.

## Context
In the first half of Issue #93, `homr` execution and the invocation of `pdf_to_images` were successfully moved in-process. However:
1. `omr-dln` is still executed via a subprocess (`experiments/models/eval_omr_dln.py`).
2. `pdf_to_images` writes images to disk, and subsequent pipeline steps read them from disk. We want to pass images in-memory (`np.ndarray`) to avoid unnecessary I/O unless debug outputs are explicitly requested.

## Requirements
- **omr-dln In-Process**:
  - Create a dedicated module (`src/pipeline/detection/omr_dln.py`) using `ultralytics.YOLO`.
  - Persist the model in memory across batches.
  - Refactor `src/pipeline/detection/hybrid.py` to use this new module instead of the subprocess command.
- **In-Memory Image Passing**:
  - Modify `src/pdf_to_images.py` to optionally return in-memory image arrays (`np.ndarray`).
  - Modify `src/pipeline/orchestrator.py` and downstream logic to process these in-memory arrays directly.
## Verification
  - Must run a full batch evaluation on the `eval2` dataset (68 pages).
  - Must achieve `FN=1, FP=0` under the SR x2 configuration (which matches the high accuracy of x4 but in a shorter time).
  - No regression in accuracy is allowed.

## Operational Constraints
- **Log Management**: If `make` commands fail and you must run Python scripts directly, you **MUST** redirect the output to a file (e.g., `> artifacts/run.log`) to avoid polluting the context window. Read only the necessary parts using tools like `grep_search` or `tail`.
- **Regression Investigation**: If any regression (degradation in F1, FP, FN) is detected, investigate the root cause by cross-referencing recent commits and historical documentation to identify where the logic diverged.
- **Evaluation Consistency**: You must use the existing evaluation scripts (e.g., `tools/evaluate_and_visualize.py`) to maintain consistency with past results. **Do not create new evaluation scripts.** If the existing script fails due to path resolution changes caused by the refactor, fix the path resolution logic within the existing script itself.
