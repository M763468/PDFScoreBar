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
- The OMR-DLN weight is an externally distributed model, not a project training
  output. The required `YOLOv8m_Measures.pt` is the measure-detection YOLOv8m
  artifact from [dmgonzalez8/OMR](https://github.com/dmgonzalez8/OMR)'s
  [official Google Drive folder](https://drive.google.com/drive/folders/13Z64ReEJGlMnCqPkA-dcCD8tzdtvLyqO?usp=sharing).
  It is stored once outside the worktree and selected with `OMR_DLN_MODEL_PATH`.
  The normal repository-relative path remains the compatible default, and a
  missing-weight error prints the official download/rename/override instructions.

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

Fresh score-isolated Stage E route (prevents repeated `page_001` stems from
colliding across scores):

```bash
docker run --rm --gpus all \
  -v "$WT:/workspace" \
  -v "$MAIN/data:/workspace/data:ro" \
  -v "$MAIN_MODEL:/models/YOLOv8m_Measures.pt:ro" \
  -v "$MAIN_SR_MODEL:/workspace/external/realesrgan/weights/RealESRGAN_x2plus.pth:ro" \
  -v "$MAIN_CNN:/workspace/logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth:ro" \
  -e OMR_DLN_MODEL_PATH=/models/YOLOv8m_Measures.pt \
  -e PYTHONPATH=/workspace -w /workspace pdfscore_pipeline_gpu \
  /opt/venv_pipeline/bin/python tools/issue245/run_fresh_stage_e_full68.py \
  --output-root logs/issue245_fresh_stage_e_full68/run_1
```

`MAIN_SR_MODEL` is the official `RealESRGAN_x2plus.pth` release asset. It is also
an ignored external weight and must be read-only mounted for a clean worktree.

## Focused fresh-route blocker (2026-07-19)

The official OMR-DLN model was restored and loaded successfully as an OMR
`detect` model (including `systemMeasure` and `staffMeasure` classes, not COCO).
A fresh x2 SR/HOMR/OMR/hybrid run for `Va_Prokofiev_Symphony1` completed with
six/ six components present; no historical detector or candidate artifact was
used.

The focused `page_004` primary path recovered the first historical detector
target `[847,2490,854,2591]` (CNN score `0.9999963`) but did not generate a
candidate for `[847,2675,854,2776]`. The same-file staff/clef rejection is
covered by an actual same-file symlink test and falls back to no clef mask when
no distinct mask exists; the fresh producer had no clef-mask file, so this
remaining target is not a same-file-clef-filter drop.

Enabling the trimmed aligned-expansion pass in this fresh run selected 131
candidates for 155 existing boxes, added all 131, and yielded 2 focused false
positives. It still did not produce the remaining detector target. This violates
the rescue safety contract, so a full-68 result is intentionally not claimed and
the runner must not be used for a release regression until a narrower,
source-general selection condition has been validated.
