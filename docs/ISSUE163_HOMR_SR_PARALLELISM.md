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

## Opt-in configs

Route-level subprocess overlap:

```yaml
detection:
  homr_route_parallel_experiment:
    enabled: true
    mode: baseline_sr_subprocess_overlap
    max_workers: 2
```

Granular in-process phase overlap:

```yaml
detection:
  homr_route_parallel_experiment:
    enabled: true
    mode: inprocess_sr_prep_baseline_overlap
    max_workers: 2
```

When disabled or omitted, `HybridDetector` uses the existing in-process sequential route.

The initial route-level experiment intentionally uses subprocess HOMR route execution even when in-process HOMR is importable. This isolates each route in its own process and avoids sharing one in-process HOMR predictor or Real-ESRGAN upsampler across threads. The trade-off is higher process/GPU memory pressure, so this mode is experimental and bounded to `max_workers=2`.

The granular experiment keeps HOMR execution in-process and overlaps only SR image preparation with the baseline HOMR route. SR HOMR inference still waits until SR preparation and baseline finish, preserving the explicit SR VRAM cleanup boundary before inference.

## Flow comparison

Default sequential flow:

```mermaid
sequenceDiagram
    participant P as Pipeline / HybridDetector
    participant B as HOMR baseline in-process
    participant S as HOMR SR in-process
    participant O as OMR-DLN subprocess
    participant C as Consensus

    P->>B: prepare originals + HOMR inference
    B-->>P: baseline/batch detections
    P->>S: SR preparation with persistent upsampler
    S->>S: release SR VRAM barrier
    S->>S: HOMR inference with persistent predictor
    S-->>P: sr/batch detections + SR images
    P->>O: consume sr/batch as precomputed SR
    O-->>P: omr_sr predictions
    P->>C: merge baseline + SR + OMR-DLN
```

Route-level subprocess-overlap experiment:

```mermaid
sequenceDiagram
    participant P as Pipeline / HybridDetector
    participant T as ThreadPoolExecutor max_workers=2
    participant B as subprocess: HOMR baseline
    participant S as subprocess: HOMR SR
    participant O as OMR-DLN subprocess
    participant C as Consensus

    P->>T: submit baseline and SR route commands
    par baseline route
        T->>B: homr_evaluator.py --enable-segnet-cache
        B-->>T: baseline/batch detections
    and SR route
        T->>S: homr_evaluator.py --enable-sr --sr-scale 2 --enable-segnet-cache
        S-->>T: sr/batch detections + SR images
    end
    T-->>P: wait for both route futures
    P->>O: consume sr/batch as precomputed SR
    O-->>P: omr_sr predictions
    P->>C: merge baseline + SR + OMR-DLN
```

Granular in-process phase-overlap experiment:

```mermaid
sequenceDiagram
    participant P as Pipeline / HybridDetector
    participant T as ThreadPoolExecutor max_workers=2
    participant B as in-process HOMR baseline full route
    participant R as in-process SR preparation only
    participant S as in-process HOMR SR inference
    participant O as OMR-DLN subprocess
    participant C as Consensus

    P->>T: submit baseline full route and SR preparation
    par baseline full route
        T->>B: prepare originals + HOMR inference
        B-->>T: baseline/batch detections
    and SR preparation only
        T->>R: RealESRGAN SR + write sr/batch images
        R->>R: release SR VRAM barrier
        R-->>T: prepared SR working images
    end
    T-->>P: wait for baseline and SR preparation
    P->>S: HOMR inference on prepared SR images
    S-->>P: sr/batch detections
    P->>O: consume sr/batch as precomputed SR
    O-->>P: omr_sr predictions
    P->>C: merge baseline + SR + OMR-DLN
```

Expected speedup model for route-level overlap:

```text
sequential HOMR wall time ~= baseline + SR
parallel HOMR wall time ~= max(baseline, SR)
```

This only helps if the per-route durations stay roughly unchanged while overlapped.

Expected speedup model for granular phase overlap:

```text
sequential HOMR wall time ~= baseline_full + sr_preparation + sr_inference
granular HOMR wall time ~= max(baseline_full, sr_preparation) + sr_inference
```

This is a narrower experiment. It can only save up to the smaller of baseline_full and sr_preparation, but it avoids the route-level subprocess model/cache/GPU-memory duplication.

## Route-level subprocess experiment result

The first opt-in run preserved the canonical detector contract:

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

However, runtime and resources regressed:

- total runtime: 9764.83 sec
- pipeline runtime: 9704.30 sec
- HOMR overlap experiment duration: 9368.13 sec
- HOMR baseline subprocess duration: 5438.08 sec
- HOMR SR subprocess duration: 9368.13 sec
- peak GPU memory: 6780 MB
- peak process-tree RSS: 7525986304 bytes

The #159 reference evidence was roughly:

- total runtime: about 7611.6 sec
- full pipeline: about 7554.2 sec
- peak GPU memory: 4776 MB

The route-level subprocess experiment therefore kept accuracy but did not reduce runtime.

## Rejection analysis for route-level subprocess overlap

The observed regression is consistent with the following explanation:

1. **The critical path remained the SR route.** In the parallel run, total overlap duration was essentially the HOMR SR subprocess duration. The baseline route finished earlier, but it did not matter because consensus and OMR-DLN cannot proceed until SR output exists.
2. **The subprocess route discarded the current in-process persistence advantage.** The default path keeps HOMR execution in-process and uses persistent objects inside each route. The experiment starts separate `homr_evaluator.py` processes, which reintroduces process startup, independent model initialization, and separate CUDA/process memory pressure.
3. **Both subprocesses contended for the same GPU.** Baseline HOMR inference and SR/HOMR processing ran at the same time on one GPU. The run reached 100% peak utilization and higher GPU memory. This can increase queuing and reduce effective throughput even though work is nominally parallel.
4. **Memory pressure increased.** Peak GPU memory rose from the #159 reference level to 6780 MB. With two independent processes, model weights, CUDA context, buffers, and SR/HOMR intermediates are duplicated rather than reused.
5. **SR route slowdown dominated any baseline overlap benefit.** The reference `homr_sr` evidence was about 5303 sec, while the experiment recorded 9368 sec for the SR subprocess. Even if baseline became fully hidden behind SR, the SR route itself became too slow.
6. **The experiment overlapped routes, not the useful subphases.** The likely useful target is narrower: maintain in-process persistence and overlap only CPU/I/O-light or GPU-idle portions where the resource profile shows slack. Full-route subprocess overlap is too coarse.

## Granular in-process phase-overlap experiment result

The second opt-in run also preserved the canonical detector contract:

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

Runtime/resource evidence:

- total runtime: 7736.00 sec
- pipeline runtime: 7673.71 sec
- HOMR granular experiment duration: 7309.15 sec
- HOMR baseline full route: 2198.31 sec
- HOMR SR preparation: 2747.39 sec
- HOMR SR inference: 4561.69 sec
- peak GPU memory: 4332 MB
- peak process-tree RSS: 5814255616 bytes

This result is much better than the route-level subprocess experiment:

- total runtime improved from 9764.83 sec to 7736.00 sec
- HOMR experiment section improved from 9368.13 sec to 7309.15 sec
- peak GPU memory improved from 6780 MB to 4332 MB

However, it is still slower than the #159 reference evidence:

- total runtime: 7736.00 sec vs about 7611.6 sec reference
- pipeline runtime: 7673.71 sec vs about 7554.2 sec reference

The narrower overlap therefore removed the subprocess regression, but it still did not produce a net runtime improvement over the accepted sequential reference.

## Rejection analysis for granular phase overlap

The measured phase timing matches the expected granular model:

```text
max(2198.31, 2747.39) + 4561.69 = about 7309.08 sec
```

The overlap itself worked mechanically. The remaining problem is that SR preparation and baseline both slowed relative to the earlier sequential evidence, and the saved overlap was not enough to overcome that overhead. Running SR preparation concurrently with baseline in the same process still creates Python-thread/CUDA/memory contention, although much less than the subprocess route-level experiment.

The granular mode has a positive resource profile compared with both prior references, especially peak GPU memory, but #163 is a runtime-reduction issue. Lower memory pressure alone is not enough to promote this mode.

## Final decision

Do not adopt either experimental mode as a default or recommended Stage E mode.

- `baseline_sr_subprocess_overlap`: rejected because it substantially regressed runtime and GPU memory.
- `inprocess_sr_prep_baseline_overlap`: rejected because it preserved the contract and improved resources, but did not improve runtime relative to the accepted sequential reference.

Default sequential behavior remains the recommendation for #163.

No formal adoption issue should be created from these results. The PR should remain as the experiment record unless a reviewer wants the unused experiment code removed before merging documentation-only evidence.

## Required validation command reference

Canonical Stage E validation:

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

Granular phase-overlap experiment:

```bash
make run-issue163-stage-e-homr-phase-overlap
make eval-issue120-stage-e-full
PYTHONPATH=. python3 tools/issue120/attach_stage_e_eval_contract.py \
  --manifest logs/issue120_e2e_recovery/stage_e_full_pipeline/manifest.json \
  --eval-dir logs/issue120_e2e_recovery/stage_e_full_pipeline/eval_detector \
  --score-threshold 0.1 \
  --xdist-threshold 12.0
```

Generated files under `logs/` are evidence artifacts and must not be committed.

## Follow-up candidates outside this experiment

The dependency review found additional runtime-reduction candidates that should remain separate from the route/phase overlap scheduling experiments:

- SR image/cache reuse across repeated Stage E attempts.
- Avoiding unnecessary repeated image copy/preparation work in the Stage E runner.
- Reducing redundant HOMR preparation work while preserving output layout and provenance.
- Page chunking only if it can preserve cache behavior and stay below resource limits.
- Moving Stage E runner glue into a clearer pipeline module/API once the contract remains stable.

These may deserve separate issues if a future measurement confirms they are material bottlenecks or if the implementation would touch canonical pipeline structure rather than only opt-in scheduling.
