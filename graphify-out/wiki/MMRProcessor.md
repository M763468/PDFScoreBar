# MMRProcessor

> 28 nodes · cohesion 0.12

## Key Concepts

- **MMRProcessor** (50 connections) — `src/measure_numbering/mmr.py`
- **._process_page_with_support()** (9 connections) — `src/measure_numbering/mmr.py`
- **VariantOCR** (8 connections) — `tests/test_issue208_mmr_variant_aggregation.py`
- **.process_pages()** (7 connections) — `src/measure_numbering/mmr.py`
- **._detect_number_with_evidence()** (6 connections) — `src/measure_numbering/mmr.py`
- **generate_numbering_overrides.py** (5 connections) — `tools/generate_numbering_overrides.py`
- **._should_veto_one_bar_rest()** (4 connections) — `src/measure_numbering/mmr.py`
- **test_issue208_mmr_variant_aggregation.py** (4 connections) — `tests/test_issue208_mmr_variant_aggregation.py`
- **test_detect_number_uses_best_scored_variant_not_first_valid_variant()** (4 connections) — `tests/test_issue208_mmr_variant_aggregation.py`
- **main()** (4 connections) — `tools/generate_numbering_overrides.py`
- **._count_high_confidence_one_bar_evidence()** (3 connections) — `src/measure_numbering/mmr.py`
- **._detect_number_with_evidence_once()** (3 connections) — `src/measure_numbering/mmr.py`
- **._draw_debug()** (3 connections) — `src/measure_numbering/mmr.py`
- **._valid_status()** (3 connections) — `src/measure_numbering/mmr.py`
- **_copy_debug_image()** (3 connections) — `tools/generate_numbering_overrides.py`
- **_resolve_model_path()** (3 connections) — `tools/generate_numbering_overrides.py`
- **._detect_number()** (2 connections) — `src/measure_numbering/mmr.py`
- **._support_view()** (2 connections) — `src/measure_numbering/mmr.py`
- **Path** (2 connections)
- **Integrated processor for batch MMR detection.** (1 connections) — `src/measure_numbering/mmr.py`
- **Process multiple pages and return measure overrides for each. Returns a list of…** (1 connections) — `src/measure_numbering/mmr.py`
- **Apply current-x4 geometry without mutating Phase-A logical indices.** (1 connections) — `src/measure_numbering/mmr.py`
- **Use bounded J2 OCR geometry consensus for low-reliability baseline OCR only.** (1 connections) — `src/measure_numbering/mmr.py`
- **.__init__()** (1 connections) — `tests/test_issue208_mmr_variant_aggregation.py`
- **.mask_hbar_candidates()** (1 connections) — `tests/test_issue208_mmr_variant_aggregation.py`
- *... and 3 more nodes in this community*

## Relationships

- [test_issue212_mmr_unmasked_fallback.py](test_issue212_mmr_unmasked_fallback.py.md) (8 shared connections)
- [object](object.md) (7 shared connections)
- [MMRClassifier](MMRClassifier.md) (6 shared connections)
- [test_issue274_mmr_support_reuse.py](test_issue274_mmr_support_reuse.py.md) (4 shared connections)
- [audit_positive_geometry_disagreements.py](audit_positive_geometry_disagreements.py.md) (4 shared connections)
- [diagnose_ocr_frame_changed_pages.py](diagnose_ocr_frame_changed_pages.py.md) (3 shared connections)
- [run_mmr_batch](run_mmr_batch.md) (2 shared connections)
- [create_mmr_rapidocr](create_mmr_rapidocr.md) (2 shared connections)
- [TestMMROCRHeuristics](TestMMROCRHeuristics.md) (2 shared connections)
- [MMROCREngine](MMROCREngine.md) (2 shared connections)

## Source Files

- `src/measure_numbering/mmr.py`
- `tests/test_issue208_mmr_variant_aggregation.py`
- `tools/generate_numbering_overrides.py`

## Audit Trail

- EXTRACTED: 73 (84%)
- INFERRED: 14 (16%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*