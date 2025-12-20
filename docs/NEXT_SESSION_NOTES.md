# Next Session Notes

**Last Updated**: 2025-12-20  
**Current Phase**: Phase 5 (FN Attribution & Recovery)

---
### Note for AI Assistant (Operational Rule)
- The `docs/SESSION_LOG.md` file must **not** be completely overwritten. During a session, new findings and logs should be appended, or only relevant sections should be edited. The file should only be cleared with explicit user permission.
---

## Phase 5 — FN Attribution & Recovery (Current Plan)

### Confirmed Context (Phase Transition)
- **Phase 4 is complete (FP reduction)**: FP problem is effectively solved on `page_3` with **FP=0 and FN=0**, and cross-dataset review indicates the rule is conservative and does **not** introduce new FNs.
- **FN is a new upstream problem**: remaining FN cases observed in cross-dataset validation are **not caused by the Phase 4b geometry filter** (it did not trigger on those pages).

### Phase 5a — FN Attribution (Next Actions)
**Goal**: Create FN-only partial GT for a limited page set, then attribute each FN to an upstream cause.

1) **Select a limited page set (where FN is observed)**
- Training (same work): `data/training/images/page_10.png`, `data/training/images/page_15.png`
- Evaluation2 (new work/publisher): `data/evaluation2/images/Va_Prokofiev_Symphony1/page_001.png`, `.../page_004.png`

2) **Create partial GT (FN-only)**
- For each page, create an FN-only JSON containing **only missing barline bboxes**.
- Keep FN-only GT separate from any full GT (this is for attribution/recovery, not a full benchmark).

3) **Attribute each FN bbox (one of)**
- **homr miss**: missing from homr baseline detections.
- **omr-dln miss**: missing from omr-dln predictions.
- **hybrid integration loss**: present in a detector output but absent from hybrid predictions (consensus rule).
- **row/context filter removal**: present in hybrid predictions but removed by row filtering or later filters.

**Deliverable**: per-page FN attribution table (one row per FN bbox) linking to visual overlays and intermediate JSONs.

### Phase 5b — FN Recovery Strategies (After Attribution)
**Goal**: Recover FN per category while preserving Phase 4 FP guarantees.

- **homr miss**: homr parameter tuning / SR enablement, controlled preprocessing variants, conservative detector fallback/union.
- **omr-dln miss**: confidence/SR tuning, conservative fallback detector for sparse layouts, model swap only if unavoidable.
- **hybrid integration loss**: revise consensus gating and matching robustness (coordinate representation / near-match handling).
- **row/context filter removal**: conditional bypass/relaxation tied to FN-only GT evidence; avoid global loosening.

### Phase 5c — Verification Strategy
**Goal**: Verify “FN recovered without FP regression” without requiring full GT on every dataset.

- **Primary (FN-only GT)**: count FN-only GT boxes matched by final predictions on the selected pages.
- **Hard regression guard**: keep `page_3` as a full-GT regression test and require **TP=152, FP=0, FN=0** to remain true.
- **Qualitative guard (no GT pages)**: overlays must show no obvious new stem-like FPs in dense note regions.

### GT Tooling (Planning Reference; Do Not Execute Here)
**Existing page_3 GT workflow (reusable for FN-only GT)**
- Manual annotation: `tools/coordinate_annotator.py` → draft JSON (dict records with `barline_location`).
- Promote + ordering: draft → `raw_boxes.json`, then `tools/sort_measures.py` → `boxes_sorted.json`.
- Visual verification: `tools/render_barline_boxes_overlay.py --base <page.png> --boxes <boxes_sorted.json> --output <overlay.png>`.

**FN-only partial GT using the same workflow**
- Annotate **only missing barlines** into a page-specific draft JSON.
- Optionally generate `boxes_sorted.json` for consistent ordering (treat `measure_number` as an “FN id” if convenient).
- Verify via overlay renders before using it for attribution/recovery checks.

---
## Completed Phases (Short Summary)

### Phase 3 ✅ COMPLETE (Row-Consistency Filter)
- Confirmed baseline on `page_3` hybrid detections: **TP=152, FP=2, FN=0**.
- Durable details: `docs/DEVELOPMENT_LOG.md`, `docs/fp_reduction/FINAL_SUMMARY.md`.

### Phase 4 ✅ COMPLETE (FP Reduction)
- Confirmed `page_3`: **TP=152, FP=0, FN=0**.
- Cross-dataset review: geometry rule is conservative and **does not introduce new FNs**; FN is treated as upstream.
- Durable details and commands: `docs/DEVELOPMENT_LOG.md`.

---
## Historical / Superseded Notes (Kept for Context)

- Phase 4b “generalization without TP loss” planning is superseded by Phase 5 and kept only as context.
- Known-unsafe (historical lesson): “any overlap” hard rejection with expansive/combined masks can cause massive FN; do not revive.
- Hybrid-baseline provenance note: treat hybrid detector composition and matching assumptions as explicit variables when attributing FN upstream.
