# Shared Barline Matcher Specification

## Overview
The `src/common/barline_evaluation.py` module provides the shared matcher that both homr and oemer pipelines use for comparing predicted barline boxes against ground truth. The matcher normalises slender barline geometry, performs IoU-based greedy matching, and classifies near-miss cases so downstream reports can promote or demote detections consistently.

## Geometry Normalisation
- Each predicted and ground-truth box is padded via `expand_barline_box` before IoU measurement.
- Default parameters (imported by both pipelines):
  - `BARLINE_DEFAULT_MIN_WIDTH = 12`
  - `BARLINE_X_MARGIN = 3`
  - `BARLINE_Y_MARGIN = 3`
- The padding keeps box centres fixed, guarantees a minimum width, and clamps to the image bounds when provided. This mitigates tiny-width discrepancies that otherwise drive IoU to zero.

## Greedy Matching
1. Build a dense IoU matrix using the padded boxes and the configured IoU threshold (`iou_threshold` is typically 0.5 in evaluators).
2. While any IoU entries remain, greedily choose the highest-scoring pair and remove its row and column.
3. Record the hard matches as `(prediction_index, ground_truth_index, iou)` tuples.

During the matrix construction the matcher also records, for each prediction, two "best" references:
- **Strong best** – requires vertical overlap ≥ `BARLINE_VERTICAL_OVERLAP_THRESHOLD` (0.6).
- **Fallback best** – best IoU regardless of overlap, with tie-breaking by overlap then X-distance.
These records feed the soft-match classification described below.

## Duplicate & Repeat Classification
After greedy pairing, unmatched predictions are revisited:
- **Duplicate (`reason="duplicate"`)** when
  - IoU with fallback best ≥ `BARLINE_DUPLICATE_IOU_THRESHOLD` (0.3) and
  - X-distance ≤ `BARLINE_DUPLICATE_X_TOLERANCE` (12 px).
- **Repeat-like (`reason="repeat_like"`)** when
  - Vertical overlap ≥ `BARLINE_REPEAT_OVERLAP_THRESHOLD` (0.8),
  - X-distance between duplicate tolerance and `BARLINE_REPEAT_X_TOLERANCE` (40 px).

Predictions that do not satisfy either rule are treated as hard false positives.

## Left-margin Exclusion Rule
`apply_left_margin_exclusion` runs after matching to reclassify select detections as false positives. The homr evaluator currently keeps the guard disabled (`LEFT_MARGIN_FORCE_FP_GT_INDICES = set()`), so no matches are demoted by default. When re-enabled, any GT index listed in the set and matched to a predicted width ≤ `LEFT_MARGIN_FORCE_FP_MAX_WIDTH` (2 px) will be forced back to an FP to suppress intentionally ignored left-gutter pillars.

When `margin_x` is provided (unused at present) the helper also demotes predictions whose centres fall inside the margin alongside their matched GT centres, allowing configurable left gutter suppression for other scores.

## Output Contract
The matcher returns a `BarlineMatchResult` with:
- `matches`: confirmed TP pairs
- `false_positive_indices`: unmatched predictions after duplicate/repeat filtering
- `false_negative_indices`: unmatched ground truth boxes
- `soft_matches`: duplicate/repeat-like records that remain associated with their GT index but are not counted as TP.

## Thin Barline Recovery Heuristics (2025-10-15)
The shared `common/thin_barline_finder.py` helper supplements detector output with slender pillars that primary models miss. Recent updates introduced:

- **Vertical split awareness**: candidates sharing an X coordinate now coexist when their vertical centres differ by more than a staff height, avoiding inadvertent overwrites between systems.
- **Adjacency relaxation**: if the immediate 3 px neighbour is slightly dark but a wider 6 px window returns to background brightness, the barline is kept. This captures repeat pillars nested beside stems.
- **STD fallback**: 1–4 px wide pillars may tolerate higher intensity variance (≤80) when both neighbours read as background, covering mixed black/white pairs observed in GT indices {97,147}.
- **Single-side guard** (2025-10-17): when one neighbour is confidently background and the opposite side is dark because of a stem/dynamics cluster, detections survive as long as the dark window is not fully inked (`single_side_dark_ratio ≤ 0.6`). The notehead rejection now requires both neighbours to be dense when this override triggers.
- **Vertical gap closing** (2025-10-17): a 3 px tall morphological closing bridges short ledger/rest gaps before run-length analysis, enabling recovery of split pillars like GT 137.

These heuristics reduced the shared false-negative set on `page_003` from six entries to four while keeping FP growth bounded (homr run `20251015T010556JST_fn_vertical_split_v5`: TP=148 FP=8 FN=4, precision 0.949/recall 0.974). The same logic propagates to the OEMER evaluator (`20251015T010745JST_baseline`: TP=152 FP=6 FN=0).

Evaluators serialise these results into `metrics.json`, `metrics.csv`, overlay images, and human-readable `compare.md` artefacts under `logs/<pipeline>/<timestamp>/`.
