# OMR job reuse (Issue #459)

Status: maintained production route for root multi-page jobs. Research evidence and the
failed/passed gate history live in PR #478 (`docs/performance/issue459/` on
`fix/issue459`). This document is the runtime contract.

## Route selection

`detection.omr_job_reuse` selects the OMR-DLN route **once, before SR starts**:

| Condition (`mode: auto`) | Route |
| --- | --- |
| production model selection, not dry run, at least `min_pages` (2) pages, process UID in `allowed_uids` (`[0]`) | `job_reuse`: one OMR process for all ordered pages |
| anything else (single page, non-root UID, exploration/comparison models, `mode: off`) | `per_page`: the existing one-OMR-process-per-page route |

The decision and its reason are recorded as `omr_route` in the detector result. A failure in
the job route fails the job; it never falls back to the per-page route. Single-page and
non-root jobs are excluded because the measurements did not show a benefit there
(root single-page warm/cold -1.10/-0.89%; UID1000 single-page cold -6.77%).

## Job route

1. Before SR, the coordinator allocates a UUID4 run ID and records each source digest.
2. After the existing batch SR process exits, it requires unchanged sources and this job's
   fresh SR outputs (the paths requested inside this job's support directory).
3. `omr_job.build` writes `request.json` under `<hybrid_output>/pipeline/omr_job/` and runs
   `src.pipeline.detection.omr_job_worker` in its own process group. The worker loads the
   manifest-verified production checkpoint once on CUDA (no CPU fallback) and runs the
   existing `omr_dln_worker.run` loop for the ordered pages, then attests run, request,
   model, page and prediction hashes.
4. Only a zero exit with no surviving descendants and matching identities publishes
   `completed.json`. Timeout, SIGTERM or an error kills and reaps the process group and
   publishes `failed.json`; partial predictions and `worker.log` remain for diagnosis.
5. Each page's support worker pins the manifest digest, verifies every row and then
   atomically exposes that page's exact prediction bytes at the usual
   `omr_sr/<page>/predictions.json` path. Downstream HOMR, consensus, numbering and MMR are
   unchanged. Support and source-page results report `omr_execution_scope:
   omr_job_process`, and the coordinator rejects a result from the other route.

Recovery is a new job: a fresh run ID, SR and output directory. SIGKILL of the whole
container is owned by the outer job boundary; nothing in the job directory is reused.

## Evidence summary (PR #478)

- Root multi-page warm, three fresh ABBA blocks: 3.22 / 2.33 / 3.42%, pooled 2.40%
  (B 238.16 s, O 232.45 s). The original v1 >=3% gate (2.57%) remains recorded as Failed.
- Root multi-page cold +2.67%; UID1000 multi-page warm/cold +3.71/+3.54%.
- Semantic equality of predictions, masks, geometry, numbering, movement and MMR in every
  run; real correction replay equal; 8-page mixed-score job equal, with comparable memory.
- Actual container SIGKILL and cgroup OOM during the OMR worker: fail closed, then a fresh
  job recovered with equal output.
- The pre-registered 25-page input failed on page_001 in both routes (a production
  limitation of that page); the job worker itself processed all 25 pages.

These research runs used the candidate module under `tools/issue459/`; this route ports that
protocol into `src/`. Production validation of this wiring is reported in its PR.
