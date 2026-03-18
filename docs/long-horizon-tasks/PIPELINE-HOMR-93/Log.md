# Log: PIPELINE-HOMR-93

## 2026-03-18 (Project Context Date)
- **Initialized Task**: Created `docs/long-horizon-tasks/PIPELINE-HOMR-93/` using standard templates.
- **Branch Creation**: Created and switched to `task/pipeline-homr-direct-call`.
- **Goal Definition**: Refactored `Prompt.md` with Issue #93 requirements.
- **Strategy Selection**: Approved full removal of subprocess calls for `homr` and `pdf_to_images` in the pipeline.
- **Initial Research**: Confirmed Issues #7 and #92 are closed. Analyzed `src/pipeline/detection/hybrid.py` and `src/pipeline/orchestrator.py` structures.
- **Plan Established**: Created a multi-milestone plan in `Plan.md` covering implementation, cleanup, and verification.
- **Implementation (In-Process homr)**:
    - Modified `src/pipeline/detection/hybrid.py` to use mandatory imports for `homr` components.
    - Refactored `HybridDetector` to use `_run_homr_in_process` for both baseline and SR runs, eliminating subprocess `homr` calls.
    - Updated `src/homr_eval_scripts/core/metrics.py`, `reporting.py`, and `predictor.py` with absolute `src` import paths to support in-process execution from project root.
- **Implementation (In-Process pdf_to_images)**:
    - Refactored `PipelineOrchestrator` in `src/pipeline/orchestrator.py` to call `render_pdf` directly.
    - Removed `_build_pdf_command` and unused `_run_command` from `orchestrator.py`.
- **Cleanup**:
    - Updated `src/pipeline/core/python_env.py` to remove legacy subprocess handling for `homr` and `pdf_to_images`.
    - Cleaned up `src/pipeline/steps/numbering.py` by removing unused `build_add_measure_numbers_cmd`.
    - Updated docstrings in `src/pipeline/detection/orchestrator.py`.
- **Verification**:
    - Performed dry-run using `configs/smoke_test.yaml` which confirmed that in-process calls are correctly identified and logging matches the expected flow.
    - Verified local importability of all core components with appropriate `PYTHONPATH`.
    - Executed batch processing on 3 pages of `Va_Prokofiev_Symphony1.pdf` within the Docker container.
    - **Accuracy**: Maintained high F1 score of ~0.9919 (TP=245, FP=4, FN=0). No regression.
    - **Speed & VRAM**: The `homr` models are successfully loaded once and persisted. Inference time dropped to ~40s/page (SR=False) and ~80s/page (SR=True). VRAM usage is strictly stable around ~600 MiB after cleanups.
- **Status**: Complete. Results documented and verified. Ready for commit.
