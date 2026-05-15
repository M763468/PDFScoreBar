# Issue 120 Stage D Producer Findings

## Purpose

This note records the #147 producer investigation after confirming that the historical Stage-D target artifact is equivalent to an Issue #36 dense probe-candidate root.

Read with:

```text
docs/refactors/issue120/ISSUE120_STAGE_D_DRIFT_RECOVERY.md
docs/refactors/issue120/ISSUE120_STAGE_D_SCHEMA_FINDINGS.md
docs/refactors/issue120/ISSUE120_STAGE_D_PROVENANCE_CHECKLIST.md
```

## Confirmed identity

The historical root:

```text
logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
```

and the Issue #36 candidate root:

```text
logs/issue36_prep/probe_candidates_filtered_v12
```

are byte-identical for the canonical per-page candidate files checked:

```text
left_files=68
missing=0
mismatch=0
```

This means `scoring_input_eval2_v12` can be treated as a copy or direct equivalent of `probe_candidates_filtered_v12` for Stage-D candidate-root recovery.

## Historical v12 raw and filtered roots

Local provenance summaries identify the actual historical v12 producer family:

```text
raw root:      logs/issue36_prep/probe_candidates_from_bench_v12
filtered root: logs/issue36_prep/probe_candidates_filtered_v12
```

Historical v12 totals:

```text
historical_raw      files=68 total=27758
historical_filtered files=68 total=22565
```

The Issue #44 scoring-input copy is byte-identical to `historical_filtered` for the canonical candidate files.

## Correct producer family

The relevant Stage-D producer is the Issue #36 GT-prep v12 dense candidate workflow:

```text
tools/verification/gt_preparation/generate_probe_candidates_from_inventory.py
  -> probe_candidates_from_bench_v12

tools/verification/gt_preparation/apply_candidate_filter_from_inventory.py
  -> probe_candidates_filtered_v12
```

This is distinct from the later Stage-C helper:

```text
tools/repro_accuracy/reproduce_clean_seed_v12.py
```

The later Stage-C helper is not the historical v12 dense candidate producer for Issue #36 / Stage D recovery.

## Raw candidate recovery

Running the Issue #36 GT-prep generation command at the historical `edf7bf6` implementation with the historical v12 parameters and current mounted `data/` + `logs/` inputs reproduced the raw candidate root exactly:

```text
historical_raw:      files=68 total=27758
repro_raw_edf7bf6:   files=68 total=27758
missing=0 mismatch=0
```

This recovers the raw candidate generation layer.

## Filter recovery: missing condition was clef-mask filtering

Filtering the byte-identical raw candidate root without clef-mask filtering produced a strict superset of the historical filtered root:

```text
historical_filtered: files=68 total=22565
repro_no_clef:       files=68 total=24020
mismatch_pages=67
extra_in_repro=1455
missing_from_repro=0
```

This means the no-clef repro retained all historical boxes plus 1455 additional boxes.

Rerunning the filter with clef-mask-aware filtering reproduced the historical filtered root exactly:

```text
historical_filtered: files=68 total=22565
repro_with_clef:     files=68 total=22565
mismatch_pages=0
extra_in_repro=0
missing_from_repro=0
```

The clef-mask-aware run recorded these drop reason counts:

```text
left_margin_zone=3520
clef_mask_overlap=4665
no_staff_overlap=781
```

Therefore the missing historical filter condition was `clef_mask_overlap` dropping.

## Recovered Stage-D candidate-root provenance

The recovered Stage-D candidate-root path is:

```text
20260208 bench inventory
  + excluded_pages_for_gt_prep.json
  + generate_probe_candidates_from_inventory.py parameters:
      band_source=row_stats
      ink_threshold=240
      min_ratio=0.6
      min_height_ratio=0.006
      min_width_ratio=0.0
      probe_width=4
      max_per_band=80
      band_scan_line_ratio=0.6
      band_scan_min_lines=5
  -> probe_candidates_from_bench_v12
  -> apply_candidate_filter_from_inventory.py parameters:
      left_margin_ratio=0.12
      clef_left_ratio=0.25
      min_height_median_ratio=0.6
      ink_threshold=180
      min_ink_ratio=0.18
      paper_threshold=200
      min_paper_overlap_ratio=0.6
      min_staff_overlap_ratio=0.02
      clef_mask filtering enabled/resolved
  -> probe_candidates_filtered_v12
  -> byte-identical to issue44_baseline_v1/scoring_input_eval2_v12 candidate files
```

## Final local reproduction commands

These commands reproduce the recovered Stage-D dense candidate root from the historical implementation and current mounted `data/` + `logs/` inputs. Generated outputs stay under ignored `logs/issue120_e2e_recovery/` paths.

### 1. Create the historical worktree

```bash
MAIN_REPO="$PWD"
WORKTREE=/tmp/pdfscorebar_issue120_edf7bf6

git worktree prune
git worktree remove --force "$WORKTREE" 2>/dev/null || true
rm -rf "$WORKTREE"
git worktree add --force --detach "$WORKTREE" edf7bf610c3355c34e660192e81f35b03fe91714

git -C "$WORKTREE" rev-parse HEAD
```

Expected commit:

```text
edf7bf610c3355c34e660192e81f35b03fe91714
```

### 2. Regenerate raw candidates

```bash
MAIN_REPO="$PWD"
WORKTREE=/tmp/pdfscorebar_issue120_edf7bf6
OUT="$MAIN_REPO/logs/issue120_e2e_recovery/stage_d_issue36_v12_repro_edf7bf6_final"

rm -rf "$OUT"
mkdir -p "$OUT"

docker run --rm --gpus all \
  --user "$(id -u):$(id -g)" \
  -v "$WORKTREE":/workspace \
  -v "$MAIN_REPO/data":/workspace/data:ro \
  -v "$MAIN_REPO/logs":/workspace/logs \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  pdfscore_pipeline_gpu \
  /opt/venv_pipeline/bin/python tools/verification/gt_preparation/generate_probe_candidates_from_inventory.py \
  --inventory logs/issue36_prep/20260208_bench_inventory.json \
  --exclude logs/issue36_prep/excluded_pages_for_gt_prep.json \
  --output-root logs/issue120_e2e_recovery/stage_d_issue36_v12_repro_edf7bf6_final/probe_candidates_from_bench_v12 \
  --summary-out logs/issue120_e2e_recovery/stage_d_issue36_v12_repro_edf7bf6_final/20260211_probe_generation_summary_v12_repro.json \
  --band-source row_stats \
  --ink-threshold 240 \
  --min-ratio 0.6 \
  --min-height-ratio 0.006 \
  --min-width-ratio 0.0 \
  --probe-width 4 \
  --max-per-band 80 \
  --band-scan-line-ratio 0.6 \
  --band-scan-min-lines 5
```

Expected raw comparison:

```text
historical_raw: files=68 total=27758
repro_raw:      files=68 total=27758
missing=0 mismatch=0
```

### 3. Apply the clef-mask-aware filter

Run this from the current #148 branch, not from the historical worktree, because this PR records clef-mask resolution in the filter summary.

```bash
MAIN_REPO="$PWD"
OUT="$MAIN_REPO/logs/issue120_e2e_recovery/stage_d_issue36_v12_repro_edf7bf6_final"

docker run --rm --gpus all \
  --user "$(id -u):$(id -g)" \
  -v "$MAIN_REPO":/workspace \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  pdfscore_pipeline_gpu \
  /opt/venv_pipeline/bin/python tools/verification/gt_preparation/apply_candidate_filter_from_inventory.py \
  --inventory logs/issue36_prep/20260208_bench_inventory.json \
  --exclude logs/issue36_prep/excluded_pages_for_gt_prep.json \
  --candidates-root logs/issue120_e2e_recovery/stage_d_issue36_v12_repro_edf7bf6_final/probe_candidates_from_bench_v12 \
  --output-root logs/issue120_e2e_recovery/stage_d_issue36_v12_repro_edf7bf6_final/probe_candidates_filtered_v12 \
  --suggestions-root logs/issue120_e2e_recovery/stage_d_issue36_v12_repro_edf7bf6_final/filter_suggestions_v12 \
  --summary-out logs/issue120_e2e_recovery/stage_d_issue36_v12_repro_edf7bf6_final/20260211_filter_apply_summary_v12_repro.json \
  --left-margin-ratio 0.12 \
  --clef-left-ratio 0.25 \
  --min-height-median-ratio 0.6 \
  --ink-threshold 180 \
  --min-ink-ratio 0.18 \
  --paper-threshold 200 \
  --min-paper-overlap-ratio 0.6 \
  --min-staff-overlap-ratio 0.02
```

Expected filter summary properties:

```text
processed=68
errors=0
clef_mask_resolution.resolved_pages=68
clef_mask_resolution.missing_pages=0
reason_counts.left_margin_zone=3520
reason_counts.clef_mask_overlap=4665
reason_counts.no_staff_overlap=781
```

### 4. Compare filtered output against the historical root

```bash
MAIN_REPO="$PWD"
OUT="$MAIN_REPO/logs/issue120_e2e_recovery/stage_d_issue36_v12_repro_edf7bf6_final"

docker run --rm --gpus all \
  --user "$(id -u):$(id -g)" \
  -v "$MAIN_REPO":/workspace \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  pdfscore_pipeline_gpu \
  /opt/venv_pipeline/bin/python tools/issue120/compare_filter_candidate_deltas.py \
    --historical-dir logs/issue36_prep/probe_candidates_filtered_v12 \
    --repro-dir logs/issue120_e2e_recovery/stage_d_issue36_v12_repro_edf7bf6_final/probe_candidates_filtered_v12 \
    --repro-suggestions-root logs/issue120_e2e_recovery/stage_d_issue36_v12_repro_edf7bf6_final/filter_suggestions_v12 \
    --output-dir logs/issue120_e2e_recovery/stage_d_issue36_v12_repro_edf7bf6_final/filter_delta_inspection
```

Expected result:

```text
Filter candidate delta comparison
Pages: 68
Historical total: 22565
Repro total: 22565
Total delta: 0
Mismatch pages: 0
Extra in repro: 0
Missing from repro: 0
```

## Provenance requirement

Any rerun of `apply_candidate_filter_from_inventory.py` intended to reproduce historical v12 must record clef-mask resolution.

The filter summary should include:

```json
{
  "clef_mask_resolution": {
    "resolved_pages": 68,
    "missing_pages": 0
  }
}
```

and per-page entries should include the resolved clef mask path.

## Current Stage-D implication

The earlier sparse HOMR/SR/OMR/hybrid regenerated roots are not the correct reconstruction family for the historical dense candidate root.

The better Stage-D framing is now:

```text
historical detector target root
  = logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
  = byte-identical to logs/issue36_prep/probe_candidates_filtered_v12
  = generated by Issue #36 GT-prep v12 raw/filter workflow with clef-mask filtering
```

## Routing decision

The candidate-root recovery itself belongs in #147 / #148.

However, integrating this recovered dense producer into the final current pipeline is a separate task from provenance recovery. That integration should not be mixed into #148 because it may require pipeline configuration, execution routing, detector evaluation, downstream measure-count evaluation, and possibly NMS interactions.

Recommended follow-up issue:

```text
[Issue120 Restart] Integrate recovered Issue36 dense candidate producer into current pipeline validation
```

Suggested scope:

- add a current pipeline/config path that can invoke or consume the recovered Issue #36 dense candidate producer;
- keep generated outputs under ignored `logs/` paths;
- evaluate with the #134 detector evaluator;
- evaluate downstream measure-count metrics separately;
- explicitly record `cnn_apply_nms` and clef-mask filtering provenance;
- do not change general pipeline defaults without #142.

## Current conclusion

Stage-D candidate-root provenance is recovered at the candidate-file level:

```text
raw generation: exact match
filter without clef mask: fails as +1455 superset
filter with clef mask: exact match
```

Remaining work is no longer provenance recovery of the historical dense root. It is integration and final-pipeline validation.
