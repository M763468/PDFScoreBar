# PipelineOrchestrator

> God node · 65 connections · `src/pipeline/orchestrator.py`

**Community:** [Community 86](Community_86.md)

## Connections by Relation

### calls
- run_pipeline() `EXTRACTED`
- run() `EXTRACTED`
- run() `EXTRACTED`
- replay() `EXTRACTED`
- run() `EXTRACTED`
- replay() `EXTRACTED`
- test_issue268_explicit_boundary_resets_at_mid_page_system_and_preserves_provenance() `EXTRACTED`
- test_three_page_phase_c_preserves_manual_precedence_without_cross_page_leakage() `EXTRACTED`
- test_issue268_skip_existing_reuses_persisted_score_state() `EXTRACTED`
- test_cached_pdf_render_restores_verified_source_geometry() `EXTRACTED`
- test_rendered_source_geometry_survives_public_review_and_correction() `EXTRACTED`
- test_pipeline_connection_materializes_enabled_review_package() `EXTRACTED`
- test_pipeline_connection_resolves_relative_review_root_from_run_dir() `EXTRACTED`
- test_issue268_rejects_boundary_inside_excluded_page() `EXTRACTED`
- test_input_validation_does_not_complete_for_malformed_structured_input() `EXTRACTED`
- test_canonical_direct_run_discovers_established_external_images() `EXTRACTED`
- test_pipeline_connection_does_not_materialize_when_disabled() `EXTRACTED`
- test_pipeline_connection_does_not_materialize_when_review_flag_missing() `EXTRACTED`
- test_pipeline_connection_skips_user_excluded_pages_in_review_package() `EXTRACTED`
- test_pipeline_connection_treats_null_overwrite_as_default_true() `EXTRACTED`

### contains
- pipeline/orchestrator.py `EXTRACTED`

### imports
- test_distribution_surface.py `EXTRACTED`
- test_issue257_mmr_page_rebase.py `EXTRACTED`
- run_phase_c_mmr_regression.py `EXTRACTED`
- test_issue236_review_package_pipeline_connection.py `EXTRACTED`
- phase_b_page001_acceptance.py `EXTRACTED`
- test_pipeline_telemetry.py `EXTRACTED`
- replay_phase_c.py `EXTRACTED`
- test_source_page_provenance.py `EXTRACTED`
- main.py `EXTRACTED`
- e2e_correction_replay.py `EXTRACTED`
- replay_numbering.py `EXTRACTED`

### method
- .run() `EXTRACTED`
- ._numbering_phase_services() `EXTRACTED`
- ._run_pdf_to_images() `EXTRACTED`
- ._validate_input_prerequisites() `EXTRACTED`
- ._load_cached_pdf_render_provenance() `EXTRACTED`
- ._review_package_config() `EXTRACTED`
- ._should_persist_pdf_images() `EXTRACTED`
- ._materialize_review_package_if_requested() `EXTRACTED`
- .run_base_numbering_and_barline_correction() `EXTRACTED`
- .run_final_numbering_and_overlays() `EXTRACTED`
- ._validate_external_image_inputs() `EXTRACTED`
- ._resolved_for_manifest() `EXTRACTED`
- .run_mmr_batch_detection() `EXTRACTED`
- .__init__() `EXTRACTED`
- ._resolve_page_runs() `EXTRACTED`
- ._validate_review_package_prerequisites() `EXTRACTED`
- ._telemetry_stage() `EXTRACTED`
- ._telemetry_progress() `EXTRACTED`

### rationale_for
- Orchestrates the different phases of the numbering pipeline. `EXTRACTED`

### references
- _runtime_provenance() `EXTRACTED`

### uses
- TelemetryRecorder `INFERRED`
- NumberingPhaseServices `INFERRED`
- ReviewPackageConfig `INFERRED`

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*