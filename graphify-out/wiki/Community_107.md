# Community 107

> 25 nodes · cohesion 0.18

## Key Concepts

- **test_probe_helpers.py** (28 connections) — `tests/test_probe_helpers.py`
- **measurements.py** (14 connections) — `src/pipeline/probe_detector/measurements.py`
- **project_staff_band()** (12 connections) — `src/pipeline/probe_detector/measurements.py`
- **measure_candidate_scan()** (10 connections) — `src/pipeline/probe_detector/measurements.py`
- **CandidateScanConfig** (10 connections) — `src/pipeline/probe_detector/types.py`
- **BandProjectionConfig** (9 connections) — `src/pipeline/probe_detector/types.py`
- **select_signal_peaks()** (7 connections) — `src/pipeline/probe_detector/measurements.py`
- **test_candidate_measurement_keeps_fallback_and_staff_peak_exclusion()** (6 connections) — `tests/test_probe_helpers.py`
- **scan_staff_band_from_ink()** (5 connections) — `src/pipeline/probe_detector/bands.py`
- **BandProjection** (5 connections) — `src/pipeline/probe_detector/measurements.py`
- **_projection_config()** (5 connections) — `tests/test_probe_helpers.py`
- **CandidateScanMeasurement** (4 connections) — `src/pipeline/probe_detector/measurements.py`
- **ndarray** (3 connections)
- **_candidate_scan_config()** (3 connections) — `tests/test_probe_helpers.py`
- **test_band_projection_keeps_domain_halo_and_extension_ratios()** (3 connections) — `tests/test_probe_helpers.py`
- **test_row_padding_ratio_precedes_staff_padding_and_clips_at_image_boundary()** (3 connections) — `tests/test_probe_helpers.py`
- **test_develop_probe_debug_remains_opt_in_and_writes_artifacts()** (2 connections) — `tests/test_probe_helpers.py`
- **test_existing_suppression_requires_vertical_overlap_and_preserves_nearest_band()** (2 connections) — `tests/test_probe_helpers.py`
- **test_peak_domain_and_limit_are_applied_before_returning_selection()** (2 connections) — `tests/test_probe_helpers.py`
- **test_peak_ties_keep_leftmost_then_apply_distance_in_score_order()** (2 connections) — `tests/test_probe_helpers.py`
- **Estimate staff band by horizontal scan around x_center within [y1, y2].** (1 connections) — `src/pipeline/probe_detector/bands.py`
- **Staff projections, peak selection and candidate measurements before acceptance.** (1 connections) — `src/pipeline/probe_detector/measurements.py`
- **Existing options for candidate-local ink measurements; no new defaults.** (1 connections) — `src/pipeline/probe_detector/types.py`
- **parametrize** (1 connections)
- **test_develop_wide_split_opt_in_calls_existing_implementation()** (1 connections) — `tests/test_probe_helpers.py`

## Relationships

- [Community 103](Community_103.md) (22 shared connections)
- [Community 10](Community_10.md) (5 shared connections)
- [Community 87](Community_87.md) (3 shared connections)
- [Community 64](Community_64.md) (1 shared connections)
- [Community 100](Community_100.md) (1 shared connections)
- [Community 67](Community_67.md) (1 shared connections)
- [Community 15](Community_15.md) (1 shared connections)

## Source Files

- `src/pipeline/probe_detector/bands.py`
- `src/pipeline/probe_detector/measurements.py`
- `src/pipeline/probe_detector/types.py`
- `tests/test_probe_helpers.py`

## Audit Trail

- EXTRACTED: 83 (95%)
- INFERRED: 4 (5%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*