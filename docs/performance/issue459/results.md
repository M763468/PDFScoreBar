# Issue #459 deployment evidence

Root warm primary screen passed; production adoption remains pending all other required gates.

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

## Remaining gates

GPU smoke **Passed** (exit0): `DOCKER_IMAGE=sha256:5c5979a26f4b232bc93af6b2d040226a6e6f0c45557ccc8ad4db56153fa0398a DOCKER_EXTRA_ARGS="-v <manager>/data/evaluation2:/workspace/data/evaluation2:ro -v <manager>/models/mmr/mmr_classifier_best.pth:/workspace/models/mmr/mmr_classifier_best.pth:ro" make verify-gpu-smoke`, on 3c953f84 plus the later experiment-tooling-only matrix diff. Fresh PDF render matched accepted input SHA-256 `48e073dd8184495b9751ad62e85a872bc93cce751ba0a8c988300f7c5ae444a6`; 85/85 barlines matched, hard FP/FN/soft all zero. Retained under `logs/issue459/validation/gpu-smoke/` (console and exit-code) and `retained/` (wrapper log and pipeline output). These generated directories were relocated from the launcher's hard-coded generic log roots after completion; embedded paths retain their original spelling. This smoke tests the unchanged production route, not adoption of reuse.

Remaining performance cells are in progress. Production reuse is disabled. Long-document/shape/state-growth, recovery, and real correction replay remain unverified. No quality-preservation or production-readiness claim is made.

Historical #447 results were not rerun as historical experiments and are not substituted for current evidence.
