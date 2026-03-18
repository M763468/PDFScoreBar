# Task: PIPELINE-HOMR-93 (Issue #93)

## Objective
Refactor the pipeline to eliminate the subprocess-based execution of `homr` (via `homr_evaluator.py`) and use direct in-process calls to the `homr` module instead. This is enabled by the recent consolidation of virtual environments and Docker images.

## Context
- **Issue #93**: [Task] パイプラインからのhomrサブプロセス実行廃止と直接呼び出し化
- **Prerequisite #7**: 仮想環境・Dockerコンテナの整理と統合 (Closed)
- **Prerequisite #92**: homr_evaluator.py のモジュール分割と軽量化 (Closed)

## Scope
- `src/pipeline/detection/hybrid.py`: Remove all subprocess logic for `homr` and `homr SR`.
- `src/pipeline/orchestrator.py`: Remove subprocess logic for `pdf_to_images` and call it directly.
- `src/pipeline/core/python_env.py`: Remove `homr` and `pdf_to_images` from step selection list.
- Eliminate dependency on `src/homr_eval_scripts/homr_evaluator.py` and `src/pdf_to_images.py` as standalone subprocesses from the main pipeline flow.

## Requirements
1. `homr` must be imported as a Python module in `hybrid.py`.
2. All `homr` related tasks (baseline and SR) must be executed in-process using `_run_homr_in_process`.
3. The environment variable setup (`PYTHONPATH`) for the subprocess must be removed.
4. Error handling should rely on Python exceptions rather than subprocess return codes.
5. VRAM management should be monitored to ensure persistence doesn't cause OOM.

## Acceptance Criteria
- [ ] Subprocess calls to `homr_evaluator.py` are completely removed.
- [ ] `homr` is directly imported in `hybrid.py` without `ImportError` suppression.
- [ ] `HybridDetector.run()` no longer uses `get_pipeline_python("homr")`.
- [ ] Smoke test `configs/smoke_test.yaml` passes.
- [ ] E2E validation `configs/evaluation2_e2e_verification.yaml` passes.
