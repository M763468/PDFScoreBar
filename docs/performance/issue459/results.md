# Issue #459 deployment evidence

**Decision: do not adopt the implemented job-v1 candidate.** It shortened the default-deployment warm median by 2.5652%, below the predeclared >=3% adoption gate. The earlier Issue447 PoC is separate evidence and does not override this result.

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
