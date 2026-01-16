# Development Log (Measure Numbering)

Active log for `feature/measure_numbering` branch.
See `docs/DEVELOPMENT_LOG.md` for historical logs prior to 2026-01-03.

This log captures all implementation and experiment steps with reproducible inputs, parameters, and outputs.

## Measure Numbering Specification Draft

### Goal
Define the measure-numbering rules and list open questions in a single place so future decisions are explicit and traceable.

### Context
We assume barline detection information is already available.

### Rules List (Draft)

1.  **Sequential Numbering**: Measures are numbered sequentially starting from 1 (typically).
2.  **Barline Dependency**: Measure numbers are incremented at each barline.

*(Placeholder for future rules)*

### Open Questions & Possible Approaches

1.  **Upbeat (Anacrusis)**
    *   *Question*: How should the initial partial measure be numbered?
    *   *Approaches*:
        *   Count as 0.
        *   Count as 1.
        *   Do not count (first full measure is 1).

2.  **Movement Boundaries**
    *   *Question*: Does the measure count reset at new movements or sections?
    *   *Approaches*:
        *   Reset to 1.
        *   Continue cumulatively.

3.  **Multi-measure Rests**
    *   *Question*: How to handle multi-measure rests in numbering?
    *   *Approaches*:
        *   Treat as single measure for numbering (incorrect for musical context usually).
        *   Increment by the number of measures indicated in the rest.

4.  **Divisi / Multiple Staves**
    *   *Question*: How to handle cases where barlines might not align perfectly or when processing individual parts vs score?
    *   *Approaches*:
        *   Use global system barlines.
        *   Handle per-part.

5.  **Repeats / Endings (Volta)**
    *   *Question*: How does numbering handle repeats (1st/2nd endings)?
    *   *Approaches*:
        *   Strict linear numbering of the printed score (ignoring execution flow).
        *   Numbering reflecting execution flow (unlikely for standard score marking).

### Decision Log Template

When a decision is made regarding the rules above, record it here.

#### [YYYY-MM-DD] Decision Title
*   **Status**: [Proposed | Decided | Rejected]
*   **Rationale**: Why we chose this approach.
*   **Examples**:
    *   *Input*: Description or snippet.
    *   *Output*: Expected numbering.
*   **Affected Code Paths**: List modules or functions that need updates.

## 2026-01-04: Baseline Detector Snapshot

### Purpose
Pin the "best baseline" barline detector run used for early verification.

### Inputs
- `logs/gt_rebuild_hybrid_eval/20260102T134300_best_repro_fullparams`

### Notes
- Summary table: `logs/gt_rebuild_hybrid_eval/20260102T134300_best_repro_fullparams/summary_table.md`
- Pinned copy: `logs/gt_rebuild_hybrid_eval/_best/summary.md` (update if a better run is confirmed).
- Reported totals: TP=611 / FP=15 / FN=0.

## 2026-01-04: Parallel Track Context

### Track A (Measure Numbering)
- Worktree: `ws_PDFScoreBar_model_exp`
- Branch: `feature/measure_numbering`

### Track B (CNN Training)
- Worktree: `../ws_PDFScoreBar_training`
- Branch: `experiment/cnn_classifier`
- Status: merged back into the main workflow after classifier integration.

## 2026-01-04: Core Numbering Implementation

### Goal
Implement linear numbering core and validate on simple synthetic systems.

### Inputs
- `src/measure_numbering/numbering.py`
- Unit tests in `tests/test_numbering.py`

### Work Summary
- Implemented `MeasureNumberer` with left-to-right, system-by-system sequencing.
- Added barline deduplication and interval-based measure creation.
- Made `Barline` and `BBox` hashable (`unsafe_hash=True`) to allow set-based deduplication.

### Outputs
- Unit tests passed for single-system and multi-page flow.

### Notes
- Baseline sequencing confirmed in synthetic tests; real-data verification handled later.

## 2026-01-04: System Inference Simplification

### Goal
Define reliable staff-to-system grouping while avoiding unstable heuristics.

### Inputs
- `src/measure_numbering/builder.py`
- Unit tests in `tests/test_builder.py`

### Work Summary
- Initial gap-clustering heuristics abandoned due to instability.
- Implemented fallback strategy:
  - Use explicit `system_index` if present.
  - Otherwise, treat page as a single system.

### Outputs
- Updated tests to reflect safe fallback behavior.

## 2026-01-04: Real Data Verification (Pipeline Prototype)

### Goal
Validate numbering and system inference using real detector outputs.

### Inputs
- Barlines: `logs/gt_rebuild_hybrid_eval/20260102T134300_best_repro_fullparams/per_page/page_10/end_recovered.json`
- Staff mask: `logs/homr_eval/20251229T_gt_rebuild_eval/page_10/page_10_debug_3_staff.png`

### Work Summary
- Extracted staff bands from homr mask using vertical dilation (kernel 1x20).
- Detected coordinate mismatch: homr mask is downscaled (1660x2214) vs original (2700x3600).
- Implemented upscaling to align staff bands to original coordinates.
- For verification, assigned each staff to its own system (1 staff = 1 system).
- Ran `MeasureNumberer` across inferred systems.

### Outputs
- Correct barline-to-staff assignment.
- Sequential numbering across systems validated on page 10.

## 2026-01-04: Deduplication + Implicit Start Completion

### Goal
Fix overlapping numbers and missing first measures seen in real data.

### Inputs
- Same as prior (Page 10 real data).

### Work Summary
- Added `_deduplicate_barlines` with 15px threshold to merge detector duplicates.
- Added implicit start detection: insert a ghost barline if first barline is >50px from staff start.
- Relaxed overlap threshold for barline-to-staff assignment (20% or 10px min).
- Updated visualization: centered numbers; ghost barlines in magenta; staves with transparent blue fill.

### Outputs
- Clean numbering with removed duplicates and captured first measures.

## 2026-01-04: Production Integration

### Goal
Package numbering pipeline and provide CLI.

### Inputs
- `src/measure_numbering/pipeline.py`
- `tools/add_measure_numbers.py`

### Work Summary
- Implemented `MeasureNumberingPipeline` integrating StaffExtractor, SystemBuilder, MeasureNumberer.
- Added coordinate scaling from staff mask to original image.
- Implemented CLI for single/multi-page processing with JSON + optional overlay output.
- Marked legacy scripts as `[EXPERIMENTAL]`.

### Outputs
- Verified on page 10:
  - JSON: `logs/gt_rebuild_hybrid_eval/20260102T134300_best_repro_fullparams/per_page/page_10/final_numbering.json`
  - Overlay: `logs/gt_rebuild_hybrid_eval/20260102T134300_best_repro_fullparams/per_page/page_10/final_pipeline_overlay.png`

## 2026-01-04: Divisi Investigation (Failure Case)

### Goal
Test default assumption (1 staff = 1 system) on divisi scores.

### Inputs
- Image: `data/evaluation2/images/prokofiev1/page_004.png`
- GT barlines: `data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_004/boxes_sorted_v20251229.json`
- Staff mask: `logs/homr_eval/20251229T_gt_rebuild_eval/page_004/page_004_debug_3_staff.png`
- CLI: `tools/add_measure_numbers.py`

### Outputs
- Overlay: `logs/experiments/page_004_system_test/overlay_default.png`
- JSON: `logs/experiments/page_004_system_test/numbering.json`

### Findings
- Divisi portion grouped incorrectly (treated as separate systems), confirming need for system grouping logic.

## 2026-01-04: Geometric System Inference (Divisi) Implementation

### Goal
Auto-group staves into systems using barline alignment and proximity.

### Inputs
- `src/measure_numbering/builder.py`
- `src/measure_numbering/pipeline.py`

### Work Summary
- Implemented `_group_by_geometry` using Union-Find:
  - Adjacent staff gap < 1.5x avg height.
  - At least 2 aligned barlines within 10px tolerance.
- Enabled geometry grouping as default when explicit indices absent.
- Set `assume_one_staff_per_system=False` by default in pipeline.

### Outputs
- Verification: `logs/experiments/verify_divisi_page004_v2.json`
- Grouping result: 7 systems, divisi grouped as expected.

## 2026-01-04: Divisi Mis-grouping Analysis

### Goal
Identify false grouping cause on dense pages.

### Findings
- Gap threshold too loose: all adjacent pairs passed on Page 004.
- Alignment-only check merged distinct systems with similar rhythmic structure.

### Conclusion
Need physical connectivity check to avoid false grouping.

## 2026-01-04: Divisi Refinement (Physical Connectivity)

### Goal
Require actual barline connection in inter-staff gap.

### Method
- For aligned barline pairs (within 10px), check vertical ink continuity in the gap using morphological opening.
- Group staves only if at least one connected pair is found.

### Verification
- Batch run:
  - Command:
    ```
    .venv_omr_dln/bin/python tools/verify_divisi_batch.py \
      --image-dirs data/evaluation2/images/prokofiev1 data/evaluation2/images/prokofiev5 \
      --mask-root logs/hybrid_generalization \
      --output-dir logs/experiments/batch_divisi_verification_v2
    ```
- Results:
  - Prokofiev1 page_004: correct divisi grouping.
  - Prokofiev5 page_015: no false grouping.

## 2026-01-05: Measure Attribute Overrides (Anacrusis / MMR)

### Goal
Enable manual overrides for special cases via config.

### Inputs
- `src/measure_numbering/types.py`
- `src/measure_numbering/numbering.py`
- `tools/add_measure_numbers.py`

### Work Summary
- Added `MeasureAttribute` and linked to `Measure`.
- Implemented overrides in `MeasureNumberer`:
  - `set_number` (e.g., anacrusis = 0).
  - `skip` (for multi-measure rest counts).
- CLI supports `--config` JSON.

### Outputs
- Tests: `tests/test_numbering_overrides.py`
- Example config and usage documented in `docs/SESSION_LOG.md`.
 - Example command:
   ```bash
   python tools/add_measure_numbers.py \
       --barlines logs/your_run/barlines.json \
       --staff-mask logs/your_run/staff_mask.png \
       --image data/images/page_001.png \
       --config overrides.json \
       --output-json results.json \
       --output-overlay overlay.png
   ```

## 2026-01-05: Investigation - Symbol and Number Detection for MMR

### Goal
Confirm whether existing detectors can read multi-measure rest numbers.

### Findings
- `homr` provides system/staff bboxes but no digit symbols; `tesseract_input.png` is only used for title OCR.
- `oemer` detects standard rests but has no digit/long-rest classes.
- Conclusion: no existing pipeline provides rest-count digits; OCR must be introduced.

## 2026-01-05: ROI Extraction for Multi-measure Rests

### Goal
Identify candidate MMR regions by detecting empty measures.

### Inputs
- `tools/extract_rest_rois.py`
- `tools/visualize_rest_rois.py`
- Homr notehead mask: `page_xxx_debug_6_notehead.png`

### Method
- For each measure bbox, check notehead pixel density (with vertical margin).
- If empty, mark as MMR candidate.

### Outputs
- Page 10 overlay: `logs/experiments/rest_roi_test_page10/gt_roi_overlay_v3_detailed.png`
- GT barlines used to remove detector noise.

### Refinements
- Added `--vertical-margin` (default 80) to reduce false positives on high notes.
- Debug helpers:
  - `tools/batch_rest_roi_test.py`
  - `tools/debug_rest_candidates.py`
  - `tools/crop_debug_image.py`

## 2026-01-05: Noise Reduction (Erosion)

### Goal
Reduce false negatives due to thin text/symbol noise.

### Method
- Apply `cv2.erode` (3x3, iter=1) on notehead mask before counting pixels.

### Result
- Recovered G.P. and rest measures previously missed.
- Page 10: M141/M142 counts dropped to near zero.

## 2026-01-05: ROI Batch Verification

### Inputs
- Pages: 001, 004, 010
- Outputs:
  - `logs/experiments/rest_roi_batch_test/page_001/roi_overlay.png`
  - `logs/experiments/rest_roi_batch_test/page_004/roi_overlay.png`
  - `logs/experiments/rest_roi_test_page10/gt_roi_overlay_v4_eroded.png`
- Numbering JSON in `logs/experiments/rest_roi_batch_test/page_xxx/numbering.json`

### Findings
- Page 004 M6 false positive traced to GT barline error.

## 2026-01-05: GT Error Investigation (Page 004 M6)

### Finding
- GT barline at `[2610, 540, 2612, 624]` created phantom measure.

### Conclusion
- ROI logic is correct; GT data had a false positive barline.

## 2026-01-06: Multi-measure Rest Number Recognition (OCR)

### Goal
Automatically read rest-count numbers from empty measures and emit overrides.

### Inputs
- OCR engine: `RapidOCR` (`rapidocr_onnxruntime` in `.venv_omr_dln`).
- Script: `tools/generate_numbering_overrides.py`

### Workflow
1. Extract ROI images using `extract_rest_rois` logic.
2. Preprocess with thresholding/inversion/denoise.
3. Run RapidOCR.
4. Filter OCR outputs (reject letters, accept digits).
5. Emit `overrides.json` with `skip = rest_count - 1`.

### Verification (Page 10)
- M120 -> "4" -> `skip: 3`
- M67 -> "3" -> `skip: 2`
- Rehearsal text (e.g., "Legni 7", "Viol.11") rejected.
- Integration check: `tools/add_measure_numbers.py` with overrides.
- Artifact: `logs/experiments/ocr_test/final_numbering.json`

## 2026-01-06: Batch Verification on Evaluation Set

### Script
- `tools/batch_verify_numbering.py`

### Dataset
- Prokofiev 1: pages 1-6
- Prokofiev 5: pages 1-23
- Inputs: GT barlines + homr baseline masks

### Results
- Processed 27/29 pages; P006/P012 skipped due to missing GT barlines.
- Output overlays: `logs/experiments/batch_verification_20260106/`
- Patched `tools/generate_numbering_overrides.py` to handle empty ROI crops.

## 2026-01-06: OCR Diagnostic Visualization

### Tools
- `tools/debug_ocr_candidates.py`
- `tools/batch_debug_ocr.py`

### Output
- `logs/experiments/ocr_debug_20260106/`

### Notes
- Ran with `threshold=50` (standard) and `threshold=200` (relaxed) to inspect missed candidates.

## 2026-01-06: ROI Expansion + Filter Relaxation

### Changes
- Expanded ROI (horizontal +10px; vertical coverage down to 70% + 30px).
- Replaced strict "no letters" filter with a blacklist and digit extraction.
- Selected largest valid integer if multiple found.

### Verification
- Batch rerun: `logs/experiments/batch_verification_20260106_v2/`

### Remaining Challenges
- Some numbers still cut off at top.
- Rehearsal marks still captured if near center.

## 2026-01-07: ROI Expansion + Spatial Filter

### Changes
- Upward margin increased to 80px.
- Rehearsal mark filter: reject text >35% away from ROI center.

## 2026-01-07: Structural Solution (H-Bar Detection + Hybrid ROI)

### Rationale
Density-only heuristics were insufficient; added explicit rest-shape detection.

### Changes
- Added `detect_hbar` using morphological opening with dynamic kernel width (~30% of measure width).
- Hybrid ROI strategy:
  - Detection ROI: vertical margin 10px (staff-only).
  - OCR ROI: vertical margin 80px (captures high counts).
- Density threshold relaxed to 150 with H-bar safety net.
- Spatial filter tightened to 20% offset from center.

## 2026-01-07: Refinement (v4)

### Changes
- Removed `MORPH_OPEN` denoise (was erasing thin digits).
- Added dilation (2x2, iter=1) to thicken text.
- Tightened spatial filter to 10% offset.

### Outcome
- Reduced false positives from rehearsal marks.
- Recovered thin digits (e.g., "3" in P1/P3/M7).

## 2026-01-07: Failure Analysis Plan

### Reported Failures
- Prokofiev 1: P3 M7, P4 M204/M207/M210, P5 M34/M36, P6 M86.
- Prokofiev 5: P1 M1/M6, P2 M26-29, P8 M101, P9 M63, P17 M1.

### Plan
- Export ROI/H-bar/OCR crops for all failures.
- Classify failure types (H-bar FN/FP, OCR FN, spatial filter FN, density FN).
- Investigate bracket detection for rehearsal mark rejection.

## 2026-01-08: Failure Crop Export

### Tool
- `tools/export_failure_crops.py`

### Output
- `logs/experiments/failure_crops_20260108/`

### Proposed Next Step
- Test refined H-bar logic in `tools/detect_hbar_refined.py` on the exported crops.

## 2026-01-08: Failure Visualization (ROI + OCR Labels)

### Tools
- `tools/analyze_failure_cases.py`
- `tools/failure_targets.json`

### Outputs
- `logs/experiments/failure_analysis_*/page_overlays/*_roi_overlay.png`
- `logs/experiments/failure_analysis_*/**/*_context.png`
- `logs/experiments/failure_analysis_*/analysis_report.json`
- `logs/experiments/failure_analysis_*/analysis_report.csv`

### Updates
- Per-page ROI overlays, optional `--overlay-all`.
- Fallback to `numbering_base.json` if `numbering_final.json` missing.
- `--all-pages` for full-page overlays; `--number-roi` for ROI index labels.

## 2026-01-08: MMR GT GUI and Config

### Tools
- `tools/gt_relabel_gui/index_rest.html`
- `tools/gt_relabel_gui/app_rest.js`
- `tools/gt_relabel_gui/build_rest_gt_config.py`

### Outputs
- Config: `data/evaluation2/rest_gt_config_prokofiev.json`
- Per-page GT: `data/evaluation2/rest_gt/<work>/page_xxx/rest_gt.json`

### Missing Inputs (Blocking)
- GT barlines missing for:
  - `data/evaluation2/annotations/prokofiev5/page_006`
  - `data/evaluation2/annotations/prokofiev5/page_012`

### add_measure_numbers Inputs Required
- Barlines: `data/evaluation2/annotations/<work>/page_xxx/boxes_sorted_*.json`
- Staff mask: `logs/hybrid_generalization/eval2_<work>_page_xxx/.../page_xxx_debug_3_staff.png`
- Image: `data/evaluation2/images/<work>/page_xxx.png`
- Notehead mask (optional OCR): `page_xxx_debug_6_notehead.png`

## 2026-01-09: MMR Recognition Analysis

### Findings
- OCR-based overrides (`overrides.json`) drive `tools/add_measure_numbers.py` skips.
- Success case: Prokofiev 5 Page 004; numbering jump matches GT.
- Failure case: Prokofiev 5 Page 008 misidentified as 165-measure rest due to H-bar FP + loose spatial filtering.

### Improvement Plan
- Refine H-bar detection to reject beams/brackets.
- Enforce stricter horizontal centering.
- Add OCR rejection reasons to debug output.

## 2026-01-10: Musical Element Check (MMR)

### Changes
- Notehead check using `notehead_mask` to reject non-rest measures.
- Vertical stem check via morphological opening in staff region.
- Relaxed OCR Y-range to allow counts above staff.
- Additional filtering for OCR candidates.

### Status
- Logic validated as more robust than residual-ink heuristics; continued tuning needed.

## 2026-01-XX: ROI Coordinate Scaling Fix (Override Generation)

### Issue
- ROI slicing used mask-space coordinates without scaling to original image space, causing false notehead hits.

### Fix
- Applied `scale_x` / `scale_y` to ROI coordinates before slicing `notehead_mask` and `staff_mask` in `tools/generate_numbering_overrides.py`.

### Verification
- Prokofiev 5 Page 008: auto-detected 4 multi-measure rests in Systems 4 and 5 (previously rejected).

## 2026-01-12: Phase 1.5 Fixes & Dataset Prep

### Changes
- End-bar fix: `MIN_MEASURE_WIDTH = 25` in `src/measure_numbering/numbering.py`.
- Added debug visualization: `tools/debug_end_bar_removal.py`.
- Added 20px padding to crops in `tools/create_mmr_train_data.py`.
- Added `tools/batch_gen_numbering_for_all.py` to create numbering JSONs for all datasets.
- Updated `tools/gt_relabel_gui/build_rest_gt_config.py` to generate `data/evaluation2/rest_gt_config_all.json`.

### Notes
- Shostakovich Sym5 skipped due to missing barlines.
- Prokofiev 5 Page 005 regenerated numbering to remove a 6px false measure.
- Prokofiev 1 Page 004 numbering synced to manual GT update.

## 2026-01-12: MMR Classifier Training & Integration

### Dataset Generation
```bash
python tools/create_mmr_train_data.py \
  --configs data/evaluation2/rest_gt_config_all.json data/evaluation2/rest_gt_config_expansion.json \
  --output-root data/mmr_dataset_v1
```

### Training
```bash
python tools/train_mmr_classifier.py --data-root data/mmr_dataset_v1 --epochs 20 --batch-size 32
```

### Integration
- Created `tools/generate_numbering_overrides_cnn.py`.
- Replaced `tools/generate_numbering_overrides.py` with CNN version.
- Renamed heuristic version to `tools/generate_numbering_overrides_heuristic.py`.

### Evaluation (Prokofiev 5)
```bash
python tools/batch_verify_numbering.py --output-dir logs/experiments/batch_cnnv1
```
- Precision 93.8% (45/48), Recall 90.0% (45/50), F1 91.8%.

## 2026-01-12: Global Evaluation & Error Analysis (v4-v6)

### v3 (Max-Number Heuristic Baseline)
- Stage 1 precision: 100.0%
- Stage 2 precision: 88.2%
- Example error locations recorded:
  - Prokofiev 1: P001 S8 M0/M2/M4, P002 S10 M5, P006 S4 M9
  - Prokofiev 5: P002 S6 M4, P007 S1 M0, P009 S9 M0, P014 S3 M0, P016 S1 M2/S2 M4, P019 S1 M2/M4
- Root cause: picking `max(valid_nums)` over-selects rehearsal/tempo numbers.
 - Status: superseded by geometric scoring (v4).

### v4 (Geometric Scoring)
- Implemented `select_best_candidate` with centering penalty and size bonus.
- Metrics: TP 172, FP 1, FN 20, Mismatch 13 (59 pages).
- Fixed rehearsal mark failure (Shostakovich P22) and noise in Prokofiev P7.
 - Some debug crops were stored outside the repo under `/home/masaki_muramatsu/.gemini/...` (not versioned).
 - Status: adopted until v6 polish.

### v5 (Candidate Refinement)
- Added `merge_ocr_results` for split numbers.
- Added low-confidence rescue (0.1 < Prob < 0.5 + GeoScore > 60).
- Fixed missing GT entry (Sibelius P2 S5 M6).
 - Status: adopted as part of v6.

### v6 (Final OCR Polish)
- Tempo mark penalty for numbers after "=".
- Vertical centering penalty.
- Multi-candidate scoring (no longer max number).
- Expanded OCR top margin to 80px.
- Metrics: TP 151, FP 0, FN 22, Mismatch 8.
 - Status: adopted in mainline until text-noise model refresh.

## 2026-01-XX: MMR FN Mitigation (Text Noise + Staff Mask + Dataset Refresh)

### Training Pipeline Enhancements
- Added text-noise overlay augmentation with staff-mask constraints.
- Added random font sampling from zip/dir.
- Switched optimizer to AdamW + CosineAnnealingLR.
- Enabled TensorBoard logging (optional).
- Increased default batch size to 64.

### Dataset Builder Updates
- Export staff-mask crops per sample.
- Auto-discover staff masks from hybrid/homr logs and DeepScores seg (staff id=165).
- Added config: `data/evaluation2/rest_gt_config_missing.json`.

### Expansion Page 003 Fix
- Regenerated x4-scaled barlines + original staff mask.
- Outputs:
  - `logs/cache_expansion_gen/expansion_eval_page_003/numbering_x4.json`
  - `logs/cache_expansion_gen/expansion_eval_page_003/debug_overlay_x4.png`

### Dataset Refresh
- Configs:
  - `data/evaluation2/rest_gt_config_all.json`
  - `data/evaluation2/rest_gt_config_expansion.json`
  - `data/evaluation2/rest_gt_config_missing.json`
- Output dataset: `data/mmr_dataset_v2` (Pos=183 / Neg=4045).

## 2026-01-XX: MMR Text-Noise Training + Global Eval

### Training Command (Partial)
- Recorded settings: dataset `data/mmr_dataset_v2`, batch size 224, epochs 30, text-noise + staff-mask constraints.
- Note: full command line was not logged.

### Global Eval Command (Partial)
- Script: `tools/global_batch_mmr_eval.py` with `--model-path` (and later `--filter` for targeted tests).
- Outputs: `logs/experiments/global_mmr_eval_textnoise`, `logs/experiments/global_mmr_eval_current_model`.
- Note: full command line was not logged.

## Branch Conclusion (Adopted State)

### Measure Numbering Core
- `MeasureNumberer` in `src/measure_numbering/numbering.py` with:
  - Deduplication (15px threshold).
  - Ghost start barline if first gap > 50px.
  - `MIN_MEASURE_WIDTH = 25` to avoid end-bar double-count.
- `SystemBuilder` in `src/measure_numbering/builder.py` with:
  - Explicit `system_index` preference.
  - Physical connectivity check for divisi grouping (aligned barline + gap ink).
- Pipeline + CLI:
  - `src/measure_numbering/pipeline.py`
  - `tools/add_measure_numbers.py`

### MMR Overrides (Production Path)
- Stage 1: CNN classifier (`tools/mmr_training/models/mmr_classifier_best_textnoise.pth`).
- Stage 2: OCR-based overrides (`tools/generate_numbering_overrides.py`) with:
  - Geometric scoring (v4+) and v6 refinements.
  - H-bar masking (v6).
  - Optional rotation TTA (`--enable-rotation-tta`, off by default).

### Adopted vs Rejected
- Adopted: H-bar masking, geometric scoring, split-digit merge, low-confidence rescue, tempo-mark penalty.
- Rejected/On hold: H-bar anchor penalty (regression), rotation TTA (no gain), early heuristic-only ROI pipeline.

## Output Index (Known Locations)

### Measure Numbering / Divisi
- `logs/gt_rebuild_hybrid_eval/20260102T134300_best_repro_fullparams/per_page/page_10/final_numbering.json`
- `logs/gt_rebuild_hybrid_eval/20260102T134300_best_repro_fullparams/per_page/page_10/final_pipeline_overlay.png`
- `logs/experiments/verify_divisi_page004_v2.json`
- `logs/experiments/batch_divisi_verification_v2/` (batch outputs)

### ROI Extraction / OCR Debug
- `logs/experiments/rest_roi_test_page10/gt_roi_overlay_v3_detailed.png`
- `logs/experiments/rest_roi_test_page10/gt_roi_overlay_v4_eroded.png`
- `logs/experiments/rest_roi_batch_test/page_001/roi_overlay.png`
- `logs/experiments/rest_roi_batch_test/page_004/roi_overlay.png`
- `logs/experiments/batch_verification_20260106/`
- `logs/experiments/batch_verification_20260106_v2/`
- `logs/experiments/ocr_debug_20260106/`
- `logs/experiments/failure_crops_20260108/`
- `logs/experiments/failure_analysis_*/` (overlays + reports)

### MMR Training / Eval
- `data/mmr_dataset_v1`
- `data/mmr_dataset_v2`
- `tools/mmr_training/models/mmr_classifier_best_textnoise.pth`
- `logs/experiments/batch_cnnv1/`
- `logs/experiments/global_mmr_eval_textnoise/`
- `logs/experiments/global_mmr_eval_current_model/`

### Output Index (Not Yet Located)
- Global eval v4/v5/v6 run directories (likely under `logs/experiments/`): not searched.
- Sibelius-specific eval runs for v3/v6/v7 (TTA attempts): not searched.

### Training
- Dataset: `data/mmr_dataset_v2`
- Model: `tools/mmr_training/models/mmr_classifier_best_textnoise.pth`
- Val metrics: F1 0.9737, Prec 0.9487, Rec 1.0000, Acc 0.9973 (epoch 30)

### Global Eval
- Output: `logs/experiments/global_mmr_eval_textnoise`
- Stage 1 (Classifier): P 1.0000, R 0.8750 (154/176)
- Stage 2 (OCR): P 0.9481, R 0.8295 (146/176)

### FN/FP Pages
- FN-heavy: Sibelius p001–p006, Festival p001/p002/p004/p009, Prokofiev5 p005/p009/p019, Prokofiev1 p001/p003, Sym5 p010/p015/p022.
- FP: Sym5 p010/p022, Festival p002, Sibelius p001/p002, Prokofiev1 p001, Prokofiev5 p005/p009.

## 2026-01-14: Global Eval (Confirmed)

### Inputs
- Script: `tools/global_batch_mmr_eval.py` (with `--model-path`)
- Model: `tools/mmr_training/models/mmr_classifier_best_textnoise.pth`
- Output: `logs/experiments/global_mmr_eval_current_model`

### Results
- Stage 1: P 0.9872, R 0.8750 (TP 154, FP 2, Total 176)
- Stage 2: P 0.9359, R 0.8295 (TP 146, FP 10, Total 176)

### Conclusion
- OCR stage is the recall bottleneck.

## 2026-01-14: FN Analysis (Root Cause)

### Inputs
- Tool: `tools/organize_mmr_errors.py`

### Findings
- No true classifier misses at Prob < 0.5.
- Many OCR rejects despite Prob >= 0.5 (often > 0.9).
- OCR cleaning needed (prefixes like E3/P3, punctuation).

## 2026-01-15: OCR Improvements (Sibelius Fix)

### Changes
- Retry loop for OCR variants (`no_dilate`, `heavy_dilate`).
- Expanded OCR crop margins (bottom +80, sides +30).
- Regex cleaning (strip noise prefixes/punctuation).
- Sanity check: large numbers in narrow measures.
- Added `--filter` to `tools/global_batch_mmr_eval.py`.

### Results (Sibelius)
- Stage 1 recall: 67.7% -> 96.8%
- Stage 2 recall: 61.3% -> 80.6%
- Precision dropped slightly (86% -> 80%).

## 2026-01-15: H-Bar Anchor + TTA (Rejected)

### Changes
- Added H-bar centroid detection and OCR retry rotations.

### Result
- Stage 2 recall dropped (80.6% -> 77.4%), reverted.

## 2026-01-15: MMR Failure Analysis (Visual Audit)

### Inputs
- Tool: `tools/analyze_mmr_failures_v2.py`

### Findings
- H-bar hallucinated as CJK digits.
- Rehearsal marks picked up at measure edges.
- Confidence vs geometry conflicts.

### Updated Plan
- CJK filtering.
- Balanced geometric scoring.
- H-bar size threshold.

## 2026-01-16: Component Analysis (Split Digit Merge)

### Changes
- Relaxed merge logic for single digits in `merge_ocr_results`.

### Results
- No recall gain; remaining errors are selection failures.

## 2026-01-16: H-Bar Masking (Success)

### Changes
- Mask H-bar candidates before OCR using morphological ops.

### Results (Sibelius)
- Stage 2 recall: 80.6% -> 87.1%
- Stage 2 precision: 83.3% -> 90.0%

## 2026-01-16: Deskew + Rotation TTA (On Hold)

### Changes
- Added `rotate_image` and rotation TTA variants in retry loop.
- Added `--enable-rotation-tta` flag to keep TTA off by default.

### Results (Sibelius)
- Stage 2 recall: 87.1% -> 87.1% (no change)
- Stage 2 precision: 90.0% -> 90.0% (no change)

### Conclusion
- Deskew/TTA alone does not resolve font/overlap errors.

## Appendix: Tool Inventory (Reference)

### MMR Pipeline
- `tools/generate_numbering_overrides.py`: Stage 2 production override generation (CNN + OCR).
- `tools/evaluate_rest_detection.py`: Stage 1/2 metric evaluation.
- `tools/analyze_mmr_errors.py`: Visual crops + error report.
- `tools/organize_mmr_errors.py`: Error categorization.
- `tools/mmr_training/create_mmr_train_data.py`: Training data crops.
- `tools/mmr_training/train_mmr_classifier.py`: ResNet18 classifier training.
- `tools/extract_rest_rois.py`, `tools/visualize_rest_rois.py`: ROI exploration.

### Measure Numbering
- `tools/add_measure_numbers.py`: Main numbering pipeline (barlines + staff mask + overrides).
- `tools/verify_measure_numbering_pipeline.py`: End-to-end verification script.
- `tools/compare_batch_structure.py`: Structure comparison across runs.

### Annotation / GT Helpers
- `tools/gt_relabel_gui/`: Browser GUI for barlines + rest counts.
- `tools/coordinate_annotator.py`: CLI annotation helper.
- `tools/sort_measures.py`: Sort barline detections into chronological order.

### Diagnostics / Visualization
- `tools/inspect_errors.py`: GT vs predicted barline visualizer.
- `tools/debug_mask_alignment.py`: Mask alignment diagnostics.
- `tools/render_barline_boxes_overlay.py`: High-quality overlays of barline detections.

### Sweeps / Legacy
- `run_omr_dln_sweep.sh`: OMR-DLN parameter sweep.
- `tools/run_hybrid_pipeline.sh`: Legacy hybrid pipeline runner.
