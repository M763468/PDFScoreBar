# Next Session Notes

**Last Updated**: 2026-01-16
**Current Phase**: Full pipeline workflow planning (image input -> measure numbering)

---
## Goal
Define the end-to-end pipeline from image input to measure-numbered output, including
user correction points for barlines and multi-measure rest (MMR) counts. This is a
planning-only phase; feature implementation will happen in child branches.

## Scope
- Input: single-page or multi-page score images.
- Output: measure-numbered JSON + optional overlays.
- User correction: barline edits and MMR count edits.

## Assumptions
- Barline detection is based on existing hybrid/homr tooling.
- Staff masks are available via homr or hybrid logs.
- MMR detection uses CNN + OCR (current `tools/generate_numbering_overrides.py`).
- Measure numbering uses `tools/add_measure_numbers.py`.

## Inputs
- Page images: `data/.../page_XXX.png`
- Barlines JSON (detector output or GT): `logs/.../boxes_sorted_*.json`
- Staff mask: `logs/.../page_XXX_debug_3_staff.png`
- (Optional) Notehead mask: `logs/.../page_XXX_debug_6_notehead.png`
- (Optional) User corrections:
  - Barline corrections file (planned)
  - MMR overrides JSON (existing)

## Outputs
- Numbered measures JSON: `.../numbering_final.json`
- Optional overlay image: `.../numbering_overlay.png`
- Intermediate artifacts:
  - Detected barlines JSON
  - MMR overrides JSON
  - Debug overlays for QA

---
## Current Output Formats (Observed)

### Barlines JSON (Input to numbering)
Accepted formats (normalized by `tools/add_measure_numbers.py`):
1. List of bbox arrays:
   ```json
   [[x1, y1, x2, y2], ...]
   ```
2. List of dicts with `barline_location`:
   ```json
   [{"barline_location": [x1, y1, x2, y2]}, ...]
   ```
3. List of dicts with flat coords:
   ```json
   [{"x1": 10, "y1": 20, "x2": 12, "y2": 300}, ...]
   ```

### Staff/Notehead Masks
- Staff mask PNG: `page_XXX_debug_3_staff.png` (binary-ish mask, homr output).
- Notehead mask PNG: `page_XXX_debug_6_notehead.png` (optional; used in older heuristics/debug).

### Numbering JSON (`tools/add_measure_numbers.py --output-json`)
```json
{
  "pages": [
    {
      "page_number": 1,
      "width": 2700,
      "height": 3600,
      "systems": [
        {
          "staves": [{"bbox": [x1, y1, x2, y2]}, ...],
          "measures": [
            {"number": 1, "bbox": [x1, y1, x2, y2]},
            ...
          ]
        }
      ]
    }
  ]
}
```

### MMR Overrides JSON (`tools/generate_numbering_overrides.py --output-overrides`)
```json
{
  "measure_overrides": [
    {"page": 0, "system": 0, "measure": 5, "skip": 3, "comment": "CNN(0.92)+OCR(84.0): 4"},
    ...
  ]
}
```

### Debug Overlays
- Numbering overlay PNG from `tools/add_measure_numbers.py --output-overlay`.
- OCR debug overlay PNG from `tools/generate_numbering_overrides.py --debug-image` (optional).

### Common Output Paths (Convention)
- Numbering: `logs/.../numbering_initial.json`, `logs/.../numbering_final.json`
- Overrides: `logs/.../overrides.json`
- Overlays: `logs/.../overlay.png` or `.../debug_overlay.png`

## Pipeline Steps

### Step 1: Ingest + Normalize
- Collect images and expected page list.
- (Optional) Normalize resolution or cache scale factors.

### Step 2: Barline Detection
- Run hybrid/homr detection to produce barline candidates.
- Expected artifacts:
  - `logs/<run_id>/per_page/page_XXX/boxes_sorted_*.json`
  - Staff mask in same run or known mask root.
- Script entry points:
  - `tools/run_hybrid_pipeline.sh` (legacy)
  - `tools/run_eval_experiment.py` (CNN training track)

### Step 3: User Correction (Barlines)
- User edits barlines to remove false positives or add missing ones.
- Planned mechanism:
  - A correction JSON file that can add/remove barlines by bbox and metadata.
  - Example shape (draft):
    ```json
    {
      "barline_overrides": [
        {"page": 0, "op": "remove", "bbox": [x1, y1, x2, y2]},
        {"page": 0, "op": "add", "bbox": [x1, y1, x2, y2]}
      ]
    }
    ```
- Implementation: in a child branch (not in this plan branch).

### Step 4: Measure Numbering (Core)
- Use `tools/add_measure_numbers.py` with:
  - barlines JSON (after corrections)
  - staff mask
  - image
  - optional `--config` for overrides (anacrusis, skip).
- Output: `numbering_base.json` (before MMR overrides).

### Step 5: MMR Detection (CNN + OCR)
- Use `tools/generate_numbering_overrides.py` to produce `overrides.json`.
- Inputs: `numbering_base.json`, image, model path.
- Apply in `tools/add_measure_numbers.py` to produce `numbering_final.json`.

### Step 6: User Correction (MMR Counts)
- User edits `overrides.json` for misread counts.
- Existing format:
  ```json
  {
    "measure_overrides": [
      {"page": 0, "system": 0, "measure": 5, "skip": 3, "comment": "MMR count 4"}
    ]
  }
  ```
- Apply via `--config` to regenerate final numbering.

### Step 7: Export + QA
- Produce final overlay for user validation.
- Store artifacts under a run directory for reproducibility.

## User Intervention Points (Planned)
1. Barlines: edit candidate list (add/remove).
2. MMR counts: fix OCR mistakes or supply missing counts.
3. Optional: anacrusis or movement reset via overrides.

## Artifact Layout (Proposed)
```
logs/pipeline_runs/<run_id>/
  inputs/
    images/
    barlines_raw.json
    staff_mask.png
  corrected/
    barlines_corrected.json
    overrides_user.json
  intermediate/
    numbering_base.json
    overrides_mmr.json
  outputs/
    numbering_final.json
    numbering_overlay.png
```

## Open Questions
- Barlines correction UI: extend existing GT GUI or provide a lightweight editor?
- Multi-page numbering state: how to handle movement boundaries?
- Default selection of staff masks across runs.

## Next Actions (This Branch)
- Document the data contracts for barline corrections and MMR overrides.
- Identify the minimal set of scripts to stitch into a single CLI entry point.
- Enumerate user touchpoints and UX expectations for corrections.

---
## Data Contracts (Draft)

### Barline Corrections (Planned)
**Purpose**: Allow user add/remove operations on detected barlines before numbering.

**File**: `barline_overrides.json`
```json
{
  "version": 1,
  "source": "manual",
  "barline_overrides": [
    {"page": 0, "op": "remove", "bbox": [x1, y1, x2, y2], "comment": "false positive"},
    {"page": 0, "op": "add", "bbox": [x1, y1, x2, y2], "comment": "missed barline"}
  ]
}
```

**Rules**:
- `bbox` is in original image coordinates (same space as barlines JSON).
- `page` is 0-based index in the input page list.
- `op` supports `add` or `remove`.
- `remove` matches by IoU threshold against detected barlines (e.g., IoU > 0.6).
- `add` inserts a new barline candidate with default metadata.

### Measure Overrides (Existing)
**Purpose**: Adjust numbering for anacrusis or MMR counts.

**File**: `overrides.json`
```json
{
  "measure_overrides": [
    {"page": 0, "system": 0, "measure": 0, "set_number": 0, "comment": "anacrusis"},
    {"page": 0, "system": 1, "measure": 5, "skip": 3, "comment": "MMR count 4"}
  ]
}
```

**Rules**:
- `page/system/measure` are 0-based indices in `numbering_base.json`.
- `skip` means advance measure count by `skip + 1` (MMR count = skip+1).
- `set_number` overrides the displayed measure number only for the target measure.

---
## CLI Design (Draft)

### Single Entry Point (Planned)
`tools/run_full_pipeline.py` (new)

**Inputs**:
- `--images`: list or glob of page images
- `--barlines`: detector output JSON (per-page or combined)
- `--staff-mask-root`: root directory for staff masks
- `--overrides`: path to measure overrides JSON (optional)
- `--barline-overrides`: path to barline corrections JSON (optional)
- `--output-dir`: run directory

**Outputs**:
- `outputs/numbering_base.json`
- `outputs/numbering_final.json`
- `outputs/numbering_overlay.png` (optional)
- `intermediate/overrides_mmr.json`
- `intermediate/barlines_corrected.json`

**Behavior**:
1. Apply `barline_overrides.json` to barline detections.
2. Run `tools/add_measure_numbers.py` to produce `numbering_base.json`.
3. Run `tools/generate_numbering_overrides.py` to produce MMR overrides.
4. Apply `overrides.json` (user + MMR) to produce final numbering.
5. Write overlays if requested.

### Compatibility
- Continue to support direct use of existing scripts for ad-hoc runs.
- The entry point should be a thin wrapper, not a rewrite.
