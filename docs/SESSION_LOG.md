---
## Phase 5b Completed

Phase 5b (merge / hybrid investigation) is closed. See `docs/NEXT_SESSION_NOTES.md` for the finalized summary and reusable assets.

---
## Session Start

- Detector-miss FN recovery phase begins here.

---
## Phase 6: Detector-miss FN analysis (visual review + coarse classification)

### Detector-miss target set
- Source: `logs/phase5b/trace_stage_analysis/20251221T222504/fn_trace_table.csv`
- Criteria: `in_baseline=False`, `in_sr=False`, `in_omr=False`
- Confirmed detector-miss count: **35**

### Visual review artifacts
- Crops + overlays: `logs/phase6_detector_miss/visual_review/<page>/fn_<gt_index>.png`
- Per-page montage: `logs/phase6_detector_miss/visual_review/<page>/montage_<page>.png`

### Classification outputs
- `logs/phase6_detector_miss/detector_miss_classification.csv`
- `logs/phase6_detector_miss/detector_miss_classification.md`
- Category counts: `logs/phase6_detector_miss/detector_miss_category_counts.csv`
- Category counts (md): `logs/phase6_detector_miss/detector_miss_category_counts.md`

### Category counts (35 total)
| category | count |
| --- | --- |
| end_barline | 15 |
| text_dynamic_overlap | 7 |
| dense_chord_accidental | 6 |
| notehead_overlap | 5 |
| double_or_repeat_bar | 2 |

### Notes / hypotheses (exploratory)
- **end_barline**: misses cluster at staff-end bars; possible detector-side fix could bias toward right-margin verticals or add a staff-end prior.
- **text_dynamic_overlap**: collisions with lyrics/dynamics; consider text/lyrics masking or joint symbol segmentation.
- **dense_chord_accidental / notehead_overlap**: occlusion by dense noteheads/accidentals; potential benefit from structural priors or gap-filling along staff lines.
- **double_or_repeat_bar**: special symbols may need explicit template/class handling.

---
## Phase 6 Plan: Detector-miss FN cleanup and GT validation

### 1) GT quality verification
- Hypothesis: some detector-miss FNs are false misses caused by GT bbox misalignment (offsets, height errors, divisi cases).
- Plan: identify suspicious detector-miss GTs from visual review and separate true misses vs near-hit/misaligned GT.

### 2) GT relabeling strategy (selective)
- Do not relabel all GT; only suspicious cases.
- Relabel on enlarged images (2x–4x scale), then map corrected bboxes back to original coordinates.
- Use staff-space and stem-contact cues as visual guides.

### 3) Rebuild detector-miss set
- After GT corrections, recompute the detector-miss FN set.
- Re-run coarse classification on the cleaned set.
- Use the cleaned set for detector-side changes and future trials.

### 4) Detector-side work (future, not now)
- Only after GT quality is validated: consider detector parameter changes, additional detectors, or structural candidate generation.

---
## Session Notes (2025-12-22)

- Read `README.md`, `docs/README.md`, and `docs/NEXT_SESSION_NOTES.md` for current goals, documentation map, and confirmed state.
- No new confirmations yet; no updates made to `docs/NEXT_SESSION_NOTES.md`.

---
## Session Notes (2025-12-25) — Detector-miss FN review

- Confirmed detector-miss FN count: 35 (page_10=9, page_15=15, page_001=1, page_004=10) from `logs/phase5b/trace_stage_analysis/20251221T222504/fn_trace_table.csv`.
- Visualization artifacts verified: `logs/phase6_detector_miss/visual_review/<page>/fn_*.png` (35 total; per-page montages present).
- Classification outputs (coarse buckets): `logs/phase6_detector_miss/detector_miss_classification.csv` and `logs/phase6_detector_miss/detector_miss_classification.md`.
- Category counts: `logs/phase6_detector_miss/detector_miss_category_counts.csv`.

---
## Phase 6: GT relabel tool smoke test (2025-12-25 JST)

- Fix: SyntaxError in `tools/gt_relabel_support.py` caused by escaped quotes (\"image\"); corrected to normal quotes.
- Change: added optional `--limit` flag for `prepare` to enable a tiny smoke test.
- Smoke test command:
  - `. .venv_omr_dln/bin/activate && python tools/gt_relabel_support.py prepare --candidates logs/phase6_detector_miss/gt_fix_plan/gt_fix_candidates.csv --limit 2`
- Outputs created:
  - `logs/phase6_detector_miss/gt_fix_review/page_10/fn_010/crop_x4.png`
  - `logs/phase6_detector_miss/gt_fix_review/page_10/fn_010/edit_template.json`
  - `logs/phase6_detector_miss/gt_fix_review/page_10/fn_018/crop_x4.png`
  - `logs/phase6_detector_miss/gt_fix_review/page_10/fn_018/edit_template.json`

---
## Phase 6: GT relabel GUI added (2025-12-25 JST)

- Added minimal browser-based bbox editor: `tools/gt_relabel_gui/server.py`, `tools/gt_relabel_gui/index.html`, `tools/gt_relabel_gui/app.js`.
- Run command:
  - `python3 tools/gt_relabel_gui/server.py --root logs/phase6_detector_miss/gt_fix_review --port 8010 --host 0.0.0.0`
- Edits are saved back into each `edit_template.json` (status + edited_bbox), keeping other fields intact.
- Smoke confirmation (test copy):
  - Root: `logs/phase6_detector_miss/gt_fix_review_test`
  - Save call updated `logs/phase6_detector_miss/gt_fix_review_test/page_10/fn_010/edit_template.json` to status=edited, edited_bbox=[11, 22, 33, 44].

---
## Phase 6: GT relabel GUI usability fixes (2025-12-25 JST)

- Fixes: added display scale control, corrected canvas sizing/drawing to respect scale, and added debug mode with coordinate readouts + hit-test logs.
- Interaction: bbox drag/resize now uses display-space hit-testing and maps back to raw x4 coords; handles and stroke are fixed-size in screen pixels.
- UI: legend clarified (pink GT editable, green detector reference), green boxes toggle, debug panel/log.
- How to verify: enable Debug, click bbox (log shows inside/handle), drag to update bbox and observe raw/display coords update, then Save.

---
## Phase 6: Apply GUI edits + near-hit recheck (2025-12-25 JST)

- Sanity check: scanned `logs/phase6_detector_miss/gt_fix_review/**/edit_template.json`.
  - Status counts: edited=24, unchanged=0, invalid=0, pending=0.
  - No format issues detected (edited_bbox present and within crop bounds).
- Applied edits (corrected GT):
  - `. .venv_omr_dln/bin/activate && python3 tools/gt_relabel_support.py apply --candidates logs/phase6_detector_miss/gt_fix_plan/gt_fix_candidates.csv --out-root logs/phase6_detector_miss/gt_fix_review --corrected-root logs/phase6_detector_miss/gt_fix_review/gt_corrected`
  - Outputs: `logs/phase6_detector_miss/gt_fix_review/gt_corrected/<page>/fn_only_corrected.json`, `logs/phase6_detector_miss/gt_fix_review/gt_corrected/diff_summary.csv`
- Near-hit recheck (corrected GT):
  - `. .venv_omr_dln/bin/activate && python3 tools/gt_relabel_support.py near-hit --candidates logs/phase6_detector_miss/gt_fix_plan/gt_fix_candidates.csv --corrected-root logs/phase6_detector_miss/gt_fix_review/gt_corrected --out-root logs/phase6_detector_miss/gt_fix_review/near_hit_recheck`
  - Outputs: `logs/phase6_detector_miss/gt_fix_review/near_hit_recheck/near_hit_recheck.csv`, `near_hit_recheck_summary.json`
- Counts (after correction, full detector-miss set): true_detector_miss=11, near_hit_gt_misaligned=19, ambiguous=5 (unchanged).
- Report: `logs/phase6_detector_miss/gt_fix_review/RECHECK_REPORT.md` (includes per-item delta table, remaining true misses list).
