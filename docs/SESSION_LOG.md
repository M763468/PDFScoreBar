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
