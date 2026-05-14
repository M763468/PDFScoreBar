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

The mismatching pages are the same in raw and filtered outputs. Sample:

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
```

Interpretation:

- The Issue #36 GT-prep path is the correct reconstruction family.
- It is much closer than the later Stage-C helper.
- The remaining drift starts in raw generation, not filtering, because the same 12 pages mismatch before and after filtering.
- Raw total is short by 313 candidates; filtered total is short by 230 candidates.
- The next boundary is input-file drift or `detect_probe_scan` implementation drift for those 12 pages.

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

Therefore the remaining 12-page drift is unlikely to be caused by this wrapper alone. Prioritize:

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

## Recommended next local check: isolate the 12-page drift

### 1. Per-page count and set differences

```bash
python3 - <<'PY' | tee logs/issue120_e2e_recovery/stage_d_provenance/v12_repro_page_diffs.txt
import json
from pathlib import Path

pairs = [
    ('raw', Path('logs/issue36_prep/probe_candidates_from_bench_v12'), Path('logs/issue120_e2e_recovery/stage_d_issue36_v12_repro/probe_candidates_from_bench_v12')),
    ('filtered', Path('logs/issue36_prep/probe_candidates_filtered_v12'), Path('logs/issue120_e2e_recovery/stage_d_issue36_v12_repro/probe_candidates_filtered_v12')),
]

def load_boxes(path):
    data = json.loads(path.read_text())
    if isinstance(data, list):
        return [tuple(x) for x in data]
    if isinstance(data, dict):
        for key in ('candidates', 'items', 'bars', 'barlines', 'predictions'):
            if isinstance(data.get(key), list):
                return [tuple(x) if isinstance(x, list) else tuple(x.get('bbox', x.get('pred_bbox'))) for x in data[key]]
    return []

for label, left_root, right_root in pairs:
    print(f'## {label}')
    for lf in sorted(left_root.rglob('pipeline2_no_peak_candidates.json')):
        rel = lf.relative_to(left_root)
        rf = right_root / rel
        if not rf.exists():
            print(rel, 'missing_right')
            continue
        left = load_boxes(lf)
        right = load_boxes(rf)
        left_set = set(left)
        right_set = set(right)
        if left_set != right_set:
            missing = sorted(left_set - right_set)[:5]
            extra = sorted(right_set - left_set)[:5]
            print(rel, 'left=', len(left), 'right=', len(right), 'missing_from_repro=', len(left_set - right_set), 'extra_in_repro=', len(right_set - left_set))
            if missing:
                print('  missing sample:', missing)
            if extra:
                print('  extra sample:', extra)
PY
```

### 2. Input-file mtimes and hashes for mismatching pages

```bash
python3 - <<'PY' | tee logs/issue120_e2e_recovery/stage_d_provenance/v12_mismatch_input_files.txt
import hashlib
import json
from datetime import datetime
from pathlib import Path

mismatch_pages = {
    ('Shostakovich-Festival_Overture_Va', 'page_001'),
    ('Shostakovich-Sym5-Va', 'page_004'),
    ('Shostakovich-Sym5-Va', 'page_005'),
    ('Shostakovich-Sym5-Va', 'page_008'),
    ('Shostakovich-Sym5-Va', 'page_012'),
    ('Shostakovich-Sym5-Va', 'page_013'),
    ('Sibelius-Violin_Concerto-Viola', 'page_004'),
    ('Va_Prokofiev_Symphony1', 'page_004'),
    ('Va__Prokofiev_Symphony5', 'page_002'),
    ('Va__Prokofiev_Symphony5', 'page_003'),
}

# The earlier mismatch sample was truncated at 10. Add remaining pages from v12_repro_page_diffs.txt if needed.
inv = json.loads(Path('logs/issue36_prep/20260208_bench_inventory.json').read_text())
records = inv.get('records', [])
for rec in records:
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
            candidates = sorted(p.rglob('*'))[:10]
            print('  sample_files', [str(x) for x in candidates])
        else:
            print('  missing')
PY
```

### 3. If input files look modified after 2026-02-12

Treat this as input drift. Recover the exact historical input files or document the boundary.

### 4. If input files look unchanged

Run the Issue #36 generation script with code from the historical commit window, or compare `detect_probe_scan` implementation between current and the 2026-02-11/12 commits.

## Routing decision

If input drift explains the 12 pages, Stage-D exact reconstruction depends on recovering the historical input files for those pages.

If `detect_probe_scan` drift explains the 12 pages, Stage-D exact reconstruction should pin or reintroduce the historical probe-detector behavior for the Issue #36 v12 producer.

If the 12-page drift is small and detector-level evaluation still matches the target after scoring, exact byte identity may not be required. Keep detector metrics separate from downstream measure-count metrics.
