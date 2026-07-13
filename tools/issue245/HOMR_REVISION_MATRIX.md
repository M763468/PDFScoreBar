# HOMR revision matrix

## Boundary

The preserved `sr_eval_gpu` runtime is no longer available locally. Local Docker inspection found no container or image containing `/opt/venv_sr/bin/python`, and the remaining `my_pdf_pipeline` container does not contain that venv.

The retained artifact was generated on 2026-01-31 through the tracked evaluator route with `onnxruntime-gpu==1.22.0`. Upstream HOMR PR #58 merged on 2026-01-30 and replaced SegNet Unet++ model 155 with Unet model 308. Its exact anchors are:

- pre-merge main: `f1c2688efe7efb0aace96b06364022baf5c65e64`
- post-merge main: `2c6c65b00c836feb167d08c2553acec36ef68401`

The first source reconstruction therefore compares those two revisions before expanding to intermediate feature-branch models.

## Isolation

`Dockerfile.homr_revision_probe` starts from the current managed `pdfscore_pipeline_gpu` image and changes only:

1. installed HOMR source revision;
2. model files selected and downloaded by that revision;
3. ONNX Runtime GPU version, fixed to `1.22.0`.

HOMR is installed with `--no-deps`, so Python, OpenCV, NumPy and the remaining managed dependencies stay fixed. This is a source/model/ORT isolation experiment, not yet a complete reconstruction of the lost historical image.

The retained historical detection JSON is used only after fresh inference for comparison. It is never supplied to the detector.

## Run

Update the Issue #245 worktree, then run the two default anchors:

```bash
cd /home/masaki_muramatsu/ws_PDFScoreBar_issue245

.venv_cnn_classifier/bin/python \
  tools/issue245/run_homr_revision_matrix.py \
  --force
```

When the venv is activated, `python` may be used instead:

```bash
python tools/issue245/run_homr_revision_matrix.py --force
```

The command builds two temporary images, runs the canonical page through evaluator/default-thin, records provenance and model hashes, compares each result with the historical 87 records, and removes the temporary images.

Keep images for inspection only when necessary:

```bash
python tools/issue245/run_homr_revision_matrix.py \
  --force \
  --keep-images
```

Run a named candidate:

```bash
python tools/issue245/run_homr_revision_matrix.py \
  --candidate pre_unet_main \
  --force
```

Run every candidate, including intermediate feature revisions, only after the anchor result justifies it:

```bash
python tools/issue245/run_homr_revision_matrix.py \
  --all \
  --force
```

## Outputs

```text
logs/issue245_homr_revision_matrix/
  homr_revision_matrix_report.json
  pre_unet_main/
    docker_build.log
    provenance.json
    provenance.log
    evaluator.log
    evaluator/...
  post_unet_main/
    ...
```

The report ranks candidates by tolerant matches, then by total unmatched records.

## Decision

- If one anchor removes or sharply reduces the historical core `2 missing / 16 extra` difference, continue with that source/model family and reconstruct the remaining package/runtime variables.
- If the two anchors bracket the result, run the intermediate `301` and `303` candidates.
- If neither anchor changes the core difference materially, hold HOMR source/model fixed and move to the historical evaluator/preprocessing ref.
- Do not run full-68 or change a production default from this matrix alone.
