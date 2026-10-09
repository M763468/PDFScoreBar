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
