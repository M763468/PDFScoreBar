# materialize_manual_correction_review_package

> 32 nodes · cohesion 0.18

## Key Concepts

- **materialize_manual_correction_review_package()** (26 connections) — `src/pipeline/review/manual_correction_materializer.py`
- **test_manual_correction_materializer.py** (17 connections) — `tests/test_manual_correction_materializer.py`
- **manual_correction_materializer.py** (15 connections) — `src/pipeline/review/manual_correction_materializer.py`
- **ManualCorrectionMaterializerError** (12 connections) — `src/pipeline/review/manual_correction_materializer.py`
- **_fake_run_root()** (12 connections) — `tests/test_manual_correction_materializer.py`
- **Any** (9 connections)
- **Path** (9 connections)
- **_resolve_barlines_review_source()** (6 connections) — `src/pipeline/review/manual_correction_materializer.py`
- **_resolve_run_artifact()** (6 connections) — `src/pipeline/review/manual_correction_materializer.py`
- **_extract_review_barline_records()** (5 connections) — `src/pipeline/review/manual_correction_materializer.py`
- **_load_json_object()** (5 connections) — `src/pipeline/review/manual_correction_materializer.py`
- **test_materialized_handoff_validates_and_builds_page_local_gui_config()** (5 connections) — `tests/test_manual_correction_materializer.py`
- **_load_json()** (4 connections) — `src/pipeline/review/manual_correction_materializer.py`
- **_page_number_from_manifest()** (4 connections) — `src/pipeline/review/manual_correction_materializer.py`
- **_require_inside()** (4 connections) — `src/pipeline/review/manual_correction_materializer.py`
- **_select_pages()** (4 connections) — `src/pipeline/review/manual_correction_materializer.py`
- **_write_json()** (4 connections) — `src/pipeline/review/manual_correction_materializer.py`
- **test_materializer_rejects_run_root_external_barlines_artifact()** (4 connections) — `tests/test_manual_correction_materializer.py`
- **_write_json()** (4 connections) — `tests/test_manual_correction_materializer.py`
- **_copy_run_artifact()** (3 connections) — `src/pipeline/review/manual_correction_materializer.py`
- **Path** (3 connections)
- **test_materializer_errors_when_barlines_source_has_no_records()** (3 connections) — `tests/test_manual_correction_materializer.py`
- **test_materializer_errors_when_manifest_has_no_barlines_source()** (3 connections) — `tests/test_manual_correction_materializer.py`
- **test_materializer_normalizes_predictions_barlines_source()** (3 connections) — `tests/test_manual_correction_materializer.py`
- **test_materializer_preserves_top_level_list_barlines_source()** (3 connections) — `tests/test_manual_correction_materializer.py`
- *... and 7 more nodes in this community*

## Relationships

- [manual_correction_handoff.py](manual_correction_handoff.py.md) (5 shared connections)
- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (2 shared connections)
- [get_nested](get_nested.md) (1 shared connections)

## Source Files

- `src/pipeline/review/manual_correction_materializer.py`
- `tests/test_manual_correction_materializer.py`

## Audit Trail

- EXTRACTED: 97 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*