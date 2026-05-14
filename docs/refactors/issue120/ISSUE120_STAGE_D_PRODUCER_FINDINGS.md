# Issue 120 Stage D Producer Findings

## Purpose
n
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

## Current Stage-C helper mismatch

The current Stage-C recovery helper does not reproduce the historical raw family. Its outputs are:

```text
current_repro_raw      files=136 total=97927
current_repro_filtered files=68  total=180
```

The `current_repro_raw` count includes both the nested raw files and the generated filtered files because it was counted with a broad `rglob`. Interpreted with the earlier Stage-C summary, this is:

```text
current raw      = 97747
current filtered =   180
```

Therefore the current helper is not a historical v12 producer. Its `low_paper_overlap` collapse is downstream evidence that it feeds a different raw candidate family into the v12 filter rules.

## Exact Issue #36 v12 reproduction attempt

Running the Issue #36 GT-prep producer family with the historical v12 summary parameters gives a close but not exact reproduction:

```text
historical_raw      files=68 total=27758
repro_raw           files=68 total=27445
historical_filtered files=68 total=22565
repro_filtered      files=68 total=22335
```

Byte comparison:

```text
historical_raw vs repro_raw
  left_files=68 missing=0 mismatch=12

historical_filtered vs repro_filtered
  left_files=68 missing=0 mismatch=12
```

The mismatching pages are the same in raw and filtered outputs:

```text
Shostakovich-Festival_Overture_Va/page_001
Shostakovich-Sym5-Va/page_004
Shostakovich-Sym5-Va/page_005
Shostakovich-Sym5-Va/page_008
Shostakovich-Sym5-Va/page_012
Shostakovich-Sym5-Va/page_013
Sibelius-Violin_Concerto-Viola/page_004
Va_Prokofiev_Symphony1/page_004
Va__Prokofiev_Symphony5/page_002
Va__Prokofiev_Symphony5/page_003
Va__Prokofiev_Symphony5/page_009
Va__Prokofiev_Symphony5/page_021
```

Interpretation:

- The Issue #36 GT-prep path is the correct reconstruction family.
- It is much closer than the later Stage-C helper.
- The remaining drift starts in raw generation, not filtering, because the same 12 pages mismatch before and after filtering.
- Raw total is short by 313 candidates; filtered total is short by 230 candidates.
- The next boundary is input-file drift or `detect_probe_scan` implementation drift for those 12 pages.

## Twelve-page drift shape

The per-page set differences show that many mismatches are near-identical boxes with small y-boundary shifts, not wholly different candidate families.

Examples:

```text
Shostakovich-Sym5-Va/page_008:
  historical: (275, 1161, 279, 1263)
  repro:      (275, 1161, 279, 1264)

Shostakovich-Sym5-Va/page_012:
  historical: (510, 1893, 514, 1992)
  repro:      (510, 1891, 514, 1991)

Va__Prokofiev_Symphony5/page_002:
  historical: (531, 2237, 535, 2347)
  repro:      (531, 2237, 535, 2345)

Va__Prokofiev_Symphony5/page_021:
  historical: (703, 1782, 707, 1891)
  repro:      (703, 1779, 707, 1889)
```

Some pages also lose candidates without replacement, for example:

```text
Shostakovich-Sym5-Va/page_005 raw:
  left=317 right=295 missing_from_repro=22 extra_in_repro=0

Va__Prokofiev_Symphony5/page_003 raw:
  left=549 right=519 missing_from_repro=30 extra_in_repro=0
```

This pattern points to row/band-boundary resolution or `detect_probe_scan` implementation drift more than final-filter drift.

## Input-file metadata check

For 10 of the 12 mismatch pages checked so far, the inventory inputs are present and have mtimes on 2026-01-31, before the v12 generation window on 2026-02-12:

```text
image:              data/evaluation2/images/.../page_*.png
staff_mask:         logs/hybrid_pipeline_bench/.../*_proxy_debug_3_staff.png
hybrid_predictions: logs/hybrid_pipeline_bench/.../hybrid_predictions.json
```

The checked inputs therefore do not show evidence of post-v12 modification. Two mismatch pages still need the same input metadata check:

```text
Va__Prokofiev_Symphony5/page_009
Va__Prokofiev_Symphony5/page_021
```

## Repository/local grep findings

The grep result identifies these relevant current repository references:

```text
tools/repro_accuracy/reproduce_clean_seed_v12.py
tools/issue120/run_stage_c_seed_regen_then_eval.py
tools/repro_accuracy/verify_repro_batch_final.py
tools/repro_accuracy/find_baseline_runs.py
tools/repro_accuracy/reorganize_seeds.py
tools/verification/gt_preparation/README.md
tools/verification/gt_preparation/generate_probe_candidates_from_inventory.py
tools/verification/gt_preparation/apply_candidate_filter_from_inventory.py
tools/gt_relabel_gui/prepare_rebuild_eval2.py
```

The current evidence distinguishes two related but different producer paths:

1. Historical Issue #36 GT-prep path:

   ```text
   generate_probe_candidates_from_inventory.py
     -> probe_candidates_from_bench_v12
   apply_candidate_filter_from_inventory.py
     -> probe_candidates_filtered_v12
   ```

2. Later Stage-C recovery helper:

   ```text
   reproduce_clean_seed_v12.py
     -> hybrid_generalization/verify_fixed_v10 score-run mapping
     -> current raw candidates
     -> current final filtered root
   ```

For Issue #120 Stage-D recovery, path 1 is now the primary reconstruction target.

## Historical v12 configuration

The v12 probe-generation summary records:

```json
{
  "band_scan_line_ratio": 0.6,
  "band_scan_min_lines": 5,
  "band_source": "row_stats",
  "ink_threshold": 240,
  "max_per_band": 80,
  "min_height_ratio": 0.006,
  "min_ratio": 0.6,
  "min_width_ratio": 0.0,
  "probe_width": 4
}
```

The v12 filter summary records:

```json
{
  "clef_left_ratio": 0.25,
  "ink_threshold": 180,
  "left_margin_ratio": 0.12,
  "min_height_median_ratio": 0.6,
  "min_ink_ratio": 0.18,
  "min_paper_overlap_ratio": 0.6,
  "min_staff_overlap_ratio": 0.02,
  "paper_threshold": 200
}
```

Historical v12 filter reason counts were:

```text
clef_mask_overlap=4665
left_margin_zone=3520
no_staff_overlap=781
```

They do not include `low_paper_overlap`, unlike the current Stage-C helper replay.

## Historical script comparison

The `generate_probe_candidates_from_inventory.py` wrapper at commit `edf7bf6` uses the same effective defaults as the current Issue #36 GT-prep invocation for v12. The current wrapper adds a `--scan-x-peak-rescue` CLI switch, but its default remains enabled, matching the historical hardcoded behavior.

The current `detect_probe_scan` implementation contains additional features and branches not present in the historical `edf7bf6` version, including `scan_gap_rescue`, `scan_disable_existing_suppression`, `scan_existing_min_vertical_iou`, nullable `band_cluster_max_dist`, and an `effective_min` path. Even if these features are not explicitly enabled in the v12 invocation, the current implementation should be compared or pinned before declaring exact reproduction failure.

Therefore the remaining 12-page drift is unlikely to be caused by the GT-prep wrapper alone. Prioritize:

1. `detect_probe_scan` implementation drift;
2. input file drift in inventory fields, especially `hybrid_predictions`;
3. image/staff-mask file drift or path resolution differences;
4. OpenCV / numpy version differences only after code/input drift is excluded.

## Current Stage-D implication

The current Stage-D upstream regeneration runner composes sparse detector-output roots from current HOMR/SR/OMR/hybrid outputs. That path is not sufficient to reproduce the historical dense candidate root.

The better Stage-D framing is:

```text
historical detector target root
  = logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
  = byte-identical to logs/issue36_prep/probe_candidates_filtered_v12
  = generated by Issue #36 GT-prep v12 raw/filter workflow
```

## Recommended next local check: finish isolating the 12-page drift

### 1. Check input metadata for the remaining two pages

```bash
python3 - <<'PY' | tee logs/issue120_e2e_recovery/stage_d_provenance/v12_remaining_mismatch_input_files.txt
import hashlib
import json
from datetime import datetime
from pathlib import Path

mismatch_pages = {
    ('Va__Prokofiev_Symphony5', 'page_009'),
    ('Va__Prokofiev_Symphony5', 'page_021'),
}

inv = json.loads(Path('logs/issue36_prep/20260208_bench_inventory.json').read_text())
for rec in inv.get('records', []):
    key = (rec.get('score'), rec.get('page'))
    if key not in mismatch_pages:
        continue
    print('##', key[0], key[1])
    for field in ('image', 'staff_mask', 'hybrid_predictions', 'run_dir'):
        value = rec.get(field)
        if not value:
            continue
        p = Path(value)
        print(field, p)
        if p.is_file():
            st = p.stat()
            print('  mtime', datetime.fromtimestamp(st.st_mtime).isoformat(timespec='seconds'))
            print('  size', st.st_size)
            print('  sha256', hashlib.sha256(p.read_bytes()).hexdigest())
        elif p.is_dir():
            st = p.stat()
            print('  dir_mtime', datetime.fromtimestamp(st.st_mtime).isoformat(timespec='seconds'))
        else:
            print('  missing')
PY
```

### 2. Rerun v12 with the historical commit implementation

If the remaining two pages also show stable pre-v12 inputs, test the historical implementation directly:

```bash
git worktree add /tmp/pdfscorebar_issue120_edf7bf6 edf7bf6
cd /tmp/pdfscorebar_issue120_edf7bf6
```

Then run the same Issue #36 v12 generation command from that worktree, mounting the original repository logs/data as needed. Keep outputs under the main repository's ignored `logs/issue120_e2e_recovery/` path.

### 3. If historical commit reproduces byte identity

Record `detect_probe_scan` implementation drift as the remaining boundary and decide whether Stage-D recovery should pin historical behavior or keep the current near-exact root plus detector metric validation.

### 4. If historical commit still does not reproduce byte identity

The remaining drift is likely input-file/environment-level. Prioritize comparing row-stat bands and OpenCV/numpy behavior on one high-drift page.

## Routing decision

If input drift explains the 12 pages, Stage-D exact reconstruction depends on recovering the historical input files for those pages.

If `detect_probe_scan` drift explains the 12 pages, Stage-D exact reconstruction should pin or reintroduce the historical probe-detector behavior for the Issue #36 v12 producer.

If the 12-page drift is small and detector-level evaluation still matches the target after scoring, exact byte identity may not be required. Keep detector metrics separate from downstream measure-count metrics.
