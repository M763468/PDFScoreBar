# MeasureNumberer

> 25 nodes · cohesion 0.12

## Key Concepts

- **MeasureNumberer** (35 connections) — `src/measure_numbering/numbering.py`
- **.number_system()** (13 connections) — `src/measure_numbering/numbering.py`
- **run_verification()** (10 connections) — `tools/verify_measure_numbering_pipeline.py`
- **run_visualization()** (10 connections) — `tools/visualize_measure_numbering.py`
- **.number_score()** (5 connections) — `src/measure_numbering/numbering.py`
- **MeasureAttribute** (5 connections) — `src/measure_numbering/types.py`
- **._deduplicate_barlines()** (4 connections) — `src/measure_numbering/numbering.py`
- **._is_narrow_ghost_start_interval()** (4 connections) — `src/measure_numbering/numbering.py`
- **Barline** (4 connections)
- **extract_staff_bands()** (4 connections) — `tools/verify_measure_numbering_pipeline.py`
- **extract_staff_bands()** (4 connections) — `tools/visualize_measure_numbering.py`
- **._measure_interval_widths()** (3 connections) — `src/measure_numbering/numbering.py`
- **._median()** (2 connections) — `src/measure_numbering/numbering.py`
- **Any** (2 connections)
- **.setUp()** (2 connections) — `tests/test_issue194_first_interval_guard.py`
- **Path** (2 connections)
- **Path** (2 connections)
- **Return true for a short non-measure region after an implicit system start.** (1 connections) — `src/measure_numbering/numbering.py`
- **Merges barlines that are too close to each other.** (1 connections) — `src/measure_numbering/numbering.py`
- **Numbers all pages and systems in a score sequentially. Returns the next…** (1 connections) — `src/measure_numbering/numbering.py`
- **Creates Measure objects for a single system and assigns numbers. Returns the…** (1 connections) — `src/measure_numbering/numbering.py`
- **Assigns measure numbers to systems of music.** (1 connections) — `src/measure_numbering/numbering.py`
- **Manual override for a specific measure's behavior.** (1 connections) — `src/measure_numbering/types.py`
- **Extract staff bands from a binary mask and scale to target size (W, H). Returns…** (1 connections) — `tools/verify_measure_numbering_pipeline.py`
- **Extract staff bands from a binary mask and scale to target size (W, H). Returns…** (1 connections) — `tools/visualize_measure_numbering.py`

## Relationships

- [Staff](Staff.md) (32 shared connections)
- [BBox](BBox.md) (6 shared connections)
- [MeasureNumberingPipeline](MeasureNumberingPipeline.md) (5 shared connections)
- [StaffExtractor](StaffExtractor.md) (2 shared connections)
- [SystemBuilder](SystemBuilder.md) (2 shared connections)

## Source Files

- `src/measure_numbering/numbering.py`
- `src/measure_numbering/types.py`
- `tests/test_issue194_first_interval_guard.py`
- `tools/verify_measure_numbering_pipeline.py`
- `tools/visualize_measure_numbering.py`

## Audit Trail

- EXTRACTED: 70 (84%)
- INFERRED: 13 (16%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*