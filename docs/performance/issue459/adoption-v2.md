# Issue #459 adoption decision contract v2 (pre-registered)

Status: fixed **before** any v2 observation, in response to the PR #478 owner review
(2026-11-03). It is a new experiment. It does not rescore, replace or relabel v1.

## What stays unchanged

- v1 result: corrected job-v1 root/multi/warm ABBA (`jobv1-root-warm2`) improved
  2.5652%, **Failed** the original >=3% primary gate in [acceptance.md](acceptance.md).
  That status, its provenance and the v1 Not-run list are retained as written in
  [results.md](results.md).
- #447 PoC results are a different candidate and are never pooled with job-v1 data.
- Candidate implementation, production route, models, thresholds, inputs, image,
  deployment (UID/GID 0:0, HOME=/root), compiler-seed policy and trace-OFF are unchanged.
- Merging the research tooling does not activate production reuse. A v2 "eligible"
  verdict only permits proposing a separate production-integration change; the
  owner decides activation in that change.

## Why the decision rule changes

The Issue states >=3% as the minimum target for considering adoption but gives no
quantitative reason why 3% is a hard practical boundary. v2 replaces the single-ratio
decision with a pre-declared combination of reproducibility, regression, quality,
lifetime and recovery gates. It is not a license to adopt arbitrarily small
differences: a floor and a noise criterion remain (P1 to P3).

## Performance evidence (root, multi-page Sym5 pages 012/013/014, warm seed copy)

New labels `v2-primary-{2,3,4}` (see "Invalid attempt" below for `v2-primary-1`). Each is a full fresh ABBA block from
`tools.issue459.screen --job-protocol` (same seed `logs/issue459/cache/root-multi-cold-b2`).
v1's block is reported next to them but is **not** included in the v2 statistics.

- Block improvement `I_k = 100 * (1 - median(O_k) / median(B_k))`.
- Pooled improvement `I = 100 * (1 - median(O, 6 runs) / median(B, 6 runs))`.
- Baseline noise `N = 100 * (max(B) - min(B)) / median(B)` over the 6 B runs.

| ID | Gate | Pass condition |
| --- | --- | --- |
| P1 | Direction reproducible | `I_k > 0` for every v2 block |
| P2 | Above measurement noise | `I >= N / 2` (the improvement exceeds half the B-arm spread) |
| P3 | Not negligible | `I >= 1.5%` |

Reported, not gated: absolute seconds saved per job and per page, CPU-s, cgroup RAM
peak, device VRAM peak, GPU mean utilization, physical I/O, OMR process count.

## Regression cells (original limits unchanged)

Run all seven remaining cells with ABBA via `tools.issue459.adoption_v2 cells`
in the original fixed order: root multi cold; root single warm; root single cold;
UID1000 multi warm; UID1000 multi cold; UID1000 single warm; UID1000 single cold.
Gate R: each cell's median regression is at most 3% and every run is semantically
equal to that cell's first B. v2 does **not** stop early, so the complete matrix is
visible. Any failure is reported and fails gate R; no rerun or exclusion.

## Quality, lifetime and memory

| ID | Check | Pass condition |
| --- | --- | --- |
| Q1 | Three-page semantic equality | All v2 primary and cell runs pass the retained `pipeline_checks` |
| Q2 | Real correction replay | Fixed barline remove/add, manual number and movement reset replayed on the first v2 primary block's B and O outputs (`e2e_correction_replay.run`); every built-in check true and corrected boxes/stats/base/final pages equal between B and O |
| L1 | Long document | All 25 Sym5 pages, root warm, one B and one O run: completes; semantic equality; O uses exactly one OMR worker process |
| L2 | Varied shapes | 8 pages interleaving four scores with four page sizes (copied inputs under `logs/issue459/inputs/`), root warm, one B and one O: same as L1 |
| M1 | Memory growth | For L1 and L2: O cgroup RAM peak <= 1.10 x B peak; O device VRAM peak <= B peak + 512 MiB |

L1/L2 timings are descriptive only (single observation per arm) and are not used for P1 to P3.

## Failure recovery (actual container boundary)

Each fault is injected into a v2 O run (root, multi, warm) after the job worker is
observed running inside the container, followed by a **fresh** recovery job (new
label, new container, new UUID/SR/output) that must complete and be semantically
equal to the v2 primary B reference.

| ID | Fault | Pass condition for the faulted run |
| --- | --- | --- |
| F1 | Container SIGKILL (`docker kill`) while the OMR worker runs | nonzero exit; no `completed.json`; previously written diagnostics retained; no surviving container |
| F2 | Real cgroup OOM: lower the running container memory limit below current use while the OMR worker runs | kernel OOM kill recorded (`OOMKilled` or `oom_kill` event); nonzero exit or a coordinator failure; no `completed.json`; no published handoff/prediction consumption |
| F3 | Recovery after F1 and after F2 | fresh job exit 0 and Q1 semantic equality |

Existing CPU unit tests remain separate evidence for nonzero exit, malformed/tampered
results, timeout and cancel.

## Decision

- **Eligible for a production-integration proposal** only if P1, P2, P3, R, Q1, Q2,
  L1, L2, M1 and F1 to F3 all pass.
- Any failed gate: **not eligible**; report which gates failed.
- A gate that could not run is **Blocked/Not run**, never Passed; the verdict is then
  **undecided**.
- No threshold, input, seed, tolerance or metric change after observing v2 data.
  Any such change creates v3 and keeps v2 visible.

## Invalid attempt (recorded before any v2 timing existed)

The first campaign start (`v2-primary-1`, run `1-b` only) overlapped a concurrent
CPU-only correction-replay dry run (on v1 outputs) on the same host. It was stopped
before `result.json` existed, so no v2 wall time was observed. Artifacts are retained;
see `logs/issue459/v2/invalid-attempt-v2-primary-1.json`. Primary blocks use fresh
labels `v2-primary-{2,3,4}`; no gate, input or threshold changed. No other workload
runs on the host during a timed v2 run.
