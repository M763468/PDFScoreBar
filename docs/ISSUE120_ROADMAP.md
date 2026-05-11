# Issue 120 Roadmap

## Purpose

This roadmap reflects the Issue #120 restart after #133, #134, and #136 work.

The current strategy is to separate five layers that were previously mixed together:

```text
Stage A: saved scored intermediates
Stage B: saved candidates -> scoring -> canonical evaluation
Stage C: regenerated candidates -> scoring -> canonical evaluation
Stage D: regenerated slow upstream HOMR/OMR/SR artifacts -> Stage C
Stage E: full 68-page pipeline validation
```

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

Result:

```bash
make eval-issue120-full
```

This evaluates saved post-CNN-scoring detector intermediates and validates the canonical 68-page set.

Verified detector result from saved Golden Baseline scored outputs:

```text
Pages: 68/68
Detector: GT=3581 Pred=3597 TP=3580 FP=0 FN=1 FN_det=0 FN_cnn=1
```

Important boundary:

- This is not full-pipeline reproduction.
- It verifies saved post-CNN-scoring intermediates only.

## #136: historical best and clean detector-level transplant target

Status: in PR / review.

Branch:

```text
audit/issue120-best-accuracy
```

PR base:

```text
rebuild/issue120
```

### Stage A result

Saved scored Golden Baseline intermediates reproduce the detector target:

```text
TP=3580 / FP=0 / FN=1
```

### Stage B result

Saved Golden Baseline candidates can reproduce the detector target through current pipeline CNN scoring if NMS is disabled:

```text
Stage B saved candidates + pipeline scorer + NMS enabled:
  Pred=3507 TP=3507 FP=0 FN=74

Stage B saved candidates + legacy scorer:
  Pred=3597 TP=3580 FP=0 FN=1

Stage B saved candidates + pipeline scorer + NMS disabled:
  Pred=3597 TP=3580 FP=0 FN=1
```

Conclusion:

- candidate files, model artifact, images, GT, and CNN inference are sufficient;
- the Stage B regression is caused by current pipeline CNN scoring NMS;
- NMS remains enabled by default globally, but Issue #120 canonical reconstruction must explicitly record `cnn_apply_nms=false`.

### Stage C result

The first attempted Stage C path was not correct:

```text
reproduce_clean_seed_v12.py:
  baseline candidates: 29443
  regenerated candidates: 180
  empty pages: 40
```

This script is treated as a residual/rescue/filtered-subset experiment, not the canonical full candidate regeneration path.

The #57 / Issue53 probe rescue path is the current clean detector-level candidate regeneration path:

```text
Issue53 probe rescue path:
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

- This still depends on the historical `bands_from` artifact:

```text
logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
```

It is not yet full slow-upstream pipeline reproduction.

## Open / next issues

### #135: generated artifact cleanup and retention policy

Status: open.

Purpose:

- Clean tracked generated outputs and define what stays in Git.
- Keep scripts/docs/configs; move or ignore bulky generated logs/JSON/CSV/PNG artifacts.

Recommended timing:

- Can proceed after #136 PR is merged.
- Should not remove evidence needed for #140/#141 until references/provenance are documented.

### #137: accuracy repair after audit

Status: open.

Purpose:

- Resume targeted accuracy work only after audit and canonical evaluation gates are established.

Updated dependency:

- Depends on #136.
- Should incorporate #142 for NMS policy before changing scoring behavior.
- Should not mix Stage D/E full-upstream validation with algorithm changes.

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

## Recommended order from here

```text
1. Merge #136 PR.
2. Use #136 result as the detector-level clean transplant target.
3. Run #135 cleanup, preserving only source/docs/scripts and documented fixtures.
4. Work #140 to verify or bound slow upstream artifact regeneration.
5. Work #142 to decide NMS behavior before broad accuracy repair.
6. Work #141 full 68-page pipeline validation after #140 boundary is known.
7. Work #137 targeted accuracy repair using the canonical gates.
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
