# Issue 120 Roadmap

## Purpose

This roadmap reflects the Issue #120 restart after #133, #134, and the #136 audit merged through PR #143.

The current strategy is to keep these layers separate:

```text
Stage A: saved scored intermediates
Stage B: saved candidates -> scoring -> canonical evaluation
Stage C: regenerated candidates -> scoring -> canonical evaluation
Stage D: regenerated slow upstream HOMR/OMR/SR artifacts -> Stage C
Stage E: full 68-page pipeline validation
```

Detector-level metrics and downstream measure-count metrics must not be mixed.

## Current completed foundation

### #133: restart plan

Status: completed.

Result:

- `rebuild/issue120` is the audit/integration target.
- `fix/probe_seeds` is frozen as an experimental/evidence branch.
- Issue #120 remains the parent Epic.
- Work is split into staged audit/cleanup/repair issues.

### #134: canonical full-68 intermediate evaluator

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

This historical `bands_from` artifact is still an upstream dependency. Full slow-upstream regeneration is not proven.

## Current / next issues

### #135: generated artifact cleanup and retention policy

Status: in progress.

Branch policy:

```text
base: rebuild/issue120
branch: chore/issue120-artifact-cleanup
PR base: rebuild/issue120
```

Purpose:

- Clean tracked generated outputs where doing so does not break the current canonical detector fixture.
- Define what stays in Git, what stays local under ignored `logs/`, and what remains a temporary retained fixture.

Current #135 policy:

- Keep source/docs/tools/config templates in Git.
- Keep canonical evaluation input data in Git while the repository depends on it.
- Temporarily retain `data/evaluation2/golden_baseline_eval2_bc23deb/` as an Issue #120 detector-intermediate fixture until Stage D/E produce a replacement artifact strategy.
- Remove generated summaries from that fixture when they are not required evaluator inputs.
- Ignore regenerated outputs under `logs/`.

### #140: Stage D upstream artifact regeneration

Status: open.

Branch policy:

```text
base: rebuild/issue120
branch: audit/issue120-stage-d-upstream-regen
PR base: rebuild/issue120
```

Purpose:

Verify whether the slow upstream artifacts used by Stage C can be regenerated:

```text
HOMR / OMR / SR / SR-side HOMR / OMR-DLN or equivalent
  -> bands_from-like artifact
  -> Issue53 probe rescue Stage C
  -> canonical evaluator
```

Primary input currently requiring provenance:

```text
logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
```

Acceptance:

- regenerated upstream artifacts can feed Stage C and preserve the detector target; or
- failure boundary is documented with follow-up issues.

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
default general pipeline: cnn_apply_nms=true
Issue120 reconstruction: cnn_apply_nms=false, explicitly recorded
```

Acceptance:

- no silent global NMS weakening;
- any default change requires detector and measure-count evidence.

### #141: Stage E full 68-page pipeline validation

Status: open.

Branch policy:

```text
base: rebuild/issue120
branch: audit/issue120-stage-e-full-pipeline
PR base: rebuild/issue120
```

Purpose:

Run or document the full 68-page pipeline result after Stage D clarifies upstream artifact regeneration.

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

- #134 and #136 completed.
- #135 should establish artifact policy before larger changes.
- #142 should decide NMS policy before broad accuracy repair.
- #140/#141 should not be mixed with algorithm changes.

## Recommended order from here

```text
1. Finish #135 cleanup/retention policy.
2. Work #140 to verify or bound slow upstream artifact regeneration.
3. Work #142 to decide NMS behavior before broad accuracy repair.
4. Work #141 full 68-page pipeline validation after #140 boundary is known.
5. Work #137 targeted accuracy repair using the canonical gates.
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
