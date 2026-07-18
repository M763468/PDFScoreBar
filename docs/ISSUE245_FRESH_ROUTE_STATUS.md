# Issue #245 fresh-route status

The production route uses fresh HOMR/SR/OMR inputs; retained historical detector or
candidate artifacts are not production inputs.

## Decisions

- Historical reproduction was not adopted as the primary goal. Focused probes ruled
  out the SR scale, evaluator revision, and retained SR working-image pixels as a
  sufficient explanation for the three fresh residuals.
- The fresh failures were traced to a staff mask reused as a clef mask, short
  current row geometry, existing-box suppression, and the paper-overlap heuristic
  on narrow ink lines.
- `aligned_expansion_rescue` is opt-in by default and enabled by canonical dense
  and Stage E configs. It runs a separate padded scan, accepts only sole
  `low_paper_overlap` drops aligned to an existing box, and emits at most one
  trimmed expansion per existing box.
- Trimmed geometry restored the focused Shostakovich and Sibelius targets with
  IoU 0.6369 and 0.6943. Generic paper-overlap threshold changes were not made.

## Reproduction

Focused candidate probe:

```bash
ISSUE245_MAIN_REPO_ROOT=/home/masaki_muramatsu/ws_PDFScoreBar \
PYTHONPATH=. /home/masaki_muramatsu/ws_PDFScoreBar/.venv_pdf/bin/python \
tools/issue245/run_aligned_expansion_candidate_probe.py --force
```

Focused CNN scoring:

```bash
PYTHONPATH=. /home/masaki_muramatsu/ws_PDFScoreBar/.venv_pdf/bin/python \
tools/issue245/run_focused_aligned_expansion_cnn.py \
--main-repo /home/masaki_muramatsu/ws_PDFScoreBar
```

Fresh full pipeline uses `configs/dense_full_pipeline.yaml`. Its image glob is
recursive because canonical Evaluation2 images are score-directory scoped.

## Full-68 blocker

The fresh run reached OMR-DLN after HOMR/SR preparation, then stopped because the
required model is absent at
`external/omr_dln/models/public_models/YOLOv8m_Measures.pt`. It was absent from
both the worktree and MAIN repository on 2026-07-19. No full-68 metric is claimed
until that model is restored and the fresh run is repeated.
