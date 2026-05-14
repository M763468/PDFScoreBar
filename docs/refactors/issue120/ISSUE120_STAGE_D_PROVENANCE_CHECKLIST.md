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

## Interpretation

### If v12 mtimes cluster near 2026-02-11

Focus on the Issue #36 GT-prep scripts from the 2026-02-08 / 2026-02-11 window. Compare historical `apply_candidate_filter_from_inventory.py` and `suggest_candidate_drops.py` behavior to current `filter_probe_candidates` behavior.

### If v12 mtimes are later than 2026-02-11

Search for later local-only iterations and metadata. The repository may contain the generic producer but not the exact v12 invocation.

### If metadata summaries include v12 rules

Prefer those historical rules over ablation-derived guesses.

### If no exact producer is recoverable

Document this as a provenance boundary. The ablation result can then inform a separate repair issue, but should not be treated as historical reconstruction.
