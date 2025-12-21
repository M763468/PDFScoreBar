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
