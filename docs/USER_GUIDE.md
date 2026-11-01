# PDFScoreBar user guide

[日本語](USER_GUIDE.ja.md)

## Obtain the distribution

`main` is the stable minimal distribution; `develop` is the development integration
branch. A change merged to `develop` does not appear on `main` until a separate release
promotion. In particular, this guide's updates reach `main` only after promotion. If you
already have a verified extracted distribution, use its root directory instead of cloning.

On the Linux host, install Git using your distribution's package manager or the
[Git installation instructions](https://git-scm.com/install/linux). Then open a terminal:

```bash
git clone --branch main --single-branch https://github.com/M763468/PDFScoreBar.git
cd PDFScoreBar
```

All following commands run from this distribution root on the host. The Git checkout
may be inspected with Git; extracted distributions instead include provenance metadata.
For the documentation currently on `develop`, use a development checkout deliberately;
it is not the stable distribution.

## Prepare the host

Use Linux with an NVIDIA GPU and a compatible NVIDIA driver. Install the driver using
[the NVIDIA driver instructions](https://docs.nvidia.com/datacenter/tesla/driver-installation-guide/choose-an-installation-method.html)
and your distribution's guidance. Install [Docker Engine for Linux](https://docs.docker.com/engine/install/),
start its daemon, then install and configure the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
for Docker. Follow the instructions appropriate to your Linux distribution and privileges;
these links do not imply that every OS or GPU combination is supported by PDFScoreBar.
Install host Python 3.12 or later using your distribution's packages or
[Python's downloads](https://www.python.org/downloads/); if `python3` points to an older
version, use the 3.12+ executable in every command below instead.

Check the host and Docker access (the last command downloads a test image if needed):

```bash
python3 --version
nvidia-smi
docker info
docker run --rm --runtime=nvidia --gpus all ubuntu nvidia-smi
```

The last command follows NVIDIA's [sample workload](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/sample-workload.html).
If host `nvidia-smi` fails, check the driver and GPU first; if it works but the container
fails, check toolkit installation, Docker runtime configuration and daemon restart. If
`docker info` cannot connect, start the daemon or resolve socket permissions using
[Docker's Linux post-install guide](https://docs.docker.com/engine/install/linux-postinstall/).
Membership in the `docker` group grants root-level privileges; understand that choice
before enabling it. The launcher invokes Docker as the current user. Its containers can
write files owned by the container user (often root), so ensure the output filesystem
has space and that you can retain and read the resulting files; consult your administrator
about ownership rather than recursively changing unrelated files.

These checks establish host and container access only, not PDFScoreBar compatibility.
Build requires network access and enough disk space for image layers and models; processing
also needs space for rendered pages and retained artifacts. No minimum VRAM is claimed.

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
A successful build preserves source commit and fingerprint labels in the image. An image
is the built runtime template, not the temporary container created for a command. The
default image tag is `pdfscore_pipeline_gpu`; when choosing another tag, pass the same
`--image YOUR_TAG` before each `build`, `preflight`, `run` and `review` subcommand.

OMR-DLN is an operator-supplied model, not included or automatically downloaded. Open
the [official model folder](https://drive.google.com/drive/folders/13Z64ReEJGlMnCqPkA-dcCD8tzdtvLyqO?usp=sharing)
listed in `models/omr_dln/manifest.json` and manually download `YOLOv8m_Measures.pt`.
The selected version is `phase1-validated-v1`; its manifest SHA-256 is
`00d0bd8b399ae872f029eb38ed3985fcef33ca81cae414992b5cdb9062e91212`.
The upstream repository does not publish an explicit license for automated redistribution.
If the folder is inaccessible, check its access with the upstream provider; do not substitute
unverified weights. Replace the example path below with the downloaded file's absolute path
and import once:

```bash
python3 -m src.common.model_artifacts import models/omr_dln/manifest.json /absolute/path/YOLOv8m_Measures.pt
python3 docker/distribution.py preflight
```

Import checks the manifest SHA-256 before publishing to the host model cache. Preflight
checks CUDA, the ONNX CUDA provider, required models, and pinned HOMR runtime provenance.
The external weight is mounted read-only into the runtime. To share a cache, set
`PDFSCOREBAR_MODEL_CACHE` on the host. The default cache root is
`~/.cache/pdfscorebar/models`; when `XDG_CACHE_HOME` is set, it is
`$XDG_CACHE_HOME/pdfscorebar/models` unless `PDFSCOREBAR_MODEL_CACHE` overrides it.
A file with the same name but different bytes fails the hash check; obtain the selected
bytes from upstream and retry, rather than bypassing verification. Changing model bytes
requires a new manifest/version. Build success alone does not check the external model or
GPU; preflight checks them but does not certify score accuracy.

## Process a PDF

```bash
python3 docker/distribution.py run /absolute/path/score.pdf --output /absolute/path/results
```

Replace the PDF and output examples with absolute paths on your host. The output directory
must be writable and outside the distribution root. Optionally add `--pages 1 2` to process selected one-based PDF pages. Each job gets a new
directory under the output root. Its `final/` directory contains the numbered PDF;
`review/manual_correction_input.json` opens the correction application. `result.json`
records status, warnings, artifact hashes, and source provenance. Review-required status
means the generated result needs user attention. The command prints JSON containing
`job_id`; use that value as `JOB_ID` below. If needed, list the output root with
`ls -lt /absolute/path/results` and inspect a job with
`cat /absolute/path/results/JOB_ID/result.json`. A failure before a job is created may
have no `result.json`; read the terminal error. Do not assume the newest directory is the
right job without checking its result.

Choose an output directory outside the distribution checkout or extracted directory,
such as `/absolute/path/results`. The launcher rejects an output directory inside the
distribution before creating files or starting Docker, so subsequent review can verify
the original distribution inventory. Selected-page reviews show the original PDF page
numbers. A failed PDF input check also saves its job's `result.json` with the error details.

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

Replace `JOB_ID` with the printed ID and use the same output root as `run`.
Open `http://127.0.0.1:8010` in a browser on the same Linux host. Add `--port 8011` when
that port is occupied, then open `http://127.0.0.1:8011`. The application binds only to localhost and uses Linux Docker host
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
   printed count, choose **Add change** (**修正を追加**), then **Save this page**
   (**このページを保存**). Use the same operation for a missed rest shown as 1 and a
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

To continue a saved correction state on an annotated copy of the original PDF, open
**Saved history / resume** (**保存履歴・再開**). Save pending edits, optionally give the
checkpoint a name, and choose **Save checkpoint**. Select a saved checkpoint, choose
an annotated PDF (up to 32 MB), then choose **Resume in new session**. The original
review remains separate; the browser URL identifies the resumed session and can be
reopened after server restart. Saves also retain checkpoints automatically.
For jobs created before checkpoints were introduced, select an entry under **Saved
inputs from earlier versions** and choose **Import selected saved inputs**. The app
verifies the original source and recorded correction identities before making a
checkpoint. An unavailable entry includes a validation reason. Import certifies the
saved inputs; it does not certify an old PDF as a successful current result.
You can also choose a checkpoint from a resumed session and resume another annotated
copy; each new URL remains separate and uses the original review's ownership evidence.
The panel's **PDF generation history** records successful, failed and interrupted
attempts; a later success does not remove an earlier failure.

The resumed canvas shows the uploaded annotations. PDF generation recalculates numbering
from the retained recognition artifacts and adds uniformly sized 9 pt row numbers near
the staff. It preserves the annotated PDF's CropBoxes, original annotations and background.
If there is no safe placement, generation reports an error; it does not erase handwriting.
Keep the review package, its `history/`, `resumed_sessions/`, retained source artifacts,
and generated `.layer.json` files together. History checks external retained dependencies;
it does not create a portable archive of all recognition artifacts.

Currently supported resume inputs contain all original pages in order, have zero rotation
and unchanged MediaBoxes/background image bytes, and use native Ink, Circle, Square,
Stamp, FreeText or Highlight annotations. CropBox changes are supported.
An annotation-only MobileSheets re-export of a numbered PDF can also be resumed
from the review that generated it, while its successful PDF and `.layer.json` remain
available. The application verifies the complete page content, owned numbering streams,
background and rendering against that saved result, removes only its old numbers, and
preserves the new handwriting. Internal PDF object numbers may change. A rewritten
background, changed page content or missing provenance is rejected.

Partial/reordered pages, flattened/re-encoded backgrounds and other interactive PDF
shapes require further validation. Export a copy with the original background and
native annotations. The application does not import MSF files or infer which handwritten numbers it may delete.
A supplied 15-page MobileSheets annotation-only roundtrip has been checked; other
versions/export settings and physical printing remain unverified. See [the integration evidence in PR #445](https://github.com/M763468/PDFScoreBar/pull/445).

## Troubleshooting and provenance

- Git failure: check Git installation, repository URL, network and access; retry the clone.
- Build failure: retain the build output; check network access and disk space.
- Docker permission failure: check daemon/socket access and the ownership of output files.
- Output rejected: choose an absolute output path outside the distribution root.
- Port occupied: choose an unused `--port` and open that port on localhost.
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

## Local storage capacity

This release runs locally in Docker. Provide enough free disk space for model
assets, temporary/intermediate files, retained review packages and final PDFs.
The PDF size, page and render-pixel preflight limits do not bound intermediate
storage. There is no enforced 16 GiB per-job quota, automatic cancellation on
storage growth, or guarantee that an accepted job fits the available space.

If the OS reports disk full (`ENOSPC`), the job fails with
`disk_capacity_exhausted` and attempts to remove partial work/public artifacts.
The adapter records a failed `result.json` when storage is writable after cleanup;
a still-full or unwritable filesystem can prevent that record. Free space before
retrying, and retain available failure output for diagnosis. Quotas and forced
process-tree cancellation are deferred to a future public-service deployment.

## Distribution scope

The distribution uses the maintained dense PDF configuration. Standalone numbering CLI,
optional numbering overlays, probe diagnostic images and optional wide-candidate splitting
remain develop-only tools. Engine runtime provenance and debug telemetry remain available.

SR is generated by the dedicated batch process. Missing or invalid precomputed SR, corrupt
detection results, and missing required rescue seeds stop the job; they do not silently become
original-resolution images or empty detections. Valid empty predictions remain supported.
Page-local SR is an explicit develop-only mode and is not included in the distribution.
