# ThinBarlineConfig

> 28 nodes · cohesion 0.18

## Key Concepts

- **ThinBarlineConfig** (23 connections) — `src/common/thin_barline_finder.py`
- **detect_thin_vertical_runs()** (22 connections) — `src/common/thin_barline_finder.py`
- **thin_barline_finder.py** (16 connections) — `src/common/thin_barline_finder.py`
- **_filter_candidates()** (11 connections) — `src/common/thin_barline_finder.py`
- **test_issue283_thin_barline_stage2.py** (11 connections) — `tests/test_issue283_thin_barline_stage2.py`
- **_centroid()** (7 connections) — `src/common/thin_barline_finder.py`
- **_find_double_pairs()** (7 connections) — `src/common/thin_barline_finder.py`
- **_is_close()** (7 connections) — `src/common/thin_barline_finder.py`
- **_legacy_filter_candidates()** (7 connections) — `tests/test_issue283_thin_barline_stage2.py`
- **Box** (5 connections)
- **test_issue283_thin_barline_preloaded_image.py** (5 connections) — `tests/test_issue283_thin_barline_preloaded_image.py`
- **_legacy_find_double_pairs()** (5 connections) — `tests/test_issue283_thin_barline_stage2.py`
- **test_batched_candidate_filter_matches_legacy()** (5 connections) — `tests/test_issue283_thin_barline_stage2.py`
- **test_double_pair_sweep_matches_legacy()** (5 connections) — `tests/test_issue283_thin_barline_stage2.py`
- **ndarray** (4 connections)
- **test_preloaded_grayscale_bypasses_image_decode()** (4 connections) — `tests/test_issue283_thin_barline_preloaded_image.py`
- **_rectangle_sums()** (3 connections) — `src/common/thin_barline_finder.py`
- **_legacy_vertical_overlap_ratio()** (3 connections) — `tests/test_issue283_thin_barline_stage2.py`
- **Box** (3 connections)
- **test_preloaded_grayscale_requires_two_dimensions()** (2 connections) — `tests/test_issue283_thin_barline_preloaded_image.py`
- **parametrize** (2 connections)
- **Path** (1 connections)
- **Heuristics for recovering thin vertical barlines missed by primary detectors.** (1 connections) — `src/common/thin_barline_finder.py`
- **Return exact double-barline membership with bounded vectorized chunks.** (1 connections) — `src/common/thin_barline_finder.py`
- **Apply the legacy candidate filters using batched rectangle statistics.…** (1 connections) — `src/common/thin_barline_finder.py`
- *... and 3 more nodes in this community*

## Relationships

- [homr_evaluator.py](homr_evaluator.py.md) (8 shared connections)
- [.predict](predict.md) (5 shared connections)
- [test_thin_barline_finder.py](test_thin_barline_finder.py.md) (4 shared connections)
- [_extract_vertical_runs](_extract_vertical_runs.md) (4 shared connections)
- [heuristics.py](heuristics.py.md) (3 shared connections)
- [metrics.py](metrics.py.md) (2 shared connections)
- [hybrid.py](hybrid.py.md) (1 shared connections)
- [HomrPredictor](HomrPredictor.md) (1 shared connections)

## Source Files

- `src/common/thin_barline_finder.py`
- `tests/test_issue283_thin_barline_preloaded_image.py`
- `tests/test_issue283_thin_barline_stage2.py`

## Audit Trail

- EXTRACTED: 90 (94%)
- INFERRED: 6 (6%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*