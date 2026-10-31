# Issue 458 production concurrency validation

Status: **not approved for production activation**. The original warm E2E target
was >=5% median reduction. This attempt measured **4.900958%**, so that gate failed;
it is not rounded into a pass. The production default remains one worker.

Implementation base: `afa19333`; successful scheduling path checkpoint:
`75e5772d`. Later commits add tests/docs and `51a4800d` adds failure-only diagnostic
retention. Final error propagation checkpoint: `0c52a226`. The final error path is covered
by 206 fast/focused tests and six real pipeline fault cases; successful inference
and geometry algorithms did not change after the timed cohort. See the [fixed contract](issue458-contract.md) and
[configuration/failure policy](issue458-source-concurrency.md).

## Fixed warm observations

Fresh containers, trace OFF, immutable image
`sha256:5c5979a26f4b232bc93af6b2d040226a6e6f0c45557ccc8ad4db56153fa0398a`,
UID 1000/GID 1001, RTX 4060, Shostakovich-Sym5-Va pages012–014 (2960×4210 each),
production compile mode and unchanged selected models/thresholds. Every scored
warm run uses a private copy of the same qualified compiler seed; OS caches were
not flushed. OMP/MKL threads_per_worker=4 in both controls and candidates.

| Mode | Ordered observations (seconds) | Median | Range |
| --- | --- | --- | --- |
| One worker | 260.465331, 262.742011 | 261.603671 | 260.465331–262.742011 |
| Two workers | 255.979682, 241.585487 | 248.782584 | 241.585487–255.979682 |

Sequence was B1/P1/P2/B2. Two repetitions do not establish a general speedup;
source throughput and timing variability remain limiting factors. No retuned
threshold, excluded case, changed primary metric or extra favorable timing run
replaces this result. The preparatory `warm-1a` run is not a scored observation.
The #447 historical speedup is not pooled with these measurements.

During B2, failure-only diagnostic retention was added and tested (74 tests,
13.33s, GPU-free). No successful-path recognition/scheduling calculation changed;
this is a provenance/CPU-background limitation, not a clean zero-background,
immutable-source performance cohort. No activation claim relies on this cohort.
All later cold/single runs use the frozen runtime at `51a4800d`.

## Remaining validation evidence

The complete matrix, strict recognition/mask/numbering/MMR/filter comparisons,
actual manual0/movement reset/continuity/barline correction replay, resource
summaries, process faults and maintained smoke are recorded in the final evidence
below. Raw data stays under `logs/issue458/`: per-run configs, command arrays,
source commits/diffs, worker requests/results/logs, compiler caches, GPU samples,
cgroup CPU/RAM/I/O samples and Docker inventories/events. Input/model digest
inventory is `validation/input-model-identity.json`. No inference outputs, weights
or caches are committed.

Root-deployment speed, arbitrary larger admitted shapes/devices and full68
accuracy are not established by this bounded cohort. Admission tests cover
out-of-envelope sizes/devices and insufficient resources without loading models.
Full68 was not run: the Issue excludes repeating it for timing alone; no broad
quality-preservation claim is made. Models, thresholds and geometry algorithms
are unchanged, and representative output equality plus canonical accuracy smoke
are the selected regression gates.

## Completed semantic, resource and failure gates

All eight E2Es completed (exit 0). Strict comparisons pass on all eight; the six
multi-page outputs also pass actual Phase A/C correction replay. Single-page
worker selections are 1 and 1, with E2E observations 111.041s/111.521s. Cold
observations are 382.947s/363.337s (5.12% reduction, one observation per mode),
reported separately from the failed primary warm gate.

Peak cgroup RAM over all runs was 8.9283 GiB; device sampled VRAM maximum 6598 MiB.
Both satisfy the fixed 16 GiB/7 GiB screens. Per-run CPU, I/O and GPU statistics,
medians/ranges and all gates are in [machine-readable results](issue458-results.json).
They are observations, not reservations or bounds for arbitrary larger inputs.
Known GPU competition was not observed; WSL process attribution and coarse
sampling do not prove complete exclusivity.

The first fault attempt exposed lost root causes when a failed later page
cancelled an earlier page. It was **Failed**, preserved under `faults/`, and fixed
by retaining the original exception before cancelling siblings. The corrected
attempt under `faults-v2/` passes all six cases: exit7, missing result, wrong-image
identity, source SIGKILL, timeout, and actual cgroup OOM. All children are reaped,
detection is aborted, failure diagnostics remain and final numbering is absent.
OOM was forced in a CPU-only 2 GiB container using retained SR and an explicitly
mocked admission probe; memory.events oom_kill increased 0→1. This is a host-memory
OOM recovery test, not a claim of tested CUDA allocator OOM recovery.

SIGTERM and descendant timeout cleanup, bounded/order consumption, queued
cancellation, preservation of the original sibling exception, resource rejection,
SR result duplicate/missing/unexpected rejection and engine scratch diagnostic
retention pass focused tests. Supervisor SIGKILL requires whole-container/cgroup
termination; no Python cleanup claim is made for a lone killed supervisor.

Final fast/focused command (shared container image 5311cf22…, manager mounted at
/workspace, worktree visible at /workspace/.worktrees/issue458, UID 1000/GID 1001):

```sh
docker exec --user 1000:1001 -w /workspace/.worktrees/issue458 \
  -e PYTHONPATH=/workspace/.worktrees/issue458 pdfscore_pipeline_pytest_dev \
  /opt/venv_pipeline/bin/python -m pytest \
  $(sed -n 's/^FAST_TESTS ?= //p' Makefile) \
  tests/test_issue458_source_concurrency.py tests/test_issue284_sr_batch_contract.py \
  tests/test_issue409_failure_contracts.py tests/test_issue255_page_local_source_generation.py -q
```

Passed: 206 tests in 10.87s, exit 0 (`validation/final-all.log`), covering final source
plus formatting-only changes in `0c52a226`. The earlier fast-config mismatch and
fixture-import test failures were corrected and their logs retained; neither is
reported as a current pass. Targeted Ruff, compileall, launcher help and diff
checks pass. Future service architecture was reviewed: no service/public boundary
changes; current architecture documents now link the scheduler policy.

## Validation status and reproducibility

| Check | Status for this attempt | Command / evidence under logs/issue458 |
| --- | --- | --- |
| Runtime compatibility/CUDA/selected models | Passed | `DOCKER_IMAGE=<immutable image above> bash scripts/docker_runtime_validation.sh --config configs/dense_full_pipeline.yaml --preflight-only`; exit 0, validation/preflight.log |
| Fast + focused | Passed:206 | exact command above; exit 0, validation/final-all.log |
| E2E matrix execution | Passed:8 | `python3 tools/issue458/matrix.py`; exit 0, validation/matrix.log and runs/*/provenance.json |
| Strict semantics and actual correction | Passed:8 comparisons/6 replays | production-image CPU command in validation/post-results.json invoking tools/issue458/summarize.py; summary.json; combined harness exit 1 is solely the failed performance assertion |
| Warm >=5% | **Failed:4.900958%** | same fixed matrix/summary.json; no rescore or favorable replacement |
| Resource screens | Passed:8 | summary.json and raw GPU/cgroup samples, <=16GiB RAM / <=7GiB sampled VRAM |
| Initial process faults | Failed, corrected | first faults/ and validation/faults.log preserve lost root-cause assertions |
| Final process faults | Passed:6 | production image, --memory2g --memory-swap2g, `python tools/issue458/faults.py --output logs/issue458/faults-v2`; exit 0, faults-v2/result.json, validation/faults-v2.log |
| Maintained GPU/accuracy smoke | Passed | `make verify-gpu-smoke DOCKER_IMAGE=<immutable image above> DOCKER_EXTRA_ARGS="-v <manager>/data/evaluation2:/workspace/data/evaluation2:ro -v <manager>/models/mmr/mmr_classifier_best.pth:/workspace/models/mmr/mmr_classifier_best.pth:ro"`; exit 0, validation/smoke.log and validation/system/gpu_smoke_20261031T173305Z/gpu_smoke.log |
| Full68, root performance, broader devices/shapes, CUDA allocator OOM, lone-supervisor SIGKILL | Not run | bounded scope and explicit limits above; no corresponding adoption claim |

Smoke launched at `51a4800d`; it passes the exact canonical input digest with 85/85
matches, hard FP 0/FN 0/soft 0. During smoke, `0c52a226` changed exception propagation
only; final fast/fault checks cover that change. No model, geometry, threshold,
input, or successful inference path changed, so the successful smoke evidence
remains applicable to those paths; it is not a smoke rerun at `0c52a226`.
Canonical smoke uses the image's default root UID and fresh root cache; timed
runs use UID 1000 with per-run compiler caches. These are separate claims.
The timed cache uses explicit TORCHINDUCTOR_CACHE_DIR/TRITON_CACHE_DIR and does
not enable PDFSCORE_SR_COMPILER_CACHE; no #454 managed-cache speedup is added.

The default smoke output aliases logs/full_pipeline_runs and logs/system point
into logs/issue458/validation/{smoke-output,system}; physical evidence has one
Issue root. The original manager checkout and its retained caches are unchanged.
The launcher was subsequently narrowed by removing unused PoC modes; the scored
production Docker argument sequence remains the one retained per run.

Historical evidence: #447's reported speedup was not rerun as that historical
candidate and is not pooled into this attempt. See that report for its limits.
There are no current blocked checks; deferred scope is marked Not run above.
