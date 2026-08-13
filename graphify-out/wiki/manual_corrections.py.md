# manual_corrections.py

> 42 nodes · cohesion 0.11

## Key Concepts

- **manual_corrections.py** (19 connections) — `src/pipeline/steps/manual_corrections.py`
- **test_manual_corrections.py** (18 connections) — `tests/test_manual_corrections.py`
- **merge_measure_overrides()** (17 connections) — `src/pipeline/steps/manual_corrections.py`
- **apply_mmr_measure_span_corrections()** (12 connections) — `src/pipeline/steps/manual_corrections.py`
- **merge_barline_overrides()** (12 connections) — `src/pipeline/steps/manual_corrections.py`
- **barlines.py** (9 connections) — `src/pipeline/steps/barlines.py`
- **barline_construction_overrides()** (9 connections) — `src/pipeline/steps/manual_corrections.py`
- **measure_construction_overrides()** (9 connections) — `src/pipeline/steps/manual_corrections.py`
- **normalise_measure_overrides()** (9 connections) — `src/pipeline/steps/manual_corrections.py`
- **Payload** (7 connections)
- **Any** (7 connections)
- **normalise_barline_overrides()** (6 connections) — `src/pipeline/steps/manual_corrections.py`
- **MeasureOverride** (5 connections)
- **_manual_comment()** (5 connections) — `src/pipeline/steps/manual_corrections.py`
- **_measure_key()** (5 connections) — `src/pipeline/steps/manual_corrections.py`
- **_set_measure_span_override()** (5 connections) — `src/pipeline/steps/manual_corrections.py`
- **_normalise_barline_override()** (4 connections) — `src/pipeline/steps/manual_corrections.py`
- **_normalise_measure_override()** (4 connections) — `src/pipeline/steps/manual_corrections.py`
- **test_barline_construction_add_and_remove_are_not_measure_overrides()** (4 connections) — `tests/test_manual_corrections.py`
- **BarlineOverride** (3 connections)
- **_bbox()** (3 connections) — `src/pipeline/steps/manual_corrections.py`
- **_to_int_or_none()** (3 connections) — `src/pipeline/steps/manual_corrections.py`
- **test_measure_construction_force_measure_is_separate_from_future_grouping_ops()** (3 connections) — `tests/test_manual_corrections.py`
- **test_measure_construction_malformed_item_reports_descriptive_error()** (2 connections) — `tests/test_manual_corrections.py`
- **test_merge_measure_overrides_applies_manual_last_regardless_of_payload_order()** (2 connections) — `tests/test_manual_corrections.py`
- *... and 17 more nodes in this community*

## Relationships

- [apply_corrections.py](apply_corrections.py.md) (5 shared connections)
- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (3 shared connections)
- [manual_correction_handoff.py](manual_correction_handoff.py.md) (3 shared connections)
- [test_manual_correction_handoff.py](test_manual_correction_handoff.py.md) (2 shared connections)
- [barline_iou](barline_iou.md) (1 shared connections)
- [greedy_barline_match](greedy_barline_match.md) (1 shared connections)
- [.run](run.md) (1 shared connections)

## Source Files

- `src/pipeline/steps/barlines.py`
- `src/pipeline/steps/manual_corrections.py`
- `tests/test_manual_corrections.py`

## Audit Trail

- EXTRACTED: 110 (99%)
- INFERRED: 1 (1%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*