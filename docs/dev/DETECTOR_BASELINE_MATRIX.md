# Detector Baseline Matrix

This document distinguishes the production detector path from historical and
evaluation-only configurations. It is the standing reference for selecting a
barline detector route.

## Current production default

The production default is the `dense` detector route with profile
`production_dense_v1`.

A config does **not** need to specify `detection.route` to receive this route.
The pipeline defaults to `dense`, reconstructs dense candidates from the
current run's images and hybrid artifacts, adds the probe-rescue candidates,
and then runs the current CNN and MMR stages.

The ordinary hybrid/probe path is available only through an explicit opt-out:

```yaml
detection:
  route: ordinary
```

This opt-out is lower accuracy and is intended only for controlled diagnosis or
compatibility work. It must not be used as a user-facing or corrected-rerun
default.

## Route and config roles

| Surface | Role | Production default? | Notes |
|---|---|---:|---|
| `production_dense_v1` | Current production detector profile | Yes | Reconstructs current-run dense and rescue candidates before CNN scoring |
| `configs/dense_full_pipeline.yaml` | Tracked full-pipeline example for the dense profile | Reference | Explicitly declares `route: dense` for readability; code defaults to the same route |
| `configs/evaluation2_e2e_verification_full.yaml` | Evaluation2 verification input | No | Evaluation baseline/config input; not sufficient by itself to reproduce the dense candidate route |
| `configs/issue120_stage_e_full_pipeline.yaml` | Historical Stage E reproduction | No | Historical artifact/reproduction config; do not use as the current production default |
| `detection.route: precomputed` | External/reproduction candidate injection | No | Requires explicit precomputed candidate artifacts |
| `detection.route: ordinary` | Legacy ordinary hybrid/probe route | No | Explicit low-accuracy opt-out only |

## Dense profile ownership

Selecting `dense` applies the validated profile-owned values, including:

- SR enabled at scale 2;
- bbox-ink crop recentering;
- row-stat dense candidate generation;
- dense candidate filtering;
- probe-gap, x-peak, rightmost, divisi, and center-on-peak rescue;
- CNN NMS disabled;
- original-image probe/CNN coordinate space;
- current dense candidate and band artifacts injected into the normal pipeline.

Environment-specific paths remain configurable. In particular, a caller may
provide a valid `cnn_model_path` and `hybrid_output_root`. The canonical CNN
model path is used when `cnn_model_path` is omitted.

## Corrected reruns

A corrected rerun inherits the logical detector route/profile, not generated
candidate paths from the source run.

The source manifest records resolved candidate roots for provenance. Before a
new run starts, stale `precomputed_probe_candidates_root`, `cnn_bands_from`,
`probe_use_original_images`, and `resolved_route` values are removed for the
dense route. Fresh artifacts are then reconstructed under the corrected run.

This prevents a corrected rerun from silently reusing artifacts owned by an
older run while preserving the same high-accuracy profile.

## Manifest provenance

For each production detection run, `manifest.json` records:

- selected route;
- profile name;
- whether selection came from the default or an explicit config;
- effective profile, generation, and filter parameters;
- configured values overridden by the profile;
- generated filtered-band and probe-rescue roots;
- dense-route execution summary;
- an `inprocess:dense_detector_route` command record.

This information is required when comparing detector results across runs.

## Issue #244 evidence

Issue #244 reproduced incorrect row-start numbering in the ordinary smoke
route. On `Va_Prokofiev_Symphony1/page_001`, the ordinary route missed five
physical measures and one relevant MMR target.

Replaying the same page with the current code and the dense route produced:

```text
base measure counts:
[5, 5, 5, 7, 7, 8, 5, 7, 10, 8, 5, 6]

MMR signatures:
[7,3,5], [7,6,3], [8,0,2], [8,2,2], [8,4,4]

final row starts:
[1, 6, 11, 16, 23, 30, 38, 43, 58, 76, 84, 89]
```

The final row starts exactly matched the human-verified sequence. This showed
that the failure was caused by route/profile plumbing rather than the final
materializer or a required score-specific correction.

## Required regression before merge

Changes to the production dense profile require:

- focused route/default and corrected-rerun tests;
- the Issue #244 one-page replay;
- full-68 detector/barline evaluation;
- Issue #206 guard cases;
- downstream physical measure-count comparison;
- Issue #221 MMR baseline;
- page-033 one-bar veto;
- manual-correction and corrected-final focused tests.

Do not replace these gates with the historical Stage E artifact alone.
