# Issue #274 — HOMR / PDFScoreBar feature ownership

This note is an investigation aid for Issue #274.  It prevents a recurring source
of confusion: a value may be *produced from HOMR data* without the surrounding
policy being an upstream HOMR feature.

Use the following ownership labels in #274 experiment reports:

- `upstream_homr`: implementation is supplied by `liebharc/homr` for the selected
  HOMR revision.
- `pdfscore_upstream_orchestration`: PDFScoreBar calls/repackages upstream HOMR
  primitives, but the orchestration, tuning surface, coordinate mapping, or output
  contract is PDFScoreBar code.  This is **not** a pure upstream behavior.
- `pdfscore_extension`: algorithm/policy is introduced by PDFScoreBar and is not
  present in upstream HOMR.

The selected upstream revision is part of the producer contract.  `stage_e_verified`
(HOMR `864e288...`) and the current HOMR installation are different upstream
producer bundles: their resize/color preprocessing and SegNet model generations
are not equivalent.

## 1. Pure upstream HOMR functionality

The following operations are upstream HOMR responsibilities.  Exact behavior can
still differ between HOMR revisions.

| Function / data | Ownership | Notes |
|---|---|---|
| `homr.autocrop.autocrop` | `upstream_homr` | Page autocrop. |
| `homr.resize.resize_image` / `calc_target_image_size` | `upstream_homr` | Pinned and current revisions use different resize policies. |
| `homr.color_adjust.*` | `upstream_homr` | Pinned and current revisions use different preprocessing. |
| `homr.segmentation.inference_segnet.extract` / SegNet | `upstream_homr` | Produces staff, notehead, symbol, stem/rest, and clef/key masks. |
| HOMR prediction `.npy` cache inside `inference_segnet.extract` | `upstream_homr` | Distinct from PDFScoreBar's ONNX-session cache wrapper. |
| `homr.main.predict_symbols` | `upstream_homr` | Converts segmentation masks to HOMR symbol/bounding-box objects. |
| `homr.staff_detection.break_wide_fragments` | `upstream_homr` | Staff-fragment processing. |
| `homr.note_detection.combine_noteheads_with_stems` | `upstream_homr` | Note/stem association. |
| `homr.bar_line_detection.detect_bar_lines` and related bar-line primitives | `upstream_homr` | Primary HOMR bar-line extraction. |
| `homr.staff_detection.detect_staff` | `upstream_homr` | HOMR staff detection. |
| `homr.brace_dot_detection.prepare_brace_dot_image` and grouping primitives | `upstream_homr` | `brace_dot` is derived by upstream HOMR from upstream masks; it is not a raw SegNet channel. |

`clefs_keys`, `symbols`, `staff`, and `notehead` pixel data therefore originate in
upstream HOMR.  Persisting those arrays under stable PDFScoreBar filenames is a
separate PDFScoreBar responsibility.

## 2. PDFScoreBar orchestration around upstream HOMR

These files are owned by PDFScoreBar even when most inner calls are upstream HOMR:

| File / function | Ownership | Added responsibility |
|---|---|---|
| `src/homr_eval_scripts/core/heuristics.py::detect_staffs_with_barlines` | `pdfscore_upstream_orchestration` | Recreates/extends the HOMR detection sequence, exposes primary barlines and masks, and adds PDFScoreBar tuning/generator hooks. |
| `src/homr_eval_scripts/core/predictor.py::HomrPredictor` | `pdfscore_upstream_orchestration` | Persistent predictor lifecycle, outer ~3.5 MP proxy, coordinate transforms, result mapping, cleanup, and PDFScoreBar post-processing. |
| `src/pipeline/detection/homr_profile_compat.py` | `pdfscore_upstream_orchestration` | Adapts API drift between pinned/current HOMR/PDFScore revisions. |
| `src/homr_eval_scripts/segnet_cache.py` | `pdfscore_upstream_orchestration` | PDFScoreBar ONNX `InferenceSession` reuse.  This is not the upstream HOMR prediction `.npy` cache. |
| `src/pipeline/detection/current_homr_worker.py` | `pdfscore_upstream_orchestration` | Executes the current HOMR bundle on persisted x4 SR and publishes PDFScoreBar artifacts. |
| `src/pipeline/detection/connector_artifacts.py` | `pdfscore_upstream_orchestration` | Captures upstream-generated semantic masks during one HOMR call and persists them for downstream consumers. |
| `src/common/connector_artifacts.py` | `pdfscore_upstream_orchestration` | Stable artifact naming, provenance/discovery, and numbering handoff. |

Important distinction for the target architecture:

- generating `clefs_keys`, `symbols`, `staff`, etc. is upstream HOMR;
- deciding to retain them and reuse them across detector/grouping/MMR is
  PDFScoreBar's artifact contract.

## 3. PDFScoreBar-only detector/post-processing functionality

The following behavior must not be described as a HOMR feature:

| File / function | Ownership | Notes |
|---|---|---|
| `src/common/thin_barline_finder.py` | `pdfscore_extension` | Thin vertical-run recovery introduced in PDFScoreBar.  Upstream HOMR does not contain `ThinBarlineConfig` / `detect_thin_vertical_runs`. |
| thin-candidate merge/replacement in `src/homr_eval_scripts/core/predictor.py` | `pdfscore_extension` | A PDFScoreBar post-process; currently capable of replacing an upstream primary box. |
| `src/pipeline/steps/hybrid_consensus.py` | `pdfscore_extension` | A/C/B/OMR evidence consensus policy. |
| `src/pipeline/probe_detector/*` | `pdfscore_extension` | Dense probe reconstruction, row bands, rescues, and existing-box suppression. |
| `src/pipeline/steps/probe_scan.py` | `pdfscore_extension` | Dense orchestration, seed splitting, trimming and candidate union. |
| `src/pipeline/steps/candidate_filters.py` | `pdfscore_extension` | Page/clef/staff/ink heuristics for dense candidates. |
| `src/pipeline/steps/cnn_scoring.py` | `pdfscore_extension` | PDFScoreBar barline CNN scoring, crop policy, geometric filtering, optional NMS. |
| MMR support mapping/handoff | `pdfscore_extension` | PDFScoreBar numbering/MMR geometry contract. |

The dense existing-box suppression discussed by Issue #274 is therefore a
**PDFScoreBar consumer bug/policy question**, not an upstream HOMR behavior.
Likewise, changing its topology semantics does not mean modifying HOMR inference.

## 4. Current #274 causal boundary

The retained pinned/current primary comparison uses byte-identical PDFScoreBar
outer proxy files but diverges immediately inside the selected upstream producer
bundle:

1. pinned HOMR `864e288...` keeps images already within its target pixel range;
2. current HOMR resizes to width 1920;
3. color adjustment differs between the revisions;
4. SegNet model generation/runtime also differs.

Therefore do not label the B/C difference as a PDFScoreBar `core` refactor effect:
the current-runtime monolithic/core comparison was exact through primary barlines.
For production selection, preprocessing + model + runtime should be treated as one
versioned upstream-HOMR producer bundle unless a later investigation specifically
needs to separate those variables.

## 5. Target ownership boundary

The intended two-HOMR architecture is:

```text
original page
  -> one selected HOMR producer bundle
  -> authoritative original-input support

persisted x4 SR
  -> one selected HOMR producer bundle
  -> raw x4 support bundle
       - primary barline evidence        [upstream data]
       - staff/notehead/symbol/clef data [upstream data]
       - brace-dot semantic image        [upstream-derived data]
       - stable paths/provenance          [PDFScoreBar contract]
       - optional thin evidence           [PDFScoreBar extension]

raw support bundle
  -> consensus / dense / CNN / grouping / MMR consumers [PDFScoreBar]
```

This boundary permits one expensive HOMR inference for a given input while allowing
multiple cheap PDFScoreBar consumer policies to be evaluated without rerunning HOMR.
