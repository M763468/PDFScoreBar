# MeasureNumberer

> 20 nodes · cohesion 0.16

## Key Concepts

- **MeasureNumberer** (35 connections) — `src/measure_numbering/numbering.py`
- **.number_system()** (13 connections) — `src/measure_numbering/numbering.py`
- **Measure** (8 connections) — `src/measure_numbering/types.py`
- **.number_score()** (5 connections) — `src/measure_numbering/numbering.py`
- **MeasureAttribute** (5 connections) — `src/measure_numbering/types.py`
- **._deduplicate_barlines()** (4 connections) — `src/measure_numbering/numbering.py`
- **._is_narrow_ghost_start_interval()** (4 connections) — `src/measure_numbering/numbering.py`
- **Barline** (4 connections)
- **._measure_interval_widths()** (3 connections) — `src/measure_numbering/numbering.py`
- **._median()** (2 connections) — `src/measure_numbering/numbering.py`
- **Any** (2 connections)
- **.setUp()** (2 connections) — `src/measure_numbering/test_numbering.py`
- **.setUp()** (2 connections) — `tests/test_issue194_first_interval_guard.py`
- **Return true for a short non-measure region after an implicit system start.** (1 connections) — `src/measure_numbering/numbering.py`
- **Merges barlines that are too close to each other.** (1 connections) — `src/measure_numbering/numbering.py`
- **Numbers all pages and systems in a score sequentially. Returns the next…** (1 connections) — `src/measure_numbering/numbering.py`
- **Creates Measure objects for a single system and assigns numbers. Returns the…** (1 connections) — `src/measure_numbering/numbering.py`
- **Assigns measure numbers to systems of music.** (1 connections) — `src/measure_numbering/numbering.py`
- **Manual override for a specific measure's behavior.** (1 connections) — `src/measure_numbering/types.py`
- **Represents a musical measure.** (1 connections) — `src/measure_numbering/types.py`

## Relationships

- [Staff](Staff.md) (24 shared connections)
- [Score](Score.md) (5 shared connections)
- [BBox](BBox.md) (4 shared connections)
- [StaffExtractor](StaffExtractor.md) (2 shared connections)
- [MeasureNumberingPipeline](MeasureNumberingPipeline.md) (1 shared connections)

## Source Files

- `src/measure_numbering/numbering.py`
- `src/measure_numbering/test_numbering.py`
- `src/measure_numbering/types.py`
- `tests/test_issue194_first_interval_guard.py`

## Audit Trail

- EXTRACTED: 52 (79%)
- INFERRED: 14 (21%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*