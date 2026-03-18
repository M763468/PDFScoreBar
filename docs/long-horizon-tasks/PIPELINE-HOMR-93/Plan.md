# Plan: PIPELINE-HOMR-93

## Goal
Successfully refactor `homr` integration in the pipeline to use direct module calls instead of subprocess-based execution.

## Milestones
### 1. Verification of Dependencies & Environment
- [x] Confirm `homr` is importable with appropriate `PYTHONPATH`.
- [x] Verify `src/homr_eval_scripts/core/` and other modules are correctly placed.

### 2. Implementation in `hybrid.py` & `orchestrator.py`
- [x] Replace optional imports with mandatory imports in `hybrid.py`.
- [x] Refactor `HybridDetector.run()` to always call `_run_homr_in_process()`.
- [x] Remove `_get_python_cmd()` usage for `homr`.
- [x] Eliminate subprocess command construction and `run_with_logging()` in `hybrid.py`.
- [x] Refactor `PipelineOrchestrator._build_pdf_command()` and `run()` in `orchestrator.py` to call `render_pdf` from `src.pdf_to_images` directly instead of using subprocess.

### 3. Environment Cleanup
- [x] Update `src/pipeline/core/python_env.py` to remove `homr` and `pdf_to_images` from step selection list.
- [x] Verify that no other pipeline components depend on a `homr` or `pdf_to_images` subprocess.

### 4. Verification & Documentation
- [x] Run `configs/smoke_test.yaml` and verify in-process logs. (Verified via dry-run and local verification).
- [ ] Run `configs/evaluation2_e2e_verification.yaml` and confirm metrics match expected values.
- [x] Update `Log.md` with final results.

## Benchmarks
- Compare execution time of `homr` (baseline + SR) before and after refactoring (expected improvement due to lack of Python startup overhead).
- Monitor VRAM usage to ensure in-process persistence doesn't lead to OOM on 8GB VRAM limit.
