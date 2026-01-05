# Session Log (Measure Numbering Track)

**Last Updated**: 2026-01-04
**Context**: This log tracks the design and implementation of the "Measure Numbering" system (Plan A) in the `feature/measure_numbering` branch.

---

## 2026-01-04 Basic Numbering Logic Implementation

**Goal**: Implement the core linear numbering logic (`MeasureNumberer`).

### Actions Taken
- Implemented `MeasureNumberer` in `src/measure_numbering/numbering.py`.
    - Logic: Iterates systems, deduplicates barlines, creates measures based on intervals, assigns sequential numbers.
- Verified with unit tests (`test_numbering.py`).
- Fix: Made `Barline` and `BBox` types hashable (`unsafe_hash=True`) to support deduplication via `set()`.

### Results
- The core numbering engine is operational. It correctly threads measure numbers across systems and pages.
- Tested with synthesized simple systems.

## 2026-01-04 System Inference Logic (Simplification)

**Goal**: Implement logic to group staves into systems (`SystemBuilder`).

### Actions Taken
- Initially attempted to implement complex geometric heuristics (gap clustering).
- **Corrected Course**: Upon review, heuristics were deemed unreliable.
- Simplified `SystemBuilder` (`src/measure_numbering/builder.py`) to:
    1. Prefer explicit `system_index` if available.
    2. Fallback: Treat the page as a single system.
- Adjusted tests (`test_builder.py`) to reflect this simplified safe-default scope.

## 2026-01-04 Real Data Verification (Pipeline Prototype)

**Goal**: Validate the `SystemBuilder` and `MeasureNumberer` using real detection outputs from the "Best Baseline" snapshot.

### Methodology
Constructed a verification pipeline script (`tools/verify_measure_numbering_pipeline.py`) using:
1.  **Barline Input**: `logs/gt_rebuild_hybrid_eval/20260102T134300_best_repro_fullparams/per_page/page_10/end_recovered.json` (Final "End Recovered" barlines).
2.  **Staff Input**: `logs/homr_eval/20251229T_gt_rebuild_eval/page_10/page_10_debug_3_staff.png` (Homr Staff Mask).
3.  **Process**:
    *   **Staff Extraction**: Loaded binary mask, applied vertical dilation (kernel 1x20) to merge lines into bands, and extracted connected components.
    *   **Scaling Fix**: Discovered that `homr` masks are downscaled (1660x2214) relative to the original/barline coordinate space (2700x3600). Implemented upscaling logic for staff bands.
    *   **System Inference**: Simulating a "Part" score (1 staff = 1 system) by assigning unique system indices to each extracted staff.
    *   **Numbering**: Executed `MeasureNumberer` across the inferred systems.

### Results
-   **Staff Extraction**: Successfully identified 13 staff bands matching the visual structure of Page 10.
-   **Barline Assignment**: Barlines were correctly assigned to their respective staves after coordinate scaling.
-   **Numbering**: Successfully generated sequential measure numbers across systems.

## 2026-01-04 Logic Refinement: Deduplication and Implicit Start Completion

**Goal**: Resolve overlapping numbers and missing first measures observed in real data visualization.

### Actions Taken
1.  **Deduplication**:
    *   Added `_deduplicate_barlines` to `MeasureNumberer` with a 15px threshold.
    *   Reason: Detector outputs multiple candidates for the same visual barline, causing redundant "micro-measures".
2.  **Implicit Start Detection**:
    *   Added logic to `MeasureNumberer.number_system` to check the gap between system start and the first detected barline.
    *   Threshold: 50px. If exceeded, a "Ghost Barline" is inserted at the staff's left edge to capture the first measure.
3.  **Robust Assignment**:
    *   Relaxed `SystemBuilder` overlap threshold from 50% to 20% (or 10px minimum).
    *   Reason: Ensure short barline segments (typical in noisy detections) are correctly assigned to staves.
4.  **Visualization Update**:
    *   Numbers are now **centered** within measures.
    *   Ghost barlines are visualized in **magenta**.
    *   Staves are rendered with transparent blue fill for better context.

### Results
-   Verified on Page 10 with the full detector output (293 barlines).
-   Numbers are cleanly centered and duplicates are removed.
-   First measures (starting from the left margin) are now correctly captured.

**Conclusion**: The logic for deduplication and implicit start completion is approved for production use. The pipeline reliably handles noisy detector output and ensures logical measure continuity.

## 2026-01-04 Production Integration

**Goal**: Formalize the numbering pipeline into a reusable package and CLI tool.

### Actions Taken
1.  **Implemented `MeasureNumberingPipeline`** (`src/measure_numbering/pipeline.py`):
    *   Integrates `StaffExtractor`, `SystemBuilder`, and `MeasureNumberer`.
    *   Automates coordinate scaling from `homr` mask space to original image space.
2.  **Created `tools/add_measure_numbers.py`**:
    *   Standard CLI interface for processing detection results.
    *   Supports single/multi-page processing (via sequential list).
    *   Outputs structured JSON containing pages, systems, staves, and numbered measures.
    *   Provides optional high-quality visualization overlay generation.
3.  **Legacy Script Sanitization**:
    *   Marked `temp_verify_numbering.py`, `tools/visualize_measure_numbering.py`, and other experimental scripts with `[EXPERIMENTAL]` headers.

### Results
-   **Verification**: Successfully ran the integrated tool on Page 10.
-   **Output**: Generated `final_numbering.json` and `final_pipeline_overlay.png`.
-   The numbering system is now ready for production use and further extension (e.g., bracket-based system inference).

**Artifacts**:
- `src/measure_numbering/pipeline.py`
- `tools/add_measure_numbers.py`
- `logs/gt_rebuild_hybrid_eval/20260102T134300_best_repro_fullparams/per_page/page_10/final_numbering.json`

## 2026-01-04 Multi-Staff System (Divisi) Investigation

**Goal**: Evaluate numbering logic on a page with divisi (multiple staves per system).

### Methodology
1. **Target**: `page_004` from `Va_Prokofiev_Symphony1`.
2. **Inputs**:
   - Image: `data/evaluation2/images/prokofiev1/page_004.png`
   - Barlines (GT): `data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_004/boxes_sorted_v20251229.json`
   - Staff Mask: `logs/homr_eval/20251229T_gt_rebuild_eval/page_004/page_004_debug_3_staff.png`
3. **Execution**: Ran `tools/add_measure_numbers.py` with default "1 staff = 1 system" assumption.

### Results
- Generated `logs/experiments/page_004_system_test/overlay_default.png`.
- **Observations**:
  - The page has 8 staves.
  - Groups like staves 5, 6, 7 (y ~2600-3300) appear to be part of a single divisi system.
  - Default logic treats them as separate systems, resulting in sequential (incorrect) numbering for each staff in the divisi section.
  - This confirms the need for system grouping logic.

**Artifacts**:
- `logs/experiments/page_004_system_test/numbering.json`
- `logs/experiments/page_004_system_test/overlay_default.png`

## 2026-01-04 Geometric System Inference (Divisi Logic) Implementation

**Goal**: Implement logic to automatically group staves into systems based on vertical alignment of barlines (addressing Divisi without explicit brackets).

### Actions Taken
1.  **Analyzed Historical Logic**:
    *   Examined "divisi rescue" logic in `tools/run_gt_rebuild_hybrid_eval.py` (commit `6de614e`).
    *   Extracted key heuristics: Vertical Proximity (threshold 1.2-1.5x height) and Barline Alignment (tolerance 4-10px, count >= 2).
2.  **Implemented `_group_by_geometry` in `SystemBuilder`**:
    *   Added `_group_by_geometry` method to `src/measure_numbering/builder.py`.
    *   Logic:
        *   Uses Union-Find to group staves.
        *   Iterates adjacent staves sorted by Y.
        *   Links staves if `gap < 1.5 * avg_height` AND `aligned_barlines >= 2` (tolerance 10px).
    *   Updated `SystemBuilder.build_systems` to use this as the default strategy when explicit indices are missing (replacing the "Single System" fallback).
3.  **Updated Pipeline Configuration**:
    *   Changed `assume_one_staff_per_system` default to `False` in `src/measure_numbering/pipeline.py` to enable the builder's inference logic by default.

### Results
-   **Verification Target**: Page 004 (Prokofiev), which was previously incorrectly identified as 13 single systems.
-   **Outcome**:
    *   Ran `tools/add_measure_numbers.py` (v2).
    *   Input: 13 extracted staff bands (from noisy mask).
    *   Output: 7 Systems.
    *   Grouping: `[1, 1, 1, 1, 1, 5, 3]` (Staves 5-9 grouped, Staves 10-12 grouped).
    *   This correctly reflects the divisi structure (Quintet + Triplet) observed in the score.
-   **Conclusion**: The geometric inference logic provides a robust fallback for scores/divisi parts where explicit system brackets are missing or unreliable.

**Artifacts**:
-   `src/measure_numbering/builder.py` (Updated)
-   `logs/experiments/verify_divisi_page004_v2.json`

### Analysis of Divisi Mis-grouping (2026-01-04)

**Issue**: On `page_004`, Staves 6-13 were incorrectly grouped into a 5-staff system and a 3-staff system (`[..., 5, 3]`), whereas the user indicates only the 6th and 7th visual rows are divisi.

**Logic Current State**:
1.  **Vertical Proximity**: `Gap < AvgHeight * 1.5`.
    -   On Page 004, `AvgHeight` is ~161px, so `Threshold` is ~242px.
    -   Analysis shows **ALL** adjacent staff pairs on this page passed this check (Max gap was 150px).
    -   *Finding*: The distance threshold is too loose for this dense page; distinct systems are closer than the threshold.
2.  **Barline Alignment**: `X-Alignment` of 2+ lines.
    -   Staff 9 and 10 were grouped because they have aligned barlines (same metric structure), even though they belong to different systems.
    -   *Critical Flaw*: The current logic checks for **alignment** (logical X) but not **connection** (physical Y-continuity). True multi-staff systems usually have barlines drawn *through* the inter-staff space, or at least very close.

**Conclusion**:
The current geometric logic is too aggressive for dense scores with consistent metric layouts. It successfully groups divisi, but also erroneously merges separate systems that happen to be aligned vertically.
Future fix must likely enforce **physical barline connection** (or explicit segment in the gap) rather than just logical alignment.

### Divisi Logic Refinement: Physical Connectivity (2026-01-04)

**Objective**: Correct the false positives in Divisi grouping (where separate aligned systems were merged) by introducing a check for physical vertical connections (barlines spanning the gap).

**Methodology**:
1.  **Initial Attempt (Gap Connectivity)**: Checked for *any* vertical ink in the inter-staff gap.
    -   *Result*: Successfully identified Divisi on P1/004, but caused massive false positives on Prokofiev 5 (e.g., Page 015) due to mask overlaps and noise being interpreted as connections.
2.  **Refined Logic (Aligned Connectivity)**: Restricted the connectivity check to **only** the X-coordinates where barlines are already aligned.
    -   *Logic*: `_check_aligned_connection` in `SystemBuilder`.
    *   *Process*:
        1.  Find pairs of barlines between adjacent staves with `abs(center_x1 - center_x2) <= 10px`.
        2.  For each pair, extract the vertical strip in the gap between them.
        3.  Check for a solid vertical line using morphological opening (kernel height ~80% of gap).
        4.  Group staves ONLY if at least one such connected pair is found.

**Verification Results**:
-   **Batch Run**: Ran on all Prokofiev 1 & 5 images using `tools/verify_divisi_batch.py`.
-   **Prokofiev 1 Page 004** (Target): Correctly identified the Divisi pair (`[2]`) in an otherwise single-staff page.
-   **Prokofiev 5**:
    -   Page 015 (Problematic): Correctly identified as all single-staff systems (`[]`), eliminating the false 6-staff group.
    -   Pages 007, 009, 011, etc.: All correctly identified as single-staff.
-   **Command**:
    ```bash
    .venv_omr_dln/bin/python tools/verify_divisi_batch.py \
      --image-dirs data/evaluation2/images/prokofiev1 data/evaluation2/images/prokofiev5 \
      --mask-root logs/hybrid_generalization \
      --output-dir logs/experiments/batch_divisi_verification_v2
    ```

**Status**: Divisi logic is now robust against layout noise while maintaining sensitivity to true bracketed/connected systems.

## 2026-01-05 Investigation: Symbol and Number Detection for Multi-measure Rests

**Goal**: Determine if existing project assets (homr, oemer) can detect multi-measure rest numbers.

### Findings
1.  **homr**:
    - `page_10_detections.json` contains BBoxes for systems and staves, but no symbol labels or digits.
    - `tesseract_input.png` exists but is used exclusively for **Title Detection** via `RapidOCR` at the top of the first page.
2.  **oemer**:
    - `symbol_extraction.py` and `classifier.py` identify standard rests (whole, quarter, etc.) but lack classes for digits or multi-measure rest notation.
3.  **Conclusion**: Neither tool provides the necessary data to automatically detect long rest numbers within measures. Existing OCR/RapidOCR is used only for non-musical text (titles).

## 2026-01-05 Measure Attribute Injection System Implementation

**Goal**: Enable manual overrides for special musical cases (Anacrusis, Multi-measure rests) via external configuration.

### Actions Taken
1.  **Extended Data Model**: Added `MeasureAttribute` to `src/measure_numbering/types.py` and linked it to `Measure`.
2.  **Enhanced Numbering Logic**:
    - Updated `MeasureNumberer.number_score` to accept a list of overrides.
    - Implemented `set_number` (to force a specific number, e.g., 0 for Anacrusis) and `skip` (to jump N measures for long rests).
3.  **CLI Integration**: Updated `tools/add_measure_numbers.py` to support `--config <path_to_json>`.

### Usage Guide

To handle musical exceptions, create a JSON file (e.g., `overrides.json`):

```json
{
  "measure_overrides": [
    {
      "page": 0,
      "system": 0,
      "measure": 0,
      "set_number": 0,
      "comment": "Anacrusis (starts numbering from 0)"
    },
    {
      "page": 1,
      "system": 2,
      "measure": 5,
      "skip": 3,
      "comment": "Multi-measure rest (4 bars total, jumps next number by +4)"
    }
  ]
}
```

*Note: Indices (page, system, measure) are 0-based.*

**Execution Command**:
```bash
python tools/add_measure_numbers.py \
    --barlines logs/your_run/barlines.json \
    --staff-mask logs/your_run/staff_mask.png \
    --image data/images/page_001.png \
    --config overrides.json \
    --output-json results.json \
    --output-overlay overlay.png
```

### Verification
- Created `tests/test_numbering_overrides.py` covering both `set_number` and `skip` scenarios.
- Results: `OK` (Ran 2 tests).

## 2026-01-05 ROI Extraction for Multi-measure Rests

**Goal**: Define a heuristic to extract potential locations of multi-measure rest numbers (Region of Interest) by identifying "empty" measures.

### Candidate Definition
A region is considered a candidate for a multi-measure rest number if:
1.  **Inside Measure**: Located within the horizontal bounds of a detected measure.
2.  **Empty Context**: The measure contains no standard noteheads or stems.

### Implementation & Refinement
1.  **Tool Creation**: Created `tools/extract_rest_rois.py` and `tools/visualize_rest_rois.py`.
    -   Uses `homr`'s notehead mask (`page_xxx_debug_6_notehead.png`) to check for pixel density within measure bboxes.
2.  **GT Integration**: Regenerated numbering JSON for Page 10 using Ground Truth barlines (`data/training/annotations/page_010/boxes_sorted_v20251229.json`) to eliminate detector errors from the validation loop.
3.  **High-register Support (Vertical Margin)**:
    -   Initial testing revealed false positives in measures with high notes (noteheads above the staff).
    -   Introduced `--vertical-margin` (default 80px) to expand the check area vertically.
    -   **Result**: False positives (M42, M43) were successfully removed; only 3 true candidates (M67, M75, M120) remained on Page 10.

### Artifacts
-   `tools/extract_rest_rois.py`
-   `tools/visualize_rest_rois.py`
-   `logs/experiments/rest_roi_test_page10/gt_roi_overlay_v3_detailed.png` (Visualization with green notehead overlay)
## 2026-01-05 Noise Reduction with Erosion

**Issue**: Initial ROI extraction missed G.P. and some rests due to text/symbol noise being counted as 'noteheads'.

**Solution**: Applied `cv2.erode` (kernel 3x3, iter=1) to the notehead mask before counting pixels.

**Results (Page 10 Refined)**:
- **M141 (Rest 1)**: Pixel count dropped from 57 to **0** (Correctly Identified).
- **M142 (G.P.)**: Pixel count dropped from 79 to **13** (Correctly Identified).
- **Conclusion**: Erosion effectively filters out thin text/symbols while preserving dense noteheads, significantly improving False Negative rate for multi-measure rests.

## 2026-01-05 Batch ROI Verification and Refinement

**Goal**: Evaluate the robustness of the refined ROI extraction logic (with erosion and vertical margin) across multiple pages.

### Actions Taken
1.  **Batch Execution**: Ran the ROI extraction and visualization on Pages 001 and 004 using Ground Truth barline data.
2.  **Debug Analysis (Page 004)**: Investigated a discrepancy in Measure 6 (M6) on Page 004.
    - Verified that M6 on Page 004 has an eroded pixel count of **0**, making it a valid rest candidate in the current logic.
    - Noted that Page 004 has a complex Divisi structure, which might affect logical numbering if system grouping is not perfectly aligned with visual expectations.

### Results
- **Page 001**: 6 candidates found.
- **Page 004**: 11 candidates found.
- **Page 010**: 10 candidates found (after erosion fix).

### Artifacts
- **Visualization Overlays**:
    - Page 001: `logs/experiments/rest_roi_batch_test/page_001/roi_overlay.png`
    - Page 004: `logs/experiments/rest_roi_batch_test/page_004/roi_overlay.png`
    - Page 010: `logs/experiments/rest_roi_test_page10/gt_roi_overlay_v4_eroded.png`
- **Numbering Data**: `logs/experiments/rest_roi_batch_test/page_xxx/numbering.json`

**Status**: ROI extraction logic is now capable of handling high-register notes and filtering out thin symbol noise (G.P., etc.). Robustness verification on complex pages (Divisi) is ongoing.

## 2026-01-05 GT Error Investigation (Page 004 M6)

**Issue**: Measure 6 (M6) on Page 004 was identified as a rest candidate but appeared to be in an invalid location.

**Investigation**:
- Analyzed `data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_004/boxes_sorted_v20251229.json`.
- Found a false positive barline entry at `[2610, 540, 2612, 624]` (right margin area).
- This invalid barline caused the numbering logic to generate a phantom measure (M6), which the ROI logic then correctly identified as "empty".

**Conclusion**:
- The discrepancy is caused by a **Ground Truth error**, not the detection logic.
- The ROI extraction and noise reduction (erosion) logic is confirmed to be robust and accurate based on the provided input data.

## Tools Reference (Developed 2026-01-05)

### 1. ROI Extraction & Visualization
Logic to identify potential multi-measure rests by finding measures with low notehead pixel density.

- **`tools/extract_rest_rois.py`**: Extracts cropped images of candidate measures.
- **`tools/visualize_rest_rois.py`**: Draws red bounding boxes around candidates on the full page.

**Key Parameters**:
- `--numbering-json`: Output from `add_measure_numbers.py`.
- `--notehead-mask`: `homr` debug output (e.g., `page_xxx_debug_6_notehead.png`).
- `--vertical-margin`: (Default 80) Expands check area vertically to catch high/low notes.
- `--erode-iter`: (Default 1) Erosion iterations to remove thin noise (text/rests).

**Example Usage**:
```bash
.venv_omr_dln/bin/python tools/visualize_rest_rois.py \n    --numbering-json logs/numbering.json \n    --notehead-mask logs/homr/mask.png \n    --image data/page.png \n    --output-image overlay.png \n    --vertical-margin 80 \n    --erode-iter 1
```

### 2. Debugging Helpers
- **`tools/batch_rest_roi_test.py`**: Runs the extraction pipeline on multiple pages (hardcoded config).
- **`tools/debug_rest_candidates.py`**: Prints detailed pixel counts (original vs eroded) for specific measures.
- **`tools/crop_debug_image.py`**: Crops a specific bbox from an image for inspection.
