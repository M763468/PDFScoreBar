# object

> 26 nodes · cohesion 0.14

## Key Concepts

- **object** (28 connections)
- **build_mmr_page_context()** (15 connections) — `src/pipeline/mmr_geometry_handoff.py`
- **test_issue213_mmr_one_bar_veto.py** (11 connections) — `tests/test_issue213_mmr_one_bar_veto.py`
- **OneEvidencePerVariantOCR** (11 connections) — `tests/test_issue213_mmr_one_bar_veto.py`
- **mmr_geometry_handoff.py** (8 connections) — `src/pipeline/mmr_geometry_handoff.py`
- **test_issue264_phase_b_mmr_geometry.py** (5 connections) — `tests/test_issue264_phase_b_mmr_geometry.py`
- **test_mmr_handoff_reuses_current_x4_support_without_rebuilding_numbering()** (5 connections) — `tests/test_issue264_phase_b_mmr_geometry.py`
- **test_mmr_handoff_skips_excluded_or_missing_numbering_pages()** (5 connections) — `tests/test_issue264_phase_b_mmr_geometry.py`
- **_box()** (4 connections) — `tests/test_issue213_mmr_one_bar_veto.py`
- **test_collect_one_bar_evidence_ignores_one_merged_into_multidigit()** (4 connections) — `tests/test_issue213_mmr_one_bar_veto.py`
- **test_collect_one_bar_evidence_keeps_single_one_and_ignores_eleven()** (4 connections) — `tests/test_issue213_mmr_one_bar_veto.py`
- **test_detect_number_preserves_three_value_contract()** (4 connections) — `tests/test_issue213_mmr_one_bar_veto.py`
- **test_detect_number_uses_max_one_bar_evidence_across_variants_not_sum()** (4 connections) — `tests/test_issue213_mmr_one_bar_veto.py`
- **test_one_bar_veto_targets_marginal_cnn_negative_ocr_score_only()** (4 connections) — `tests/test_issue213_mmr_one_bar_veto.py`
- **test_mmr_handoff_requires_declared_current_homr_staff_mask()** (4 connections) — `tests/test_issue264_phase_b_mmr_geometry.py`
- **.collect_one_bar_evidence()** (3 connections) — `tests/test_issue213_mmr_one_bar_veto.py`
- **test_count_one_bar_evidence_is_compatible_with_minimal_injected_ocr()** (3 connections) — `tests/test_issue213_mmr_one_bar_veto.py`
- **Path** (3 connections)
- **.ocr_engine()** (2 connections) — `tests/test_issue213_mmr_one_bar_veto.py`
- **MonkeyPatch** (2 connections)
- **Any** (1 connections)
- **Attach current-x4 MMR support without rebuilding Phase-A numbering.** (1 connections) — `src/pipeline/mmr_geometry_handoff.py`
- **.__init__()** (1 connections) — `tests/test_issue213_mmr_one_bar_veto.py`
- **.mask_hbar_candidates()** (1 connections) — `tests/test_issue213_mmr_one_bar_veto.py`
- **.preprocess_variant()** (1 connections) — `tests/test_issue213_mmr_one_bar_veto.py`
- *... and 1 more nodes in this community*

## Relationships

- [MMROCREngine](MMROCREngine.md) (13 shared connections)
- [MMRProcessor](MMRProcessor.md) (8 shared connections)
- [test_issue274_mmr_support_reuse.py](test_issue274_mmr_support_reuse.py.md) (6 shared connections)
- [load_json](load_json.md) (3 shared connections)
- [MeasureNumberingPipeline](MeasureNumberingPipeline.md) (3 shared connections)
- [run_phase_c_mmr_regression.py](run_phase_c_mmr_regression.py.md) (3 shared connections)
- [test_issue254_connector_artifact_contract.py](test_issue254_connector_artifact_contract.py.md) (2 shared connections)
- [cnn_classifier/train.py](cnn_classifier-train.py.md) (1 shared connections)
- [current_homr_worker.py](current_homr_worker.py.md) (1 shared connections)
- [SystemBuilder](SystemBuilder.md) (1 shared connections)
- [build_detector_input_contract](build_detector_input_contract.md) (1 shared connections)
- [TestMMROCRHeuristics](TestMMROCRHeuristics.md) (1 shared connections)

## Source Files

- `src/pipeline/mmr_geometry_handoff.py`
- `tests/test_issue213_mmr_one_bar_veto.py`
- `tests/test_issue264_phase_b_mmr_geometry.py`

## Audit Trail

- EXTRACTED: 61 (68%)
- INFERRED: 29 (32%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*