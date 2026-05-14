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
  -> probe_candidates_filtered_v12
  -> copied/synced into issue44_baseline_v1/scoring_input_eval2_v12
  -> consumed by Issue #44 CNN scoring/training configs
  -> later used as Issue #53/#57 probe-rescue bands_from
```

The current `tools/repro_accuracy/reproduce_clean_seed_v12.py` is not yet proven to be the original producer. It may be a later reconstruction helper that encodes some v12 assumptions, but the local mtime evidence points to the Issue #36 GT-preparation scripts and local summary/suggestion files as the primary provenance source.

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

Because v12 summary and suggestion files are present at the exact generation time, inspect their contents before proposing code changes.

```bash
python3 - <<'PY' | tee logs/issue120_e2e_recovery/stage_d_provenance/v12_summary_rules.txt
import json
from pathlib import Path

paths = [
    Path('logs/issue36_prep/20260211_probe_generation_summary_v12.json'),
    Path('logs/issue36_prep/20260211_filter_apply_summary_v12.json'),
]
for path in paths:
    print(f'## {path}')
    obj = json.loads(path.read_text())
    for key in ('config', 'rules', 'processed', 'skipped', 'errors', 'reason_counts', 'output_root', 'candidates_root', 'suggestions_root'):
        if key in obj:
            print(key, json.dumps(obj[key], indent=2, sort_keys=True, ensure_ascii=False))
    print()
PY
```

Also inspect the comparison note:

```bash
sed -n '1,220p' logs/issue36_prep/20260211_v10b_v11_v12_comparison.md \
  | tee logs/issue120_e2e_recovery/stage_d_provenance/v10b_v11_v12_comparison_head.txt
```

## Interpretation

### If v12 summaries identify the exact rules

Use those rules as provenance facts. Do not infer rules from ablation.

### If v12 comparison identifies why v12 was selected

Record that as the Stage-D historical target rationale.

### If the summary rules match current code but output does not

The drift is likely in implementation behavior, image/staff-mask inputs, or candidate-generation source, not just CLI parameters.

### If the summary rules differ from current code

The current reproduction helper is not the historical producer profile. Stage-D recovery should route to a historical-profile runner rather than tune `filter_probe_candidates` ad hoc.

### If no exact producer is recoverable

Document this as a provenance boundary. The ablation result can then inform a separate repair issue, but should not be treated as historical reconstruction.
