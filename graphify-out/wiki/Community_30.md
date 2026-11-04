# Community 30

> 48 nodes · cohesion 0.09

## Key Concepts

- **test_review_correction_server.py** (30 connections) — `tests/test_review_correction_server.py`
- **test_review_correction_application.py** (26 connections) — `tests/test_review_correction_application.py`
- **_application()** (21 connections) — `tests/test_review_correction_application.py`
- **_request()** (19 connections) — `tests/test_review_correction_server.py`
- **create_server()** (15 connections) — `tools/review_correction/server.py`
- **_handoff()** (13 connections) — `tests/test_review_correction_server.py`
- **_fake_engine()** (12 connections) — `tests/test_review_correction_application.py`
- **_load_saved_movement()** (6 connections) — `tests/test_review_correction_server.py`
- **review_server()** (6 connections) — `tests/test_review_correction_server.py`
- **test_end_to_end_review_save_apply_and_download_preserves_pdf_and_filename()** (5 connections) — `tests/test_review_correction_application.py`
- **test_manual_movement_save_preserves_other_pages_and_rechecks_saved_bytes()** (5 connections) — `tests/test_review_correction_server.py`
- **test_apply_http_rejects_path_substitution_and_exposes_only_own_result()** (4 connections) — `tests/test_review_correction_application.py`
- **test_abandoned_history_requires_state_attestation_not_pdf_existence()** (4 connections) — `tests/test_review_correction_history.py`
- **test_every_failed_and_successful_application_is_retained()** (4 connections) — `tests/test_review_correction_history.py`
- **test_immutable_checkpoints_survive_restart_and_all_four_correction_types()** (4 connections) — `tests/test_review_correction_history.py`
- **test_distinct_movement_paths_are_rejected_before_any_save_or_apply()** (4 connections) — `tests/test_review_correction_server.py`
- **test_review_movement_export_uses_declared_package_paths()** (4 connections) — `tests/test_review_correction_server.py`
- **_request_with_headers()** (3 connections) — `tests/test_review_correction_application.py`
- **test_application_carries_handoff_output_name_into_apply_snapshot()** (3 connections) — `tests/test_review_correction_application.py`
- **test_application_does_not_recover_generic_score_from_legacy_final_pdf()** (3 connections) — `tests/test_review_correction_application.py`
- **test_application_recovers_name_from_existing_legacy_final_pdf()** (3 connections) — `tests/test_review_correction_application.py`
- **test_apply_snapshots_inputs_and_records_exact_success()** (3 connections) — `tests/test_review_correction_application.py`
- **test_failed_apply_and_pdf_generation_preserve_last_success()** (3 connections) — `tests/test_review_correction_application.py`
- **test_startup_failure_after_begin_apply_is_recorded_and_retryable()** (3 connections) — `tests/test_review_correction_application.py`
- **test_checkpoint_corruption_symlink_and_dependency_changes_fail_closed()** (3 connections) — `tests/test_review_correction_history.py`
- *... and 23 more nodes in this community*

## Relationships

- [Community 23](Community_23.md) (27 shared connections)
- [Community 103](Community_103.md) (13 shared connections)
- [Community 17](Community_17.md) (4 shared connections)
- [Community 244](Community_244.md) (3 shared connections)
- [Community 35](Community_35.md) (2 shared connections)
- [Community 33](Community_33.md) (2 shared connections)
- [Community 182](Community_182.md) (2 shared connections)
- [Community 241](Community_241.md) (2 shared connections)
- [Community 29](Community_29.md) (2 shared connections)
- [Community 32](Community_32.md) (1 shared connections)

## Source Files

- `tests/test_review_correction_application.py`
- `tests/test_review_correction_history.py`
- `tests/test_review_correction_server.py`
- `tools/review_correction/server.py`

## Audit Trail

- EXTRACTED: 147 (93%)
- INFERRED: 11 (7%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*