# Current production performance investigation — Issue #447

This records the initial measurement and bounded-PoC investigation for
[Issue #447](https://github.com/M763468/PDFScoreBar/issues/447). Investigation continues
at the user's request; this initial record is not final acceptance. No optimization is adopted.
The highest-priority follow-up is explicit compiler-cache lifecycle for short-lived
Docker jobs, filed as [Issue #454](https://github.com/M763468/PDFScoreBar/issues/454).
Bounded page-source concurrency is promising but needs integration/regression
work. Disabling compilation and eager tile batching did not pass their experiment gates.

## Evidence identity and limits

Source is `2ac7d5245fe65dbfa2093b4e0d60119c58192f86`, still current `origin/develop` after
fetching on 2026-10-27 UTC. The worktree is `.worktrees/issue447`, branch
`perf/issue447-current-e2e`. Runtime-sensitive production source/config/models are unchanged.
The identified uncommitted diff adds investigation tools, tests and records only.

The verified immutable image is
`sha256:5c5979a26f4b232bc93af6b2d040226a6e6f0c45557ccc8ad4db56153fa0398a`,
runtime compatibility fingerprint
`d73cfaa3096e662faca36d85f425553ebeb258f912a7bd424827425caaac2f97`.
Hardware is RTX 4060 8188 MiB, driver `610.88`, 8 host logical CPUs. Runtime is torch
`2.14.0+cu130`, CUDA `13.0`, cuDNN `92400`, ONNX Runtime GPU `1.24.4`.
The configuration is [`dense_full_pipeline.yaml`](../../configs/dense_full_pipeline.yaml),
maintained-original HOMR pin `457e7c6518a10ba755db2e60883419e56c4d7369`.
Full input/config/model hashes and actual mounts are retained in
`logs/issue447/preflight/initial/`; a new post-run digest check still matched the frozen inputs.

The launch mode explicitly uses UID/GID `1000:1001`, verified read-only model-cache/input/MMR
mounts and `HOME=/tmp`. This is the measured operator mode, not a claim that the image's
default root UID has identical import/cache behavior. The shared pytest image is incompatible
with current production; it was used only for GPU-free utility tests, never performance data.

Representative inputs are existing rendered Shostakovich-Sym5-Va page 013 and pages 012–014.
These dense-pipeline times exclude PDF rendering and service PDF export. Single-page
observations from 2026-10-26 UTC are **reused evidence**, not reruns on 2026-10-27 UTC.
Trace OFF Docker wall time includes startup/imports/teardown. Trace ON, profiled and standalone
component wall times are diagnostic, not interchangeable exclusive E2E stages.

Every GPU experiment ran sequentially with no observed competing GPU workload; the two
workers inside the concurrency PoC are the intentional treatment. Docker/GPU before/after
records and device samples are retained. WSL process-level GPU memory accounting was
unusable; device totals are reported instead. The brief GPU-free utility test during the
eager run is an additional CPU-noise limitation; no marginal speed claim is made from it.

## E2E and stage observations

Each E2E condition has one observation, without a confidence interval. Cold means empty
Issue-local Inductor/Triton disk caches, not flushed OS/driver caches. Warm uses a fresh
process with that disk cache retained, not a persistent loaded model. The 3-page run had
prior cache files but also new image/tile shapes and dynamic-graph recordings; it is not
a fully warmed fixed-shape throughput benchmark.

| Observation | Trace | Docker E2E | Detection | MMR | Sampled device VRAM peak |
| --- | --- | ---: | ---: | ---: | ---: |
| Reused single-page, empty compile cache | OFF | 219.45 s | 209.39 s | 4.80 s | 3428 MiB |
| Reused single-page, retained compile cache | OFF | 103.25 s | 93.40 s | 4.95 s | 3430 MiB |
| Reused single-page diagnostic | ON | 104.22 s | 93.68 s | 4.81 s | 3434 MiB |
| New pages 012–014, prior cache/new shapes | OFF | 266.46 s | 243.79 s | 13.05 s | 3458 MiB |
| New single-page eager candidate | OFF | 104.74 s | 93.92 s | 5.56 s | 3453 MiB |

The multi-page telemetry is 259.34 s inside the pipeline, versus 266.46 s Docker wall.
Its other reported stages are measure construction 0.873 s, final numbering 0.831 s and
artifact materialization 0.096 s. The remaining intervals include collection/filter/handoff
and startup/teardown; they are not assigned wholesale to I/O, Python or subprocess launch.
Observed throughput is 0.676 pages/minute for this slice versus 0.581 for the retained
single-page warm case. Different page sets/cache histories prevent a controlled speedup claim.

The actual 3-page SR worker reports 125.34 s, nested within detection. Its page processing
times are 48.00/32.70/32.88 s, including enhancement and image I/O, with one model lifetime.
The observed source-worker residencies for the same E2E run are 34.20/35.85/34.65 s.
Within those parents, x4 HOMR child residencies are 13.29/14.72/14.14 s and OMR-DLN
9.84/9.64/9.84 s. Original-HOMR worker-native totals are 10.04/10.46/9.26 s.
Residency endpoints have approximately 0.2 s sampling uncertainty; **parent and child
durations overlap and must not be added**. Independent replay component times below
are not substituted into this E2E accounting.

## Resources, I/O and internal attribution

The multi-page container's cgroup peak memory was 8,522,805,248 bytes (7.94 GiB).
Cumulative CPU at the last sample was 484.55 CPU-seconds, including 1.05 CPU-seconds
for the observer. Device GPU utilization averaged 38.1% across one-second samples and
reached 100%; an average does not identify an individual kernel or CPU stall.
The final sampled cgroup I/O counters were 3,553,554,432 physical read bytes and
82,624,512 write bytes. These include libraries/weights/filesystem activity; page-cache hits,
logical reads and delayed writeback differ. They are not exclusive image-I/O cost.
Sampling began after SR startup; its earlier process residency is left-censored, while
cgroup lifetime counters/peak include that earlier activity. Summed Python RSS is not
physical RAM because shared mappings can be counted repeatedly; cgroup memory is preferred.

The reused synchronized trace records SR enhancement 43.76 s, model initialization 7.18 s,
image read 0.09 s, image write 1.22 s and image SHA-256 0.014 s. The enclosing subprocess
is 56.60 s; these nested values are not additive. Removing that hash has no useful
measured E2E case and would weaken provenance.

Retained-input **standalone monotonic** diagnostics, with equal semantic outputs, found:

- Current x4 HOMR: 12.63 s including 2.19 s explicit runtime imports; predictor call
  9.95 s, nested image reads 1.57 s and session construction 0.61 s. ONNX run/I/O-binding
  spans overlap and asynchronous work can finish in later calls, so no exclusive GPU
  percentage is inferred from their sum.
- OMR-DLN: 7.98 s including 2.11 s runtime imports and 3.39 s lazy YOLO class resolution;
  worker body 2.48 s includes 1.51 s image reads, 0.075 s model construction and 0.90 s
  first prediction including setup. Both model and predictor selected `cuda:0`.
  The approximately 10 s E2E worker residency is not 10 s of neural inference.
- MMR is 13.05 s for three pages (4.9% of E2E), with one persistent classifier/OCR
  instance. Its existing CUDA-provider-preference log is retained. Retry/threshold
  changes were not tested or silently substituted.

cProfile diagnostics completed with equal outputs, but their call-graph time accounting
failed validity checks: root calls were missing and, for example, an OMR cumulative entry
was 69.83 s inside an 8.99 s measured region. Those quantitative profiles are retained as
failed diagnostic attempts and excluded from rankings. The independent monotonic spans
above supplement them; no causal profiler defect or pure-Python percentage is claimed.

## Predeclared PoCs and decisions

The additional contract was fixed before the trials in
[`tools/issue447/contract.json`](../../tools/issue447/contract.json), preserving the earlier
contracts under the ignored Issue evidence root. No threshold, weight, input subset or
pass/fail tolerance was changed after seeing a result.

| PoC | Speed / memory observation | Correctness and decision |
| --- | --- | --- |
| Disable SR compilation, one page | E2E 104.74 s versus reused cached baseline 103.25 s; not a demonstrated warm-job improvement. Different attempts and limited sampling prevent causal precision. | Final detector geometry, base/final numbering and MMR override targets/skips match, but x4 HOMR predictions and staff/connector masks differ. Strict source-semantic gate **Failed**. Eager SR differs from compiled SR in 2,401,752 channel values, maximum absolute difference 5. Not adoption-ready. |
| Tile batch 1 versus 2, eager mode fixed for both | First variant calls 39.58/40.79 s; warm ABBA medians 41.93/42.89 s. A/B ratio 0.978, below the predeclared 1.05 advancement gate. Peak reserved VRAM 2.465/3.793 GiB; allocated 0.881/1.661 GiB. | Eager A/B pixels identical, memory gate passed, speed gate **Failed**. This is a current CPU-stitch screening result, not the historical rejection and not a compiled-production result. Compiled batch 2 was **Not run**: a new shape/compile experiment is not justified by this negative bounded screen. |
| Two concurrent disposable source workers, pages 012 and 014 | Component wall 47.54 s versus retained sequential observed residencies totaling 68.85 s; exploratory ratio 1.45. Docker wall 48.41 s. Peak device VRAM 6604 MiB, cgroup memory 8.44 GiB within a 16 GiB ceiling. | Ordered original/x4 predictions, decoded staff/connector masks and ordered OMR source predictions all match for both pages. Source-component gates **Passed**. Historical sequential sampling versus a fresh component is not repeated causal E2E evidence. Final merge/order/movement/numbering/MMR/correction guards **Not run**. Promising follow-up, not adoptable implementation. |

The concurrency experiment used retained production SR and preserved each worker's
disposable lifetime; no SR model ran concurrently with HOMR/OMR. The observed GPU headroom
does not authorize unrestricted page concurrency, persistent GPU model pools or shared-model
mutation. The first batch variant calls are not independent cold-process measurements;
the model was loaded once, allocator cache was cleared outside each timed enhancement,
and initial/steady behavior is kept separate. Each ABBA median has two warm observations.

## Prioritized backlog

1. **Compiler-cache lifecycle for short-lived jobs.** Reused OFF measurements show
   219.45→103.25 s cold/cache-retained E2E, with matching SR digest and checked downstream
   semantics. The 114.21 s nested SR-phase difference explains most of the 116.19 s observed
   E2E difference. This is enough implementation value for [one focused follow-up, #454](https://github.com/M763468/PDFScoreBar/issues/454), but not a
   general 2.1× production promise. Verify root/non-root launcher modes, job/container
   lifetimes, image/runtime/weight/device identity keys, safe cache permissions and repeated
   comparisons before adoption. Persistent services may already reuse container-local caches.
2. **Resource-bounded page-source concurrency.** A current two-page screen improved source
   completion with equal source semantics. Preserve output order and page/movement identity,
   measure actual E2E and CPU contention, cap memory/workers and implement cancellation/error
   isolation before proposing a production pool. Retain this in #447 backlog; an additional
   implementation Issue is premature until the integrated benefit/regression contract is fixed.
3. **Import/initialization reuse, especially OMR.** The independent OMR diagnostic spends
   5.50 s in imports/class resolution versus 0.90 s in initial prediction. Inspect bytecode
   cache/UID behavior before a persistent model architecture. Keep intentional VRAM-release
   boundaries and manifests. No claim is made about the default root UID's import cost.
4. **SR backend efficiency and batching.** SR still dominates a substantial measured region,
   but eager batch 2 did not improve it on this GPU/current stitch path. Revisit compiled
   batching or another backend only with a distinct predeclared experiment and numerical/
   downstream gates. Do not silently switch the production compile mode after its failed gate.
5. **Image decode/representation handoff.** x4 HOMR and OMR each read the large SR image;
   about 1.5 s per consumer is visible in separate diagnostics. Shared-memory/representation
   changes might save a few seconds per page, but memory lifetime, input digest and coordinate
   semantics must survive. Do not remove persistence, hashing or process boundaries merely
   because they are repeated. Physical I/O counters alone cannot establish avoidable decode cost.
6. **MMR/OCR and native geometry code.** MMR is about 4.9% of this E2E; no shortcut or retry/
   threshold change is justified. Tracked construction and numbering together are below 1%
   of E2E. No reliable profile establishes a dominant pure-Python loop worth a C++/Rust/Zig
   port; NumPy/OpenCV/native model work and framework imports remain distinct hypotheses.
   No language rewrite or extra implementation Issue is proposed.

## Reproduction and retention

[`issue447-results.json`](issue447-results.json) retains a compact machine-readable snapshot;
the full raw evidence is ignored under `logs/issue447/` (about 315 MiB before final records).
Important paths are `runs/<label>/{provenance,result,container-inspect}.json`, GPU/process
samples, `pipeline/manifest.json`, worker outputs, and `followup/{contract-v2,contract-v3,
frozen-input-recheck,summary}.json`. Later launches retain exact helper snapshots and digests
in each run's `script-snapshots/`; initial launch commands/helpers remain under the Issue root.
All large inputs, models, generated images, caches and raw logs remain outside Git.

The launchers require the existing manager input/MMR assets, registered shared model cache,
verified immutable production image and frozen source. Component replay additionally needs
the retained `single-off-warm` and `multi-off-warm` reference artifacts; no fixture substitutes
for those inputs. Run in an unused checkout/evidence namespace; launchers refuse existing
run labels and do not delete retained data.

```bash
# First resolve/verify the image using the maintained preflight for the active checkout.
python3 scripts/docker_image_resolver.py resolve --repo-root . --image-ref <immutable-id> --explicit
# Cold reproduction: choose a NEW empty cache directory, without deleting an existing one.
python3 tools/issue447/run_experiment.py --label single-off-cold --image <immutable-id> \
  --compile-cache logs/issue447/reproduction-cache
python3 tools/issue447/run_experiment.py --label single-off-warm --image <immutable-id> \
  --compile-cache logs/issue447/reproduction-cache
python3 tools/issue447/run_experiment.py --label multi-off-warm --image <immutable-id> --scope multi \
  --compile-cache logs/issue447/reproduction-cache
# Bounded component examples, reusing the required retained references.
python3 tools/issue447/run_experiment.py --label sr-tile-batch-screen --image <immutable-id> \
  --compile-mode off --component sr-screen
python3 tools/issue447/run_experiment.py --label source-parallel-two --image <immutable-id> \
  --scope multi --component source-parallel
# Rescore existing evidence; this launches no inference.
python3 tools/issue447/analyze.py
```

Run-local `proc-samples.jsonl` always takes precedence. To rescore the frozen original
`multi-off-warm` attempt, whose observer was started externally, explicitly add
`--legacy-multi-proc logs/issue447/followup/multi-off-proc.jsonl`. The selected association
and exact file path are recorded in the summary. Without that argument the analyzer does
not attach historical observations to a new run.

Exact actual image IDs/commands/config digests/cache states are in run provenance. The
measurement contract is fixed to this source/config/input identity; another runtime/dataset
requires a newly labeled experiment. Do not treat disk-cache warmth as in-process model warmth.

## Validation status

Tested runtime: the frozen source/image above. Final tooling/docs validation is against that
base plus the identified research-only diff; final patch/script digests and logs are retained
under `logs/issue447/followup/validation/`. A successful experiment execution is not a passed
optimization gate.

| Check | Status for this continuation | Evidence / limit |
| --- | --- | --- |
| Production GPU smoke | Not run | Production runtime source is unchanged; the prior result is historical evidence below, not a current rerun. |
| Multi-page OFF, eager OFF, component executions | Passed | Exact commands/exit 0 in each run's provenance/result. Eager/batch acceptance failures below remain failures. |
| Single-page cold/warm/source repeatability | Passed by rescoring retained outputs | Detector/base/final/MMR and source predictions/masks checked; no new baseline inference. |
| Eager source-semantic gate | Failed | Predictions/masks differ despite matching final one-page detector/numbering/MMR fields. |
| Eager tile batch 2 speed gate | Failed | 0.978 ratio < 1.05; pixel/memory gates Passed. No compiled batch result claimed. |
| Source-parallel source gates | Passed | Both pages' ordered source predictions and decoded masks equal; no final pipeline-order claim. |
| cProfile quantitative accounting | Failed | Inconsistent/missing call-graph timing; excluded, supplemented by monotonic spans. Outputs matched. |
| Process-attributed GPU memory / power | Blocked | WSL PID GPU accounting returned unusable zero; power `[N/A]`. Total-device memory and cgroup RAM recorded instead. |
| Focused utility tests, syntax, CLI help, targeted Ruff, diff/link review | Passed | 6 focused tests passed; commands and final results retained in `followup/validation/`; no GPU/model loading in focused tests. |
| Full68, repeated multi-page cold/warm, integrated parallel regression | Not run | Full68 is not warranted solely for profiling unchanged production. Repeated multi E2E was avoided after one representative run; parallel final integration is follow-up work, not a current pass. |

**Historical evidence:** the 2026-10-26 UTC attempt on source `2ac7d524` and the immutable
production image above ran `bash scripts/docker_runtime_validation.sh --config
logs/issue447/configs/smoke.yaml`, exit 0. Its verified source PDF/render produced 85/85
matches, hard FP/FN/soft all zero. Evidence is
`logs/issue447/preflight/initial/production-smoke.log` and
`logs/issue447/validation/production-smoke/detector_accuracy_smoke_summary.json`.
It was not rerun for this research-only diff. The initial single-page cold/warm/trace
runs likewise retain their original commands, environment and outputs under the same Issue root.

No shared tag/container was replaced, no production model/threshold/routing was changed,
and no merge or destructive cleanup was performed. The evidence supports a ranked follow-up
backlog while preserving failed gates and unresolved acceptance boundaries.
