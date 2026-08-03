# Issue #255 Historical Stage E Reconstruction Map

> Status: focused experiment design record. This document and the associated
> wrapper are temporary until Issue #255 either reconnects the route to the
> canonical fresh production pipeline or disproves the reconstruction.

## Corrected objective

Issue #255 is not choosing a HOMR profile or rescue policy. It must determine
whether the previously successful Stage E detector route can be regenerated
from current fresh upstream inputs without using historical detector/candidate
artifacts as runtime inputs, and then implement the required production wiring.

The public-baseline A/B only established that replacing baseline HOMR inside the
current normal route does not by itself reproduce historical Stage E output.
It did not execute the historical dense reconstruction sequence.

## Historical successful route

| Layer | Historical evidence | Exact behavior | Current branch counterpart |
|---|---|---|---|
| Checkpoint | Issue #149 / PR #150 | Detector recovery to `TP=3580 FP=0 FN=1` | Retained production helpers and compatibility tools |
| Full pipeline | Issue #141 / PR #155 | Full HOMR/SR/OMR-inclusive Stage E run | `tools/issue120/run_stage_e_full_pipeline.py` |
| Productionization | Issue #156 / PR #157 | Removed runner monkey patch and added explicit detector hooks | `src/pipeline/detector_routes/dense_full_pipeline.py`, `src/pipeline/detection/orchestrator.py` |
| Dense producer | Issue #36 v12 provenance recovered by #147/#149 | Inventory plus existing boxes, `row_stats`, cluster distance `25.0`, dense probe generation | `generate_probe_candidates_from_inventory.py`, `GENERATION_PARAMS` |
| Inventory | `20260208_bench_inventory.json` | Per-page image, current-for-that-run hybrid predictions, staff mask, clef mask/run directory | Historical runner still defaults to retained inventory; no fresh run-local builder is connected |
| Raw output | PR #150 | `probe_candidates_from_bench_v12`, 68 pages | `dense_candidate_reconstruction/probe_candidates_from_inventory` |
| Clef filter | #147/#149 | Clef-mask-aware drop filtering, 68 resolved masks | `apply_candidate_filter_from_inventory.py`, `FILTER_PARAMS` |
| Filtered output | PR #150 | 22,565 boxes; byte-identical to historical `scoring_input_eval2_v12` | `dense_candidate_reconstruction/probe_candidates_filtered` |
| Issue53 reconstruction | PR #150 | Filtered root used as `bands_from`; regenerate probe-rescue candidates | `regenerate_probe_rescue_candidates()` |
| `bands_from` | PR #150 | Issue36 filtered root | `filtered_root` passed to `run_probe_scan_batch()` |
| Probe candidate input | PR #157 | Run-local reconstructed Issue53 root | Orchestrator key `precomputed_probe_candidates_root` |
| CNN bands | PR #157 | Run-local Issue36 filtered root | Orchestrator key `cnn_bands_from` |
| Probe image | PR #157 | Original image coordinates, scale 1 | `probe_use_original_images=true` |
| CNN | PR #150/#157 | `issue44_iter7_final_rescue_v1/cnn_classifier_best.pth`, threshold `0.1` | Canonical config retains the model and threshold |
| NMS | PR #150/#157 | `cnn_apply_nms=false` | Canonical config retains `false` |
| Full-pipeline connection | PR #157 | Reconstructed roots injected through orchestrator hooks | Hooks remain, but input contract classifies them as precomputed overrides |
| Runtime artifact rule | Issue #141/#156 | Dense/filter/Issue53 roots rebuilt inside the run; historical candidate roots not used as detector input | Functions still rebuild roots, but inventory is historical by default |

## Exact historical parameters retained in current code

Dense generation:

```text
band_source=row_stats
band_cluster_max_dist=25.0
ink_threshold=240
min_ratio=0.6
min_height_ratio=0.006
min_width_ratio=0.0
probe_width=4
max_per_band=80
band_scan_line_ratio=0.6
band_scan_min_lines=5
```

Clef-mask-aware filter:

```text
left_margin_ratio=0.12
clef_left_ratio=0.25
min_height_median_ratio=0.6
ink_threshold=180
min_ink_ratio=0.18
paper_threshold=200
min_paper_overlap_ratio=0.6
min_staff_overlap_ratio=0.02
```

Issue53-style reconstruction:

```text
bands_from=<fresh filtered root>
ink_threshold=180
min_ratio=0.85
min_height_ratio=0.012
min_width_ratio=0.0001
scan_gap_rescue=true
scan_gap_threshold_ratio=1.5
scan_gap_rescue_min_ratio=0.3
scan_x_peak_rescue=true
scan_rightmost_rescue=true
divisi_rescue=true
scan_center_on_peak=true
max_per_band=100
enable_heuristic_filters=false
```

CNN:

```text
model=logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth
threshold=0.1
input_image_scale=1
bands_from=<fresh filtered root>
cnn_apply_nms=false
```

## Current implementation gap classification

| Classification | Finding | Evidence/impact |
|---|---|---|
| 1. Implemented but not configured | Yes | Canonical fresh route runs normal hybrid bands/probe flow and does not invoke dense reconstruction |
| 2. Implemented but outside canonical config | Yes | Historical Stage E settings and runner remain separate from canonical activation |
| 3. Refactor/rename changed call path | Yes | PR #157 module is now represented by `dense_full_pipeline.py`; orchestrator hooks remain explicit |
| 4. Deleted/regressed implementation | Not established | Core generation, filtering, Issue53 reconstruction, original-coordinate scoring, and no-NMS behavior remain; focused runtime evidence is required before claiming equivalence |
| 5. Fresh regeneration input not connected | Yes, primary gap | Stage E runner defaults to `logs/issue36_prep/20260208_bench_inventory.json`; it does not construct inventory from same-run current hybrid predictions and masks |
| 6. Focused wrapper missing | Addressed by this experiment | Existing Issue #255 wrappers exercised current normal route or public-HOMR A/B, not the exact dense/filter/Issue53 route |
| Contract mismatch | Yes, primary production gap | `precomputed_probe_candidates_root` or `cnn_bands_from` marks a run as `precomputed_candidate_route`, even when roots were generated inside that run |

The current input-contract classification is correct for externally supplied
candidate roots, but too coarse for the historical Stage E production design.
A production fix must distinguish external retained artifacts from same-run,
hash-recorded reconstruction products. This distinction must not permit a path
outside the current run to claim `fresh_upstream`.

## Focused experiment added for Issue #255

Entry points:

```text
tools/issue255/run_focused_stage_e_reconstruction.py
scripts/run_issue255_focused_stage_e_reconstruction.sh
```

The experiment performs:

```text
canonical input images (2 pages)
  -> current fresh baseline HOMR
  -> current fresh SR HOMR
  -> current fresh OMR-DLN
  -> current fresh consensus
  -> run-local inventory JSON
  -> Issue36 dense raw candidates
  -> clef-mask-aware filtering
  -> Issue53-style reconstruction using filtered bands_from
  -> current CNN, original coordinates, NMS disabled
  -> page metrics against evaluation-only Stage E reference
  -> eight-target layer trace
  -> manifest and tar.gz package
```

Historical accepted Stage E JSON is used only after detector inference for page
metrics and target matching. It is marked
`evaluation_only_not_runtime_input`; it is never passed to generation,
filtering, Issue53 reconstruction, or CNN scoring.

The report records:

- repository commit, branch, and worktree status;
- canonical/effective config hashes;
- run-specific path and page selection separately from detector overrides;
- input image, OMR-DLN model, CNN model, inventory, and generated tree hashes;
- coordinate space and scale for each layer;
- raw, filtered, Issue53, scored, accepted, control, and reference counts;
- focused `TP/FP/FN` for control and reconstructed outputs;
- for all eight targets: accepted bbox, best bbox, IoU, x-center distance,
  filter drop evidence, CNN score, acceptance, and first-loss boundary;
- exact fresh contract and absence of historical detector/candidate runtime inputs.

## Decision gate after local execution

If all eight targets recover without focused FP growth, the next implementation
should connect same-run dense reconstruction to the production orchestrator and
extend the input contract with verifiable same-run provenance. No new candidate
rescue algorithm is needed first.

If targets do not recover, inspect in this order:

1. fresh inventory fields and current consensus geometry;
2. staff/clef mask selection and resolution;
3. original/SR coordinate conversion;
4. retained generation/filter parameters versus the successful commits;
5. refactor regression in Issue53 reconstruction or CNN scoring;
6. changes in accepted Stage E reference/GT.

Do not run full-68 or add generic rescue logic until this focused evidence is
available.
