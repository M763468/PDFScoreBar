# PDFScoreBar user guide

## Requirements and installation

The primary installation route is Docker on Linux with an NVIDIA GPU, a working NVIDIA
Container Toolkit, host Python 3.12 or later, and sufficient disk space for CUDA/model
images and rendered PDF pages. Build needs network access; normal runs are offline.
The runtime image owns Python dependencies, maintained HOMR models, Real-ESRGAN models,
and the hash-verified barline CNN. The distribution contains the MMR checkpoint.

From the distribution root:

```bash
python3 docker/distribution.py build
```

Use `--image YOUR_TAG` before the command to select a separate image. The launcher checks
its production asset label, immutable image ID, and runtime compatibility fingerprint.
A successful build preserves source commit and fingerprint labels in the image.

OMR-DLN is an operator-supplied model. Obtain the selected `YOLOv8m_Measures.pt` from
the official model folder recorded in `models/omr_dln/manifest.json`. Import it once:

```bash
python3 -m src.common.model_artifacts import models/omr_dln/manifest.json /absolute/path/YOLOv8m_Measures.pt
python3 docker/distribution.py preflight
```

Import checks the manifest SHA-256 before publishing to the host model cache. Preflight
checks CUDA, the ONNX CUDA provider, required models, and pinned HOMR runtime provenance.
The external weight is mounted read-only into the runtime. To share a cache, set
`PDFSCOREBAR_MODEL_CACHE` on the host. Changing model bytes requires a new manifest/version.

## Process a PDF

```bash
python3 docker/distribution.py run /absolute/path/score.pdf --output /absolute/path/results
```

Optionally add `--pages 1 2` to process selected one-based PDF pages. Each job gets a new
directory under the output root. Its `final/` directory contains the numbered PDF;
`review/manual_correction_input.json` opens the correction application. `result.json`
records status, warnings, artifact hashes, and source provenance. Review-required status
means the generated result needs user attention.

Numbered PDFs retain the source PDF's visible page size, including cropping and
rotation, independently of render DPI or image resizing. Older review packages
may lack this size information: image DPI is used when available, otherwise a
warning reports a 300-DPI assumption. Reprocess the original PDF when its exact
paper size must be recovered from such a package.

Before using the numbered PDF, open the job's review application and follow the
[rest-count inspection procedure](#check-and-correct-multi-measure-rests), even
when the job succeeded without warnings. Job success is not a completed score review.

The local adapter binds the review handoff to a relocated retained-source manifest and
records the original manifest hash. The same preparation runs when opening a retained
local job.

Keep the entire output directory: the review package, source manifest, and retained engine
artifacts support correction and inspectable provenance. The launcher mounts input read-only
at `/input` and the output root at `/results`, using stable paths across sessions.
The supported dense route uses the canonical configuration; evaluation/GT files are unnecessary.

## Review and generate a corrected PDF

```bash
python3 docker/distribution.py review --output /absolute/path/results \
  --handoff /absolute/path/results/JOB_ID/review/manual_correction_input.json
```

Open `http://127.0.0.1:8010` in a browser on the same Linux host. Add `--port 8011` when
that port is occupied. The application binds only to localhost and uses Linux Docker host
networking. It is intended for local use. Select English or Japanese using the language control.

Review page images and numbering. Record barline, measure, or MMR changes using Save;
confirm any supplied movement-boundary evidence and finalize it before applying.
The application shows recorded and pending edits separately. Generate the corrected PDF
through the application, wait for completion, and use its result link to open/download it.
Pending edits and errors must be resolved before applying.

### Check and correct multi-measure rests

Treat automatic numbering as a draft to review before use. Compare **every printed
multi-measure-rest count on every page** with the application's measure count. An
unflagged result or a high recognition confidence does not establish a correct count.
Missed rests appear as ordinary measures with count 1; checking only detected rests
or warning-marked results will miss these errors. A boxed rehearsal number near a
rest can also be mistaken for its count.

1. Open the review application for the job as shown above. Use **Inspect all measures**
   (**全小節を確認**) in **Check multi-measure rests** (**複数小節休符を確認**).
   This selects the multi-measure-rest task and opens the current page's full measure
   list, including count-1 measures. Repeat the inspection on every page.
2. Read the original printed rest digit on the score. Zoom in or hide the overlays
   if they obscure it. Select its physical measure on the canvas or in the list;
   the selection shows the page, system, measure and original/current counts.
   Visible system/measure indices start at 1 and are locations, not musical numbers.
3. Choose **Set rest measure count** (**複数小節休符の小節数を設定**), enter the
   printed count, choose **Add change** (**修正を追加**), then **Save changes**
   (**変更を保存**). Use the same operation for a missed rest shown as 1 and a
   misread rest. If a normal measure was falsely treated as a multi-measure rest,
   choose **Do not treat as multi-measure rest** instead. Do not reset a movement
   or insert barlines merely to compensate for a rest-count error.
4. Generate and open the corrected PDF. Check the corrected rest's increment,
   subsequent row starts, and the next page start against independently counted
   score numbers. A change from an incorrect 37 to a printed 7 shifts later numbers
   by -30 until a separately specified numbering reset; checking only the edited
   box will miss downstream effects.
5. Retain the complete job and its saved changes and application attempt. A saved
   edit or successful PDF generation confirms persistence/application, not musical
   correctness. If a rest cannot be read, located or corrected reliably, leave its
   result unaccepted and report the page/location and the problem for follow-up.

This workflow depends on visual review; it does not guarantee that every error is
automatically flagged or that no rest is overlooked. Movement resets and barline
errors require their own review and corrections. Use the corrected output only
after those numbering checks also pass.

Corrections stay under the review package's `corrections/` directory. Each apply attempt
stores immutable input copies and consumed-input provenance under `application_runs/`.
Successful corrected PDFs are in each attempt's `corrected/final/` directory. Previous
successful output remains available after a failed attempt. Stop the server with Ctrl+C.

## Troubleshooting and provenance

- Build failure: retain the build output; check network access and disk space.
- Missing GPU/provider: verify GPU access in Docker and rerun preflight. Host GPU detection
  alone does not establish container CUDA availability.
- Missing or corrupt model: use the selected manifest and repeat verified import. A hash
  mismatch fails rather than selecting another model.
- Runtime mismatch: build this distribution with a separate image tag, then use that tag.
- Review/apply failure: preserve the entire job directory and read the reported application
  error. A moved or partially copied package may lack its original manifest/artifacts.
- English/Japanese UI: both dictionaries are local assets; no translation service is required.

Extracted distributions include `DISTRIBUTION_PROVENANCE.json`, with source commit, dirty
status and hashes for every shipped file. The machine-readable selection is
[MINIMAL_MAINLINE_SURFACE.json](MINIMAL_MAINLINE_SURFACE.json). Image labels, preflight JSON,
job `result.json`, and correction consumed-input records provide the remaining runtime/model
and result identity. A dirty extraction is a development candidate, not an immutable release.

## Distribution scope

The distribution uses the maintained dense PDF configuration. Standalone numbering CLI,
optional numbering overlays, probe diagnostic images and optional wide-candidate splitting
remain develop-only tools. Engine runtime provenance and debug telemetry remain available.

SR is generated by the dedicated batch process. Missing or invalid precomputed SR, corrupt
detection results, and missing required rescue seeds stop the job; they do not silently become
original-resolution images or empty detections. Valid empty predictions remain supported.
Page-local SR is an explicit develop-only mode and is not included in the distribution.
