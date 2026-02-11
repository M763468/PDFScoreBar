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
