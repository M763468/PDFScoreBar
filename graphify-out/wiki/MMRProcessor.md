# MMRProcessor

> 42 nodes · cohesion 0.08

## Key Concepts

- **MMRProcessor** (50 connections) — `src/measure_numbering/mmr.py`
- **MMRClassifier** (26 connections) — `src/measure_numbering/mmr.py`
- **mmr.py** (14 connections) — `src/measure_numbering/mmr.py`
- **._process_page_with_support()** (9 connections) — `src/measure_numbering/mmr.py`
- **VariantOCR** (8 connections) — `tests/test_issue208_mmr_variant_aggregation.py`
- **.process_pages()** (7 connections) — `src/measure_numbering/mmr.py`
- **._detect_number_with_evidence()** (6 connections) — `src/measure_numbering/mmr.py`
- **run_mmr_batch()** (6 connections) — `src/measure_numbering/mmr.py`
- **.__init__()** (5 connections) — `src/measure_numbering/mmr.py`
- **.__init__()** (5 connections) — `src/measure_numbering/mmr.py`
- **Path** (5 connections)
- **generate_numbering_overrides.py** (5 connections) — `tools/generate_numbering_overrides.py`
- **._load_model()** (4 connections) — `src/measure_numbering/mmr.py`
- **._should_veto_one_bar_rest()** (4 connections) — `src/measure_numbering/mmr.py`
- **test_issue208_mmr_variant_aggregation.py** (4 connections) — `tests/test_issue208_mmr_variant_aggregation.py`
- **test_detect_number_uses_best_scored_variant_not_first_valid_variant()** (4 connections) — `tests/test_issue208_mmr_variant_aggregation.py`
- **main()** (4 connections) — `tools/generate_numbering_overrides.py`
- **.predict()** (3 connections) — `src/measure_numbering/mmr.py`
- **._count_high_confidence_one_bar_evidence()** (3 connections) — `src/measure_numbering/mmr.py`
- **._detect_number_with_evidence_once()** (3 connections) — `src/measure_numbering/mmr.py`
- **._draw_debug()** (3 connections) — `src/measure_numbering/mmr.py`
- **._valid_status()** (3 connections) — `src/measure_numbering/mmr.py`
- **device** (3 connections)
- **_copy_debug_image()** (3 connections) — `tools/generate_numbering_overrides.py`
- **_resolve_model_path()** (3 connections) — `tools/generate_numbering_overrides.py`
- *... and 17 more nodes in this community*

## Relationships

- [MMROCREngine](MMROCREngine.md) (16 shared connections)
- [object](object.md) (8 shared connections)
- [load_json](load_json.md) (8 shared connections)
- [audit_positive_geometry_disagreements.py](audit_positive_geometry_disagreements.py.md) (8 shared connections)
- [diagnose_ocr_frame_changed_pages.py](diagnose_ocr_frame_changed_pages.py.md) (6 shared connections)
- [test_issue274_mmr_support_reuse.py](test_issue274_mmr_support_reuse.py.md) (5 shared connections)
- [run_grouped_final_numbering_comparison.py](run_grouped_final_numbering_comparison.py.md) (4 shared connections)
- [TestMMROCRHeuristics](TestMMROCRHeuristics.md) (3 shared connections)
- [run_mmr_batch](run_mmr_batch.md) (3 shared connections)
- [run_original_geometry_graft.py](run_original_geometry_graft.py.md) (2 shared connections)
- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (2 shared connections)
- [get_nested](get_nested.md) (1 shared connections)

## Source Files

- `src/measure_numbering/mmr.py`
- `tests/test_issue208_mmr_variant_aggregation.py`
- `tools/generate_numbering_overrides.py`

## Audit Trail

- EXTRACTED: 123 (88%)
- INFERRED: 17 (12%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*