# Issue 120 Stage D Provenance Checklist

## Purpose

This checklist records the #147 decision to verify historical generation provenance before proposing filter or algorithm changes.

The filter-ablation result is useful as a diagnostic, but it is not a repair proposal. Before changing `filter_probe_candidates`, confirm the generation period, the scripts present around that period, and whether the current reproduction script is actually the historical producer.

## Known facts

The historical Issue #120 Stage-D dense candidate root:

```text
logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
```

is byte-identical, for the 68 canonical candidate files checked, to:

```text
logs/issue36_prep/probe_candidates_filtered_v12
```

Observed:

```text
left_files=68
missing=0
mismatch=0
```

Therefore the immediate provenance target is the producer of:

```text
logs/issue36_prep/probe_candidates_filtered_v12
```

not a replacement filter rule.

## GitHub-side historical anchors

Known repository-history anchors:

```text
2026-02-08 d2072eb04c40b509f910fa58698f419fb74b67d8
  chore(verification): group issue36 gt-prep scripts and document workflow

2026-02-11 82b26d990b8d0ffb64a78747f135bb37905bf90b
  chore(gt): generalize preparation tools and formalize design principles
```

The 2026-02-08 commit introduced or grouped the Issue #36 GT-prep workflow, including:

```text
tools/verification/issue36_gt_prep/generate_probe_candidates_from_inventory.py
tools/verification/issue36_gt_prep/apply_candidate_filter_from_inventory.py
tools/verification/issue36_gt_prep/suggest_candidate_drops.py
tools/verification/issue36_gt_prep/render_candidate_filter_overlay.py
```

The documented canonical run in that commit points to `probe_candidates_filtered_v4`, not v12. This means v12 was likely produced by later local iterations or later untracked/local-log runs, and local file metadata matters.

The local mtime-window git log contains these relevant later anchors:

```text
edf7bf6 GT seeds: switch probe generation default to row_stats (v9)
d54382e GT seeds: adopt v13 workflow and document manual-finish policy
ce9595f gt_relabel_gui: resume from output_raw and add reset-to-initial
```

## Local provenance findings

### Candidate-root mtimes

Local file mtimes show that both roots were materialized over the same narrow window:

```text
logs/issue36_prep/probe_candidates_filtered_v12
  files=68
  min_mtime=2026-02-12T01:43:38
  max_mtime=2026-02-12T01:44:03

logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
  files=68
  min_mtime=2026-02-12T01:43:38
  max_mtime=2026-02-12T01:44:03
```

This makes a direct copy/sync from the Issue #36 v12 filtered root into the Issue #44 scoring input root more likely than independent generation.

### Metadata mtimes

The v12 metadata aligns with the candidate-root mtime window:

```text
2026-02-12 01:43:30 logs/issue36_prep/20260211_probe_generation_summary_v12.json
2026-02-12 01:43:38..01:44:03 logs/issue36_prep/filter_suggestions_v12/**
2026-02-12 01:44:03 logs/issue36_prep/20260211_filter_apply_summary_v12.json
2026-02-12 01:44:32 logs/issue36_prep/20260211_v10b_v11_v12_comparison.md
```

This confirms that v12 was part of an iterative local Issue #36 seed-preparation sequence, not the initial 2026-02-08 v4 run.

### Historical v12 generation config

The local v12 probe-generation summary identifies the historical raw root and generation settings:

```text
output_root=/workspace/logs/issue36_prep/probe_candidates_from_bench_v12
processed=68
skipped=0
errors=0
```

Historical v12 probe-generation config:

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

The v12 final-filter summary identifies:

```text
candidates_root=/workspace/logs/issue36_prep/probe_candidates_from_bench_v12
output_root=/workspace/logs/issue36_prep/probe_candidates_filtered_v12
suggestions_root=/workspace/logs/issue36_prep/filter_suggestions_v12
processed=68
skipped=0
errors=0
```

Historical v12 filter rules:

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

Historical v12 filter reason counts are small and do not include `low_paper_overlap`:

```text
clef_mask_overlap=4665
left_margin_zone=3520
no_staff_overlap=781
```

This is the key provenance result: the current Stage-C reproduction helper uses similar final-filter rules, but it is not feeding the historical raw root. The current helper's raw probe candidates collapse under `low_paper_overlap`; the historical raw root did not.

### v10b/v11/v12 comparison

The local comparison note records why v12 is a stricter local iteration:

```text
v10b: overall 35867/43053 (0.833) | fp 6848/8268 (0.828) | miss 16398/19519 (0.840)
v11:  overall 27308/33367 (0.818) | fp 5418/6617 (0.819) | miss 12455/15145 (0.822)
v12:  overall 22565/27758 (0.813) | fp 4499/5494 (0.819) | miss 10455/12758 (0.819)
```

v12 intentionally reduced candidate volume relative to v10b/v11 while preserving similar ratios in the local review metrics.

### Current checkout grep

The current checkout still contains references to the v12 root in Issue #44 CNN configs and docs:

```text
configs/cnn_barline_runs/issue44_baseline_v1/dataset_build.yaml
configs/cnn_barline_runs/issue44_baseline_v1/score_candidates_batch_splitwide_v1.yaml
configs/cnn_barline_runs/issue44_baseline_v1/score_candidates_batch_splitwide_recenter_v1.yaml
configs/cnn_barline_runs/issue44_baseline_v1/score_candidates_batch_splitwide_recenter_merge_v1.yaml
tools/cnn_classifier/README_issue44_retrain_eval2.md
```

This supports the interpretation that the v12 Issue #36 filtered root was later consumed by the Issue #44 CNN scoring/training workflow.

## Updated interpretation

The exact Stage-D historical root is now best described as:

```text
Issue #36 iterative local GT-seed workflow
  -> probe_candidates_from_bench_v12
     generated with band_source=row_stats, ink_threshold=240,
     max_per_band=80, probe_width=4
  -> probe_candidates_filtered_v12
     filtered with min_height_median_ratio=0.6,
     min_paper_overlap_ratio=0.6, min_staff_overlap_ratio=0.02,
     min_ink_ratio=0.18
  -> copied/synced into issue44_baseline_v1/scoring_input_eval2_v12
  -> consumed by Issue #44 CNN scoring/training configs
  -> later used as Issue #53/#57 probe-rescue bands_from
```

The current `tools/repro_accuracy/reproduce_clean_seed_v12.py` should not be treated as the historical producer. It may be a later reconstruction helper that encodes some v12 assumptions, but the local evidence points to the Issue #36 GT-preparation scripts, `probe_candidates_from_bench_v12`, and the v12 summary/suggestion files as the primary provenance source.

## Local provenance commands

Run these locally and keep outputs under ignored `logs/` paths.

### 1. File modification-time inventory

```bash
mkdir -p logs/issue120_e2e_recovery/stage_d_provenance

python3 - <<'PY' | tee logs/issue120_e2e_recovery/stage_d_provenance/issue36_v12_file_mtimes.txt
from pathlib import Path
from datetime import datetime
import os

roots = [
    Path('logs/issue36_prep/probe_candidates_filtered_v12'),
    Path('logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12'),
]
for root in roots:
    print(f'ROOT {root}')
    files = sorted(root.rglob('pipeline2_no_peak_candidates.json'))
    print(f'files={len(files)}')
    mtimes = []
    for path in files:
        st = path.stat()
        mtimes.append(st.st_mtime)
        print(datetime.fromtimestamp(st.st_mtime).isoformat(timespec='seconds'), path)
    if mtimes:
        print('min_mtime', datetime.fromtimestamp(min(mtimes)).isoformat(timespec='seconds'))
        print('max_mtime', datetime.fromtimestamp(max(mtimes)).isoformat(timespec='seconds'))
    print()
PY
```

### 2. Issue #36 metadata-time inventory

```bash
find logs/issue36_prep -maxdepth 3 -type f \
  \( -name '*summary*' -o -name '*config*' -o -name '*.json' -o -name '*.yaml' -o -name '*.txt' -o -name '*.md' \) \
  -printf '%TY-%Tm-%Td %TH:%TM:%TS %p\n' \
  | sort \
  | tee logs/issue120_e2e_recovery/stage_d_provenance/issue36_metadata_mtimes.txt
```

### 3. Nearby git history

After reading the min/max mtimes, inspect commits around that window. For the known Issue #36 dates:

```bash
git log --all --date=iso --since='2026-02-07' --until='2026-02-12' --oneline --decorate -- \
  tools/verification docs src tools configs \
  | tee logs/issue120_e2e_recovery/stage_d_provenance/git_log_20260207_20260212.txt
```

If mtimes point later, adjust the window. For example:

```bash
git log --all --date=iso --since='2026-02-10' --until='2026-02-20' --oneline --decorate -- \
  tools/verification docs src tools configs \
  | tee logs/issue120_e2e_recovery/stage_d_provenance/git_log_mtime_window.txt
```

### 4. Historical grep at current checkout

```bash
grep -R "probe_candidates_filtered_v12\|filter_suggestions_v12\|20260211_filter_apply_summary_v12\|min_paper_overlap_ratio\|low_paper_overlap" -n \
  docs tools configs experiments src .github \
  2>/dev/null \
  | tee logs/issue120_e2e_recovery/stage_d_provenance/current_checkout_provenance_grep.txt
```

### 5. Historical grep across git commits

This can be slow. Run only if needed:

```bash
git rev-list --all | while read sha; do
  git grep -n "probe_candidates_filtered_v12\|filter_suggestions_v12\|20260211_filter_apply_summary_v12" "$sha" -- \
    docs tools configs experiments src .github 2>/dev/null \
    | sed "s/^/$sha:/"
done | tee logs/issue120_e2e_recovery/stage_d_provenance/git_all_refs_v12_grep.txt
```

## Next required local inspection

Because the historical raw candidate root is explicitly identified, compare it directly against the current Stage-C reproduction raw root.

### 1. Confirm historical raw root exists

```bash
test -d logs/issue36_prep/probe_candidates_from_bench_v12 && echo exists || echo missing
```

### 2. Summarize historical raw -> filtered counts

```bash
PYTHONPATH=. python3 tools/issue120/summarize_stage_c_seed_regen_outputs.py \
  --historical-root logs/issue36_prep/probe_candidates_filtered_v12 \
  --regen-root logs/issue36_prep \
  --output-dir logs/issue120_e2e_recovery/stage_d_provenance/issue36_v12_raw_filtered_summary
```

Note: `summarize_stage_c_seed_regen_outputs.py` expects a current helper layout for raw files, so this command may not resolve raw files unless adapted. If it does not, use direct counts:

```bash
python3 - <<'PY' | tee logs/issue120_e2e_recovery/stage_d_provenance/issue36_v12_raw_filtered_counts.txt
import json
from pathlib import Path

roots = {
    'historical_raw': Path('logs/issue36_prep/probe_candidates_from_bench_v12'),
    'historical_filtered': Path('logs/issue36_prep/probe_candidates_filtered_v12'),
    'current_repro_raw': Path('logs/issue120_e2e_recovery/stage_d_issue36_repro'),
    'current_repro_filtered': Path('logs/issue120_e2e_recovery/stage_d_issue36_repro/probe_candidates_filtered_v12'),
}

def count_file(path):
    data = json.loads(path.read_text())
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        for key in ('candidates', 'items', 'bars', 'barlines', 'predictions'):
            if isinstance(data.get(key), list):
                return len(data[key])
    return 0

for label, root in roots.items():
    total = 0
    files = list(root.rglob('pipeline2_no_peak_candidates.json'))
    for path in files:
        total += count_file(path)
    print(label, 'files=', len(files), 'total=', total)
PY
```

### 3. Inspect historical producer scripts around v12

Focus on these commands/scripts rather than `reproduce_clean_seed_v12.py` first:

```text
tools/verification/gt_preparation/generate_probe_candidates_from_inventory.py
tools/verification/gt_preparation/apply_candidate_filter_from_inventory.py
```

The reconstruction question is now:

```text
Can the Issue #36 GT-prep generator reproduce:
  logs/issue36_prep/probe_candidates_from_bench_v12
using:
  20260208_bench_inventory.json
  band_source=row_stats
  ink_threshold=240
  max_per_band=80
  probe_width=4
  min_ratio=0.6
  band_scan_line_ratio=0.6
  band_scan_min_lines=5
  min_height_ratio=0.006
  min_width_ratio=0.0

and then can the Issue #36 filter reproduce:
  logs/issue36_prep/probe_candidates_filtered_v12
using the v12 filter rules?
```

## Interpretation

### If historical raw root exists and matches v12 summary totals

The Stage-D recovery path should use the Issue #36 GT-prep scripts and v12 summary config, not `reproduce_clean_seed_v12.py`.

### If historical raw root differs from current reproduction raw root

The current Stage-C helper is not reconstructing the correct raw candidate family. The `low_paper_overlap` collapse is downstream evidence of wrong raw candidates, not necessarily a filter bug.

### If historical raw root is missing

The raw provenance boundary remains. The filtered root is present and byte-identical to the scoring input, but full producer reproduction requires recovering `probe_candidates_from_bench_v12` or its generator behavior.

### If historical raw root can be regenerated but filtered root cannot

Then investigate `apply_candidate_filter_from_inventory.py` or current `filter_probe_candidates` drift.

### If both raw and filtered roots regenerate

Stage-D dense candidate-root recovery is solved and #147 can close with a corrected reconstruction path.
