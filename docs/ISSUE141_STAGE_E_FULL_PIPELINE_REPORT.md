# Issue 141: Stage E Full Pipeline Validation Report

## Purpose

This document records the full 68-page Stage E pipeline validation result against the Issue #120 detector target.

Stage E validates the real full pipeline path. It is distinct from the #151 dense probe-candidate route, which is a detector-level partial route and does not run the full HOMR/SR/OMR-inclusive pipeline or downstream measure numbering.

## Execution Configuration

- **Run ID**: `stage_e_full_pipeline`
- **Output location**: `logs/issue120_e2e_recovery/stage_e_full_pipeline/`
- **Components run**: dense candidate reconstruction, probe-rescue candidate reconstruction, HOMR/SR/OMR-inclusive full pipeline execution, CNN scoring, and downstream measure numbering.
- **NMS policy**: `cnn_apply_nms: false` per Issue #142.

## Runtime, Resource, and Log Surface

Issue #159 adds metric-neutral observability around the Stage E runner and dense route:

- `dense_route_execution_summary.json` records dense-route phase durations, command log paths, log sizes, and generated artifact roots.
- `stage_e_runtime_summary.json` records the dense-route summary plus image-copy and full-pipeline durations.
- `stage_e_resource_samples.jsonl` records best-effort CPU/RSS/GPU samples during full-pipeline execution.
- `stage_e_resource_samples.summary.json` records best-effort peak CPU/RSS/GPU summaries derived from those samples.
- `pipeline_stdout_stderr.log` captures stdout/stderr emitted during full-pipeline execution.
- `pipeline_stdout_stderr.summary.json` records compact counts and markers from the captured console log.
- If a pipeline phase summary is produced by the run, `stage_e_runtime_summary.json` attaches its path and payload for convenience. Issue #159 does not make full-pipeline phase timing a default pipeline artifact.
- Dense reconstruction subprocess logs are compact by default. The compact log keeps bounded head/tail output and records omitted middle-line counts.
- Diagnostic full logs can be enabled with `--dense-route-verbose-logs`, but the runner should be invoked through the Stage E make target / managed pipeline environment.

Resource sampling is best-effort:

- Process memory uses Python `resource` and, when installed, `psutil` process-tree RSS.
- Live process-tree CPU percentage uses `psutil` process-tree CPU-time deltas when available.
- Child-process `resource` CPU deltas are kept only as a diagnostic signal, not as live subprocess CPU.
- GPU memory/utilization uses `nvidia-smi` when available.
- Sampling can be disabled with `--no-resource-sampling`.
- The sampling interval can be adjusted with `--resource-sample-interval-sec`; non-positive intervals are rejected while sampling is enabled.

These summaries are generated under `logs/` and should not be committed.

Issue #159 uses these artifacts to identify safe parallelization opportunities. The measurements showed that Stage E runtime is dominated by HOMR/SR detection, but actual HOMR/SR parallelization experiments are intentionally deferred to follow-up issue #163/#166 so this validated checkpoint does not introduce new resource scheduling behavior.

Pipeline logging taxonomy and default noisy-log policy are deferred to follow-up issue #162/#164. Issue #159 captures and summarizes stdout/stderr but does not redesign default logger semantics.

## One-command Stage E Contract Evaluation

After the full Stage E run completes, first run the small smoke check:

```bash
make eval-issue120-stage-e-smoke
```

This smoke target evaluates only the first `ISSUE120_STAGE_E_SMOKE_PAGES` canonical pages, defaulting to `2`. It is intended to verify Stage E artifact discovery, `eval_inputs` materialization, and contract output writing before spending time on the full 68-page contract evaluation. Because it is partial by design, the target passes `--allow-partial --allow-target-mismatch` and writes to smoke-specific directories:

```text
logs/issue120_e2e_recovery/stage_e_full_pipeline/eval_inputs_smoke/
logs/issue120_e2e_recovery/stage_e_full_pipeline/eval_detector_smoke/
```

When the smoke check succeeds, run full contract evaluation with:

```bash
make eval-issue120-stage-e-full
```

The full make target calls `tools/issue120/eval_stage_e_contract.py`, using `ISSUE120_STAGE_E_OUTPUT` as the input `--output-root`. By default this is:

```text
logs/issue120_e2e_recovery
```

The evaluator does not require manual path discovery or one-off copy scripts. It materializes an evaluator-compatible input tree from the current full-pipeline artifact layout:

```text
logs/issue120_e2e_recovery/stage_e_full_pipeline/eval_inputs/
```

It then writes detector contract outputs to:

```text
logs/issue120_e2e_recovery/stage_e_full_pipeline/eval_detector/
```

Expected full contract outputs:

```text
logs/issue120_e2e_recovery/stage_e_full_pipeline/eval_detector/evaluation_contract.json
logs/issue120_e2e_recovery/stage_e_full_pipeline/eval_detector/detector_metrics.json
logs/issue120_e2e_recovery/stage_e_full_pipeline/eval_detector/detector_page_metrics.csv
logs/issue120_e2e_recovery/stage_e_full_pipeline/eval_detector/manifest.json
```

The wrapper checks the canonical Stage E detector target by default and exits non-zero if the target is not met. For diagnostic runs that intentionally inspect a mismatch, pass extra arguments through:

```bash
make eval-issue120-stage-e-full ISSUE120_STAGE_E_EVAL_EXTRA_ARGS=--allow-target-mismatch
```

The full run artifacts and resource summaries remain under:

```text
logs/issue120_e2e_recovery/stage_e_full_pipeline/
logs/issue120_e2e_recovery/stage_e_full_pipeline/stage_e_runtime_summary.json
logs/issue120_e2e_recovery/stage_e_full_pipeline/dense_route_execution_summary.json
logs/issue120_e2e_recovery/stage_e_full_pipeline/stage_e_resource_samples.summary.json
```

## Detector Metrics vs Target

The detector metrics are produced from full-pipeline Stage E artifacts using `tools/issue120/eval_stage_e_contract.py` and recorded in `evaluation_contract.json`.

- **Target**: `TP=3580 / FP=0 / FN=1`
- **Observed Stage E run**: `TP=3580 / FP=0 / FN=1`
- **Target met**: yes

Additional detector summary:

```text
Pages=68/68
GT=3581
Pred=3600
TP=3580
FP=0
FN=1
FN_det=0
FN_cnn=1
Precision=1.000000
Recall=0.999721
cnn_apply_nms=false
```

## Repair Summary

The initial Stage E full-pipeline route did not reproduce the recovered detector target:

```text
Initial Stage E: TP=3359 FP=145 FN=222 FN_det=222 FN_cnn=0
```

The failure was not caused by CNN NMS policy. It was caused by the full pipeline not using the same reconstructed candidate route as the recovered dense detector path.

The repair connects Stage E to the recovered route without consuming historical candidate logs as runtime input:

1. Regenerate dense probe candidates inside the current Stage E run.
2. Apply clef/staff-aware candidate filtering inside the current Stage E run.
3. Regenerate probe-rescue candidates from that filtered root inside the current Stage E run.
4. Feed the freshly regenerated probe-rescue candidate root into the full pipeline detector/CNN scoring path.
5. Evaluate detector metrics from the full-pipeline Stage E artifacts.

This keeps #151 as detector-level evidence while making #141 validate a real full-pipeline Stage E run.

## Downstream Measure-Count Metrics

Detector metrics and downstream measure-count metrics remain separate.

The full pipeline writes downstream numbering output under:

```text
logs/issue120_e2e_recovery/stage_e_full_pipeline/outputs/numbering_final.json
```

A canonical downstream measure-count comparator is not attached in this audit. The Stage E evaluation contract records measure-count status as `not_provided` rather than deriving detector conclusions from downstream numbering output.

## Conclusion

- Stage E now completes all 68 canonical evaluation pages.
- The full HOMR/SR/OMR-inclusive Stage E pipeline now meets the Issue #120 canonical detector target: `TP=3580 / FP=0 / FN=1`.
- Detector metrics and downstream measure-count status are recorded separately in the machine-readable evaluation contract.
- #151 remains a detector-level partial route and should not be reported as a full-pipeline result by itself.
- Remaining productionization/refactor work should focus on replacing Stage E runner glue with a cleaner pipeline module/API while preserving the recovered route and evaluation contract semantics.
