# PipelineOrchestrator

> 21 nodes · cohesion 0.28

## Key Concepts

- **PipelineOrchestrator** (40 connections) — `src/pipeline/orchestrator.py`
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

- [get_nested](get_nested.md) (11 shared connections)
- [load_yaml](load_yaml.md) (5 shared connections)
- [run_phase_c_mmr_regression.py](run_phase_c_mmr_regression.py.md) (3 shared connections)
- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (3 shared connections)
- [manual_correction_handoff.py](manual_correction_handoff.py.md) (3 shared connections)
- [Staff](Staff.md) (2 shared connections)
- [load_json](load_json.md) (2 shared connections)
- [MeasureNumberingPipeline](MeasureNumberingPipeline.md) (2 shared connections)
- [MMRClassifier](MMRClassifier.md) (1 shared connections)
- [MMROCREngine](MMROCREngine.md) (1 shared connections)

## Source Files

- `src/pipeline/orchestrator.py`
- `tests/test_issue236_review_package_pipeline_connection.py`

## Audit Trail

- EXTRACTED: 87 (96%)
- INFERRED: 4 (4%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*