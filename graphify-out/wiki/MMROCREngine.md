# MMROCREngine

> 52 nodes · cohesion 0.07

## Key Concepts

- **MMROCREngine** (64 connections) — `src/measure_numbering/mmr.py`
- **test_issue212_mmr_unmasked_fallback.py** (19 connections) — `tests/test_issue212_mmr_unmasked_fallback.py`
- **MaskedEmptyUnmaskedNumberOCR** (12 connections) — `tests/test_issue212_mmr_unmasked_fallback.py`
- **CurrentEmptyLeftWideNumberOCR** (11 connections) — `tests/test_issue212_mmr_unmasked_fallback.py`
- **_processor()** (11 connections) — `tests/test_issue212_mmr_unmasked_fallback.py`
- **MaskedNumberUnmaskedDifferentNumberOCR** (9 connections) — `tests/test_issue212_mmr_unmasked_fallback.py`
- **RaisesOnEmptyCropOCR** (8 connections) — `tests/test_issue212_mmr_unmasked_fallback.py`
- **.collect_one_bar_evidence()** (7 connections) — `src/measure_numbering/mmr.py`
- **_box()** (6 connections) — `tests/test_issue212_mmr_unmasked_fallback.py`
- **CurrentEmptyLeftWideLowScoreOCR** (6 connections) — `tests/test_issue212_mmr_unmasked_fallback.py`
- **MaskedEmptyUnmaskedLowScoreOCR** (6 connections) — `tests/test_issue212_mmr_unmasked_fallback.py`
- **._candidate_items()** (5 connections) — `src/measure_numbering/mmr.py`
- **ndarray** (5 connections)
- **.select_best_candidate()** (4 connections) — `src/measure_numbering/mmr.py`
- **._extract_numeric_candidates()** (3 connections) — `src/measure_numbering/mmr.py`
- **._has_blacklisted_text()** (3 connections) — `src/measure_numbering/mmr.py`
- **.preprocess_variant()** (3 connections) — `src/measure_numbering/mmr.py`
- **.rotate_image()** (3 connections) — `src/measure_numbering/mmr.py`
- **.collect_one_bar_evidence()** (3 connections) — `tests/test_issue212_mmr_unmasked_fallback.py`
- **.select_best_candidate()** (3 connections) — `tests/test_issue212_mmr_unmasked_fallback.py`
- **.collect_one_bar_evidence()** (3 connections) — `tests/test_issue212_mmr_unmasked_fallback.py`
- **.select_best_candidate()** (3 connections) — `tests/test_issue212_mmr_unmasked_fallback.py`
- **.collect_one_bar_evidence()** (3 connections) — `tests/test_issue212_mmr_unmasked_fallback.py`
- **.select_best_candidate()** (3 connections) — `tests/test_issue212_mmr_unmasked_fallback.py`
- **test_current_unmasked_fallback_runs_in_rescue_band()** (3 connections) — `tests/test_issue212_mmr_unmasked_fallback.py`
- *... and 27 more nodes in this community*

## Relationships

- [MMRProcessor](MMRProcessor.md) (16 shared connections)
- [object](object.md) (13 shared connections)
- [run_mmr_batch](run_mmr_batch.md) (8 shared connections)
- [audit_positive_geometry_disagreements.py](audit_positive_geometry_disagreements.py.md) (4 shared connections)
- [load_json](load_json.md) (4 shared connections)
- [TestMMROCRHeuristics](TestMMROCRHeuristics.md) (3 shared connections)
- [run_grouped_final_numbering_comparison.py](run_grouped_final_numbering_comparison.py.md) (3 shared connections)
- [diagnose_ocr_frame_changed_pages.py](diagnose_ocr_frame_changed_pages.py.md) (3 shared connections)
- [run_original_geometry_graft.py](run_original_geometry_graft.py.md) (2 shared connections)
- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (2 shared connections)
- [phase_c_fixture_rebase.py](phase_c_fixture_rebase.py.md) (2 shared connections)
- [get_nested](get_nested.md) (1 shared connections)

## Source Files

- `src/measure_numbering/mmr.py`
- `tests/test_issue212_mmr_unmasked_fallback.py`
- `tools/issue264/phase_c_fixture_rebase.py`

## Audit Trail

- EXTRACTED: 131 (82%)
- INFERRED: 28 (18%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*