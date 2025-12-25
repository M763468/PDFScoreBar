# GT Relabel Support Script (Phase 6)

This script assists human GT cleanup for detector-miss near-hits.
It **does not** auto-relabel and never overwrites original GT files.

## What it does
- Generates enlarged crops with overlays (GT + nearby detections).
- Creates JSON templates for manual edits (numbers only, no GUI required).
- Applies edits to produce **new** corrected GT files.
- Produces a diff summary and a near-hit recheck report.

## What it does NOT do
- No detector reruns.
- No automatic GT changes.
- No changes to original GT files.

## Usage (recommended venv)
Use a venv that has Pillow installed (e.g., `.venv_omr_dln`).

### 1) Prepare crops + edit templates
```bash
. .venv_omr_dln/bin/activate
python3 tools/gt_relabel_support.py prepare \
  --candidates logs/phase6_detector_miss/gt_fix_plan/gt_fix_candidates.csv
```
Optional smoke test limit:
```bash
python3 tools/gt_relabel_support.py prepare \
  --candidates logs/phase6_detector_miss/gt_fix_plan/gt_fix_candidates.csv \
  --limit 2
```
Outputs under `logs/phase6_detector_miss/gt_fix_review/<page>/fn_<gt_index>/`:
- `crop_x4.png`
- `edit_template.json`

### 2) Edit JSON templates (manual)
Open each `edit_template.json` and adjust one of:
- `status`: `unchanged` / `edited` / `invalid`
- `edited_bbox`: edited bbox in **scaled crop coordinates**
- or `delta`: dx/dy/dtop/dbottom in **scaled pixels**

Notes:
- If `status` is `edited`, `edited_bbox` takes priority.
- `delta` is applied to the scaled bbox if `edited_bbox` is not set.
- For `invalid`, the script sets `invalid_gt=true` in the corrected GT.
- Mapping back uses `round(value / scale + crop_offset)` to avoid systematic bias.

### 3) Apply edits (write corrected GT)
```bash
. .venv_omr_dln/bin/activate
python3 tools/gt_relabel_support.py apply \
  --candidates logs/phase6_detector_miss/gt_fix_plan/gt_fix_candidates.csv
```
Outputs:
- `logs/phase6_detector_miss/gt_fix_review/gt_corrected/<page>/fn_only_corrected.json`
- `logs/phase6_detector_miss/gt_fix_review/gt_corrected/diff_summary.csv`

### 4) Re-run near-hit check (corrected GT)
```bash
. .venv_omr_dln/bin/activate
python3 tools/gt_relabel_support.py near-hit \
  --candidates logs/phase6_detector_miss/gt_fix_plan/gt_fix_candidates.csv
```
Outputs:
- `logs/phase6_detector_miss/gt_fix_review/near_hit_recheck/near_hit_recheck.csv`
- `logs/phase6_detector_miss/gt_fix_review/near_hit_recheck/near_hit_recheck_summary.json`

## GUI editor (mouse drag/resize)
Run the browser-based editor to modify `edit_template.json` via drag/resize:

```bash
python3 tools/gt_relabel_gui/server.py \
  --root logs/phase6_detector_miss/gt_fix_review \
  --port 8010 \
  --host 0.0.0.0
```

Open in a browser (WSL): `http://127.0.0.1:8010` (or `http://<wsl-ip>:8010` from Windows).
Edits are saved back into each `edit_template.json` with updated `status` and `edited_bbox`.

### Display scale + Debug mode
- Use the **Display scale** dropdown (0.25/0.5/1.0) to control on-screen size. This does **not** change coordinates saved to JSON.
- Enable **Debug** to see mouse coords (display + raw x4) and bbox coords, plus hit-test logs.
- Debug checklist: click bbox -> log shows “inside bbox”; click handle -> log shows “handle N”; drag updates bbox numbers.

## Optional: custom page config
If you need custom GT/image/detection paths, pass `--page-config` with a JSON file:
```json
{
  "page_10": {
    "gt": ".../fn_only.json",
    "image": ".../page_10.png",
    "baseline": ".../detections.json",
    "sr": ".../detections.json",
    "omr": ".../predictions.json"
  }
}
```
