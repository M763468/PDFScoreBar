# Issue 447: repeated E2E and integrated OMR reuse PoCs

This extends [the previous continuation](issue447-deepening.md). This is the retained measurement-stage record; final disposition is in
[the consolidated results](issue447-results.md). No production files, models, thresholds, dependencies or runtime configuration were
changed. Full68 and formal implementation were explicitly excluded. No new Issue/PR was created;
#454 remains the existing compile-cache follow-up.

## Contract and comparison

The current develop checked before execution was `658e2e6e454436765c53e275aaf0412aede39755`.
Its changes after the frozen production source `2ac7d5245fe65dbfa2093b4e0d60119c58192f86`
are documentation/translation-verification only; production source/config/model/build paths
have no difference. Image, runtime, model identities and inputs are inherited and revalidated:
`sha256:5c5979a26f4b232bc93af6b2d040226a6e6f0c45557ccc8ad4db56153fa0398a`, runtime fingerprint
`d73cfaa3096e662faca36d85f425553ebeb258f912a7bd424827425caaac2f97`, RTX4060 8 GiB,
UID:GID1000:1001, dense_full_pipeline config, Shostakovich-Sym5-Va pages 012–014.
Official runtime preflight and an in-container CUDA computation passed before inference.

[The predeclared contract](../../tools/issue447/e2e_candidates_contract.json) fixes the primary
metric as trace OFF fresh-container Docker E2E measured with host perf_counter, including
startup/model work/teardown and excluding observer teardown. Every timed E2E regenerates SR,
both HOMR sources, OMR, detector fusion, MMR and numbering. Retained detector/MMR output is
used only for comparisons and supplemental replay, never to shortcut a timed E2E.

B is the unmodified production entrypoint. P changes only source scheduling to two disposable
workers after SR exits. O runs the production OMR worker once for all three fresh SR pages,
waits for it to exit, then uses one source worker. C combines that OMR phase with two source
workers. The experimental wrappers and same-run hash-bound handoff live only in tools/issue447.
Source result consumption remains ordered. All modes release SR before sources; O/C additionally
release the OMR batch before their source pool. P retains page-local OMR children whose lifetime
can overlap another page's HOMR work. The OMR model, confidence and production prediction
code are unchanged. All conditions use a 16 GiB cgroup RAM cap and the same mounts/environment.

Warm order is B,P,O,O,P,B, two observations per condition from identical private copies of the
538-file retained compiler-cache seed. Cold order is B,P,O, each with a new empty private
Inductor/Triton cache. OS/driver caches are not flushed; these are compiler-cold/warm jobs,
not power-on/disk-cold machines. Both candidates improved in both warm block comparisons,
passed the predeclared >=3% median advance gate, strict semantic/resource gates and real
Phase C replay before combination runs. Combination is warm twice and cold once, using the
same cache rules, compared with the recorded B controls. No additional production control was
run solely to improve the apparent comparison after observing C.

Harness checkpoint `488193d2` freezes the matrix. `99098a97` corrects the OMR hook to target
the concrete maintained detector's overridden source_worker_module, before any OMR candidate
executes. B/P effective code is unchanged by that correction; no OMR observation was discarded.
Each run retains its exact commit, script hashes/snapshot, config, command and cache inventory.
The effective OMR code is identical for every O/C observation.

## Measured three-page E2E

Warm n=2 per mode; cold n=1 per mode. Every observation is retained. Percentages are reductions
in elapsed time against the corresponding B median, not added component savings.

| Mode | Warm observations (s) | Warm median (s) | Reduction | Cold (s) | Cold reduction |
| --- | --- | ---: | ---: | ---: | ---: |
| Production | 247.064, 242.446 | 244.755 | 0.00% | 359.970 | 0.00% |
| Page parallel | 224.243, 223.228 | 223.736 | 8.59% | 349.407 | 2.93% |
| OMR reuse | 227.500, 228.198 | 227.849 | 6.91% | 362.361 | -0.66% |
| Combined | 217.818, 216.267 | 217.042 | 11.32% | 336.847 | 6.42% |

OMR reuse **does not demonstrate a cold improvement**: its observed cold result is 0.66% slower.
That result is not discarded or converted into a pass by subtracting SR time. Native SR batch
walls are B236.358/P236.357/O245.754/C236.962 s cold, versus 117.785–119.142 s across warm jobs.
Cold compile/setup variance is visible, but one observation cannot establish the cause or a
stable regression estimate. The combination advance gate was explicitly based on warm results
plus correctness/resources, not a new post-result cold criterion.

Combined warm is 2.99% faster than page parallel alone and 4.74% faster than OMR reuse alone.
Its 11.32% reduction versus production is an actual integrated measurement, not 8.59%+6.91%.
Measured three-page throughput from fresh-container median is B0.735/P0.805/O0.790/C0.829
pages/minute; this is not steady-state server throughput. The combined block runs later than
the recorded controls; matching input/cache/settings does not remove all time-of-run drift.
The similar native warm SR observations are diagnostic, not an adjustment to primary E2E.

## Resource and phase observations

| Mode | Warm cgroup RAM max (GiB) | Cold RAM (GiB) | Device VRAM max over all runs (MiB) | Warm CPU-s observations |
| --- | ---: | ---: | ---: | --- |
| Production | 6.675 | 4.884 | 3464 | 470.17, 466.96 |
| Page parallel | 8.106 | 8.959 | 6605 | 494.82, 505.07 |
| OMR reuse | 4.794 | 4.753 | 3451 | 449.59, 451.48 |
| Combined | 8.373 | 8.931 | 6593 | 491.00, 489.31 |

All runs meet the predeclared 16 GiB RAM and sampled <=7 GiB device VRAM screen. P/C need
roughly 6.4 GiB device memory and up to 8.96 GiB cgroup RAM on these pages; that is not an OOM
guarantee for larger inputs. O reduces repeated process work without the parallel-memory cost.
Cumulative CPU includes the observer and is not elapsed time. Cgroup RAM includes charged
file cache; summed RSS can double-count shared mappings. The first warm B reads 2.03 GiB
physically while later warm reads are near zero; compiler-warm does not mean disk-cache matched.
The reversed warm sequence partly balances ordering, but two repetitions do not eliminate it.
Writes are roughly 77–83 MiB warm and 106–109 MiB cold. These counters are not image-decode time.

Independent process observations confirm three OMR subprocesses in every B/P run and one in
every O/C run. Every O/C support result records the same current-run manifest and the released
OMR process boundary. SR image hashes and shapes match across all 12 E2Es. Warm device GPU
utilization means are B39.7–40.0%, P43.9–45.1%, O42.8–43.3%, C45.2–45.9%; coarse samples do
not identify a kernel or causal stall. Native SR spans, worker residency and coarse integrated
telemetry are retained separately; they are never summed into exclusive E2E stage shares.
The prior device/host clock-domain calibration limitation remains: no GPU-event minus host-time
CPU-wait calculation or retrospective E2E clock conversion is used.

No external GPU workload was observed in serialized run inventories/events. Warm P1 includes a
brief GPU-free concrete-hook pytest exec (10 tests in0.07s) in the shared utility container;
no claim of zero background CPU work is made. WSL device-PID attribution remains unavailable.
Known external GPU competition would invalidate a benchmark; independent utilization samples
and Docker events are not an OS-level proof of complete exclusivity.

## Recognition, numbering, MMR and corrections

All 12 timed outputs pass strict comparisons against the fresh production control, whose
output also matches the retained production reference. Checks include ordered original/x4
predictions, decoded staff/connector masks, OMR predictions, final detector geometry, page/
manifest order, per-page and combined base/final numbering plus movement metadata, filters,
correction statistics, MMR support geometry and override targets/skips. Run paths and display-only
OCR comments are excluded as previously declared; there is no geometry/number tolerance.
MMR is active: page013 has three overrides (skip3,6,6), page014 six (9,1,9,4,2,6).

Actual production Phase C replay passes for nine single-candidate outputs and the three combined
outputs (plus the control): first-measure manual number0, second-page movement reset1,
third-page continuity, page order and complete pages/metadata equality. Retained real MMR output
is consumed; no detector/MMR inference is repeated for replay.

The additive correction replay additionally runs real Phase A/C on every output with the fixed
first-page barline removal and re-addition shifted two source pixels. It verifies a matched
remove, one add, changed geometry, identical corrected boxes/statistics/base/final pages and
metadata across all modes, manual0/reset1/continuity and order. All 12 pass. This is a separate
fixed correction input, not a timing observation or a threshold/model retune. It does not claim
accuracy on arbitrary edited geometry or a new MMR recognition result after editing.

## Failure behavior

Actual production pipeline fault propagation is exercised after a retained-SR substitution,
without new model inference or a performance score. Three real subprocess scenarios pass the
expected-failure contract: OMR exit7, OMR exit0 but missing predictions, and source child exit7
under two-worker scheduling. Each reaches the intended boundary, exits nonzero, records aborted
detection, publishes no final numbering and no completed OMR handoff. Source child PIDs are gone
when the pipeline returns. Partial scratch/log outputs remain for diagnosis; no fallback or
retry converts failure into success.

GPU-free unit guards also reject missing/modified input, SR or prediction bytes, incomplete or
wrong-image manifests and output overwrite; order/bounded workers and queued cancellation/join
are covered. No OOM, hung GPU/child, forced container kill or user-cancel latency was injected.
These untested failure modes remain adoption risks, not Passed checks.

## Adoption assessment and priority

1. **Bounded page parallelism is a supported E2E implementation candidate**, with warm8.59%
   and observed cold2.93% reductions. It requires explicit RAM/VRAM admission limits, ordered
   merge, release boundaries and cancellation/error policy. Larger pages/devices are untested.
2. **OMR phase reuse is a lower-memory alternative**, with warm6.91% and lower CPU work,
   but no observed cold win. The model/predictor state persists across pages; source equality
   and current downstream guards pass, while other shapes/page counts and recovery remain open.
   UID1000 import overhead contributes: earlier root controls show writable bytecode caching,
   so default-root production needs its own E2E before promising this gain there.
3. **Combined scheduling is the fastest tested configuration**, warm11.32% / observed cold6.42%,
   but adds only2.99% beyond P with two mechanisms and a new handoff protocol. Retain it as an
   integration candidate; the marginal gain does not justify bypassing portability, failure
   and broader semantic gates or creating another implementation Issue automatically.

The existing cache-lifetime Issue #454 remains especially relevant for short-lived cold jobs.
No candidate is labeled production-adoption ready. Next decisions concern deployment UID/cache
policy, more input shapes/page counts, resource admission and abnormal termination. Larger
accuracy/regression validation belongs to an approved implementation task; full68 was not run.
No additional E2E was launched after this predeclared matrix to optimize the reported outcome.

## Validation and retained provenance

Performance/source checkpoint:488193d2, with OMR correction99098a97 before any O/C execution;
per-run provenance/snapshots identify exact effective code. Final utility tests cover the same
candidate code plus formatting-only promotion of supplemental replay/analysis scripts. The final
code patch and digest are retained under e2e-candidates/validation/final-code.patch(.sha256).

| Check | Status | Command / evidence under logs/issue447/e2e-candidates |
| --- | --- | --- |
| Official runtime preflight | Passed | immutable DOCKER_IMAGE, `bash scripts/docker_runtime_validation.sh --config configs/dense_full_pipeline.yaml --preflight-only`; validation/runtime-preflight.log, exit0 |
| Container CUDA operation | Passed | fixed torch.ones CUDA sum using production image; validation/cuda-probe.log, exit0 |
| Timed E2E matrix and strict/resource/process-count/SR guards | Passed:12 | `PYTHONPATH=. python3 tools/issue447/e2e_candidate_matrix.py`; matrix.jsonl, results.json, run-local provenance/checks, exit0 |
| Actual Phase C | Passed | matrix-recorded CPU-only docker commands invoking e2e_semantic_replay.py; replay-single and replay-combined/result.json |
| Actual Phase A/C barline/manual/movement replay | Passed:12 | CPU-only image command invoking retained correction_replay.py; correction-replay/result.json and validation/correction-replay.log, exit0 |
| Fault propagation contract | Passed:3 | CPU-only image command invoking retained fault_integration.py; faults/result.json, validation/fault-integration.log; harness exit0, expected injected pipeline exits1 |
| Focused and related numbering/MMR/movement tests | Passed:56 in3.44s | shared utility container `python -m pytest tests/test_issue447_profiling_tools.py tests/test_issue447_source_scheduling.py tests/test_issue447_omr_reuse.py tests/test_issue257_mmr_page_rebase.py tests/test_numbering_overrides.py tests/test_movement_boundary_review.py -q`; validation/final-focused.log, exit0 |
| Input/config/selected weights and image model identities | Passed | validation/input-identity.json, selected-model-identity.json, image-model-identity.log |
| Compile, targeted Ruff, public help, JSON/links/diff | Passed | validation/final-static.log and final-help.log; initial copied-script import-style lint violations were fixed before final checks; launcher line wrapping was also corrected |
| OMR cold performance improvement | Failed to demonstrate | -0.66% observed reduction; original result retained, no corrected/rescored speed claim |
| Complete GPU-PID / exact CPU-GPU wait attribution | Blocked | WSL PID query unavailable and different clock domains; independent host/GPU evidence retained |
| Root/single-page/broader shapes, OOM/hang/kill/cancel recovery, make test-fast, canonical smoke, full68 | Not run | fixed bounded research scope; no production/service code change. Focused tests plus actual bounded E2E/replays cover this diff; full68 explicitly excluded |

Utility-only tests use the existing5311cf22… image; performance and actual pipeline replay use
the immutable production image above. Raw models/datasets/cache/output remain out of git.
[Machine-readable results](issue447-e2e-candidates.json) retain observations and exact provenance
commands; raw journals, cache inventories, logs and original supplemental script snapshots are
under logs/issue447/e2e-candidates and run-local directories. Supplemental validation was fixed
before execution in e2e_supplemental_contract.json; original version/chronology is preserved locally.
Exact supplemental Docker argument arrays and script hashes are retained in validation/commands.json.
Public launch/replay CLI help is recorded. Reproduction requires new unique output labels or a
fresh output checkout: original evidence directories intentionally refuse overwrite.

Historical evidence: previous cache repeats, trace ON, compiled-batch failure, eager semantic
failure and the 2026-10-26 canonical smoke remain in the earlier reports and were not rerun or
pooled into this cohort. No current full-dataset accuracy or exclusive wait attribution is implied.
Architecture docs are unchanged because no production/service boundary was modified.
