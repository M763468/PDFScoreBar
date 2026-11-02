# Issue 458: independent opt-in adoption reassessment

The clean-source reassessment supports a **conditional opt-in proposal** on the
measured deployment. It does not activate production, change the default of one
worker, mark PR #467 ready, or authorize merge. The original cohort's
**4.900958% / Failed under its >=5% contract remains unchanged** in
[the historical report](issue458-results.md). Results are not pooled.

Authority: [owner request](https://github.com/M763468/PDFScoreBar/pull/467#issuecomment-6559450448).
The [new contract](issue458-reassessment-contract.md) was committed before new
inference at `d246ceba14904f9c01ee99f32b93cf0800616407`. Phase key is
`reassessment-20261101` (UTC; execution continued on November2 JST).

## Controlled warm performance

Four matched pairs, B/P, P/B, B/P, P/B; four observations per mode. Fresh
containers; trace OFF; identical inputs, selected models/thresholds, compile
mode, private compiler-warm seed copies, source OMP/MKL threads4, UID 1000/GID 1001,
RTX 4060 8 GiB and 16 GiB container RAM limit. Source was mounted read-only, with
only the Issue evidence root writable; no source edits or test/evaluation jobs
were run during the cohort. Actual command arrays and mounts are retained.

Source commit and tracked-source digest matched before/after every run:
`d246ceba14904f9c01ee99f32b93cf0800616407` / `2a580c4d0afd7d05bf98ea35f215fc3bb680de44a7c39edbf4057b2c14de268c`.
The primary seed contains538 files/20648097 bytes; its content digest is
`a0beb8ee131cad711b076c8efa0a00b4dddc33dba55e96cc85785f27a64027dd`. All eight primary caches retained
that same digest after execution. This is compiler-warm, not a claim of matched
OS file caches or an inferred compiler-hit rate. Managed #454 caching was not
enabled; the explicit legacy Inductor/Triton cache policy was identical in B/P.
Latest develop checked before execution was 6d53c5c2, whose delta from the PR base
was documentation only; the runtime lineage was intentionally kept fixed.

| Pair | One worker (s) | Two workers (s) | Reduction |
| --- | ---: | ---: | ---: |
| 1 | 247.472 | 226.527 | 8.46% |
| 2 | 248.567 | 228.400 | 8.11% |
| 3 | 248.764 | 226.883 | 8.80% |
| 4 | 252.762 | 232.606 | 7.97% |

| Mode | Median (s) | Range (s) | MAD (s) |
| --- | ---: | --- | ---: |
| One worker | 248.666 | 247.472–252.762 | 0.646 |
| Two workers | 227.641 | 226.527–232.606 | 0.936 |

Median saving: **21.024s / 8.45%**.
All four pairs improve. The predeclared practical gates (positive median,
>=5s saved, >=3/4 pair wins, no pair regression>3%) all pass. These descriptive
criteria support a limited deployment proposal; four pairs do not establish
statistical confidence, population-wide reliability or cross-device speed.
No extra favorable repetitions, excluded cases or retuned thresholds replace
the original negative result. The difference between the two cohorts is not
causally attributed to any one background/cache/source factor.

## Resources and additional shape

| Input / mode | Peak cgroup RAM (GiB) | Peak sampled device VRAM (MiB) | Median cgroup CPU (s) |
| --- | ---: | ---: | ---: |
| 2960×4210, one worker | 6.471 | 3472 | 472.51 |
| 2960×4210, two workers | 8.224 | 6610 | 504.04 |
| 3600×4680, one worker | 4.651 | 3462 | 407.08 |
| 3600×4680, two workers | 8.607 | 6613 | 444.60 |

The primary CPU median rises by 6.67%.
This is a latency/memory/CPU tradeoff, not an efficiency improvement on every
resource. Cgroup counters include file cache and the in-container observer;
summed RSS/residency must not be interpreted as exclusive model memory or stages.
Per-run physical I/O, utilization and CPU counters are in the
[machine-readable results](issue458-reassessment.json), with raw samples retained.

The larger-shape qualification and same-seed B/P pair completed. Its B/P times
were229.276s/202.313s. One pair tests safety and
semantic equality, not reproducible performance on that shape. A requested 2-
worker single-page run selected1 and completed in115.760s.
All 12 normal runs satisfy <=16 GiB cgroup RAM / <=7 GiB sampled device VRAM.
Across shapes the observed maxima are8.607 GiB and6613MiB, leaving approximately
7.39GiB below the RAM limit and555MiB below the sampled-VRAM screen. Neither
screen reserves memory nor bounds unsampled peaks or arbitrary content.

Actual 2 GiB cgroup admission rejects 2 workers; explicit pre-start serial policy
selects 1 with a recorded reason. Actual 3640×5155 and 3685×5174 inputs reject
under the exact-shape profile without model inference. Synthetic low-VRAM and
unsupported-device probes are separately labeled. A new optional
`allowed_input_shapes` guard rejects unvalidated shapes even when pixel area fits.

No sustained >=one-core/10s unrelated Linux-visible CPU activity was detected.
Docker inventories/events show no foreign container start/exec during the runs.
WSL/Windows and GPU PID observability cannot prove complete absence of all host
noise. This is a limitation, not a zero-background claim.

## Quality, ordering and failures

All 12 successful runs pass the original strict source predictions, decoded
masks, detector geometry, numbering/movement metadata, MMR and filter comparisons.
All 8 primary outputs pass actual manual0/movement reset/continuity/barline-edit
Phase A/C replay. The new primary baseline also matches the retained historical
baseline under the same strict comparisons. Sampled process/schedule audit passes
for all 12 runs: SR/source do not overlap, source concurrency stays within the
selected count, every page process is observed and consumption follows input order.

Fresh canonical GPU accuracy smoke at `d246ceba` passes 85/85, hard FP 0/FN 0/soft 0.
Six fresh real process fault cases pass: nonzero/missing/wrong-image/kill/timeout/
host cgroup OOM, with no final numbering, retained diagnostics and reaped children.
The real host OOM increments memory.events oom_kill0→1 in its isolated2 GiB test.
SIGTERM/descendant timeout cleanup and original sibling-error propagation are
also covered by the focused tests. Forced supervisor termination operationally
requires killing its whole job container/cgroup.

The initial CUDA 16 GiB torch.empty attempt **failed to inject OOM**: allocation
returned, and missing-result handling correctly aborted the job. Preserve that
Failed injection under `cuda-oom/`; it does not demonstrate physical exhaustion.
A separately fixed case at `e70b44d8` sets only the disposable fault child's native
CUDA allocator fraction to 5% and throw_on_cudamalloc_oom=True, then requests 1 GiB.
The actual allocator OutOfMemoryError, root-cause propagation, child cleanup,
retained diagnostics and no final publication all pass. This is real
**allocator-budget OOM**, not physical VRAM exhaustion. Production/performance
allocators were never retuned. See the contract addendum and
[PyTorch 2.14 documentation](https://github.com/pytorch/pytorch/blob/v2.14.0/docs/source/notes/cuda.md).

The first semantic analysis was **Blocked** by its historical hardcoded score
folder. Helper fix `e70b44d8` and 23 focused tests allow the alternative score;
the same retained inference outputs were rescored successfully. No neural
inference was repeated, tolerance relaxed, or case omitted for that correction.
The original blocked/failed logs remain separate from corrected attempts.

## Conditional opt-in proposal and rollback

Use the block below only as a reviewed proposal for the measured image/runtime,
UID 1000/GID 1001, eight-logical-CPU, dedicated single RTX 4060 deployment. Require
one active pipeline job per GPU, source read-only, a16 GiB job container limit,
private writable per-UID caches and unchanged selected model digests. It is not
an automatic default or a recommendation for untested devices, root performance,
worker counts or arbitrary shapes. Broader content/shape safety is unproven.

```yaml
detection:
  source_concurrency:
    workers: 2
    validated_workers: 2
    threads_per_worker: 4
    timeout_sec: 300
    device: NVIDIA GeForce RTX 4060
    ram_gib: 12
    vram_gib: 7
    max_input_pixels: 16848000
    allowed_input_shapes: [[2960, 4210], [3600, 4680]]
    on_unavailable: error
```

An operator must still enforce exclusive GPU scheduling; admission is a snapshot,
not a reservation. Keep failure/publication and peak-resource monitoring enabled
for any canary. Reject unavailable/unknown profiles; there is no running-job
retry or serial fallback. Validate new envelopes before increasing worker count,
which remains configurable without scheduler code edits.

Rollback affects new jobs: restore the default source_concurrency block
(workers: 1, timeout_sec: 900, on_unavailable: error, removing the opt-in thread/
envelope settings). Abort an unhealthy active job through its whole container/
cgroup, retain diagnosis, and start a new serial job with a fresh output root.
Do not resume partial artifacts or silently turn the failed run into success.
Default changes, activation and merge remain a separate owner decision; PR stays
Draft and Issue #458 remains open.

## Evidence and limitations

Timed source `d246ceba`; analysis/fault harness correction `e70b44d8`; immutable
production image5c5979a26f4b232bc93af6b2d040226a6e6f0c45557ccc8ad4db56153fa0398a,
Torch 2.14.0+cu130, CUDA 13.0. Utility tests use inspected image5311cf22… at the
nested issue worktree with matching PYTHONPATH and UID. Input/model digests were
checked before and after timing; original caches and manager work were preserved.

All raw phase evidence is under `logs/issue458/reassessment-20261101/` except the
maintained smoke's conventional paths, physically below the existing Issue #458
validation root. Exact argv/config/UID/mounts are in runs/*/provenance.json,
matrix.json and validation/commands.json (including the original post-results
and separate corrected attempts). Later corrected checks use the
explicit commands below and their separate logs. Runtime tests are applicable to
the exact frozen application source, which did not change in the analysis-only
correction or this report commit.

| Check | Current status | Command / evidence |
| --- | --- | --- |
| Runtime preflight | Passed | DOCKER_IMAGE=<immutable image> bash scripts/docker_runtime_validation.sh --config configs/dense_full_pipeline.yaml --preflight-only; validation/preflight.log, exit 0 |
| Fast/focused application guards | Passed:212 | shared container exact pytest invocation in validation/commands.json; validation/focused-fast.log, exit 0/11.44s; final application guard source committed unchanged at `d246ceba` |
| Fixed-source matrix | Passed:12 completions | PYTHONPATH=. python3 tools/issue458/reassess.py; matrix.json, validation/matrix.log; primary practical performance gates Passed |
| Semantic/correction first analysis | Blocked | incorrect historical score path; validation/semantic-correction.log, exit 1 |
| Corrected retained-output analysis | Passed:12/8 | production-image CPU command invoking tools/issue458/reassess_summary.py; validation/semantic-correction-v2.log, summary.json; exit 0 |
| Analysis helper regression | Passed:23 | exact docker/pytest argv in validation/commands.json; validation/analysis-focused.log, exit 0/1.49s |
| Process/SR/order/historical audit | Passed:12 | production-image CPU /audit.py command; validation/boundary-historical-audit.json(.log), exit 0 |
| Fresh process faults | Passed:6 | production image --memory 2g --memory-swap 2g; tools/issue458/faults.py --output logs/issue458/reassessment-20261101/faults; exit 0 |
| Initial CUDA injection | Failed to inject intended OOM | --gpus all --memory 4g; faults.py --cases cuda-oom; cuda-oom/result.json, exit 1; missing-result cleanup passed |
| Capped CUDA allocator injection | Passed | --gpus all --memory 4g; faults.py --cases cuda-allocator-oom --output logs/issue458/reassessment-20261101/cuda-allocator-oom; exit 0, real allocator error |
| Canonical GPU/accuracy smoke | Passed | make verify-gpu-smoke with exact immutable image/dataset/MMR mounts in validation/post-results.json; exit 0,85/85; logs/issue458/validation/system/gpu_smoke_20261101T160237Z/gpu_smoke.log |
| Full68/root performance/other devices/other shapes/physical VRAM exhaustion/lone supervisor SIGKILL | Not run or not achieved | bounded scope; no corresponding adoption claim |

Reproduction requires retained inputs/models and private compiler seed, new unique
phase/output paths and matching UID/runtime. The matrix refuses overwrite,
tracked source drift and persistent observed CPU competition. No cold/full68
rerun was launched for timing alone. Reproduction of the failed16 GiB injection
is not a requirement for or guarantee of physical GPU exhaustion.
