# Issue #459 deployment evidence

**Decision: do not adopt the implemented job-v1 candidate.** It shortened the default-deployment warm median by 2.5652%, below the predeclared >=3% adoption gate. The earlier Issue447 PoC is separate evidence and does not override this result. The separate adoption-v2 evaluation (bottom of this file) also concluded **not eligible**.

## Fixed contract and runtime

See [acceptance.md](acceptance.md). Trace OFF; fresh containers; UID/GID 0:0; HOME=/root; image `sha256:5c5979a26f4b232bc93af6b2d040226a6e6f0c45557ccc8ad4db56153fa0398a`; RTX 4060 8 GiB. Inputs: ordered Shostakovich-Sym5-Va pages 012/013/014. Each warm run uses an independent copy of the same inventoried compiler seed. OS/driver caches were not flushed.

Production source fingerprint is `3ff4ea687eb2630a667594ff388364ec3cbc3d6fa621e38ef27899dc509111ef`. The first run records base b130c0b7 plus the retained HOME-policy diff; later runs record 3c953f84. The launcher SHA-256 is identical across all four runs: `d3c41f03efd0c6c3d5b6e41fcb5f3e8c6a47f223300f402a3f27f989a75f2c00`. No production source, model, threshold or input changed between arms.

## Current measurements

| Run (ABBA) | Wall s | OMR processes | CPU s (cgroup) | RAM peak GiB (cgroup) | Device VRAM peak MiB | GPU mean % | Physical read/write MiB | Semantic |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| root-deploy-screen1-1-b | 240.688 | 3 | 452.64 | 4.818 | 3453 | 43.51 | 0.01 / 165.06 | True |
| root-deploy-screen1-2-o | 230.259 | 1 | 441.90 | 4.865 | 3453 | 45.88 | 0.16 / 167.02 | True |
| root-deploy-screen1-3-o | 248.587 | 1 | 478.48 | 4.882 | 3455 | 41.90 | 60.57 / 167.08 | True |
| root-deploy-screen1-4-b | 253.175 | 3 | 477.37 | 4.918 | 3393 | 41.49 | 230.60 / 167.60 | True |

B median 246.931 s, range [240.68785074993502, 253.1746001970023]; O median 239.423 s, range [230.25947777798865, 248.58684741496108]. Improvement **3.0405%**, **Passed** against the original >=3% primary gate. The margin is small and the observations vary; this is not a robustness or adoption claim.

All three-page source predictions, decoded masks, detector geometry, numbering/movement metadata, filters and MMR mappings/targets/skips compared equal in the retained semantic checks. This is not the separate real correction replay or long-document gate. Process counts come from sampled PID/start-time identities; CPU/RAM are container totals, VRAM includes device-level display/runtime use. Raw GPU/process samples are retained; no causal performance attribution is made from utilization alone.

Artifacts: `logs/issue459/screens/root-deploy-screen1/{seed.json,journal.jsonl,summary.json}` and `logs/issue459/runs/root-deploy-screen1-{1-b,2-o,3-o,4-b}/` (provenance, script snapshots, console, predictions, semantic checks and process/GPU/I/O records).

## Separate preliminary attempts

- `root-multi-cold-b1`: incompatible canonical-tag image, intentionally stopped (exit137); invalid timing, not a performance result.
- `root-multi-cold-b2`: compatible image, completed (382.549 s); used only for compiler-seed generation because the original observer UID could not see root workers.
- `root-warm-screen1`: historical HOME=/tmp diagnostic; B1 245.939 s, O1 intentionally stopped after the HOME discrepancy was identified (exit137). Not default-deployment evidence and not averaged with the corrected screen.

## PoC cold cell and implementation transition

The PoC root multi-page cold ABBA completed: B 374.659/374.106 s (median
374.382), O 363.369/371.290 s (median 367.329), improvement 1.8839%.
**Passed** the original <=3% cold regression limit; all semantic comparisons equal.
Evidence: `logs/issue459/screens/deployment1-0-multi-cold/` and its four run roots.
The next PoC single-page control was deliberately stopped (exit143) when switching
to the implemented formal protocol. That partial run is not a numerical gate result.
Remaining PoC cells were not run: they cannot establish adoption of a different
implementation. No failed numerical observation was excluded from a completed cell.

## Formal job-v1 attempts

- `jobv1-root-warm1`, 313e638d: **Failed**. B1 completed in 226.980 s; O1
  exited1 after 136.241 s because the new validator rejected zero-width edge
  barlines already supported by `hybrid_consensus.load_json_boxes`. The OMR bytes
  remain retained; no complete handoff was published and no source/HOMR phase was
  started. This is an implementation defect, not a completed candidate E2E timing.
- 3b232a0e aligns validation with that existing source contract and binds the
  pre-SR source/run identity plus fresh SR output namespace. It does not change
  predictions, thresholds, the target dataset or numerical acceptance gates.
- `jobv1-root-warm2`: new full ABBA for the corrected candidate, with the original
  root deployment, inputs, compiler seed, trace-OFF and >=3% primary gate.
  Completed; see the decision below. The incomplete old E2E cannot be rescored into a complete E2E: it
  never reached the downstream phases. Old generated OMR bytes remain available
  for direct comparisons; they are not promoted into a fresh job or silently retried.

## Remaining gates

GPU smoke **Passed** (exit0): `DOCKER_IMAGE=sha256:5c5979a26f4b232bc93af6b2d040226a6e6f0c45557ccc8ad4db56153fa0398a DOCKER_EXTRA_ARGS="-v <manager>/data/evaluation2:/workspace/data/evaluation2:ro -v <manager>/models/mmr/mmr_classifier_best.pth:/workspace/models/mmr/mmr_classifier_best.pth:ro" make verify-gpu-smoke`, on 3c953f84 plus the later experiment-tooling-only matrix diff. Fresh PDF render matched accepted input SHA-256 `48e073dd8184495b9751ad62e85a872bc93cce751ba0a8c988300f7c5ae444a6`; 85/85 barlines matched, hard FP/FN/soft all zero. Retained under `logs/issue459/validation/gpu-smoke/` (console and exit-code) and `retained/` (wrapper log and pipeline output). These generated directories were relocated from the launcher's hard-coded generic log roots after completion; embedded paths retain their original spelling. This smoke tests the unchanged production route, not adoption of reuse.

The corrected formal primary gate failed. Remaining candidate adoption gates are Not run for the reason below; PoC passes do not substitute for this. Production reuse is disabled. Long-document/shape/state-growth, recovery, and real correction replay remain unverified. No quality-preservation or production-readiness claim is made.

Historical #447 results were not rerun as historical experiments and are not substituted for current evidence.


## Corrected formal job-v1 decision

**Not adopted:** the implemented candidate failed the original >=3% root multi-page warm primary gate. The criterion is unchanged; PoC results and the faster individual observation are not substituted for this result. Production routing remains unchanged.

Command: `python3 -m tools.issue459.screen --job-protocol --image sha256:5c5979a26f4b232bc93af6b2d040226a6e6f0c45557ccc8ad4db56153fa0398a --seed logs/issue459/cache/root-multi-cold-b2 --label jobv1-root-warm2`.

Tested implementation 3b232a0e, with later test/documentation-only commit f651ed75. Each run retains its exact commit/diff and script snapshots. Runtime image, model digest, ordered inputs, UID0/GID0, HOME=/root, compiler seed and trace-OFF policy are the same across the cell.

| Run (ABBA) | Wall s | OMR processes | CPU s | RAM peak GiB | Device VRAM peak MiB | GPU mean % | Physical read/write MiB | Semantic |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| jobv1-root-warm2-1-b | 222.363 | 3 | 432.15 | 4.858 | 3465 | 45.21 | 0.00 / 164.19 | True |
| jobv1-root-warm2-2-o | 219.001 | 1 | 427.68 | 4.904 | 3459 | 46.22 | 0.00 / 164.12 | True |
| jobv1-root-warm2-3-o | 218.875 | 1 | 430.78 | 4.868 | 3461 | 46.74 | 0.00 / 164.13 | True |
| jobv1-root-warm2-4-b | 227.041 | 3 | 436.67 | 4.870 | 3463 | 45.78 | 0.00 / 164.15 | True |

B median **224.702 s**, range [222.36295300198253, 227.04073499294464]; O median **218.938 s**, range [218.87452878803015, 219.0010152340401]. Improvement **2.5652%**: **Failed** the original >=3% primary gate.

All completed runs passed the retained three-page semantic comparison. OMR process identities were 3/1/1/3. Candidate worker attestations record UID/GID 0:0, the immutable image ID, CUDA, model SHA-256 `00d0bd8b399ae872f029eb38ed3985fcef33ca81cae414992b5cdb9062e91212`, request/run/ordered input and prediction hashes. This establishes the tested three-page result, not long-document or general quality preservation.

Artifacts: `logs/issue459/screens/jobv1-root-warm2/` and `logs/issue459/runs/jobv1-root-warm2-{1-b,2-o,3-o,4-b}/`. The initial failed v1 OMR bytes were also rescored directly against the corrected baseline: all three match (`logs/issue459/validation/failed-v1-retained-rescore.json`). No expensive inference was rerun just to compare those retained bytes.

**Not run for the corrected candidate:** remaining cold/single/non-root cells, actual long/varied-shape model-state/memory-growth checks, actual OOM/container kill recovery and real correction replay. The required primary adoption gate already failed; these cannot rescue that result and were not used as alternative success criteria. Unit timeout/cancel/failure recovery tests and the unchanged-production GPU smoke are separate evidence, not substitutes for these gates. Reconsidering adoption requires a new candidate and the complete original gates.


## Adoption-v2 result (separate experiment; v1 result above unchanged)

Contract: [adoption-v2.md](adoption-v2.md), pre-registered in 4d7045db; block labels
changed in adc30825 before any v2 wall time existed (invalid first attempt below).
Runner: `tools.issue459.adoption_v2`; driver `logs/issue459/v2/campaign.sh`; log
`logs/issue459/v2/campaign.log`; evaluation `logs/issue459/v2/decision.json`.
All v2 runs used source commit adc30825 (no source diff), image
`sha256:5c5979a26f4b232bc93af6b2d040226a6e6f0c45557ccc8ad4db56153fa0398a`, RTX 4060,
trace OFF, fresh containers, independent copies of seed `root-multi-cold-b2`
(warm) or empty compiler caches (cold). 2026-11-03 18:30 to 22:22 JST.

**Decision: not eligible** for a production-integration proposal. Gate R failed
(UID1000 single-page cold) and L1 failed (25-page document; see below). Production
reuse remains disabled.

| Gate | Result | Evidence |
| --- | --- | --- |
| P1 direction | Passed | block improvements 3.2205 / 2.3271 / 3.4226% |
| P2 noise | Passed | pooled 2.3959% >= B spread 2.4944% / 2 |
| P3 floor | Passed | pooled 2.3959% >= 1.5% |
| R regression cells | **Failed** | UID1000 single cold -6.7686% (limit -3%); other six cells within limit |
| Q1 semantic | Passed | all v2 primary and cell runs equal to their first B |
| Q2 correction replay | Passed | `logs/issue459/v2/correction-replay/summary.json` (v2-primary-2 B vs O) |
| L1 long document | **Failed** | both B and O exit1 on page_001 in production current x4 support |
| M1 (long) | **Failed** (not assessable) | both runs failed; no memory comparison possible |
| L2 mixed shapes | Passed | completed, semantic equal, O used one OMR process (B: 8) |
| M1 (mixed) | Passed | RAM peak O 6.162 vs B 6.202 GB; VRAM O 3558 vs B 3567 MiB |
| F1 container SIGKILL | Passed | exit137, no completed.json, diagnostics retained, no downstream, no survivor |
| F2 real cgroup OOM | Passed | two Docker `oom` events, exit137, no completed.json, diagnostics retained |
| F3 recovery | Passed | fresh jobs after F1 and F2 completed and matched v2-primary-2-1-b |

### Primary performance blocks (root, multi-page, warm)

| Block | B s | O s | Improvement |
| --- | --- | --- | ---: |
| v2-primary-2 | 237.299 / 243.240 | 232.376 / 232.688 | 3.2205% |
| v2-primary-3 | 237.959 / 237.738 | 235.045 / 229.582 | 2.3271% |
| v2-primary-4 | 241.530 / 238.360 | 230.934 / 232.531 | 3.4226% |

Pooled: B median 238.159 s, O median 232.453 s, **2.3959%** (5.706 s per three-page
job). v1 `jobv1-root-warm2` (2.5652%) is reported only for context and is not pooled.
Sampled OMR processes were 3 (B) and 1 (O); O cgroup RAM peaks 4.81 to 4.91 GiB and
device VRAM peaks about 3445 MiB were comparable to B.

### Regression cells (ABBA, original limits)

| Cell | B s | O s | Improvement | Gate |
| --- | --- | --- | ---: | --- |
| root multi cold | 357.517 / 351.576 | 347.834 / 342.304 | 2.673% | Passed |
| root single warm | 98.626 / 97.910 | 99.370 / 99.324 | -1.098% | Passed |
| root single cold | 223.719 / 220.095 | 226.569 / 221.190 | -0.889% | Passed |
| UID1000 multi warm | 246.719 / 247.868 | 234.684 / 241.553 | 3.710% | Passed |
| UID1000 multi cold | 369.002 / 372.443 | 362.082 / 353.153 | 3.535% | Passed |
| UID1000 single warm | 106.398 / 109.146 | 109.818 / 106.920 | -0.554% | Passed |
| UID1000 single cold | 229.849 / 231.821 | **258.046** / 234.873 | **-6.769%** | **Failed** |

The failing cell's O observations are 258.046 and 234.873 s; the second alone would be
within the limit. Under the contract a two-run median is the cell statistic and no
observation is excluded or retried, so R is Failed. The cause of the slow run was
not investigated in this campaign; it is not attributed to noise. Artifacts:
`logs/issue459/screens/v2-cell-*/` and the corresponding `logs/issue459/runs/`.

### Lifetime, input and fault notes

- L1: `v2-long-b` and `v2-long-o` both failed (exit1) with `Current x4 support requires
  a complete connector semantic pair` on Sym5 page_001 (log also shows "No noteheads
  found"). The production route fails the same way, so this is an input/production
  limitation, not a candidate difference. In O the job worker had already processed
  all 25 pages in one process and published `completed.json` (25 rows) before the
  shared downstream failure. The gate is still Failed as pre-registered. A rerun on
  pages 002 to 025 would be a new experiment and requires approval.
- L2: the contract describes four page sizes, but the eight pages from four scores
  have three distinct sizes (Sibelius and Prokofiev Symphony 1 are both 3600x4680).
  Inputs and their hashes are in `logs/issue459/inputs/mixed-shape-v2.json`. Timings
  (B 766.6 s, O 731.2 s) are single observations and are descriptive only.
- F2: the kernel OOM-killed the coordinator as well as the worker, so no `failed.json`
  was written; the contract accepts nonzero exit with no completed publication.
- Invalid attempt: `v2-primary-1` overlapped a CPU dry run and was stopped before any
  wall time (`logs/issue459/v2/invalid-attempt-v2-primary-1.json`). It contributes no data.
- Not covered: very long documents without the page_001 limitation, OOM confined to the
  worker only, and repeated cell observations. These are not inferred.
