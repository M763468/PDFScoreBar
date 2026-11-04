# Community 19

> 41 nodes · cohesion 0.13

## Key Concepts

- **test_engine_input_safety.py** (24 connections) — `tests/test_engine_input_safety.py`
- **engine_input_safety.py** (22 connections) — `src/pipeline/engine_input_safety.py`
- **validate_local_pdf()** (22 connections) — `src/pipeline/engine_input_safety.py`
- **JobSafetyPolicy** (16 connections) — `src/pipeline/engine_input_safety.py`
- **_error()** (13 connections) — `src/pipeline/engine_input_safety.py`
- **resolve_local_input_path()** (13 connections) — `src/pipeline/engine_input_safety.py`
- **Path** (11 connections)
- **_write_pdf()** (10 connections) — `tests/test_engine_input_safety.py`
- **validate_local_input_reference()** (8 connections) — `src/pipeline/engine_input_safety.py`
- **validate_output_name()** (8 connections) — `src/pipeline/engine_input_safety.py`
- **Path** (6 connections)
- **_filesystem_unavailable()** (5 connections) — `src/pipeline/engine_input_safety.py`
- **_read_bounded_file()** (5 connections) — `src/pipeline/engine_input_safety.py`
- **test_page_and_render_amplification_are_rejected_before_rendering()** (5 connections) — `tests/test_engine_input_safety.py`
- **test_path_resolution_oserror_is_normalized()** (5 connections) — `tests/test_engine_input_safety.py`
- **test_pdf_byte_limit_is_enforced_before_parser_work()** (5 connections) — `tests/test_engine_input_safety.py`
- **test_raw_page_selection_is_bounded_before_deduplication()** (5 connections) — `tests/test_engine_input_safety.py`
- **test_read_oserror_is_normalized()** (5 connections) — `tests/test_engine_input_safety.py`
- **_reject_symlink_components()** (4 connections) — `src/pipeline/engine_input_safety.py`
- **_resolve_existing_input_path()** (4 connections) — `src/pipeline/engine_input_safety.py`
- **_selected_pages()** (4 connections) — `src/pipeline/engine_input_safety.py`
- **test_out_of_range_page_has_stable_code()** (4 connections) — `tests/test_engine_input_safety.py`
- **test_output_name_is_a_stem_not_a_path()** (4 connections) — `tests/test_engine_input_safety.py`
- **test_symlink_input_is_rejected_by_default()** (4 connections) — `tests/test_engine_input_safety.py`
- **test_valid_pdf_preflight_returns_safe_metadata_without_internal_path()** (4 connections) — `tests/test_engine_input_safety.py`
- *... and 16 more nodes in this community*

## Relationships

- [Community 41](Community_41.md) (14 shared connections)
- [Community 30](Community_30.md) (10 shared connections)
- [Community 48](Community_48.md) (3 shared connections)
- [Community 73](Community_73.md) (3 shared connections)
- [Community 106](Community_106.md) (1 shared connections)

## Source Files

- `src/pipeline/engine_input_safety.py`
- `tests/test_engine_input_safety.py`

## Audit Trail

- EXTRACTED: 134 (98%)
- INFERRED: 3 (2%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*