# Issue 447: continued investigation, historical continuation

Final disposition: [consolidated Issue 447 results](issue447-results.md).

This record extends [the initial investigation](issue447-initial-results.md), following the request
to deepen the evidence rather than close the PR. It does not authorize production adoption.
No production code, model, threshold, configuration, dependency or release behavior changed.
The open Issue acceptance criteria were re-read for this continuation. No full68 or merge
was performed. The existing implementation follow-up is #454; no additional Issue was created.

Further investigation: [repeated E2E and integrated OMR reuse](issue447-e2e-candidates.md).

## Review correction and reproducibility

Codex's unresolved P2 review identified incorrect association of historical process samples
with a newly reproduced multi-page run. Commit `b5e03b2c` prefers run-local samples, requires
an explicit matching-run legacy fallback, and records the selected path. Eight focused tests
and retained rescoring passed; the review thread is resolved. Historical evidence remains intact.

Production source is frozen at `2ac7d5245fe65dbfa2093b4e0d60119c58192f86`,
`configs/dense_full_pipeline.yaml`, runtime fingerprint
`d73cfaa3096e662faca36d85f425553ebeb258f912a7bd424827425caaac2f97`, image
`sha256:5c5979a26f4b232bc93af6b2d040226a6e6f0c45557ccc8ad4db56153fa0398a`.
The image's older build label is not the mounted runtime-source identity; retained fingerprints
and source snapshots establish the effective code. The runner uses UID:GID `1000:1001`,
RTX 4060 8 GiB, eight host logical CPUs, torch 2.14.0+cu130 / ORT GPU 1.24.4.
Inputs remain Shostakovich-Sym5-Va pages 012–014, single-page tests use 013. Input/weight
hashes, exact commands, effective-code hashes, runtime/model identities, mounts and timestamps
are in each `logs/issue447/runs/deep-*/provenance.json` and `script-snapshots/`.

The research harness checkpoint is `c052d09a`; cache runs used `b5e03b2c` plus the retained
working snapshot. Effective runner/observer hashes are stable across the six cache runs.
[The machine-readable results](issue447-deepening.json) retain measured values, semantic
checks and evidence paths. Large local outputs are intentionally not committed.

Predeclared contracts are [the original](../../tools/issue447/contract.json),
[continuation performance contract](../../tools/issue447/deepening_contract.json) and
[additive validation supplement](../../tools/issue447/deepening_validation_contract.json).
Local `deepening/contract-v1.json` through `contract-v4.json` preserve chronology; supplemental
numbering/root/timer checks do not change the original performance or correctness gates.
Exact ordered commands and cache inventories are retained in `deepening/cache-matrix.jsonl`,
`followup-matrix.jsonl` and `e2e-cache-seeds.json`. Reproduction entry points are
`run_experiment.py --help`, `deepening_components.py --help`,
`replay_numbering.py --help`, and `PYTHONPATH=. python3 tools/issue447/deepening_analyze.py`.
`pipeline_poc.py` is an internal environment-driven shim, invoked by the launcher, not a standalone CLI.
All paths in this paragraph are under `tools/issue447/` or `logs/issue447/` respectively.

## Repeated compile-cache observations

Every observation is a fresh container, trace OFF. Each cold run starts with a separate empty
private Inductor/Triton directory; its warm partner reuses that directory. OS/driver caches
were not flushed, and no model process survives between containers. Thus “cold” means compiler
cache cold, not a power-on or disk-cache-cold machine. Preparation and observer teardown are
outside Docker E2E; production startup/teardown remain inside.

| Pair | Cold E2E (s) | Warm E2E (s) | Paired saving (s) |
| --- | ---: | ---: | ---: |
| 1 | 230.822 | 108.449 | 122.373 |
| 2 | 233.242 | 111.652 | 121.590 |
| 3 | 243.139 | 112.382 | 130.757 |
| Median | 233.242 | 111.652 | 122.373 |

Cold range is 230.822–243.139 s; warm range 108.449–112.382 s. All six strict checks pass
against retained compiled production outputs: original/x4 ordered source predictions,
decoded staff/connector masks, detector geometry, base/final numbering and MMR targets/mapping.
Cache inventories/digests are recorded before/after; paired warm runs reuse the cold inventory.
Do not pool these repeats with the initial 219.45/103.25 s observations.

Native SR batch wall is 176.80–185.97 s cold versus 56.54–57.56 s warm; sampled cumulative
cgroup CPU is 331–349 CPU-s versus 195–201 CPU-s. This supports compiler/cache work as the
largest cold-job target. Warm jobs still perform SR and source processing. It does not prove
all cold excess is a single compiler kernel, nor justify disabling compilation: the earlier
eager source-semantic failure remains Failed.

## Matched page concurrency and integrated E2E

The experimental shim schedules disposable source workers only after the production SR batch
has succeeded and exited, and consumes results in input order. Both conditions use the same
shim, fixed assets, fresh containers and a 16 GiB cgroup cap; only worker count changes.
This preserves the intentional SR/model lifetime boundary. It is not installed in production.

| Scope and order | One worker (s) | Two workers (s) | Interpretation |
| --- | --- | --- | --- |
| Retained-SR source component, ABBA on pages 012/014 | 65.304, 64.767 | 51.971, 47.839 | Median 65.036 → 49.905, 23.3% reduction |
| Fresh integrated 3-page trace OFF, one pair | 249.932 | 231.541 | 18.391 s / 7.36% reduction, 1.079× speed ratio |

The E2E controls start from identical private copies of the same compiled-cache snapshot.
All four component source checks pass. Integrated one-worker output matches retained
production multi-page output, and two-worker output matches the one-worker control across
all three pages: ordered image/manifest identities, original/x4 predictions and decoded masks,
OMR predictions, final detector geometries, base/final per-page and combined numbering,
movement metadata, filters/correction fields, MMR mappings and override targets/skips.
Only run paths and display-only OCR comments are excluded, with no geometry/number tolerance.

The actual production Phase C was additionally replayed CPU-only with retained real MMR
outputs, first-measure manual number 0 and an explicit second-page movement reset to 1.
Both conditions pass manual anacrusis, reset, third-page continuity and page-order checks;
all replayed pages and metadata agree. Evidence: `deepening/numbering-replay/result.json`.
This exercises correction and movement semantics without repeating detector/MMR inference.

| Integrated resource observation | One worker | Two workers |
| --- | ---: | ---: |
| Cgroup memory peak (GiB) | 4.773 | 8.784 |
| Device VRAM sampled peak (MiB) | 3438 | 6581 |
| Cgroup cumulative CPU-s, final sample | 469.52 | 508.39 |
| GPU utilization mean, ~1 Hz samples | 40.60% | 43.97% |
| Physical read/write counters (MiB) | 0 / 81.44 | 0 / 81.82 |

Both pass the bounded memory screen (16 GiB RAM, sampled VRAM <=7 GiB). The parallel component
peaks at 6603 MiB VRAM; this is a screen on this device/input, not an OOM guarantee for larger
pages or all machines. Summed process RSS double-counts shared mappings; cgroup memory is
preferred. Additional CPU cost and sampled main-thread runqueue wait rise under concurrency
(1.72 → 15.62 summed seconds in E2E, not all-thread or critical-path wait). E2E has only one
pair in fixed order; no confidence interval, generalized throughput or adoption claim follows.

## Initialization, I/O, batching and model internals

A new OMR-DLN reuse PoC compares three fresh per-page subprocesses with one subprocess accepting
the same three retained SR pages. ABBA component walls are serial 27.681/26.961 s versus
reuse 12.456/12.514 s: medians 27.321 → 12.485 s (54.3% reduction). All ordered source
predictions agree. This addresses observed import/class-resolution overhead rather than
assuming the roughly 10 s worker residency is neural inference. Reuse raises cgroup memory
from about 1.66 to 2.76 GiB, sampled device VRAM remains 665 MiB. Integration, downstream
MMR/correction behavior under a new worker protocol, failures and lifetime policy remain
unverified. These component seconds cannot be added to concurrency/cache E2E savings.

CPU-only import comparisons use identical image, interpreter and resolved YOLO class/version;
CUDA never initializes. At UID 1000, warm fresh-child default import process wall is
6.492/6.747 s versus writable private bytecode prefix 2.614/2.669 s. First prefix preparation
costs 7.796 s versus default 6.560 s. Root control is essential: default UID 0 can write the
site cache and its second child already falls from 6.673 to 2.567 s, whereas UID 1000 stays
6.337/6.176 s. Do not extrapolate this nonroot cache effect to the default-root production
launcher. No root E2E or writable-prefix E2E was run; this remains a conditional init hypothesis.

Compiled SR batch=2 was retested independently of the prior eager negative result. Fixed
400-core/10-pad interior tiles, FP16/channels-last/reduce-overhead, CPU uint8 readback and
ABBA fresh-process blocks each contain six warm calls. Per-block warm medians for two tiles:
batch=1 0.7650/0.7682 s; batch=2 0.7621/0.7669 s. The sub-1% difference fails the predeclared
5% advance gate; reserved VRAM increases about 1.41 → 2.55 GiB. Tested core pixels exactly
match retained compiled full-page ROIs. First calls (33.03/34.83/6.12/5.94 s) include differing
cache/setup work and are kept separate. Full-page batch=2/downstream semantics are Not run;
this bounded result provides no reason for that cost or production adoption.

Existing trace ON data remain diagnostic, not authoritative E2E. The reused synchronized SR
trace reports enhancement 43.76 s, initialization 7.18 s, image read 0.09 s, write 1.22 s,
SHA-256 0.014 s inside a 56.60 s enclosing subprocess. Existing independent monotonic spans
show x4 HOMR 12.63 s (image reads 1.57 s; session construction 0.61 s), OMR 7.98 s (runtime
imports 2.11 s and lazy class resolution 3.39 s; nested reads 1.51 s). These support startup/
reuse and decode candidates. MMR/OCR is 13.05 s for three pages in the initial E2E (~4.9%);
no retry/threshold shortcut is justified. Native model code dominates substantial work; no
valid evidence establishes a dominant pure-Python geometry loop worth a language port.
The prior invalid cProfile accounting stays Failed and excluded from quantitative ranking.

New host observations see the SR worker for ~181–191 s cold versus ~59 s warm and ~33–36 s
source activity on the single page. Native-body entry/result-write envelopes leave about
5.9–7.3/4.2–4.3 s before/after the cold SR body and 1.0–2.1/1.7–2.8 s warm (sampled endpoints
~0.2 s uncertainty). These envelopes contain mixed startup/finalization work; they are not
exclusive import/teardown or I/O timers. Integrated native SR batch stays 122.10/122.37 s
between concurrency conditions while source-worker observation decreases ~97.13 →79.31 s.
This localizes the plausible scheduling effect without treating process residency as stage time.
Physical read counters often reach zero through the OS page cache; image decode and logical
reads still occur. Removing hashes/provenance is low-value; process reuse and representation
handoff deserve more attention than raw disk bandwidth.

## Timing and attribution limits

CUDA timing uses recorded timing-enabled events with synchronization per the
[PyTorch 2.14 Event API](https://docs.pytorch.org/docs/2.14/generated/torch.cuda.Event.html).
Calibration found device-event intervals ~3.9% above host `perf_counter` intervals, and nearer
`CLOCK_MONOTONIC_RAW` intervals, on three fixed GEMM brackets. Cause is unassigned. The primary
metric remains the same host `perf_counter` for every E2E; no retrospective conversion or gate
change was made. Event minus host time cannot establish enqueue/CPU wait or GPU-busy time.

An earlier diagnostic correlated driver absolute timestamps with host samples using an inferred
hour offset. That is withdrawn: `summary-v1-driver-clock.json` is retained as superseded;
the final analyzer uses host-monotonic phase observations and independent GPU summaries.
Absolute CPU/GPU wait correlation is Blocked pending calibrated acquisition in one clock domain.
No GPU-low/CPU-active duration from the superseded diagnostic is used here. Polling cannot
identify a causal stall or exclusive stage. Independent component walls, nested native spans,
source residencies and E2E must never be summed into a synthetic E2E partition.

No external GPU job was observed: each benchmark's continuous Docker events contains only its
own container, surrounding container inventories and idle samples are retained, and benchmark
runs were serialized. WSL process queries return `[Not Found]`/`[N/A]`, so complete device-PID
attribution, power and detailed device wait remain Blocked. Known competition would invalidate
performance evidence; this record does not claim an OS-level proof of exclusive ownership.

## Priority and remaining work

| Rank | Candidate | Evidence and next decision |
| --- | --- | --- |
| 1 | Compile-cache lifetime, existing #454 | Repeated ~122 s paired cold-job benefit, strict gates pass on sampled page. Validate cache identity/invalidation and permission policy before implementation. |
| 2 | Bounded source-page concurrency after SR exit | Matched component benefit and integrated 7.36% observation, semantic/replay gates pass. More independent E2E pairs and resource/failure portability needed before adoption. |
| 3 | OMR process/model reuse, conditional bytecode setup | Large matched component gain, source predictions equal. Integrated protocol/lifetime/failure and downstream gates still open; root permissions limit bytecode extrapolation. Keep in this investigation rather than create another Issue now. |
| 4 | Shared image decode / representation handoff | Repeated reads are measured; ownership/lifetime/IPC and full-page semantics need a bounded PoC. Disk counters do not show decode cost. |
| 5 | HOMR/session internals, MMR/OCR and CPU native work | Retain existing native optimizations. No demonstrated Python-loop hotspot; avoid speculative port or model/threshold changes. |
| Defer | SR batch=2, deeper SR/source overlap | Compiled batch misses speed gate and adds VRAM. Overlapping SR with two source workers risks this 8 GiB device; not justified by current headroom. |

No candidate is labeled adoption-ready. Highest-value untested work is repeated integrated
concurrency on independently seeded runs and integrated OMR reuse with full downstream gates;
these remain investigation work, not an implicit production implementation or new Issue queue.

## Current validation

Research utilities and additive diagnostics only; production diff from the frozen source is empty.
Final tested code is checkpoint `c052d09a` plus the continuation diff retained under
`logs/issue447/deepening/validation/final-code.patch` and its SHA-256 file. Workdir is this
Issue worktree. Utility-only pytest uses existing `pdfscore_pipeline_pytest_dev`, image
`5311cf22…`; all performance/model evidence uses the immutable production image above.

| Check | Status | Command / evidence |
| --- | --- | --- |
| Focused utility/scheduling/clock tests | Passed, 13 in 1.29 s | `docker exec --user 1000:1001 -w /workspace/.worktrees/issue447 -e PYTHONPATH=/workspace/.worktrees/issue447 pdfscore_pipeline_pytest_dev /opt/venv_pipeline/bin/python -m pytest tests/test_issue447_profiling_tools.py tests/test_issue447_source_scheduling.py -q`; `deepening/validation/final-focused.log`, exit 0 |
| Initial focused launcher attempt | Blocked | Same command in sandbox: Docker socket permission denied before tests. Authorized external-sandbox retry above Passed. |
| Cache/source/integrated semantic gates | Passed | Retained run-local `semantic-check.json` / `cache-semantic-check.json`; exact launch commands in run provenance and matrix journals |
| Real Phase C manual/movement/MMR replay | Passed | Production image CPU-only: `/opt/venv_pipeline/bin/python tools/issue447/replay_numbering.py --output logs/issue447/deepening/numbering-replay`; `validation/numbering-replay.log` and replay result, exit 0 |
| Compiled batch=2 advance gate | Failed | Host-wall improvement <5%; tested ROI equality passes, full-page correctness untested |
| Absolute CPU/GPU wait attribution | Blocked | Cross-clock calibration difference and unavailable WSL PID attribution; independent host/GPU observations retained |
| Python compile, targeted Ruff, public CLI help, JSON/link/diff checks | Passed | Commands and exit codes in `deepening/validation/final-static.log` and `final-public-help.log` |
| Internal shim standalone `--help` attempt | Failed | `pipeline_poc.py --help` lacks required environment; `final-help.log`. Corrected reproduction docs to use launcher; public CLI checks above pass. No inference launched. |
| Canonical smoke, make test-fast, full68 | Not run | No production change; focused tools plus actual bounded GPU E2E/source/Phase C checks cover this research diff. Full68 explicitly excluded. No production-adoption claim. |

Historical evidence: the initial report's canonical smoke (2026-10-26 UTC, same frozen runtime,
85/85 with FP/FN/soft=0), eager semantic failure and cProfile failure were not rerun. They remain
separate from this attempt. Current bounded experiments do not establish full-dataset accuracy.
Architecture documents require no change because production/service boundaries did not change.
