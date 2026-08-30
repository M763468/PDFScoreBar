# Current Production Pipeline Architecture

> **Canonical architecture source.** This document describes the current production
> pipeline on `develop`, with emphasis on the `dense_full_pipeline` route. Source code,
> tests, and machine-readable profiles remain authoritative when they disagree with prose.
> Historical Issue documents describe how this architecture was reached; they are not
> required reading for understanding the current route.

## Scope and canonical entry points

The maintained full-pipeline runtime is the `pdfscore_pipeline_gpu` image and the
config-driven entry point in `src/pipeline/main.py`.

```bash
make docker-build
make run-pipeline CONFIG=configs/dense_full_pipeline.yaml
```

The dense production config selects:

```yaml
detection:
  detector_route: dense_full_pipeline
  homr_profile: stage_e_verified
  enable_sr: true
  sr_scale: 4
  sr_compile_mode: reduce-overhead
```

`src/pipeline/detection/__init__.py` dispatches that route to
`src/pipeline/detection/restored_orchestrator_batch_sr.py`. This is the accepted restored
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
       -> page-local verified source worker
            -> pinned Stage-E HOMR on original image
            -> current x4 support consumer
                 -> current-runtime HOMR on precomputed persisted x4 image
                 -> OMR-DLN on the same persisted x4 image
            -> hybrid consensus
       -> dense candidate/probe reconstruction
       -> CNN scoring
  -> page filtering / user barline corrections
  -> Phase A physical grouping + numbering_base
       -> pinned original-image staff geometry
       -> current-x4 connector semantic evidence
  -> current-x4 MMR support sidecar
       -> reuse Phase-A topology/x geometry
       -> map current-x4 HOMR staff y geometry
  -> MMR CNN + RapidOCR
  -> merge MMR and user measure overrides
  -> Phase C final numbering / optional overlay
  -> manifest / review-package materialization when configured
```

`pdf_to_images` is currently in-process inside `PipelineOrchestrator` when enabled. The
verified dense route itself requires persisted page image files; it rejects in-memory-only
images at the detector boundary.

## Two-HOMR ownership contract

For each page on the dense production route there are exactly two HOMR neural inference
purposes. The all-pages Real-ESRGAN phase is not an additional HOMR inference; it is the
shared x4 image producer consumed by the page-local source workers.

### 1. Original-image pinned Stage-E HOMR

- **Producer:** `run_homr_profile("stage_e_verified", ...)` through
  `BatchSRVerifiedProfileHybridDetector` / `VerifiedProfileHybridDetector`.
- **Input:** original/source page image, scale 1.
- **Provenance:** `configs/detector_profiles/stage_e_verified_homr.json`.
- **Role:** authoritative detector baseline and authoritative staff geometry for Phase-A
  system/measure construction.
- **Coordinate space:** source-page coordinates.
- **Primary durable runtime artifact subtree:**
  `<hybrid_output>/baseline/batch/<page>/...`.
- **Consumer:** detector inventory / hybrid consensus; later numbering consumes the
  resolved baseline staff mask.

This pinned profile exists to preserve the accepted Stage-E baseline. It is not rerun on
x4 in the current production path.

### 2. Current-runtime HOMR on persisted x4 support

- **x4 image producer:** `src/pipeline/detection/current_sr_batch_worker.py`, launched once
  for the selected page set by `BatchSRVerifiedProfileHybridDetector`.
- **x4 HOMR/support owner:** `src/pipeline/detection/current_support_worker.py`.
- **Input:** the precomputed persisted Real-ESRGAN x4 image from the dedicated SR process.
- **Producer runtime:** current pipeline HOMR runtime, not the pinned Stage-E profile.
- **Published bundle:** source-coordinate `current_sr_detection`, current-HOMR staff mask,
  the complete connector semantic pair, x4 image/provenance, and OMR-DLN predictions.
- **Coordinate contract:** detection and semantic support exposed to downstream consumers
  are restored to source-page coordinates where required; the persisted x4 image remains
  the physical x4 source artifact.
- **Consumers:** detector hybrid consensus, connector-aware grouping support, and MMR
  vertical staff support.

The production path does not initialize Real-ESRGAN inside each page-local support worker.
The dedicated SR process finishes all pages first and exits. Only then do disposable
page-local workers run pinned baseline HOMR plus current-x4 HOMR and OMR-DLN. This prevents
Real-ESRGAN model/activation state from overlapping the later HOMR/OMR GPU phases while
still reusing the SR model across pages.

## Current-x4 SR runtime contract

Issue #284 makes the Real-ESRGAN phase an explicit reusable runtime boundary.

- Model: `RealESRGAN_x4plus`.
- Precision/layout: FP16, `channels_last`.
- Tiling: `tile=400`, `tile_pad=10`.
- Output path: each tile is converted to CUDA `uint8`, copied/stiched on CPU, and written as
  the persisted x4 page image.
- Model lifetime: one SR process/model is reused across the selected page batch.
- Compile mode: `torch.compile(..., mode="reduce-overhead")` in the production config.
- Memory boundary: the SR process exits before any page-local HOMR or OMR-DLN inference.

The compiled and eager SR paths intentionally need not be byte-identical. Acceptance is at
the detector/topology/numbering/MMR semantic contracts. The final Issue #284 full-68 gate
preserved those contracts on all 68 canonical pages while reducing both SR-batch and E2E
wall time.

## Detector consensus and dense candidate route

`BatchSRVerifiedProfileHybridDetector` retains the same consensus semantics as
`VerifiedProfileHybridDetector` and combines:

- pinned original-image baseline detections;
- `current_x4_support.current_sr_detection`;
- OMR-DLN predictions produced from the persisted x4 support image.

The hybrid step filters baseline HOMR boxes by x4 HOMR or OMR-DLN support; it does not merge
x4 coordinates into the returned baseline boxes. The old pinned HOMR-on-x4 inference is not
part of this consensus. The current x4 HOMR output is the single x4 HOMR owner and is reused.

`restored_orchestrator_batch_sr.py` then follows the accepted restored-orchestrator route:
it writes the current-run inventory and calls `reconstruct_dense_full_pipeline_route()`.
Candidate/probe reconstruction and CNN scoring operate on the current run;
`historical_detector_artifact_runtime_input` is false for the verified production route.

## Grouping, connector semantics, and coordinate ownership

Phase A (`run_base_numbering_and_barline_correction`) constructs the physical numbering
layout with `MeasureNumberingPipeline`.

- **Barline x geometry:** accepted dense detector output, after optional user barline
  corrections.
- **Staff/system geometry:** pinned original-image Stage-E staff mask.
- **Connector semantics:** current-x4 HOMR connector semantic artifacts discovered from
  the declared current-support subtree.
- **Image used by numbering:** source/original page image.
- **Output:** `intermediate/<page>/numbering_base.json`.

A declared `current_support` subtree is a contract. If that subtree exists but its required
connector semantic pair is missing, production raises instead of silently switching the
meaning of connector evidence. Generic callers that do not declare current support retain
their legacy fallback behavior.

The accepted production numbering behavior also distinguishes missing semantic artifacts
from producer-geometry disagreement. A semantic staff-count mismatch may fall back to
numbering geometry; that compatibility behavior is intentional and was retained by Issue
#274.

## MMR support reuse contract

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

## Final numbering is not the removed MMR rebuild

Phase C still materializes `numbering_final.json`: it reloads the accepted barlines and
staff mask, reconstructs the page object with the normal `MeasureNumberingPipeline`, and
applies the merged MMR/user measure overrides before optional overlay rendering.

This normal finalization is distinct from the **removed legacy MMR-specific second
numbering rebuild**. The removed path existed only to prepare separate Phase-B/MMR geometry
and could diverge from Phase A. Current MMR support instead reuses the Phase-A topology.

## Process and memory boundaries

| Boundary | Process model | Memory/ownership purpose |
| --- | --- | --- |
| `src/pipeline/main.py` / `PipelineOrchestrator` | main pipeline process | owns orchestration, numbering, persistent MMR classifier/OCR |
| `current_sr_batch_worker` | one disposable process for all selected pages | owns Real-ESRGAN model/import/CUDA lifetime and persisted x4 generation |
| SR batch process exit | hard phase boundary | releases Real-ESRGAN/compile/CUDA state before HOMR/OMR |
| `verified_source_page_worker` | disposable top-level Python worker per page, started after SR batch | bounds lifetime of page-local verified source generation |
| pinned original HOMR | inside page worker | pinned-profile baseline only |
| `current_support_worker` | child worker using precomputed x4 | current x4 HOMR + OMR-DLN support contract; does not own production SR model lifetime |
| dense route + CNN | imported/run after source workers exit | avoids retaining heavy source-generation state |
| MMR batch | main pipeline process | reuses persistent classifier/OCR; no HOMR execution |

The exact child interpreter is selected by `src/pipeline/core/python_env.py`. The maintained
runtime is `pdfscore_pipeline_gpu` with `/opt/venv_pipeline/bin/python`. A legacy
`sr_eval_gpu` compatibility fallback still exists in that selector, but it is not the
canonical environment.

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

See `docs/TWO_HOMR_MILESTONE.md` for the accepted Issue #274 accuracy/performance milestone
that precedes the Issue #284 SR scheduling/runtime optimization.
