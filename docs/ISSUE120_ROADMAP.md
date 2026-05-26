# Issue 120 Roadmap

## Purpose

This roadmap reflects the Issue #120 restart after these merged recovery PRs:

```text
#138: restart plan
#139: canonical full-68 intermediate evaluator
#143: historical best and reconstruction-path audit
#144: generated artifact cleanup / retention policy
#145: Stage D upstream-regeneration diagnostic runner and current boundary
#150: recovered Issue36 dense candidate validation route
```

The current strategy is to keep these layers separate:

```text
Stage A: saved scored intermediates
Stage B: saved candidates -> scoring -> canonical evaluation
Stage C: regenerated candidates -> scoring -> canonical evaluation
Stage D: regenerated slow upstream HOMR/OMR/SR artifacts -> Stage C
Stage E: full 68-page pipeline validation
Productionization: promote recovered validation routes into regular pipeline modules/configs
```

Detector-level metrics and downstream measure-count metrics must not be mixed.

Metric note:

- In these Issue #120 evaluator summaries, `Pred` is the evaluator-reported prediction/intermediate count for the scored detector output. It is recorded as provenance/context and is not used as the detector false-positive count.
- `TP`, `FP`, and `FN` are the canonical detector matching metrics. The detector target is therefore stated explicitly as `TP=3580 / FP=0 / FN=1`.

## Current completed foundation

### #133 / PR #138: restart plan

Status: completed.

Result:

- `rebuild/issue120` is the audit/integration target.
- `fix/probe_seeds` is frozen as an experimental/evidence branch.
- Issue #120 remains the parent Epic.
- Work is split into staged audit/cleanup/repair issues.

### #134 / PR #139: canonical full-68 intermediate evaluator

Status: completed.

Canonical command:

```bash
make eval-issue120-full
```

This evaluates saved post-CNN-scoring detector intermediates and validates the canonical 68-page set.

Verified detector result from saved Golden Baseline scored outputs:

```text
Pages: 68/68
Detector: GT=3581 Pred=3597 TP=3580 FP=0 FN=1 FN_det=0 FN_cnn=1
```

Boundary:

- This is not full-pipeline reproduction.
- It verifies saved post-CNN-scoring intermediates only.

### #136 / PR #143: historical best and clean detector-level transplant target

Status: completed.

PR:

```text
#143 docs/tools: audit Issue 120 historical best and reconstruction path
merge commit: 0c0eaafcb9dda3c3d48be2db6cea41c603187f0a
```

Stage A result:

```text
saved scored Golden Baseline intermediates
  -> #134 canonical evaluator
  -> TP=3580 / FP=0 / FN=1
```

Stage B result:

```text
saved candidates + pipeline scorer + NMS enabled:
  Pred=3507 TP=3507 FP=0 FN=74

saved candidates + legacy scorer:
  Pred=3597 TP=3580 FP=0 FN=1

saved candidates + pipeline scorer + NMS disabled:
  Pred=3597 TP=3580 FP=0 FN=1
```

Stage C result:

```text
Issue53 probe rescue candidates:
  baseline candidates: 29443
  regenerated candidates: 29772
  empty pages: 0
  detector result: TP=3580 FP=0 FN=1
```

Current clean detector-level reconstruction target:

```text
#57 / Issue53 probe rescue candidate generation
  -> current pipeline CNN scoring
  -> cnn_apply_nms=false
  -> #134 canonical full-68 evaluator
  -> TP=3580 FP=0 FN=1
```

Remaining limitation:

```text
logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
```

This historical `bands_from` artifact remains the upstream dependency for Stage C, but #149 / PR #150 recovered a reproducible Issue36 dense producer route that can regenerate an equivalent root.

### #135 / PR #144: generated artifact cleanup and retention policy

Status: completed.

PR:

```text
#144 chore/docs: define Issue 120 artifact retention policy
merge commit: f18dc801345e56a6ac90c95228b9448f2a34a440
```

Policy document:

```text
docs/ISSUE120_ARTIFACT_RETENTION.md
```

Current #135 decision:

- Keep source/docs/tools/config templates in Git.
- Keep canonical evaluation input data in Git while the repository depends on it.
- Temporarily retain `data/evaluation2/golden_baseline_eval2_bc23deb/` as an Issue #120 detector-intermediate fixture until Stage D/E produce a replacement artifact strategy.
- Remove generated summaries from that fixture when they are not required evaluator inputs.
- Ignore regenerated outputs under `logs/`.

Retained fixture boundary:

- It is detector-intermediate evidence.
- It is not full-pipeline reproduction evidence.
- It should not be removed until Stage D/E define a replacement artifact path.

### #140 / PR #145: Stage D upstream artifact regeneration

Status: completed; diagnostic foundation merged and boundary recorded.

PR:

```text
#145 tools/docs: add Issue 120 Stage D upstream regeneration runner
merge commit: a685bef1bda26e66937bd276df560ce655f67f5f
```

Stage D document:

```text
docs/refactors/issue120/ISSUE120_STAGE_D_UPSTREAM_REGEN.md
```

Purpose:

Verify whether the slow upstream artifacts used by Stage C can be regenerated:

```text
HOMR / OMR / SR / SR-side HOMR / OMR-DLN or equivalent
  -> bands_from-like artifact
  -> Issue53 probe rescue Stage C
  -> canonical evaluator
```

Current local Stage-D boundary recorded by PR #145:

```text
Target: TP=3580 FP=0 FN=1
Best current Stage D composition tested: baseline source
Observed: TP=3543 FP=288 FN=38
```

Interpretation:

- Current upstream components can regenerate structurally complete 68-page artifacts.
- Tested current compositions do not reproduce the historical detector target.
- The recovered Issue36 dense route from #149 now provides a reproducible validation route for the historical dense/bands-like root, but it is not yet a regular production pipeline module.

### #149 / PR #150: recovered Issue36 dense candidate validation route

Status: completed.

PR:

```text
#150 Issue120: integrate Issue36 dense candidate validation route
merge commit: 4824826d13fc87e93dce15b1fdcd4c9ed51dd448
```

Result:

```text
Issue36 inventory
  -> dense raw candidates
  -> clef-mask-aware filtered root
  -> historical raw/filtered/scoring-input candidate-root equality checks
  -> Issue53 probe-rescue using regenerated filtered root as bands_from
  -> current pipeline CNN scoring
  -> cnn_apply_nms=false
  -> #134 canonical full-68 evaluator
  -> TP=3580 FP=0 FN=1
```

Validation command:

```bash
make -f Makefile -f tools/issue120/Makefile.issue36_dense.mk \
  verify-issue120-issue36-dense \
  ISSUE120_ISSUE36_DENSE_REQUIRE_TARGET=1
```

Confirmed detector result:

```text
Pages: 68/68
Detector: GT=3581 Pred=3600 TP=3580 FP=0 FN=1 FN_det=0 FN_cnn=1
```

Boundary:

- #149 is a reproducible validation route, not yet a production pipeline module.
- Direct scoring of the Issue36 filtered root is diagnostic only; the accepted route uses that root as Issue53 `bands_from`.
- Productionization and module-level refactoring are split to #151.

## Current / next issues

### #151: production pipeline route / module refactoring

Status: in progress.

Branch policy:

```text
base: rebuild/issue120
branch: refactor/issue120-production-reconstruction-route
PR base: rebuild/issue120
```

Purpose:

Promote the recovered Issue36 dense reconstruction route from issue-specific validation tooling into regular, maintainable pipeline modules/configuration.

Current #151 implementation route:

```bash
python -m src.pipeline.detector_routes.dense_probe_candidate_route \
  --config configs/detector_routes/issue120_dense_probe_candidate_route.yaml \
  --require-detector-target
```

The route writes generated artifacts under:

```text
logs/issue120_e2e_recovery/dense_probe_candidate_route/
```

Scope note:

- This is a detector-level partial route: dense candidate/bands generation, clef-mask-aware filtering, probe rescue, CNN scoring, and canonical detector evaluation.
- It does not run slow HOMR/SR/OMR upstream generation, full PDF pipeline orchestration, downstream measure numbering, or measure-count evaluation.

Compatibility note:

- `tools/issue120/run_issue36_dense_bands_then_issue53_eval.py` delegates to the production module.
- `tools/issue120/run_issue36_dense_candidates_then_eval.py` remains a diagnostic direct-score wrapper only.

This is intentionally separate from:

- #149, which closed the reproducible validation-route integration;
- #141, which remains a full 68-page validation/audit issue;
- #142, which remains NMS policy only.

Scope:

- factor reusable dense generation / clef-mask filtering / Issue53 probe-rescue orchestration out of `tools/issue120/` where appropriate;
- add a production-style entrypoint or config route;
- preserve provenance for candidate generation, clef-mask resolution, `cnn_apply_nms`, detector metrics, and downstream metrics;
- support practical incremental/debug workflows without silently deleting generated artifacts;
- keep all generated outputs under ignored `logs/` paths.

Acceptance:

```text
dense probe-candidate detector route
  -> TP=3580 FP=0 FN=1 with cnn_apply_nms=false explicitly recorded
```

### #142: CNN scoring NMS repair/tuning

Status: open.

Branch policy:

```text
base: rebuild/issue120
branch: fix/issue120-cnn-nms-policy
PR base: rebuild/issue120
```

Purpose:

Decide whether NMS should be kept, tuned, made conditional, or disabled in specific reconstruction modes.

Current policy:

```text
default general pipeline: cnn_apply_nms=false
NMS experiments: cnn_apply_nms=true only as explicit opt-in
Issue120 reconstruction: cnn_apply_nms=false, explicitly recorded
```

Acceptance:

- no silent NMS behavior changes;
- any future default-on change requires detector and measure-count evidence.

### #141: Stage E full 68-page pipeline validation

Status: open.

Branch policy:

```text
base: rebuild/issue120
branch: audit/issue120-stage-e-full-pipeline
PR base: rebuild/issue120
```

Purpose:

Run or document the full 68-page pipeline result after Stage D/#149 clarified upstream/recovered-route boundaries.

Current dependency:

- Stage D has a current-upstream failure boundary.
- #149 has a reproducible recovered dense validation route that preserves the detector target.
- #151 owns promotion of that route into regular pipeline modules/configuration.
- Stage E can proceed as an audit if it records which route is being validated and does not conflate full slow upstream regeneration with recovered dense-route validation.

Acceptance:

- complete 68-page output;
- #134 canonical detector evaluation;
- downstream measure-count metrics recorded separately;
- generated artifacts remain under ignored paths.

### #137: targeted accuracy repair

Status: open.

Branch policy:

```text
base: rebuild/issue120
branch: fix/issue120-accuracy-after-audit
PR base: rebuild/issue120
```

Purpose:

Resume targeted accuracy work only after audit and canonical evaluation gates are established.

Dependencies:

- #134, #135, #136, #140, and #149 are completed.
- #151 should productionize the recovered dense route before it is treated as a regular pipeline path.
- #142 should decide NMS policy before broad accuracy repair.
- #141/#151 should not be mixed with broad algorithm changes.

## Recommended order from here

```text
1. Work #151 to promote the recovered dense validation route into production pipeline modules/configuration.
2. Work #142 to decide NMS behavior before broad accuracy repair.
3. Work #141 as full 68-page validation/audit, explicitly separating detector metrics from downstream measure-count metrics and recording whether #151 is complete or pending.
4. Work #137 targeted accuracy repair using the canonical gates.
```

## Current canonical detector target

Until changed by a later audited issue:

```text
TP=3580 / FP=0 / FN=1
```

Canonical reconstruction mode:

```yaml
detection:
  cnn_apply_nms: false
```

Canonical evaluator:

```bash
make eval-issue120-full
```

Issue53-derived Stage C verifier:

```bash
docker run --rm --gpus all \
  -v "$PWD":/workspace \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  pdfscore_pipeline_gpu \
  /opt/venv_pipeline/bin/python tools/issue120/run_issue53_probe_rescue_then_eval.py
```

Recovered Issue36 dense-route verifier:

```bash
make -f Makefile -f tools/issue120/Makefile.issue36_dense.mk \
  verify-issue120-issue36-dense \
  ISSUE120_ISSUE36_DENSE_REQUIRE_TARGET=1
```
