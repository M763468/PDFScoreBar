# Current Production Pipeline Architecture

[日本語](PIPELINE_ARCHITECTURE.ja.md)

> **Canonical architecture source.** This document describes the current production
> pipeline on `develop`, with emphasis on the `dense_full_pipeline` route. Source code,
> tests, and machine-readable profiles remain authoritative when they disagree with prose.
> Historical Issue documents describe how this architecture was reached; they are not
> required reading for understanding the current route.
>
> The intended future engine/service responsibility boundary is documented separately in
> [`FUTURE_SERVICE_ARCHITECTURE.md`](FUTURE_SERVICE_ARCHITECTURE.md). That roadmap document is
> not a source of truth for current runtime behavior.

## Reading this document

This guide is for developers and reviewers who need to understand how the current
production pipeline turns a score into numbered measures, including readers who have not
followed the project Issues. Start with the overview and component table below; the later
sections retain the exact configuration, artifacts, coordinate ownership, failure rules,
thresholds and historical evidence. A **staff** is a set of score lines for a part; a
**system** groups the staves played together on one horizontal row. A **measure** is the
musical interval bounded by barlines, including implicit boundaries at system edges.

## From score to numbered output

The input is a PDF or persisted page images. If PDF rendering is enabled, the pipeline
first renders pages; the dense detector, which reconstructs barline candidates, requires
the page images to be saved as files.
For each selected page, it finds possible barlines, scores the candidates, builds a
staff/system/measure layout, recognizes multi-measure rests (MMRs), and computes final
measure numbers. A convolutional neural network (CNN) scores barline candidates.
Depending on configuration, it also produces overlays, a manifest, and a review package; the user distribution can produce a final numbered PDF through its review flow.

```text
PDF or saved page images
  -> render PDF pages if enabled; save page images
  -> prepare x4 super-resolution (SR) images for selected pages (Real-ESRGAN)
  -> detect on original and x4 images (HOMR twice; OMR-DLN on x4)
  -> combine supporting detections; generate and score barline candidates (CNN)
  -> filter pages and apply optional user barline corrections
  -> Phase A: group staves into systems, construct measures and base numbering
  -> Phase B: recognize multi-measure rests and their counts when enabled
  -> merge recognized and user measure overrides
  -> Phase C: apply overrides and movement boundaries; finalize numbering
  -> configured outputs: numbering, overlays, manifest / review package / final PDF
```

HOMR and OMR-DLN are optical music recognition systems used here to detect score
features, including barlines. **Two HOMR inferences per page have different jobs.**
Maintained original-image HOMR
provides the authoritative baseline barline boxes and staff geometry. A second HOMR
inference reads the persisted x4 image and supplies support for detection, connector
semantics and MMR crops; OMR-DLN also reads that x4 image. Detection results passed
downstream are restored to original-page coordinates where needed. These are two
input/ownership roles, not two historical and current HOMR runtimes in production. The
maintained original profile and current-x4 support use the maintained production
image/runtime; the historical `stage_e_verified` baseline runtime assets are isolated in the
separately built Stage-E reproduction extension, outside the configured canonical
production route.

| Component | Input | Output and role |
| --- | --- | --- |
| Real-ESRGAN x4 | Selected original page images | Persisted x4 images and provenance (metadata identifying their origin) for the two x4 support detectors; one SR process serves the batch and exits before HOMR/OMR inference. |
| Maintained original-image HOMR | Original page image | Baseline barline detections and staff mask in source-page coordinates; authoritative geometry for detection and Phase A. |
| Current-x4 HOMR | Persisted x4 page image | Supporting detections, staff mask and connector semantic masks; detection/support coordinates are restored where needed. |
| OMR-DLN | Same persisted x4 page image | Supporting barline predictions used with x4 HOMR to check the original-image baseline detections. |
| Barline CNN | Dense candidates on the page image, after any staff-local normalization by the staff-stroke adapter | Candidate scores used by the detector, followed by staff-stroke duplicate suppression. |
| MMR CNN + RapidOCR | Phase-A measures, original page image and optional x4 staff-y support | Multi-measure-rest recognition and number reading; produces measure overrides for final numbering. |

**Phase A — staff and measure structure and base numbering:** accepted barline geometry,
optional user barline corrections, original-image staff geometry and current-x4 connector
evidence construct the physical systems and measures. The result is
`intermediate/<page>/numbering_base.json`. This is the common topology for the next phase;
without it MMR would have no agreed measure locations and indices to address.

**Phase B — multi-measure-rest recognition:** a multi-measure rest (MMR) represents
several silent measures with one notated symbol and a count. When enabled, the MMR CNN
and RapidOCR examine the original image using Phase-A measures and optional x4-derived
vertical staff support, producing `intermediate/<page>/overrides_mmr.json`. Phase B reuses
Phase-A topology instead of building a second, potentially different layout. A missing
Phase-A result causes MMR preparation for that page to be skipped.

**Phase C — final numbering with corrections:** the pipeline combines MMR and user measure
overrides, applies them and any movement boundaries during normal final numbering, and
writes `outputs/<page>/numbering_final.json`. This step is needed because one displayed
MMR may represent several measures and user corrections can change the numbering. Optional
overlays and configured review/final outputs use the finalized result.

## How the detection and grouping terms fit together

The **dense route** is the configured detector path that reconstructs a broad set of
barline candidates for the current run before CNN scoring. **Dispatch** means choosing the
implementation for the configured detector route; `src/pipeline/detection/__init__.py`
selects `dense_orchestrator_batch_sr.py` for this route.

The **hybrid consensus** checks original-image HOMR baseline boxes against support from x4
HOMR or OMR-DLN and keeps supported baseline boxes in baseline coordinates. Next, the
**probe** scans eligible staff bands and image ink to generate additional candidates;
**rescue** procedures recover candidates using existing cross-band, rightmost and gap
rules. These are candidate-generation steps, not a guarantee that every candidate is a
barline. In `src/pipeline/steps/staff_strokes.py`, the **staff-stroke adapter** adjusts
candidates spanning multiple staves into single-staff pieces (staff strokes) when its
conditions are met,
before CNN scoring. It also supplies eligible original-HOMR pieces through the existing
consensus check. After CNN scoring, duplicate suppression removes overlapping staff-stroke candidates;
the detailed conditions and exceptions appear below.

**Grouping** in Phase A assigns staves to systems and constructs aligned measures from
staff and barline geometry. A **connector** here is evidence of a connection between
adjacent staves near the left/start of a system, used alongside geometry when deciding
which staves belong together. Current-x4 HOMR supplies two semantic masks:
`connector_symbols` (symbol layer) and `connector_brace_dot` (brace/dot layer).
`SystemConnectorEvidenceExtractor` measures the relevant mask regions for adjacent
staff pairs; `ConnectorAwareSystemBuilder` uses the resulting presence or absence as
one grouping signal. These connector masks are distinct from the original-image staff
mask that owns Phase-A staff geometry. A **sidecar** is a separate artifact written next
to the main result to carry support or audit data, such as `mmr_support.json`. A
**producer** creates an artifact; a **consumer** reads it for a later operation.

In the present design, support artifacts are reused
for grouping and MMR instead of running extra HOMR inferences or rebuilding a separate
MMR layout. SR previously ran page by page; it now runs for the selected page batch and
its process exits before page-local HOMR/OMR work. The historical original-image Stage-E
baseline was replaced by the maintained original-image baseline; the old runtime assets
remain in the separate reproduction extension. [Issue #274](https://github.com/M763468/PDFScoreBar/issues/274),
[Issue #284](https://github.com/M763468/PDFScoreBar/issues/284), and
[Issue #294](https://github.com/M763468/PDFScoreBar/issues/294) provide the corresponding
investigation and decision history. Their measurements and old configurations are historical
evidence, not new validation results or a substitute for current source and profiles.

## Scope and canonical entry points

The user distribution adds `docker/distribution.py` as a Linux Docker launcher and
`docker/distribution_job.py` as a thin adapter to the existing v1 `PipelineJobExecutor`.
It ships the package-bound `tools/review_correction` application alongside the engine.
The local review application owns immutable `history/` checkpoints, package-scoped
resume sessions and process-locked application state. An uploaded annotated PDF is
validated against the checkpoint's original source and displayed separately from clean
recognition inputs. Resumed apply operations reuse retained recognition and use
`review/number_layer.py` to add a verified 9 pt numbering layer while preserving native
annotations and CropBoxes. Annotation-only re-exports may remap xrefs: the resume adapter
proves ordered content/stream hashes, markers and full-page rendering against attested
package-local results before removing the old owned streams. Unknown rewrites are rejected.
Legacy input snapshots are imported only after source/correction identity validation;
old PDF presence does not establish success. Repeated resumes use a flat session registry
under the original review, with checkpoint state and numbering ownership resolved separately.
Checkpoint IDs and session IDs are local artifact identities;
they do not add a public service/job API. See
[`dev/ISSUE441_PRODUCT_INTEGRATION.md`](dev/ISSUE441_PRODUCT_INTEGRATION.md).
The exact selection and develop-only boundary are in
[`MINIMAL_MAINLINE_SURFACE.md`](MINIMAL_MAINLINE_SURFACE.md); user operation is in
[`USER_GUIDE.md`](USER_GUIDE.md). Shared barline geometry lives in
`src/common/barline_geometry.py`; GT matching stays outside the distribution.


The maintained full-pipeline runtime is the `pdfscore_pipeline_gpu` image and the
config-driven entry point in `src/pipeline/main.py`. The root `Dockerfile` builds only
the maintained production runtime. Historical Stage-E source, venv, model assets and
provenance live in the explicit `docker/Dockerfile.stage-e` reproduction extension;
canonical preflight requires only maintained-profile provenance. See
[`ENVIRONMENTS.md`](ENVIRONMENTS.md) for the two build paths.

```bash
make docker-build
make run-pipeline CONFIG=configs/dense_full_pipeline.yaml
```

The dense production config selects:

```yaml
detection:
  detector_route: dense_full_pipeline
  homr_profile: maintained_original
  enable_sr: true
  sr_scale: 4
  sr_compile_mode: reduce-overhead
```

`src/pipeline/detection/__init__.py` dispatches that route to
`src/pipeline/detection/dense_orchestrator_batch_sr.py`. This is the accepted dense
orchestrator with one Issue #284 specialization: Real-ESRGAN x4 generation is lifted into a
dedicated all-pages phase before page-local HOMR/OMR source generation. The generic
`src/pipeline/detection/orchestrator.py` / `HybridDetector` path is a separate standard
route and must not be used to infer the dense production architecture.

## End-to-end order

The current caller chain is:

```text
PDF or persisted page images
  -> optional in-process PDF rendering / page collection
  -> dense detector route dispatch
       -> dedicated all-pages current-x4 SR process
            -> one Real-ESRGAN x4 model/runtime reused across all selected pages
            -> FP16 + channels_last + tile=400/tile_pad=10
            -> torch.compile(reduce-overhead)
            -> tile-wise CUDA uint8 conversion + CPU stitch
            -> persisted x4 images + per-page provenance
       -> SR process exits and releases its CUDA/model state
       -> page-local maintained source worker (maintained_source_page_worker)
            -> maintained HOMR pinned at immutable commit on original image
            -> current-x4 support worker (consumes the precomputed x4 image)
                 -> current-runtime HOMR on precomputed persisted x4 image
                 -> OMR-DLN on the same persisted x4 image
            -> hybrid consensus
       -> dense candidate/probe reconstruction
       -> staff-local CNN candidate normalization (maintained_original only)
            -> split multi-staff boxes; supplement original HOMR pieces with SR-or-OMR consensus
            -> preserve original probe row seeds and connector-mask evidence
       -> CNN scoring + strict staff-stroke duplicate suppression
  -> page filtering / user barline corrections
  -> Phase A physical grouping + numbering_base
       -> maintained original-image staff geometry
       -> current-x4 connector semantic evidence
  -> current-x4 MMR support sidecar
       -> reuse Phase-A topology/x geometry
       -> map current-x4 HOMR staff y geometry
  -> MMR CNN + RapidOCR
  -> merge MMR and user measure overrides
  -> Phase C final numbering / optional overlay
  -> manifest / review-package materialization when configured
```

The staff-stroke adapter runs after dense generation, filtering and rescue. It splits
only boxes intersecting at least two extracted staves by at least two staff units each;
single-staff connector tails remain unchanged. Added original-HOMR pieces pass the existing SR-or-OMR
IoU > 0.5 consensus before actual CNN inference. Post-CNN duplicate suppression uses
X-center distance <= 0.1 median extracted staff unit and vertical overlap >= 0.8,
retaining the numbering-compatible canonical geometry and its own CNN score. This is
separate from logical time-boundary merging. Per-page normalization and suppression
sidecars preserve the source hashes and representatives. No GT or evaluation data enters
this runtime step. CNN lookup resolves relative, absolute and symlink image paths to
the same staff-unit map identity (the map associates an image with its staff unit size).
Probe directories use the image parent/stem identity
consistently through rescue, the adapter and CNN, including composite score/page stems;
logical inventory score/page labels do not select the adapter directory.
The inventory makes image paths absolute without resolving symlinks, preserving the
caller's parent/stem for rescue and CNN output locations. Support metadata can use that
identity or the resolved identity used inside disposable source-page workers; the adapter
requires exactly one physical result at these known locations and checks its image and
completion status. The unit-map lookup still resolves the file identity.
Successful empty CNN results also write an empty
suppression audit when deduplication is enabled, and
reruns with deduplication disabled remove stale suppression sidecars.
A page containing any accepted staff without an estimated
unit (including one-line percussion notation) keeps its original candidates and skips
this adapter and stroke deduplication; its sidecar records `no_staff_unit_size` rather
than inventing a geometric threshold. This also preserves unknown voices on mixed pages.
See `tools/issue416/IMPLEMENTATION.md` for the fixed-input validation.

`pdf_to_images` is currently in-process inside `PipelineOrchestrator` when enabled. The
verified dense route itself requires persisted page image files; it rejects in-memory-only
images at the detector boundary.

## Orchestration and probe module boundaries

`PipelineOrchestrator` owns input validation/rendering, phase order, shared model caches,
telemetry and manifest/review dispatch. Its existing phase methods delegate execution to
`steps/numbering_phases.py`, which contains base layout/barline corrections, batch MMR preparation,
and final override application, cross-page numbering and overlays.
`NumberingPhaseServices` in that module supplies the current orchestrator operation hooks at dispatch time;
phase helpers share the same context and caches and do not import their caller. Review
configuration/prerequisites and manifest projection live in `review/pipeline_review.py`.

The probe entry point keeps the existing option/API contract and candidate acceptance order.
`bands.py` resolves staff bands and eligible x domains. `measurements.py` projects band and
extension ink, selects seeds, and measures candidate-local scan bands, row profiles, x peaks
and overhang. Measurement does not accept or rescue a
candidate. `existing.py` owns existing-barline matching, `rescue.py` performs the existing
cross-band/rightmost/gap rescues, `debug.py` serializes debug evidence, and `types.py` carries
configuration records. No thresholds, rounding rules, result schemas or process lifetimes
change with these module boundaries.
Probe diagnostic rendering and optional wide-candidate splitting are imported only when
requested. The minimal user distribution excludes those develop tools and standalone
numbering CLI/overlays; final user PDFs are generated by `review/final_output.py`.

## Detection failure contracts

Canonical batch/source-page/support workers require non-null valid `precomputed_sr` before
HOMR execution. `sr_mode=page_local` is an explicit develop compatibility mode, rather than
recovery from a failed batch. Legacy non-batch profiles write that mode explicitly. Page-local
SR calls the generic helper with `strict=True` and checks exact x4 shape; generic development
callers retain `strict=False` compatibility. Batch SR propagates runtime errors and shape failures.
Canonical HOMR/OMR consensus uses strict detection JSON parsing, including finite numeric
coordinates and valid bounds; valid empty predictions remain normal. Canonical dense rescue
requires seed files, while generic no-seed probe operation remains optional. Errors propagate
through workers to a FAILED engine job before final/review publication.

## HOMR module ownership

The maintained/current workers import production-owned `src/homr_runtime/`:

| Responsibility | Module |
| --- | --- |
| Prediction/coordinate records and established runtime defaults | `types.py` |
| Image/segmentation coordinate mapping | `transforms.py` |
| Image-feature and segmentation barline candidates | `barline_candidates.py` |
| Staff/symbol assembly and compatibility patch points | `heuristics.py` |
| Notehead/staff filtering and end-barline recovery | `filtering.py`, `end_barlines.py` |
| Model prediction, Segnet cache and callable API adaptation | `predictor.py`, `segnet_cache.py`, `api_compat.py` |
| Logging and prediction/mask serialization | `utils.py`, `reporting.py` |

`maintained_profile.py` owns maintained baseline execution. Shared source-generation and
batch-SR scheduling live in `profile_sources*.py`; `maintained_profile_hybrid.py` selects
the maintained backend and `maintained_source_page_worker.py`. Historical profile adapters
remain under `homr_profile.py`, `homr_profile_compat.py`, `profile_hybrid*.py`, and
`verified_source_page_worker.py`. They are loaded only for an explicitly selected historical
profile. `src/homr_eval_scripts/core/` retains old import adapters plus evaluation metrics,
diagnostic CSV generation and comparison reporting. Production does not import that package.

Callable compatibility and connector capture still patch the actual predictor/heuristics
bindings held by the consumer. The heuristics, predictor and Segnet cache adapters alias the canonical
module object, preserving callable patch points and class/cache identity for old import paths. These ownership changes
do not change the two-HOMR input/coordinate or process-lifetime contracts below.

## Two-HOMR ownership contract

For each page on the dense production route there are exactly two HOMR neural inference
purposes. The all-pages Real-ESRGAN phase is not an additional HOMR inference; it is the
shared x4 image producer consumed by the page-local source workers.

### 1. Original-image maintained HOMR

- **Producer:** `run_homr_profile("maintained_original", ...)` through
  `BatchSRVerifiedProfileHybridDetector` / `VerifiedProfileHybridDetector`.
- **Input:** original/source page image, scale 1.
- **Provenance:** `configs/detector_profiles/maintained_original_homr.json`.
- **Role:** authoritative detector baseline and authoritative staff geometry for Phase-A
  system/measure construction.
- **Coordinate space:** source-page coordinates.
- **Primary durable runtime artifact subtree:**
  `<hybrid_output>/baseline/batch/<page>/...`.
- **Consumer:** detector inventory / hybrid consensus; later numbering consumes the
  resolved baseline staff mask.

This pinned profile provides the authoritative original-image baseline in current
production. It uses the maintained runtime, not the historical Stage-E runtime, and is
not rerun on x4 in the current production path.

### 2. Current-runtime HOMR on persisted x4 support

- **x4 image producer:** `src/pipeline/detection/current_sr_batch_worker.py`, launched once
  for the selected page set by `BatchSRVerifiedProfileHybridDetector`.
- **x4 HOMR/support owner:** `src/pipeline/detection/current_support_worker.py`.
- **Input:** the precomputed persisted Real-ESRGAN x4 image from the dedicated SR process.
- **Producer runtime:** current pipeline HOMR runtime, not the historical `stage_e_verified` runtime.
- **Published bundle:** source-coordinate `current_sr_detection`, current-HOMR staff mask,
  the complete connector semantic pair, x4 image/provenance, and OMR-DLN predictions.
- **Coordinate contract:** detection and semantic support exposed to downstream consumers
  are restored to source-page coordinates where required; the persisted x4 image remains
  the physical x4 source artifact.
- **Consumers:** detector hybrid consensus, connector-aware grouping support, and MMR
  vertical staff support.

The pinned original-image `maintained_original` profile is immutable and is not rerun on
x4 in the current production path. The isolated runtime assets for the historical
`stage_e_verified` profile are retained in the separately built Stage-E reproduction extension image
(`docker/Dockerfile.stage-e`), not the root production image; the historical profile is
not part of canonical dispatch. The extension does not reconstruct the complete historical
two-HOMR environment or guarantee its full-68 metrics.

The production path does not initialize Real-ESRGAN inside each page-local support worker.
The dedicated SR process finishes all pages first and exits. Only then do disposable
page-local workers run maintained baseline HOMR plus current-x4 HOMR and OMR-DLN. This prevents
Real-ESRGAN model/activation state from overlapping the later HOMR/OMR GPU phases while
still reusing the SR model across pages.

## Current-x4 SR runtime contract

Issue #284 makes the Real-ESRGAN phase an explicit reusable runtime boundary.

- Model: `RealESRGAN_x4plus`.
- Precision/layout: FP16, `channels_last`.
- Tiling: `tile=400`, `tile_pad=10`.
- Output path: each tile is converted to CUDA `uint8`, copied/stitched on CPU, and written as
  the persisted x4 page image.
- Model lifetime: one SR process/model is reused across the selected page batch.
- Compile mode: `torch.compile(..., mode="reduce-overhead")` in the production config.
- Memory boundary: the SR process exits before any page-local HOMR or OMR-DLN inference.

The compiled and eager SR paths intentionally need not be byte-identical. Acceptance is at
the detector/topology/numbering/MMR semantic contracts. The final Issue #284 full-68 gate
preserved those contracts on all 68 canonical pages while reducing both SR-batch and E2E
wall time.

## Detector input provenance and scoring defaults

Detector input provenance is a machine-readable contract, not something inferred from a
run-directory name or from the fact that HOMR/SR/OMR executed. `src/pipeline/detection/input_contract.py`
classifies each detector configuration as one of:

```text
fresh_upstream
precomputed_candidate_route
```

A run is `fresh_upstream` only when both candidate-source overrides are unset:

```text
precomputed_probe_candidates_root
cnn_bands_from
```

If either override is configured, the run is a `precomputed_candidate_route`, even if the
current HOMR/SR/OMR stages also execute and even if the run writes new candidate JSON into a
new output directory. New output bytes do not prove fresh authoritative inputs.

The detector orchestrator records this contract in:

```text
<run_dir>/intermediate/detector_input_contract.json
```

A result may be described as a fresh detector validation only when the manifest reports:

```text
mode = fresh_upstream
fresh_upstream_authoritative = true
override_keys = []
```

Checkpoint/precomputed routes remain useful for historical regression, CNN comparison, and
downstream isolation, but their metrics must remain labelled with that input mode. The
forensic investigation that established this distinction is retained in Issue #245 and PR
#251; current source/tests and the machine-readable manifest are authoritative now.

CNN scoring NMS is default-off in `src/pipeline/detection/config.py`
(`DEFAULT_CNN_APPLY_NMS = False`) and remains an explicit opt-in through
`detection.cnn_apply_nms: true`. Issue #142 records the historical causal evidence and PR
#154 that established this default. Any future default change requires explicit canonical
accuracy/downstream evidence rather than a silent scoring-policy change.

## Detector consensus and dense candidate route

`BatchSRVerifiedProfileHybridDetector` retains the same consensus semantics as
`VerifiedProfileHybridDetector` and combines:

- maintained original-image baseline detections;
- `current_x4_support.current_sr_detection`;
- OMR-DLN predictions produced from the persisted x4 support image.

The hybrid step filters baseline HOMR boxes by x4 HOMR or OMR-DLN support; it does not merge
x4 coordinates into the returned baseline boxes. The old pinned HOMR-on-x4 inference is not
part of this consensus. The current x4 HOMR output is the single x4 HOMR owner and is reused.

`dense_orchestrator_batch_sr.py` then follows the accepted dense-orchestrator route:
it writes the current-run inventory and calls `reconstruct_dense_full_pipeline_route()`.
Candidate/probe reconstruction and CNN scoring operate on the current run;
`historical_detector_artifact_runtime_input` is false for the verified production route.

## Phase A: staff and measure structure, connector semantics, and coordinate ownership

Phase A (`run_base_numbering_and_barline_correction`) constructs the physical numbering
layout with `MeasureNumberingPipeline`.

- **Barline x geometry:** accepted dense detector output, after optional user barline
  corrections.
- **Staff/system geometry:** maintained original-image staff mask.
- **Connector semantics:** current-x4 HOMR connector semantic artifacts discovered from
  the declared current-support subtree.
- **Image used by numbering:** source/original page image.
- **Output:** `intermediate/<page>/numbering_base.json`.

A declared `current_support` subtree is a contract. If that subtree exists but its required
connector semantic pair is missing, production raises instead of silently switching the
meaning of connector evidence. Generic callers that do not declare current support retain
their legacy fallback behavior.

The accepted production numbering behavior also distinguishes missing semantic artifacts
from producer-geometry disagreement. If the current-HOMR semantic staff mask and the
numbering staff geometry have different staff counts, the connector evidence is measured using the numbering staff geometry
instead. The connector masks are still used. This compatibility behavior is intentional
and was retained by Issue #274.

## Phase B: multi-measure-rest recognition and support reuse

Dense MMR does **not** run HOMR again on the original page and does **not** rebuild Phase-A
numbering in an MMR-specific subtree.

`src/pipeline/mmr_geometry_handoff.py` builds `intermediate/<page>/mmr_support.json` via
`src/pipeline/mmr_support_reuse.py`.

The contract is asymmetric by design:

- Phase-A `numbering_base` remains authoritative for topology, measure numbers, system
  membership, and normal horizontal/x geometry.
- current-x4 HOMR staff geometry contributes vertical/y crop support for MMR.
- staff-slot mapping is scale-free. If a current-x4 staff cannot be mapped for a slot, the
  support view falls back to that slot's Phase-A geometry rather than creating a new
  topology.
- `original_image_homr` is false and `second_numbering_rebuild` is false in MMR support
  provenance.

`run_mmr_batch()` consumes the Phase-A page payload, original page image, and optional MMR
support views. The persistent `MMRClassifier` and `MMROCREngine` (RapidOCR) are reused
across pages in the orchestrator process.

## Phase C: final numbering with corrections, not the removed MMR rebuild

Phase C still materializes `numbering_final.json`: it reloads the accepted barlines and
staff mask, reconstructs the page object with the normal `MeasureNumberingPipeline`, and
applies the merged MMR/user measure overrides before optional overlay rendering.

MMR/manual overrides and movement boundaries use zero-based indices in the compact
(non-empty systems only) `numbering_base.json` / `numbering_final.json` `systems` array.
Internal `Page.systems` also retains empty systems; Phase C resolves visibility from uncorrected measure geometry
before applying corrections, so empty systems never consume a public system index. Page
indices remain batch-global at merge time and are rebased to zero for per-page numbering.
Final metadata records `system_index_contract: compact_nonempty_systems.v1`; cached final
artifacts without that marker are rebuilt because their corrections may target a different
physical system. This contract is shared by the combined JSON and final PDF row labels.

This normal finalization is distinct from the **removed legacy MMR-specific second
numbering rebuild**. The removed path existed only to prepare separate Phase-B/MMR geometry
and could diverge from Phase A. Current MMR support instead reuses the Phase-A topology.

## Process and memory boundaries

| Boundary | Process model | Memory/ownership purpose |
| --- | --- | --- |
| `src/pipeline/main.py` / `PipelineOrchestrator` | main pipeline process | owns orchestration, numbering, persistent MMR classifier/OCR |
| `current_sr_batch_worker` | one disposable process for all selected pages | owns Real-ESRGAN model/import/CUDA lifetime and persisted x4 generation |
| SR batch process exit | hard phase boundary | releases Real-ESRGAN/compile/CUDA state before HOMR/OMR |
| `maintained_source_page_worker` | disposable top-level Python worker per page, started after SR batch | bounds lifetime of page-local verified source generation |
| maintained original HOMR | inside page worker | immutable maintained baseline only |
| `current_support_worker` | child worker using precomputed x4 | current x4 HOMR + OMR-DLN support contract; does not own production SR model lifetime |
| dense route + CNN | imported/run after source workers exit | avoids retaining heavy source-generation state |
| MMR batch | main pipeline process | reuses persistent classifier/OCR; no HOMR execution |

The exact child interpreter is selected by `src/pipeline/core/python_env.py`. The maintained
runtime is `pdfscore_pipeline_gpu` with `/opt/venv_pipeline/bin/python`. Issue #379 removed the
former SR-container compatibility selector, so heavy subprocess selection no longer falls back to a
second legacy container/interpreter environment.

## Principal artifacts

Typical per-run artifacts relevant to architecture are:

```text
<run_dir>/
  intermediate/detector_input_contract.json
  intermediate/dense_full_pipeline_inputs/inventory.json
  intermediate/dense_full_pipeline_route/**
  intermediate/<page>/barlines_corrected.json        # when materialized
  intermediate/<page>/numbering_base.json
  intermediate/<page>/mmr_support.json
  intermediate/<page>/overrides_mmr.json
  intermediate/<page>/overrides_combined.json        # debug
  outputs/<page>/numbering_final.json
  outputs/<page>/numbering_overlay.png                # when enabled
  filters.json
  manifest.json
```

The detector hybrid root also contains `baseline/`, `current_support/`, and
`hybrid_results/`. The current-support page subtree includes the persisted precomputed x4
image/provenance originating from the all-pages SR phase. Generated run outputs belong under
ignored `logs/` paths unless a narrow retention policy explicitly says otherwise.

## Invariants for future changes

Do not introduce any of the following as a hidden downstream operation:

- a page-local Real-ESRGAN model initialization on every dense production page;
- overlap between the production Real-ESRGAN lifetime and later HOMR/OMR heavy phases;
- pinned Stage-E HOMR on x4 solely for detector consensus;
- current-runtime HOMR on the original page solely for MMR staff geometry;
- an MMR-specific second numbering rebuild whose topology can diverge from Phase A.

If a future stage genuinely requires a different HOMR producer/input/profile, make that
producer a named upstream artifact with machine-readable provenance and an explicit owner.
If SR scheduling changes, preserve explicit ownership/provenance and revalidate the full-68
downstream semantic contract rather than relying only on SR pixel equality.

Any change to these ownership boundaries, route order, authoritative geometry, or major
process/memory boundaries must update this document and then refresh the committed Graphify
artifacts according to `docs/ai-workflow/GRAPHIFY.md`.

When a current-runtime change also alters assumptions visible at the future engine boundary
(one-job invocation/result semantics, externally meaningful final/review artifacts, correction
semantics, lifecycle/error/resource ownership, or caller-visible isolation assumptions), also review
[`FUTURE_SERVICE_ARCHITECTURE.md`](FUTURE_SERVICE_ARCHITECTURE.md). Update that document only when
the long-term boundary materially changes; do not copy detailed pipeline internals into it.

See `docs/TWO_HOMR_MILESTONE.md` for the accepted Issue #274 accuracy/performance milestone
that precedes the Issue #284 SR scheduling/runtime optimization.
