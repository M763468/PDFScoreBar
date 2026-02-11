# GT Preparation Scripts

Purpose: Standard scripts for Ground Truth (GT) preparation and candidate filtering.

## Why this directory exists
- Centralize verification and pre-processing scripts for GT creation.
- Originally developed during Issue #36, these tools are now part of the standard workflow for rebuilding or expanding evaluation datasets.
- Ensure resolution independence and consistent filtering rules across scores.

## Scripts
- `generate_probe_candidates_from_inventory.py`
  - Rebuilds probe-scan candidates from bench inventory records.
- `suggest_candidate_drops.py`
  - Generates drop suggestions based on heuristics (left margin, staff overlap, short segments, low ink).
- `apply_candidate_filter_from_inventory.py`
  - Applies filtering suggestions to all pages listed in inventory and writes filtered candidate JSONs.
- `render_candidate_filter_overlay.py`
  - Creates visual overlays: gray=all, green=keep, red=drop.

## Canonical inputs/outputs for current run (v5)
- Inventory: `logs/issue36_prep/20260208_bench_inventory.json`
- Exclusions: `logs/issue36_prep/excluded_pages_for_gt_prep.json`
- Raw candidates root: `logs/issue36_prep/probe_candidates_from_bench_v5`
- Filtered candidates root: `logs/issue36_prep/probe_candidates_filtered_v5`
- Suggestions root: `logs/issue36_prep/filter_suggestions_v5`
- Generate summary: `logs/issue36_prep/20260211_probe_generation_summary_v5.json`
- Filter summary: `logs/issue36_prep/20260211_filter_apply_summary_v5.json`

Legacy reference:
- v4 filtered root: `logs/issue36_prep/probe_candidates_filtered_v4`
- v4 summary: `logs/issue36_prep/20260208_filter_apply_summary_v4.json`

## Reproduction (sr_eval_gpu, v5)
Run in this order (`generate` -> `apply`):
```bash
docker exec sr_eval_gpu /opt/venv_sr/bin/python /workspace/tools/verification/gt_preparation/generate_probe_candidates_from_inventory.py \
  --inventory /workspace/logs/issue36_prep/20260208_bench_inventory.json \
  --exclude /workspace/logs/issue36_prep/excluded_pages_for_gt_prep.json \
  --output-root /workspace/logs/issue36_prep/probe_candidates_from_bench_v5 \
  --summary-out /workspace/logs/issue36_prep/20260211_probe_generation_summary_v5.json \
  --ink-threshold 230 \
  --min-ratio 0.60 \
  --min-height-ratio 0.008 \
  --min-width-ratio 0.0

docker exec sr_eval_gpu /opt/venv_sr/bin/python /workspace/tools/verification/gt_preparation/apply_candidate_filter_from_inventory.py \
  --inventory /workspace/logs/issue36_prep/20260208_bench_inventory.json \
  --exclude /workspace/logs/issue36_prep/excluded_pages_for_gt_prep.json \
  --candidates-root /workspace/logs/issue36_prep/probe_candidates_from_bench_v5 \
  --output-root /workspace/logs/issue36_prep/probe_candidates_filtered_v5 \
  --suggestions-root /workspace/logs/issue36_prep/filter_suggestions_v5 \
  --summary-out /workspace/logs/issue36_prep/20260211_filter_apply_summary_v5.json \
  --left-margin-ratio 0.12 \
  --clef-left-ratio 0.25 \
  --min-height-median-ratio 0.6 \
  --ink-threshold 180 \
  --min-ink-ratio 0.18 \
  --paper-threshold 200 \
  --min-paper-overlap-ratio 0.6 \
  --min-staff-overlap-ratio 0.01
```

## Reproduction (sr_eval_gpu, v6: increased candidate recall)
Run in this order (`generate` -> `apply`):
```bash
docker exec sr_eval_gpu /opt/venv_sr/bin/python /workspace/tools/verification/gt_preparation/generate_probe_candidates_from_inventory.py \
  --inventory /workspace/logs/issue36_prep/20260208_bench_inventory.json \
  --exclude /workspace/logs/issue36_prep/excluded_pages_for_gt_prep.json \
  --output-root /workspace/logs/issue36_prep/probe_candidates_from_bench_v6 \
  --summary-out /workspace/logs/issue36_prep/20260211_probe_generation_summary_v6.json \
  --ink-threshold 230 \
  --min-ratio 0.55 \
  --min-height-ratio 0.006 \
  --min-width-ratio 0.0

docker exec sr_eval_gpu /opt/venv_sr/bin/python /workspace/tools/verification/gt_preparation/apply_candidate_filter_from_inventory.py \
  --inventory /workspace/logs/issue36_prep/20260208_bench_inventory.json \
  --exclude /workspace/logs/issue36_prep/excluded_pages_for_gt_prep.json \
  --candidates-root /workspace/logs/issue36_prep/probe_candidates_from_bench_v6 \
  --output-root /workspace/logs/issue36_prep/probe_candidates_filtered_v6 \
  --suggestions-root /workspace/logs/issue36_prep/filter_suggestions_v6 \
  --summary-out /workspace/logs/issue36_prep/20260211_filter_apply_summary_v6.json \
  --left-margin-ratio 0.12 \
  --clef-left-ratio 0.25 \
  --min-height-median-ratio 0.6 \
  --ink-threshold 180 \
  --min-ink-ratio 0.18 \
  --paper-threshold 200 \
  --min-paper-overlap-ratio 0.6 \
  --min-staff-overlap-ratio 0.01
```

To split likely merged double/end/repeat-like wide bars in provisional seeds:
```bash
docker exec sr_eval_gpu /opt/venv_sr/bin/python /workspace/tools/split_double_barlines.py \
  --json-root /workspace/data/evaluation2/annotations \
  --image-root /workspace/data/evaluation2/images \
  --output-vis /workspace/logs/issue36_prep/doublebar_split_preview_v6 \
  --file-pattern boxes_provisional.json \
  --min-split-width 12 \
  --apply
```

## Reproduction (sr_eval_gpu, v7: probe-only aggressive expansion)
This variant keeps the same filter settings and only loosens probe candidate generation.
```bash
docker exec sr_eval_gpu /opt/venv_sr/bin/python /workspace/tools/verification/gt_preparation/generate_probe_candidates_from_inventory.py \
  --inventory /workspace/logs/issue36_prep/20260208_bench_inventory.json \
  --exclude /workspace/logs/issue36_prep/excluded_pages_for_gt_prep.json \
  --output-root /workspace/logs/issue36_prep/probe_candidates_from_bench_v7 \
  --summary-out /workspace/logs/issue36_prep/20260211_probe_generation_summary_v7.json \
  --ink-threshold 240 \
  --min-ratio 0.50 \
  --min-height-ratio 0.004 \
  --min-width-ratio 0.0 \
  --probe-width 4 \
  --max-per-band 160 \
  --band-scan-line-ratio 0.6 \
  --band-scan-min-lines 5

docker exec sr_eval_gpu /opt/venv_sr/bin/python /workspace/tools/verification/gt_preparation/apply_candidate_filter_from_inventory.py \
  --inventory /workspace/logs/issue36_prep/20260208_bench_inventory.json \
  --exclude /workspace/logs/issue36_prep/excluded_pages_for_gt_prep.json \
  --candidates-root /workspace/logs/issue36_prep/probe_candidates_from_bench_v7 \
  --output-root /workspace/logs/issue36_prep/probe_candidates_filtered_v7 \
  --suggestions-root /workspace/logs/issue36_prep/filter_suggestions_v7 \
  --summary-out /workspace/logs/issue36_prep/20260211_filter_apply_summary_v7.json \
  --left-margin-ratio 0.12 \
  --clef-left-ratio 0.25 \
  --min-height-median-ratio 0.6 \
  --ink-threshold 180 \
  --min-ink-ratio 0.18 \
  --paper-threshold 200 \
  --min-paper-overlap-ratio 0.6 \
  --min-staff-overlap-ratio 0.01
```

## Reproduction (sr_eval_gpu, v8: thin-barline focused probe expansion)
This variant further relaxes probe generation for missed thin normal barlines.
```bash
docker exec sr_eval_gpu /opt/venv_sr/bin/python /workspace/tools/verification/gt_preparation/generate_probe_candidates_from_inventory.py \
  --inventory /workspace/logs/issue36_prep/20260208_bench_inventory.json \
  --exclude /workspace/logs/issue36_prep/excluded_pages_for_gt_prep.json \
  --output-root /workspace/logs/issue36_prep/probe_candidates_from_bench_v8 \
  --summary-out /workspace/logs/issue36_prep/20260211_probe_generation_summary_v8.json \
  --ink-threshold 240 \
  --min-ratio 0.45 \
  --min-height-ratio 0.003 \
  --min-width-ratio 0.0 \
  --probe-width 2 \
  --max-per-band 160 \
  --band-scan-line-ratio 0.6 \
  --band-scan-min-lines 3

docker exec sr_eval_gpu /opt/venv_sr/bin/python /workspace/tools/verification/gt_preparation/apply_candidate_filter_from_inventory.py \
  --inventory /workspace/logs/issue36_prep/20260208_bench_inventory.json \
  --exclude /workspace/logs/issue36_prep/excluded_pages_for_gt_prep.json \
  --candidates-root /workspace/logs/issue36_prep/probe_candidates_from_bench_v8 \
  --output-root /workspace/logs/issue36_prep/probe_candidates_filtered_v8 \
  --suggestions-root /workspace/logs/issue36_prep/filter_suggestions_v8 \
  --summary-out /workspace/logs/issue36_prep/20260211_filter_apply_summary_v8.json \
  --left-margin-ratio 0.12 \
  --clef-left-ratio 0.25 \
  --min-height-median-ratio 0.6 \
  --ink-threshold 180 \
  --min-ink-ratio 0.18 \
  --paper-threshold 200 \
  --min-paper-overlap-ratio 0.6 \
  --min-staff-overlap-ratio 0.01
```

## Reproduction (sr_eval_gpu, v9: row_stats bands for GT seed stability)
This variant keeps the v8 probe thresholds but switches `band_source` to `row_stats`
to use row bands estimated from existing hybrid boxes.
```bash
docker exec sr_eval_gpu /opt/venv_sr/bin/python /workspace/tools/verification/gt_preparation/generate_probe_candidates_from_inventory.py \
  --inventory /workspace/logs/issue36_prep/20260208_bench_inventory.json \
  --exclude /workspace/logs/issue36_prep/excluded_pages_for_gt_prep.json \
  --output-root /workspace/logs/issue36_prep/probe_candidates_from_bench_v9 \
  --summary-out /workspace/logs/issue36_prep/20260211_probe_generation_summary_v9.json \
  --band-source row_stats \
  --ink-threshold 240 \
  --min-ratio 0.45 \
  --min-height-ratio 0.003 \
  --min-width-ratio 0.0 \
  --probe-width 2 \
  --max-per-band 160 \
  --band-scan-line-ratio 0.6 \
  --band-scan-min-lines 3

docker exec sr_eval_gpu /opt/venv_sr/bin/python /workspace/tools/verification/gt_preparation/apply_candidate_filter_from_inventory.py \
  --inventory /workspace/logs/issue36_prep/20260208_bench_inventory.json \
  --exclude /workspace/logs/issue36_prep/excluded_pages_for_gt_prep.json \
  --candidates-root /workspace/logs/issue36_prep/probe_candidates_from_bench_v9 \
  --output-root /workspace/logs/issue36_prep/probe_candidates_filtered_v9 \
  --suggestions-root /workspace/logs/issue36_prep/filter_suggestions_v9 \
  --summary-out /workspace/logs/issue36_prep/20260211_filter_apply_summary_v9.json \
  --left-margin-ratio 0.12 \
  --clef-left-ratio 0.25 \
  --min-height-median-ratio 0.6 \
  --ink-threshold 180 \
  --min-ink-ratio 0.18 \
  --paper-threshold 200 \
  --min-paper-overlap-ratio 0.6 \
  --min-staff-overlap-ratio 0.01
```

Overlay generation (all covered pages):
```bash
docker exec sr_eval_gpu bash -lc 'cd /workspace && /opt/venv_sr/bin/python - <<"PY"
import json
import subprocess
from pathlib import Path

inv = json.loads(Path("logs/issue36_prep/20260208_bench_inventory.json").read_text())
excluded = json.loads(Path("logs/issue36_prep/excluded_pages_for_gt_prep.json").read_text())
excluded_set = {(e["score"], e["page"]) for e in excluded.get("excluded", [])}

for r in inv["records"]:
    score = r["score"]
    page = r["page"]
    if (score, page) in excluded_set:
        continue
    image = Path(r["image"])
    all_c = Path("logs/issue36_prep/probe_candidates_from_bench") / score / page / "pipeline2_no_peak_candidates.json"
    keep_c = Path("logs/issue36_prep/probe_candidates_filtered_v4") / score / page / "pipeline2_no_peak_candidates.json"
    out = Path("logs/issue36_prep/filter_overlays_v4") / score / page / "candidate_filter_overlay.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "/opt/venv_sr/bin/python",
        "tools/verification/gt_preparation/render_candidate_filter_overlay.py",
        "--image", str(image),
        "--all-candidates", str(all_c),
        "--keep-candidates", str(keep_c),
        "--output", str(out),
    ], check=True, cwd="/workspace", stdout=subprocess.DEVNULL)
PY'
```
