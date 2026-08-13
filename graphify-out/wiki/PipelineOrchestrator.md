# PipelineOrchestrator

> 21 nodes · cohesion 0.28

## Key Concepts

- **PipelineOrchestrator** (35 connections) — `src/pipeline/orchestrator.py`
- **test_issue236_review_package_pipeline_connection.py** (23 connections) — `tests/test_issue236_review_package_pipeline_connection.py`
- **_fake_pipeline_config()** (16 connections) — `tests/test_issue236_review_package_pipeline_connection.py`
- **_patch_lightweight_pipeline_phases()** (8 connections) — `tests/test_issue236_review_package_pipeline_connection.py`
- **Path** (5 connections)
- **test_pipeline_connection_materializes_enabled_review_package()** (5 connections) — `tests/test_issue236_review_package_pipeline_connection.py`
- **test_pipeline_connection_resolves_relative_review_root_from_run_dir()** (5 connections) — `tests/test_issue236_review_package_pipeline_connection.py`
- **test_pipeline_connection_does_not_materialize_when_disabled()** (4 connections) — `tests/test_issue236_review_package_pipeline_connection.py`
- **test_pipeline_connection_does_not_materialize_when_review_flag_missing()** (4 connections) — `tests/test_issue236_review_package_pipeline_connection.py`
- **test_pipeline_connection_skips_user_excluded_pages_in_review_package()** (4 connections) — `tests/test_issue236_review_package_pipeline_connection.py`
- **test_pipeline_connection_treats_null_overwrite_as_default_true()** (4 connections) — `tests/test_issue236_review_package_pipeline_connection.py`
- **test_pipeline_connection_uses_absolute_review_root()** (4 connections) — `tests/test_issue236_review_package_pipeline_connection.py`
- **test_pipeline_manifest_uses_corrected_barlines_for_review_package()** (4 connections) — `tests/test_issue236_review_package_pipeline_connection.py`
- **_write_json()** (4 connections) — `tests/test_issue236_review_package_pipeline_connection.py`
- **test_pipeline_connection_rejects_missing_review_artifact_steps()** (3 connections) — `tests/test_issue236_review_package_pipeline_connection.py`
- **test_pipeline_manifest_keeps_raw_barlines_when_corrected_missing()** (3 connections) — `tests/test_issue236_review_package_pipeline_connection.py`
- **test_pipeline_review_package_forces_pdf_image_persistence()** (3 connections) — `tests/test_issue236_review_package_pipeline_connection.py`
- **test_pipeline_without_review_package_allows_in_memory_pdf_images()** (3 connections) — `tests/test_issue236_review_package_pipeline_connection.py`
- **test_review_package_example_config_is_parseable()** (3 connections) — `tests/test_issue236_review_package_pipeline_connection.py`
- **_write_text()** (3 connections) — `tests/test_issue236_review_package_pipeline_connection.py`
- **Orchestrates the different phases of the numbering pipeline.** (1 connections) — `src/pipeline/orchestrator.py`

## Relationships

- [.run](run.md) (11 shared connections)
- [run_stage_e_full_pipeline.py](run_stage_e_full_pipeline.py.md) (5 shared connections)
- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (3 shared connections)
- [manual_correction_handoff.py](manual_correction_handoff.py.md) (3 shared connections)
- [Barline](Barline.md) (2 shared connections)
- [run_grouped_final_numbering_comparison.py](run_grouped_final_numbering_comparison.py.md) (1 shared connections)
- [MMROCREngine](MMROCREngine.md) (1 shared connections)
- [MeasureNumberingPipeline](MeasureNumberingPipeline.md) (1 shared connections)
- [Score](Score.md) (1 shared connections)

## Source Files

- `src/pipeline/orchestrator.py`
- `tests/test_issue236_review_package_pipeline_connection.py`

## Audit Trail

- EXTRACTED: 82 (95%)
- INFERRED: 4 (5%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*