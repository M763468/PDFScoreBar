# Issue #372: physical measure-count regression audit

## Decision and scope

The fresh evaluation2 68-page production run reported 3562 TP / 11 hard FP /
5 FN against the inherited D27 stroke-level comparison of 3565 / 1 / 2.
This historical detector metric comparison remains a recorded failure, but
is not the closure gate for this physical-count investigation. Its result is at
`logs/issue372/production_full68_validation_20260923T123514Z/production_full68_validation.json`.
The new FN are second strokes of merged double barlines, and the new FP are
staff-spanning detections corresponding to two staff-local GT strokes. See
`logs/issue372/detector_recovery/fresh68_residual_geometry_v3.json` and the
original-image crops in `logs/issue372/detector_recovery/visual/`.

For this issue, the deciding downstream check is physical measure count from
barline geometry. `evaluate_retained_physical_counts.py` sends the retained
detector boxes and evaluation2 GT **barline locations only** through the same
production builder and numberer, with identical source images and staff masks.
It does not use printed system-start measure numbers or insert resets. The
retained result, `logs/issue372/physical_count_audit/full68_v3.json`, matches
all system counts across all 68 pages: 3287 measures on each side. The maximum
interval-endpoint shift among 6574 endpoints is 14 px. Thus the stroke-level
metric regression did not propagate to physical measure count on this set.
This is not an independent annotation audit or proof for other scores.

No production detector/counting change is retained for #372. Reopen this
investigation if a page has a changed physical count or boundary topology.
MMR/OCR skip values and final *logical* numbering are separate, pre-existing
issues (notably #277 and #332), not acceptance gates for this count audit.
The experimental MMR and automatic movement-boundary implementation from this
worktree was removed; retained logs remain historical evidence, not an enabled
pipeline route.

## Reproduce the deciding check

Use the saved production report above, the evaluation2 source images and GT,
and the current repository's Python environment:

```bash
/home/masaki_muramatsu/ws_PDFScoreBar/.venv_pdf/bin/python -m \
  experiments.issue372.evaluate_retained_physical_counts \
  --report logs/issue372/production_full68_validation_20260923T123514Z/production_full68_validation.json \
  --repo /home/masaki_muramatsu/ws_PDFScoreBar_issue372 \
  --image-root /home/masaki_muramatsu/ws_PDFScoreBar/data/evaluation2/images \
  --gt-root /home/masaki_muramatsu/ws_PDFScoreBar/data/evaluation2/annotations \
  --output logs/issue372/physical_count_audit/full68_recheck.json
```

Choose an unused output filename for each rerun. The JSON records source and
input hashes, per-page/per-system counts, and interval shifts. The original
production run can be reproduced with `run_production_full68_validation.py`.

The worktree retains only this audit, the fresh-production validation runner,
and this summary. Earlier one-off diagnostics remain recoverable from Git
history at commit `36548e0b`; their retained reports and visual evidence were
not deleted. No new detector inference is needed to rescore the saved output.
