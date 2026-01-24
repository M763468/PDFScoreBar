# Next Session Notes: Pipeline Optimization & Performance Tuning

<<<<<<< HEAD
**Last Updated**: 2026-01-16
**Current Phase**: Full pipeline workflow planning (image input -> measure numbering)

---
## Current Status (2026-01-17)
- A Phase 1 orchestrator exists but **does not yet include barline detection**; it assumes pre-existing
  hybrid outputs and is therefore **not sufficient** for the intended end-to-end pipeline.
- The next session must **rework the orchestrator** to run hybrid detection (candidate search → probe scan →
  CNN scoring) before numbering and MMR.
- Reference log for last changes: `docs/SESSION_LOG.md` (2026-01-17 entries).

### What Was Added (2026-01-17)
- `tools/run_full_pipeline.py`: config-driven orchestrator (PDF→images, barline overrides, numbering, MMR).
  - **Limitation**: expects pre-existing barlines/staff masks (no detection step).
  - Supports `--validate-only`, writes `manifest.json` and `filters.json`.
- `configs/full_pipeline_template.yaml`: config template with filters and barline overrides settings.
- `docs/FULL_PIPELINE_README.md`: usage + config summary.

### Immediate Pitfalls
- Do **not** reuse `logs/hybrid_generalization` outputs for the target full-pipeline run.
- Current orchestrator will fail the “end-to-end” requirement until hybrid detection is integrated.
- Toy Symphony PDF (`data/evaluation/pdfs/おもちゃの交響曲_bass.pdf`) has cover/blank pages; expect
  blank filtering and page mapping issues.

### First Files to Inspect
1. `tools/run_hybrid_pipeline.sh` (hybrid detection entry point)
2. `docs/DEVLOG_CNN_TRAINING.md` (CNN scoring flow + model path)
3. `tools/cnn_classifier/score_candidates_batch.py` (batch scoring)
4. `tools/run_full_pipeline.py` (current orchestrator to be reworked)

## Goal
Define the end-to-end pipeline from image input to measure-numbered output, including
user correction points for barlines and multi-measure rest (MMR) counts. This is a
planning-only phase; feature implementation will happen in child branches.

### Implementation Strategy
Phase 1 (now): Build a minimal, end-to-end orchestrator that reuses existing scripts to
produce final outputs in a single run (thin wrapper + stable run directory layout).
**Crucial Requirement**: This phase must demonstrate a working flow from CNN-based barline detection directly into measure numbering (counting) and MMR overrides. It is a "loose coupling" of existing standalone tools.

Phase 2 (later): Based on Phase 1 observations, refactor for bottleneck removal,
deduplication, optimization, and parallelization.
**Goal**: Consolidate into a single, efficient, optimized application. This phase begins only after the Phase 1 flow is verified to work correctly.
**Task**: Consolidate dispersed Python virtual environments (.venv_pdf, .venv_omr_dln, etc.) into a unified environment or a well-defined container strategy to eliminate runtime inconsistencies.

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
- What observed bottlenecks in Phase 1 should drive Phase 2 redesign (I/O, model load, OCR)?

## Next Actions (This Branch)
- Document the data contracts for barline corrections and MMR overrides.
- Identify the minimal set of scripts to stitch into a single CLI entry point (Phase 1).
- Enumerate user touchpoints and UX expectations for corrections.
- Add a Phase 2 note outlining intended optimization targets (parallelization, I/O, model reuse).

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
- `remove` matches by IoU threshold against detected barlines (default 0.5 per `BARLINE_MATCHER.md`).
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
## Config-Driven Orchestrator (Draft)

### Single Entry Point (Planned)
`tools/run_full_pipeline.py` (new) + YAML config

**Inputs (via config)**:
- `config.yaml` path (primary)
- optional CLI overrides for `run_id` and `output_root`

**Outputs**:
- `logs/full_pipeline_runs/<run_id>/outputs/numbering_base.json`
- `logs/full_pipeline_runs/<run_id>/outputs/numbering_final.json`
- `logs/full_pipeline_runs/<run_id>/outputs/numbering_overlay.png` (optional)
- `logs/full_pipeline_runs/<run_id>/intermediate/overrides_mmr.json`
- `logs/full_pipeline_runs/<run_id>/intermediate/barlines_corrected.json`

**Config Structure (Draft)**:
```yaml
run:
  run_id: "2026-01-16_demo_001"  # optional; auto if missing
  output_root: "logs/full_pipeline_runs"
inputs:
  pdf_path: "data/scores/demo/score.pdf"
  pdf_to_images:
    output_dir: "logs/preprocess/demo_pages"
    dpi: 300
    pages: null            # optional: "1,2,5" (1-based indices)
    target_width: null     # optional resize in pixels
    target_height: null    # optional resize in pixels
    interpolation: "area"  # nearest|linear|area|cubic|lanczos
    prefix: "page"
    format: "png"
    overwrite: false
    alpha: false
    image_glob: "page_*.png"
  barlines_root: "logs/hybrid_generalization"
  barlines_pattern: "{page_run}/pipeline2_no_peak_filtered_cnn.json"
  staff_mask_pattern: "{page_run}/baseline/{page_id}/{page_id}/{page_id}_debug_3_staff.png"
  page_runs: ["eval2_prokofiev1_page_001"]  # optional explicit list; defaults to inferred
  barline_overrides: "logs/overrides/barline_overrides.json"  # optional
  measure_overrides: "logs/overrides/overrides_user.json"     # optional
steps:
  pdf_to_images: true
  filter_pages: true
  apply_barline_overrides: true
  numbering_base: true
  mmr_overrides: true
  apply_measure_overrides: true
  overlay: false
filters:
  blank_page: "auto"    # planned: detect empty/near-empty pages
  staff_detect: "auto"  # planned: drop pages where homr fails to detect staff
  user_exclude: []      # optional: 1-based page indices to skip
mmr:
  model_path: "models/mmr_cnn.pt"
  ocr_lang: "eng"
numbering:
  config_path: null   # optional extra config for add_measure_numbers.py
```

**Behavior**:
1. Resolve `run_id` and create `logs/full_pipeline_runs/<run_id>/...`.
2. If `pdf_to_images` enabled, call `src/pdf_to_images.py` and record a page list.
3. If `filter_pages` enabled, drop blank or non-music pages (planned detection).
4. Apply `barline_overrides.json` to barline detections (if enabled).
5. Run `tools/add_measure_numbers.py` to produce `numbering_base.json`.
6. Run `tools/generate_numbering_overrides.py` to produce MMR overrides.
7. Apply `overrides_user.json` (user + MMR) to produce final numbering.
8. Write overlays if requested.

**Notes**:
- `src/pdf_to_images.py` is the canonical PDF renderer (see `docs/ENVIRONMENTS.md` for the
  `.venv_pdf` environment). Parameter names mirror the script options.
- Page filtering strategies (planned): near-empty page detection, homr staff detection failure,
  and explicit user exclusion list. Any of these can be used initially; refined later.
- For Phase 1, barlines/staff masks are resolved via `barlines_root` + pattern templates
  (`{page_run}`, `{page_id}` placeholders). Multi-page PDFs can list `page_runs` explicitly.
- `page_id` is derived from `pdf_to_images.prefix` and 1-based index (e.g., `page_001`),
  matching the hybrid output naming convention.

---
## Existing Hybrid Output Structure (Observed)

### Example Root (Per-Page Runs)
`logs/hybrid_generalization/eval2_prokofiev1_page_001/`

### Barline Candidates / CNN Filtering
- Pre-CNN candidates: `pipeline2_no_peak_candidates.json` (list of bboxes)
- CNN scores: `pipeline2_no_peak_scored.json` (list of `{bbox, score}`)
- Final barlines after CNN: `pipeline2_no_peak_filtered_cnn.json` (list of bboxes)
- Alternate baseline: `pipeline1_baseline_filtered.json` (list of bboxes)

### Staff Mask (Homr Output)
`baseline/page_001/page_001/page_001_debug_3_staff.png`

### Implication for Phase 1 Config
- Prefer `pipeline2_no_peak_filtered_cnn.json` as barlines source.
- Resolve barlines/staff masks via `barlines_root` + template patterns.
- For multi-page PDFs, either infer `page_runs` or specify them explicitly.

---
## Phase 1 Orchestrator Design (Draft)

### Core Responsibilities
- Read YAML config and resolve defaults.
- Generate images from PDF via `src/pdf_to_images.py` (if enabled).
- Run barline detection + staff mask generation via the hybrid pipeline.
- Build a page list (ordered `page_001`, `page_002`, ...).
- Resolve barline JSON + staff mask paths via `barlines_root` + patterns.
- Invoke existing scripts for numbering and MMR overrides.
- Write a `manifest.json` capturing inputs, resolved paths, and command lines.

### Resolution Rules (Draft)
1. **Page list**: derive from rendered images matching `image_glob` and sorted by page index.
2. **page_id**: `"{prefix}_{index:03d}"` where `index` is 1-based.
3. **barlines path**: `barlines_root / barlines_pattern.format(page_run=..., page_id=...)`
4. **staff mask path**: `barlines_root / staff_mask_pattern.format(page_run=..., page_id=...)`
5. **page_runs**:
   - Phase 1 uses explicit mapping for safety: config must provide `page_runs` ordered to
     match the `page_id` list.
   - Each `page_run` directory name should embed the corresponding `page_id` (e.g.,
     `eval2_prokofiev1_page_001` for `page_001`).
   - No auto-inference in Phase 1 to avoid accidental mismatches.

### Run Directory Layout (Phase 1)
`logs/full_pipeline_runs/<run_id>/`
- `inputs/`: symlink or copy of images, barlines jsons, staff masks
- `intermediate/`: corrected barlines, numbering_base, overrides_mmr
- `outputs/`: numbering_final, overlays
- `manifest.json`: config snapshot + resolved paths + commands
- `filters.json`: page filter status/metrics (blank/staff/user)

### Script Invocation (Draft)
- `src/pdf_to_images.py` with `pdf_to_images` args from config.
- `tools/run_hybrid_pipeline.sh` to generate hybrid candidates, probe scan output, CNN-scored barlines,
  and staff masks (uses the CNN model and hybrid probe configs from `docs/DEVLOG_CNN_TRAINING.md`).
- `tools/add_measure_numbers.py` for base numbering and final numbering.
- `tools/generate_numbering_overrides.py` for MMR overrides.

### README
- Usage and config summary: `docs/FULL_PIPELINE_README.md`

### Phase 2 Readiness Notes
- Replace file-based handoff with in-memory or shared cache where safe.
- Parallelize per-page barline resolution and MMR inference.
- Deduplicate staff mask generation across adjacent steps.

### Open Decisions (Track for Validation)
- **Page filtering inputs**: image-only vs. homr outputs (decide after prototyping).
- **Blank page handling**: keep directory entries but mark as blank in metadata.
- **Manifest content**: track alternatives (minimal vs. verbose) so we can compare for Phase 2.

---
## Immediate Replan (2026-01-17 Draft)

### Goal (Phase 1, Corrected)
Build a single pipeline that runs **from PDF input through barline detection, staff masks,
measure numbering, MMR overrides, and final numbering** without relying on pre-existing
hybrid outputs.

### Planned Sequence (Phase 1)
1. **PDF → images**: `src/pdf_to_images.py`.
2. **Barline detection** (hybrid):
   - Run `tools/run_hybrid_pipeline.sh` (hybrid candidate detection → probe scan expansion).
   - Score candidates with CNN (`tools/cnn_classifier/score_candidates_batch.py`) per
     `docs/DEVLOG_CNN_TRAINING.md`, producing `pipeline2_no_peak_filtered_cnn.json`.
   - Ensure staff masks are generated in the same run (homr output path).
3. **Measure numbering**: `tools/add_measure_numbers.py`.
4. **MMR overrides**: `tools/generate_numbering_overrides.py`.
5. **Final numbering + overlay**: `tools/add_measure_numbers.py` with overrides.

### Deliverables
- Updated orchestrator that runs the above sequence end-to-end.
- Unified run directory under `logs/full_pipeline_runs/<timestamp>_<score>_<part>/`.
- No reliance on pre-generated hybrid outputs.

### First Target PDF
`data/evaluation/pdfs/おもちゃの交響曲_bass.pdf` (note: cover/blank pages, score page likely page 3).

### Compatibility
- Continue to support direct use of existing scripts for ad-hoc runs.
- The entry point should be a thin wrapper, not a rewrite.

---

## Update (2026-01-20): Detection Integration
The orchestrator (`tools/run_full_pipeline.py`) has been updated to support the full detection pipeline.

### Implemented Steps
1. **Hybrid Detection**: Calls `tools/run_hybrid_pipeline.sh` (Docker `sr_eval_gpu`).
   - Outputs: Reliable candidates (hybrid) + Staff Masks (homr).
2. **Probe Scan**: Calls `tools/run_eval_experiment.py` (Host).
   - Inputs: Hybrid candidates + Staff Masks (via new `--staff-mask-dir`).
   - Logic: Expands candidates using the staff mask context.
3. **CNN Scoring**: Calls `tools/cnn_classifier/score_candidates_batch.py` (Host).
   - Logic: Filters expanded candidates using the trained CNN model.

### Pending Verification
- **Integration Test**: The new detection logic has been verified with a "Smoke Test" using `data/evaluation2/pdfs/Va_Prokofiev_Symphony1.pdf`.
- **Validation**:
  - `run_hybrid_pipeline.sh` is correctly invoked in Docker.
  - Path translation between Host/Docker is working (using `data/workbench` mount).
  - Staff masks are correctly passed to downstream steps.
=======
**NOTE**: This file is a historical snapshot. The authoritative, reproducible record
is in `docs/DEVLOG_MEASURE_NUMBERING.md` (measure numbering/MMR) and
`docs/DEVLOG_CNN_TRAINING.md` (CNN training).

**Last Updated**: 2026-01-24
**Current Phase**: Pipeline Optimization - Ready for Integration

---

## 1. Current Status (2026-01-24)
- **Proxy Inference Strategy**: Implemented and verified (Phase 2).
    - **Performance Gain**: Segnet ~66x speedup, TrOmr ~6.5x speedup.
    - **Bottleneck Shift**: Inference is no longer the bottleneck. Real-ESRGAN generation (~120-180s/page) now dominates.
- **Real-ESRGAN Tuning (Phase 5A)**: Completed.
    - **Optimal Config**: `tile=512` (Auto) + `fp16` is the best balance for RTX 4060 (8GB).
    - **CLI Control**: Added `--sr-tile`, `--sr-tile-pad`, `--sr-fp32` to `homr_evaluator.py`.
- **SR Reuse Validation (Phase 4)**: Verified.
    - **Page 10 (Large)**: ~54s reduction (~20% total time). Reuse is highly effective for large images.
- **Documentation**: Benchmarks recorded in `docs/performance_comparison.md`.

## 2. Tasks & Strategy (Updated)

### Phase 5B: Batch Processing Architecture (Migrated)
**Decision (2026-01-24)**: This task is migrated to merge with the `plan/full_pipeline_workflow` initiative.
- **Reason**: The "Python Loop" optimization is functionally identical to the "End-to-End Orchestrator" planned in the full pipeline workflow. Developing them separately would cause redundancy.
- **Next Step**: Create a new integration branch based on `plan/full_pipeline_workflow` and incorporate the SR/Inference optimizations.

### Phase 5C: SR Decoupling & Caching (Pending)
*   Migration to the new orchestrator will naturally handle this via `generate_sr_image.py` or internal method calls.

## 3. Optimization Conclusion (2026-01-24)
- **Real-ESRGAN**: Tuning is considered complete. `tile=512` + `fp16` is the optimal configuration.
- **Inference**: Proxy Inference strategy effectively solved the bottleneck.
- **Pipeline**: The remaining overhead is purely "Cold Start" (Python startup & Model loading), which will be addressed by the Batch Processing Architecture / Orchestrator.

---

## 4. Reference Commands
```bash
# Full Benchmark Run (with SR generation)
bash tools/run_hybrid_pipeline.sh --image data/training/images/page_10.png --run-id page_10_bench_v3

# Benchmark with SR Reuse
bash tools/run_hybrid_pipeline.sh \
  --image data/training/images/page_10.png \
  --run-id page_10_reuse_test \
  --sr-image logs/hybrid_pipeline_bench/previous_run/sr/page_10/page_10/page_10.png

# Compare Results
python3 tools/compare_hybrid_results.py logs/bench/baseline_run.json logs/bench/optimized_run.json
```
>>>>>>> main
