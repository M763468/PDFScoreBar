# MMRProcessor

> 46 nodes · cohesion 0.08

## Key Concepts

- **MMRProcessor** (50 connections) — `src/measure_numbering/mmr.py`
- **object** (28 connections)
- **mmr.py** (14 connections) — `src/measure_numbering/mmr.py`
- **test_issue213_mmr_one_bar_veto.py** (11 connections) — `tests/test_issue213_mmr_one_bar_veto.py`
- **OneEvidencePerVariantOCR** (11 connections) — `tests/test_issue213_mmr_one_bar_veto.py`
- **._process_page_with_support()** (9 connections) — `src/measure_numbering/mmr.py`
- **VariantOCR** (8 connections) — `tests/test_issue208_mmr_variant_aggregation.py`
- **.process_pages()** (7 connections) — `src/measure_numbering/mmr.py`
- **._detect_number_with_evidence()** (6 connections) — `src/measure_numbering/mmr.py`
- **generate_numbering_overrides.py** (5 connections) — `tools/generate_numbering_overrides.py`
- **._should_veto_one_bar_rest()** (4 connections) — `src/measure_numbering/mmr.py`
- **test_issue208_mmr_variant_aggregation.py** (4 connections) — `tests/test_issue208_mmr_variant_aggregation.py`
- **test_detect_number_uses_best_scored_variant_not_first_valid_variant()** (4 connections) — `tests/test_issue208_mmr_variant_aggregation.py`
- **_box()** (4 connections) — `tests/test_issue213_mmr_one_bar_veto.py`
- **test_collect_one_bar_evidence_ignores_one_merged_into_multidigit()** (4 connections) — `tests/test_issue213_mmr_one_bar_veto.py`
- **test_collect_one_bar_evidence_keeps_single_one_and_ignores_eleven()** (4 connections) — `tests/test_issue213_mmr_one_bar_veto.py`
- **test_detect_number_preserves_three_value_contract()** (4 connections) — `tests/test_issue213_mmr_one_bar_veto.py`
- **test_detect_number_uses_max_one_bar_evidence_across_variants_not_sum()** (4 connections) — `tests/test_issue213_mmr_one_bar_veto.py`
- **test_one_bar_veto_targets_marginal_cnn_negative_ocr_score_only()** (4 connections) — `tests/test_issue213_mmr_one_bar_veto.py`
- **main()** (4 connections) — `tools/generate_numbering_overrides.py`
- **._count_high_confidence_one_bar_evidence()** (3 connections) — `src/measure_numbering/mmr.py`
- **._detect_number_with_evidence_once()** (3 connections) — `src/measure_numbering/mmr.py`
- **._draw_debug()** (3 connections) — `src/measure_numbering/mmr.py`
- **._valid_status()** (3 connections) — `src/measure_numbering/mmr.py`
- **.test_malformed_connector_pair_metadata_is_ignored()** (3 connections) — `tests/test_issue197_system_grouping_connector_evidence.py`
- *... and 21 more nodes in this community*

## Relationships

- [test_issue212_mmr_unmasked_fallback.py](test_issue212_mmr_unmasked_fallback.py.md) (16 shared connections)
- [MMROCREngine](MMROCREngine.md) (14 shared connections)
- [test_issue274_mmr_support_reuse.py](test_issue274_mmr_support_reuse.py.md) (8 shared connections)
- [MMRClassifier](MMRClassifier.md) (5 shared connections)
- [audit_positive_geometry_disagreements.py](audit_positive_geometry_disagreements.py.md) (4 shared connections)
- [phase_b_page001_acceptance.py](phase_b_page001_acceptance.py.md) (3 shared connections)
- [write_json](write_json.md) (3 shared connections)
- [diagnose_ocr_frame_changed_pages.py](diagnose_ocr_frame_changed_pages.py.md) (3 shared connections)
- [test_issue254_connector_artifact_contract.py](test_issue254_connector_artifact_contract.py.md) (2 shared connections)
- [SystemBuilder](SystemBuilder.md) (2 shared connections)
- [cnn_classifier/train.py](cnn_classifier-train.py.md) (1 shared connections)
- [current_homr_worker.py](current_homr_worker.py.md) (1 shared connections)

## Source Files

- `src/measure_numbering/mmr.py`
- `tests/test_issue197_system_grouping_connector_evidence.py`
- `tests/test_issue208_mmr_variant_aggregation.py`
- `tests/test_issue213_mmr_one_bar_veto.py`
- `tools/generate_numbering_overrides.py`

## Audit Trail

- EXTRACTED: 110 (72%)
- INFERRED: 42 (28%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*