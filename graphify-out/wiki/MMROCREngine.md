# MMROCREngine

> 71 nodes · cohesion 0.06

## Key Concepts

- **MMROCREngine** (64 connections) — `src/measure_numbering/mmr.py`
- **object** (28 connections)
- **test_issue212_mmr_unmasked_fallback.py** (19 connections) — `tests/test_issue212_mmr_unmasked_fallback.py`
- **MaskedEmptyUnmaskedNumberOCR** (12 connections) — `tests/test_issue212_mmr_unmasked_fallback.py`
- **CurrentEmptyLeftWideNumberOCR** (11 connections) — `tests/test_issue212_mmr_unmasked_fallback.py`
- **_processor()** (11 connections) — `tests/test_issue212_mmr_unmasked_fallback.py`
- **test_issue213_mmr_one_bar_veto.py** (11 connections) — `tests/test_issue213_mmr_one_bar_veto.py`
- **OneEvidencePerVariantOCR** (11 connections) — `tests/test_issue213_mmr_one_bar_veto.py`
- **MaskedNumberUnmaskedDifferentNumberOCR** (9 connections) — `tests/test_issue212_mmr_unmasked_fallback.py`
- **RaisesOnEmptyCropOCR** (8 connections) — `tests/test_issue212_mmr_unmasked_fallback.py`
- **.collect_one_bar_evidence()** (7 connections) — `src/measure_numbering/mmr.py`
- **_box()** (6 connections) — `tests/test_issue212_mmr_unmasked_fallback.py`
- **CurrentEmptyLeftWideLowScoreOCR** (6 connections) — `tests/test_issue212_mmr_unmasked_fallback.py`
- **MaskedEmptyUnmaskedLowScoreOCR** (6 connections) — `tests/test_issue212_mmr_unmasked_fallback.py`
- **._candidate_items()** (5 connections) — `src/measure_numbering/mmr.py`
- **ndarray** (5 connections)
- **.select_best_candidate()** (4 connections) — `src/measure_numbering/mmr.py`
- **_box()** (4 connections) — `tests/test_issue213_mmr_one_bar_veto.py`
- **test_collect_one_bar_evidence_ignores_one_merged_into_multidigit()** (4 connections) — `tests/test_issue213_mmr_one_bar_veto.py`
- **test_collect_one_bar_evidence_keeps_single_one_and_ignores_eleven()** (4 connections) — `tests/test_issue213_mmr_one_bar_veto.py`
- **test_detect_number_preserves_three_value_contract()** (4 connections) — `tests/test_issue213_mmr_one_bar_veto.py`
- **test_detect_number_uses_max_one_bar_evidence_across_variants_not_sum()** (4 connections) — `tests/test_issue213_mmr_one_bar_veto.py`
- **test_one_bar_veto_targets_marginal_cnn_negative_ocr_score_only()** (4 connections) — `tests/test_issue213_mmr_one_bar_veto.py`
- **.predict()** (3 connections) — `src/measure_numbering/mmr.py`
- **._extract_numeric_candidates()** (3 connections) — `src/measure_numbering/mmr.py`
- *... and 46 more nodes in this community*

## Relationships

- [MMRProcessor](MMRProcessor.md) (25 shared connections)
- [run_mmr_batch](run_mmr_batch.md) (8 shared connections)
- [TestMMROCRHeuristics](TestMMROCRHeuristics.md) (4 shared connections)
- [audit_positive_geometry_disagreements.py](audit_positive_geometry_disagreements.py.md) (4 shared connections)
- [load_json](load_json.md) (4 shared connections)
- [phase_b_page001_acceptance.py](phase_b_page001_acceptance.py.md) (3 shared connections)
- [test_issue274_mmr_support_reuse.py](test_issue274_mmr_support_reuse.py.md) (3 shared connections)
- [run_grouped_final_numbering_comparison.py](run_grouped_final_numbering_comparison.py.md) (3 shared connections)
- [diagnose_ocr_frame_changed_pages.py](diagnose_ocr_frame_changed_pages.py.md) (3 shared connections)
- [test_issue254_connector_artifact_contract.py](test_issue254_connector_artifact_contract.py.md) (2 shared connections)
- [run_original_geometry_graft.py](run_original_geometry_graft.py.md) (2 shared connections)
- [cnn_classifier/train.py](cnn_classifier-train.py.md) (1 shared connections)

## Source Files

- `src/measure_numbering/mmr.py`
- `tests/test_issue212_mmr_unmasked_fallback.py`
- `tests/test_issue213_mmr_one_bar_veto.py`

## Audit Trail

- EXTRACTED: 159 (76%)
- INFERRED: 49 (24%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*