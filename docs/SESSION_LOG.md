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
## Session Notes (2025-12-22) — Detector-miss near-hit recheck

- Generated near-hit review overlays with relaxed tolerance (TOL_X=12px, TOL_Y=8px; crop margins 40x60px).
- Output overlays: `logs/phase6_detector_miss/near_hit_review/<page>/fn_*.png`.
- Classification tables: `logs/phase6_detector_miss/near_hit_review/near_hit_classification.csv` and `.md`.
- Category breakdown: `logs/phase6_detector_miss/near_hit_review/near_hit_summary.csv` and `.md`.
- Aggregate counts: true_detector_miss=11, near_hit_gt_misaligned=19, ambiguous=5.

---
