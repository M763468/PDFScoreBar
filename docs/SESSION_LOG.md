---
## 2025-12-21 Session Start (Phase 5b Planning)

**Working Tree Status**: Option A chosen.
- `git status` check showed only `docs/NEXT_SESSION_NOTES.md` and `docs/SESSION_LOG.md` were modified.
- No partial code changes from interrupted runs found.
- Proceeding from current HEAD.

---
## Phase 5a History (Preserved)

### 2025-12-20 Phase 5a Start (FN Attribution)

**Goal**:
- Select page(s) for FN-only partial GT.
- Verify GT creation tooling (FN-only workflow).
- Plan FN attribution runs.

**1. Page Selection**:
- data/training/images/page_10.png
- data/training/images/page_15.png
- data/evaluation2/images/Va_Prokofiev_Symphony1/page_001.png
- data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png

**2. GT Tooling Verification**:
- Verified `coordinate_annotator.py`, `sort_measures.py`, `render_barline_boxes_overlay.py`.
- Created annotation directories.

**3. FN Attribution Plan**:
- Attribute each bbox in `fn_only.json` to: `homr miss`, `omr-dln miss`, or `hybrid_integration_loss`.

### 2025-12-21 Maintenance: Processed Manual FN-only GT

**Actions**:
- Standardized user-provided raw JSONs into canonical `fn_only.json` for the 4 target pages.
- Generated overlays to verify.
- Phase 5a unblocked.

### 2025-12-21 Phase 5a Results (FN Attribution)

**Summary**:
- ~92% of FNs are "ambiguous" (missed by both detectors).
- ~8% are "hybrid_integration_loss".
- Post-filter removal is negligible.

**Conclusion**: FN is fundamentally a detector / candidate-generation problem.

---
\n## Session \n- Read README.md, docs/README.md, docs/NEXT_SESSION_NOTES.md. Ready to proceed.

## Phase 5b B1.1 homr recall relaxation (2025-12-21)

- Checked docs/ENVIRONMENTS.md: homr eval must run in `homr_eval_gpu`.
- Found existing artifacts in `logs/phase5b_homr_recall/` with runs:
  - `homr_factor_1p0`: `--barline-min-height-factor 1.0` (max-width 1.0)
  - `homr_factor_0p8`: `--barline-min-height-factor 0.8` (max-width 1.0)
  - `homr_factor_0p6`: `--barline-min-height-factor 0.6` (max-width 1.0)
- FN-only recovery summary (IoU 0.5):
  - page_10: TP 15/24 (FN 9) for 1.0/0.8/0.6 (no change).
  - page_15: TP 7/22 (FN 15) for 1.0/0.8/0.6 (no change).
  - page_001: TP 0/6 (FN 6) for 1.0/0.8/0.6 (no change).
  - page_004: TP 0/12 (FN 12) for 1.0/0.8/0.6 (no change).
- Regression guard (page_3):
  - 1.0: TP=152 FP=30 FN=0 (not FP-clean; baseline not filtered here).
  - 0.8: TP=152 FP=34 FN=0.
  - 0.6: TP=150 FP=62 FN=2 (regression vs required TP=152 FP=0 FN=0 after full pipeline).
- FP risk: substantially higher predictions in all runs; 0.6 introduces clear regression on page_3.


## Phase 5b B1.1 OMR-DLN sweep + raw union (2025-12-21)

- Run root: `logs/phase5b/b1_1/omrdln_sweep/20251221T123707/`
- Homr raw baseline for union: `logs/phase5b_homr_recall/homr_factor_1p0/*/*_detections.json`
- Conf grid: 0.1, 0.2, 0.3, 0.4, 0.5
- OMR-DLN command (per image/conf):
  - `python experiments/models/eval_omr_dln.py --image <img> --gt <gt> --output-dir <out_dir> --conf <conf>`
- Command log with runtimes: `logs/phase5b/b1_1/omrdln_sweep/20251221T123707/omr_dln_commands.log`
- Summary artifacts:
  - `logs/phase5b/b1_1/omrdln_sweep/20251221T123707/summary.json`
  - `logs/phase5b/b1_1/omrdln_sweep/20251221T123707/summary_table.md`

### Summary table (FN-only recovery + page_3 raw FP)
| Variant | page_10 TP | page_15 TP | page_001 TP | page_004 TP | FN total | page_3 FP | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| omr-dln conf=0.1 | 7 | 7 | 5 | 3 | 42 | 20 |  |
| union(homr, omr-dln) conf=0.1 | 7 | 7 | 5 | 3 | 42 | 154 |  |
| omr-dln conf=0.2 | 7 | 7 | 5 | 3 | 42 | 18 |  |
| union(homr, omr-dln) conf=0.2 | 7 | 7 | 5 | 3 | 42 | 152 |  |
| omr-dln conf=0.3 | 7 | 7 | 5 | 3 | 42 | 17 |  |
| union(homr, omr-dln) conf=0.3 | 7 | 7 | 5 | 3 | 42 | 151 |  |
| omr-dln conf=0.4 | 7 | 7 | 5 | 3 | 42 | 17 |  |
| union(homr, omr-dln) conf=0.4 | 7 | 7 | 5 | 3 | 42 | 151 |  |
| omr-dln conf=0.5 | 7 | 7 | 5 | 3 | 42 | 17 |  |
| union(homr, omr-dln) conf=0.5 | 7 | 7 | 5 | 3 | 42 | 151 |  |

### Quick readout
- OMR-DLN recall is flat across conf values on FN-only pages (TP total = 22/64). No FN recovery improvement vs homr baseline.
- Raw union with homr does not increase FN recovery (same TP as OMR-DLN alone) and causes high raw FP on page_3 (151–154).
- No runtime errors detected in command log.


### Correction (union evaluation)
- Updated union evaluation to use homr `orig_bbox` (matches homr evaluator). Recomputed summary:

| Variant | page_10 TP | page_15 TP | page_001 TP | page_004 TP | FN total | page_3 FP | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| omr-dln conf=0.1 | 7 | 7 | 5 | 3 | 42 | 20 |  |
| union(homr, omr-dln) conf=0.1 | 16 | 12 | 5 | 3 | 28 | 50 |  |
| omr-dln conf=0.2 | 7 | 7 | 5 | 3 | 42 | 18 |  |
| union(homr, omr-dln) conf=0.2 | 16 | 12 | 5 | 3 | 28 | 48 |  |
| omr-dln conf=0.3 | 7 | 7 | 5 | 3 | 42 | 17 |  |
| union(homr, omr-dln) conf=0.3 | 16 | 12 | 5 | 3 | 28 | 47 |  |
| omr-dln conf=0.4 | 7 | 7 | 5 | 3 | 42 | 17 |  |
| union(homr, omr-dln) conf=0.4 | 16 | 12 | 5 | 3 | 28 | 47 |  |
| omr-dln conf=0.5 | 7 | 7 | 5 | 3 | 42 | 17 |  |
| union(homr, omr-dln) conf=0.5 | 16 | 12 | 5 | 3 | 28 | 47 |  |
- Consulted `docs/ENVIRONMENTS.md` for environment and logs/ conventions before cleanup.

## Phase 5b B2 union→Phase4 filter check (2025-12-21)

- Consulted `docs/ENVIRONMENTS.md` before running filters.
- Run root: `logs/phase5b/b2_phase4_filter_check/20251221T132439/`
- Union source inputs:
  - homr raw: `logs/phase5b_homr_recall/homr_factor_1p0/<page>/*_detections.json`
  - omr-dln raw: `logs/phase5b/b1_1/omrdln_sweep/20251221T123707/omr_dln/conf_0p5/<page>/predictions.json`
  - union builder: `experiments/phase5b_b2_phase4_filter_check/build_union_inputs.py`
- Phase4 filter entry point: `experiments/fp_reduction/analyze_staff_consistency.py`
- Baseline (page_3):
  - `python experiments/fp_reduction/analyze_staff_consistency.py --json logs/hybrid_results.json --image data/evaluation/images/page_3.png --gt data/evaluation/annotations/page_003/boxes_sorted.json --output logs/phase5b/b2_phase4_filter_check/20251221T132439/baseline_page3 --no-use-ratio-tolerance --tol-top-px 5 --tol-bottom-px 5 --staff-space 8.7 --enable-geom-notehead-filter --geom-notehead-mode page3_known_fp --homr-context-dir logs/homr_eval_baseline/baseline_verification/page_3`
  - Note: needed `.venv_pdf` for `cv2`.
- Union page_3: same command with `--json logs/phase5b/b2_phase4_filter_check/20251221T132439/union_inputs/page_3_union.json` and output `.../union_page3`.
- Union FN-only pages: row filter only (geom notehead disabled) with `--no-use-ratio-tolerance --tol-top-px 5 --tol-bottom-px 5`, outputs under `.../union_fn_pages/`.
- Summary table: `logs/phase5b/b2_phase4_filter_check/20251221T132439/summary_table.md`
- Overlay outputs:
  - `logs/phase5b/b2_phase4_filter_check/20251221T132439/overlays/page_3_union_phase4_fp.png`
  - `logs/phase5b/b2_phase4_filter_check/20251221T132439/overlays/page_3_union_phase4_all_with_fp_highlight.png`
  - `logs/phase5b/b2_phase4_filter_check/20251221T132439/overlays/README.md`

| Variant | page_3 final FP | page_3 TP/FN | FN-only recovery (post-Phase4) | Notes |
| --- | --- | --- | --- | --- |
| Baseline Phase4 (page_3) | 0 | 152/0 | n/a | Phase4 repro via analyze_staff_consistency |
| Union→Phase4 (page_3) | 26 | 152/0 | n/a | union inputs, geom notehead enabled |
| Union→Phase4 (FN-only pages) | n/a | n/a | 34/64 | geom notehead disabled; row filter only |

Interpretation: union inputs do not preserve FP=0 after Phase4 on page_3 (FP=26). FN-only recovery drops to 34/64 after row filtering.

## Phase 5b generalized geom notehead filter (Phase5-only eval) (2025-12-21)

- Masks located (no new homr runs):
  - page_3: `logs/phase5b_homr_recall/homr_factor_1p0/page_3/page_3_debug_6_notehead.png`
  - page_10: `logs/phase5b_homr_recall/homr_factor_1p0/page_10/page_10_debug_6_notehead.png`
  - page_15: `logs/phase5b_homr_recall/homr_factor_1p0/page_15/page_15_debug_6_notehead.png`
  - page_001: `logs/phase5b_homr_recall/homr_factor_1p0/page_001/page_001_debug_6_notehead.png`
  - page_004: `logs/phase5b_homr_recall/homr_factor_1p0/page_004/page_004_debug_6_notehead.png`
- Union inputs (no detector reruns):
  - `logs/phase5b/union_inputs/20251221T141710/<page>_union.json`
  - built from homr `logs/phase5b_homr_recall/homr_factor_1p0/<page>/*_detections.json` + omr-dln `logs/phase5b/b1_1/omrdln_sweep/20251221T123707/omr_dln/conf_0p5/<page>/predictions.json`
- Phase5-only script:
  - `experiments/phase5b_notehead_geom/run_union_notehead_geom_eval.py`
  - defaults: endpoint_ratio_threshold=0.1, endpoint_radius_scale=0.6, row tol=5px
- Command:
  - `python experiments/phase5b_notehead_geom/run_union_notehead_geom_eval.py --run-root logs/phase5b/notehead_geom_eval/20251221T141710 --union-root logs/phase5b/union_inputs/20251221T141710`
  - Required `.venv_pdf` for cv2.
- Outputs:
  - `logs/phase5b/notehead_geom_eval/20251221T141710/summary_table.md`
  - Overlays: `logs/phase5b/notehead_geom_eval/20251221T141710/overlays/`

| Page | TP | FP | FN | kept | rejected |
| --- | --- | --- | --- | --- | --- |
| page_3 | 151 | 24 | 1 | 460 | 20 |
| page_10 | 15 | 441 | 9 | 481 | 0 |
| page_15 | 11 | 319 | 11 | 344 | 0 |
| page_001 | 4 | 220 | 2 | 229 | 2 |
| page_004 | 3 | 307 | 9 | 321 | 0 |
| FN-only total | 33 | n/a | 31 | n/a | n/a |

Interpretation: generalized ratio filter did not preserve page_3 baseline (TP=151, FP=24, FN=1) and FN-only recovery dropped to 33/64. Requires visual review of overlays.

## Phase 5b2 analysis/visualization hygiene (2025-12-21)

- Analysis folder: `logs/phase5b/notehead_geom_eval/20251221T141710/analysis_20251221T145756/`
- Overlays README: `logs/phase5b/notehead_geom_eval/20251221T141710/analysis_20251221T145756/overlays/README.md`
- Stage counts: `logs/phase5b/notehead_geom_eval/20251221T141710/analysis_20251221T145756/stage_counts.md`
- Margin breakdown: `logs/phase5b/notehead_geom_eval/20251221T141710/analysis_20251221T145756/fp_margin_breakdown.md`

| Page | union_raw | row_kept | row_rejected | geom_kept | geom_rejected | matched | unmatched | fn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| page_3 | 504 | 480 | 24 | 460 | 20 | 151 | 24 | 1 |
| page_10 | 548 | 481 | 67 | 481 | 0 | 15 | 441 | 9 |
| page_15 | 384 | 344 | 40 | 344 | 0 | 11 | 319 | 11 |
| page_001 | 257 | 231 | 26 | 229 | 2 | 4 | 220 | 2 |
| page_004 | 370 | 321 | 49 | 321 | 0 | 3 | 307 | 9 |
