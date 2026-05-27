# Issue 163: HOMR/SR Route Parallelism Experiment

## Scope

Issue #163 evaluates whether Stage E runtime can be reduced by overlapping the HOMR baseline and HOMR SR routes without changing detector semantics.

The default Stage E path remains unchanged:

- HOMR baseline runs before HOMR SR.
- HOMR SR runs before OMR-DLN SR.
- OMR-DLN SR still consumes `sr/batch` as precomputed SR input.
- Hybrid consensus still consumes the baseline, SR, and OMR-DLN outputs.
- CNN scoring, detector thresholds, candidate generation, NMS policy, and downstream measure numbering are not changed.

The experiment is opt-in only. It must not be enabled in canonical configs unless a later adoption issue proves that it is safe and effective.

## Opt-in config

```yaml
detection:
  homr_route_parallel_experiment:
    enabled: true
    mode: baseline_sr_subprocess_overlap
    max_workers: 2
```

When disabled or omitted, `HybridDetector` uses the existing in-process sequential route.

The initial experiment intentionally uses subprocess HOMR route execution even when in-process HOMR is importable. This isolates each route in its own process and avoids sharing one in-process HOMR predictor or Real-ESRGAN upsampler across threads. The trade-off is higher process/GPU memory pressure, so this mode is experimental and bounded to `max_workers=2`.

## Required validation

Before considering the experiment successful, run the canonical Stage E validation and compare both runtime and resources against the sequential baseline:

```bash
make run-issue120-stage-e-full \
  ISSUE120_STAGE_E_EXTRA_ARGS="--resource-sample-interval-sec 1.0"

make eval-issue120-stage-e-full

PYTHONPATH=. python3 tools/issue120/attach_stage_e_eval_contract.py \
  --manifest logs/issue120_e2e_recovery/stage_e_full_pipeline/manifest.json \
  --eval-dir logs/issue120_e2e_recovery/stage_e_full_pipeline/eval_detector \
  --score-threshold 0.1 \
  --xdist-threshold 12.0
```

The expected detector contract is unchanged:

```text
expected_pages=68
evaluated_pages=68
missing_pages=[]
GT=3581
Pred=3600
TP=3580
FP=0
FN=1
FN_det=0
FN_cnn=1
cnn_apply_nms=false
target_met.detector=true
```

Generated files under `logs/` are evidence artifacts and must not be committed.

## Acceptance decision rule

The experiment can be recommended for a formal adoption issue only if all of the following are true:

1. The Stage E detector contract is unchanged.
2. `cnn_apply_nms=false` is preserved.
3. Runtime improves enough to justify the added scheduling complexity.
4. Resource summaries show acceptable GPU memory, GPU utilization, CPU, and RSS behavior.
5. Failures or missing outputs are absent from the HOMR route experiment summary.

If the detector contract changes, resource usage becomes unstable, or runtime does not materially improve, keep the experiment opt-in and document the rejection rationale in #163 instead of adopting it.

## Follow-up candidates outside this experiment

The dependency review found additional runtime-reduction candidates that should remain separate from the initial parallel scheduling experiment:

- SR image/cache reuse across repeated Stage E attempts.
- Avoiding unnecessary repeated image copy/preparation work in the Stage E runner.
- Reducing redundant HOMR preparation work while preserving output layout and provenance.
- Moving Stage E runner glue into a clearer pipeline module/API once the contract remains stable.

These may deserve separate issues if the #163 run confirms they are material bottlenecks or if the implementation would touch canonical pipeline structure rather than only opt-in scheduling.