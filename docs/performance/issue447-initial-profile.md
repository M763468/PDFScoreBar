# Issue #447: initial current-production profiling evidence

Subsequent investigation and decisions: [Issue #447 results](issue447-results.md).

This is an initial investigation record for [Issue #447](https://github.com/M763468/PDFScoreBar/issues/447),
not acceptance of an optimization or completion of the Issue. Production source, models,
thresholds and detector routing were unchanged during these measurements.

## Frozen source and runtime

- Source: `2ac7d5245fe65dbfa2093b4e0d60119c58192f86`, current `origin/develop` when fetched.
- Worktree: `.worktrees/issue447`; branch: `perf/issue447-current-e2e`.
- Production configuration: [`dense_full_pipeline.yaml`](../../configs/dense_full_pipeline.yaml),
  SHA-256 `0edfdfda89ed50be6d0dafbf28fccc80840ef6330f193d19823a94f934cb2209`.
- Immutable Docker image:
  `sha256:5c5979a26f4b232bc93af6b2d040226a6e6f0c45557ccc8ad4db56153fa0398a`.
  The resolver verified runtime compatibility fingerprint
  `d73cfaa3096e662faca36d85f425553ebeb258f912a7bd424827425caaac2f97` against this checkout.
  Its retained build source is `9ccd57fbf93ac70bac0ee3a85cfd9ef676c88254`;
  application source comes from the active worktree mounted at `/workspace`.
- GPU: NVIDIA GeForce RTX 4060, 8188 MiB; driver `610.88`.
- Runtime: torch `2.14.0+cu130`, CUDA `13.0`, cuDNN `92400`, ONNX Runtime GPU `1.24.4`.
  Image-base CUDA and torch CUDA are distinct identities; the container CUDA probe passed.
- Original-image HOMR: pinned maintained profile at
  `457e7c6518a10ba755db2e60883419e56c4d7369`.

The shared development container and canonical image tag still pointed to image `5311cf22ab01`,
which failed current runtime compatibility. The maintained resolver found the compatible
image above. No shared image tag or development container was changed.

Inputs and MMR weights were explicitly mounted read-only from the manager checkout.
The verified shared CNN/OMR model cache was mounted read-only at `/model-cache` and selected
through `PDFSCOREBAR_MODEL_CACHE`. This avoided a non-root permission error reading the
image-owned CNN cache; model identities remained those selected by the tracked manifests.

## Measurement contract

The representative input is `Shostakovich-Sym5-Va/page_013.png`, SHA-256
`071b237bbcb8f41c42b510c99663016f3232a89f12940bc871b4f6ec0720699e`.
Pages 012–014 are also available, with identities recorded before measurement.
The slice uses existing rendered images, as the production dense config specifies;
its E2E time does not include PDF rendering or the separate service PDF export boundary.

Trace OFF wall time around a fresh Docker invocation is the primary latency measurement.
It includes container startup, Python imports and teardown. Every run uses fresh output,
without `--skip-existing`. Stage telemetry summaries are enabled; resource sampling is
enabled only for trace ON diagnostics. An external one-second GPU sampler records total
device memory and utilization; these are sampled observations, not allocator peaks or
exclusive per-process GPU memory.

For the single-page comparison, cold means an initially empty Issue-local Inductor/Triton
cache. Warm means a fresh process reusing that cache. Neither means an in-process reused
model, and OS/driver caches were not flushed. The cache mount is an explicit experimental
condition, not a production configuration change or an adopted optimization.

Trace ON results include synchronization/sampling overhead and must not replace trace OFF
latency. Existing fine-grained spans principally cover SR; maintained original HOMR also
reports worker timings. The high-level detection stage includes additional HOMR, OMR,
Dense/Probe and CNN work. Nested spans must not be summed as exclusive time shares, and
unmeasured residuals must not be presented as pure I/O or pure Python time.

## Initial single-page observations

Each condition below was run once. These observations do not establish a distribution,
statistical significance, or a general production speedup.

| Measurement | Empty compile cache, trace OFF | Reused compile cache, trace OFF |
| --- | ---: | ---: |
| Docker E2E wall time | 219.45 s | 103.25 s |
| Detection stage | 209.39 s | 93.40 s |
| SR worker phase, nested inside detection | 167.84 s | 53.63 s |
| SR model initialization, nested inside SR phase | 8.89 s | 8.68 s |
| SR page processing, including first-call compilation/cache loading and image I/O | 158.95 s | 44.95 s |
| Measure construction | 0.25 s | 0.28 s |
| MMR recognition | 4.80 s | 4.95 s |
| Final numbering | 0.25 s | 0.25 s |
| Sampled total device VRAM maximum | 3428 MiB | 3430 MiB |

Detection accounts for approximately 95.4% and 90.5% of the corresponding E2E time.
The observed E2E difference is 116.19 s; the nested SR phase differs by 114.21 s.
This makes compile/cache lifecycle a useful hypothesis to investigate further, but the
SR page timer alone does not isolate compiler CPU time from inference, transfer or I/O.
OS caches were not controlled and there is only one observation per condition.
The remaining detection time cannot yet be assigned completely to x4 HOMR, OMR, Dense/Probe,
CNN, initialization or orchestration. No language rewrite, page parallelism or batch-size
change is justified by this initial attribution alone.

For cold versus warm, a structural repeatability check compared ordered detector geometry,
base and final page/system/staff/measure geometry and numbers, MMR override targets/skips,
and page identities/MMR geometry mappings. The warm trace ON run was checked against
the cold run as well. All compared fields were equal. This is a
one-page repeatability observation, not a GT accuracy claim or a correction/movement-boundary
regression gate. Commands and detailed fields are retained in `check_repeatability.py`
and `repeatability.json` under the local Issue evidence root.

The separate warm trace ON diagnostic completed in 104.22 s. This number is not an
authoritative trace OFF benchmark or an estimate of tracer overhead from repeated trials.
Its synchronized SR enhancement span was 43.76 s, model initialization 7.18 s, image read
0.09 s, image write 1.22 s and SR hash 0.014 s. The enclosing SR subprocess span was
56.60 s. These spans overlap and are not additive. This sample does not support removing
the SR provenance hash as a meaningful E2E optimization.

The trace ON resource sampler observed a maximum summed process-tree RSS of 7,283,650,560
bytes (6.78 GiB), 11 processes, sampled peak process-tree CPU of 820.7% and device GPU
utilization reaching 100%. Summed RSS may double-count shared pages, and a peak is not
sustained utilization. The external sampler observed total device VRAM up to 3434 MiB.
The in-container sampler reported process GPU memory as zero despite active inference;
this is unusable process-memory attribution in this environment, not evidence of zero
GPU memory consumption. Power readings were `[N/A]`.

## Validation and retained evidence

All local artifacts are under the worktree's ignored `logs/issue447/` root:

- `contract.json`: measurement and correctness contract fixed before representative runs.
- `preflight/initial/source-inputs.json`: source/config/manifest/input/MMR hashes.
- `preflight/initial/image-inspect.json`, `smoke-container-inspect.json`, `gpu.txt`,
  `pip-freeze.txt`, `image-model-hashes.json`, `selected-models.json`: actual runtime,
  mounts, installed dependencies, SR/HOMR weights and selected model identities.
- `preflight/initial/attempts.json`: commands, environment, exit status and separate attempts.
- `configs/smoke.yaml`: canonical smoke with only run/output locations changed.
- `validation/production-smoke/detector_accuracy_smoke_summary.json`: current accuracy gate.
- `runs/<label>/provenance.json`: exact command, source commit/diff, config digest and cache state.
- `runs/<label>/result.json`, `telemetry.json`, `gpu-samples.csv`, `container-inspect.json`,
  `console.log` and pipeline/worker artifacts: individual measurement evidence.
- `benchmark.py`, `summarize.py`: local experiment launch/summary helpers, not production tooling.

| Check | Status | Command / result |
| --- | --- | --- |
| Existing shared image compatibility | Blocked | Explicit resolver for `5311cf22ab01`; exit 2, `stale_image`. Not used for production measurements. |
| Initial non-root runtime preflight | Blocked | `bash scripts/docker_runtime_validation.sh --preflight-only`; exit 2, CNN cache permission error before inference; retained as `runtime-preflight.log`. |
| Runtime preflight with verified cache mount | Passed | Same command with corrected read-only cache selection; exit 0, `runtime-preflight-cache-mounted.log`. |
| Canonical production accuracy smoke | Passed | `bash scripts/docker_runtime_validation.sh --config logs/issue447/configs/smoke.yaml`; exit 0, `production-smoke.log`. PDF/render identity verified, GT 85, matched 85, hard FP/FN/soft all 0. |
| Representative trace OFF, empty compile cache | Passed | `python3 logs/issue447/benchmark.py single-off-cold single off`; exit 0, `runs/single-off-cold/`. This means successful measurement, not optimization acceptance. |
| Representative trace OFF, reused compile cache | Passed | `python3 logs/issue447/benchmark.py single-off-warm single off`; exit 0, `runs/single-off-warm/`. |
| Representative trace ON diagnostic | Passed | `python3 logs/issue447/benchmark.py single-on-warm single on`; exit 0, `runs/single-on-warm/`. |
| Representative semantic repeatability | Passed | `python3 logs/issue447/check_repeatability.py single-off-warm single-on-warm`; exit 0, `repeatability.json`. Scope limited to the compared fields and one page. |
| Documentation whitespace and local links | Passed | `git diff --check`; exit 0, including the new document via intent-to-add. The relative production-config link was resolved locally. |
| Fast tests | Not run | Only this investigation document is added to tracked source; no application behavior changed. Local experiment helpers were exercised by the measurements above. |
| Multi-page attribution and candidate PoCs | Not run | This initial record covers environment verification and single-page cold/warm attribution. Multi-page throughput, further instrumentation and predeclared candidate regression gates are outstanding. |
| Full68 | Not run | No numerical, model, detector, evaluation or production behavior change; profiling alone does not require full68. |

The smoke is a correctness/environment gate on Prokofiev page 001. Its elapsed time is not
the representative Shostakovich benchmark. No candidate PoC is accepted, and the full
Issue #447 stage attribution, multi-page throughput and optimization ranking remain open.
