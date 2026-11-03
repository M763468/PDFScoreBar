# OMR job protocol candidate v1

Status: implemented research candidate, **not adopted** after the original root
warm >=3% gate failed (2.5652% observed improvement; see [results.md](results.md)).
The separate pre-registered adoption-v2 evaluation also found it **not eligible**
(UID1000 single-page cold regression and the 25-page input gate failed).
It is not wired into the maintained production route. Select only through the experiment launcher's `--job-protocol
--source-workers 1 --omr-reuse`. This changes the candidate and requires its own
performance/quality results; PoC timings do not establish v1 performance.

The outer fresh job/container owns the ultimate kill boundary. Before SR, the
coordinator allocates a UUID4 and records ordered source hashes and the selected
model-manifest digest. It checks those identities after the existing batch SR worker
exits, requires each SR result to match this job's requested output inside its fresh
support directory, and adds the source/run binding to the SR rows. Only then does it
allocate the exclusive OMR output directory and bind source/SR hashes and the selected
production model digest into request.json.
A dedicated job_worker loads that explicit native checkpoint on CUDA once and uses
the existing OMR run loop for the ordered pages. No model/confidence/threshold change
or CPU fallback is selected. The worker verifies identities before and after
inference and publishes an atomic result attesting the request digest, run, model,
ordered page association and each prediction hash. PID/UID/GID/image/interpreter
metadata accompanies the result.

The coordinator requires successful worker exit, validates that attestation against
its original request, validates every source-coordinate prediction, and rechecks
inputs/model before atomically publishing completed.json. Only then can disposable
source/HOMR workers consume predictions. A separate trusted handle pins the complete
manifest hash, run ID and model hash. Consumption validates all rows and the worker
attestation before publishing any page with an exclusive atomic hard-link operation.
An existing destination is an error. Missing/invalid/mixed-run/changed data has no
fallback. Partial predictions and worker.log remain diagnostic evidence, while
failed.json records the error and completed.json remains absent.

The worker runs in a dedicated process group. A finite timeout, SIGTERM cancellation
or exception terminates the group, escalates to SIGKILL when needed and reaps the
direct worker. The coordinator temporarily owns SIGTERM only on the main thread and
restores the previous handler. Unexpected descendants after a successful worker exit
also reject completion and are killed. SIGKILL of the coordinator requires the outer
job/container to terminate its namespace; this implementation does not claim that a
standalone host coordinator can clean up after its own SIGKILL. Production adoption
requires an actual container kill/OOM recovery check under that boundary.

There is no same-directory resume or cross-job resident model. Recovery starts a new
job UUID, fresh SR validation, fresh worker and exclusive output root; previous
failed artifacts are retained. The experiment adapter exports the trusted handle
only after success and clears an older handle before starting another phase. It is
for one fresh job per process, not a concurrent in-process service API.

Permission/cache policy remains explicit in the launcher: UID/GID, HOME and optional
PYTHONPYCACHEPREFIX, read-only external models and private compiler caches. All raw
artifacts belong below logs/issue459. Keep diagnostics and input/model/protocol
provenance together; no automatic cleanup or model/cache deletion is performed.

CPU tests exercise atomic publication, whole-job tamper detection, mixed-run
attestation, nonzero exit, missing/malformed/partial output, input mutation, timeout
with a SIGTERM-ignoring worker, cancellation and fresh-directory recovery. Actual
GPU model state, long/varied-shape documents, OOM/kill and correction replay are
separate gates and are not inferred from those unit tests.

The prediction validator follows the existing strict consensus contract: finite
numeric coordinates, ordered bounds, and preserved zero-extent clipping at image
edges. It copies the exact prediction bytes; it does not filter, widen or retune
barlines. The first v1 E2E exposed an overly strict validator and is retained as a
failed attempt, not corrected into a successful timing observation.
