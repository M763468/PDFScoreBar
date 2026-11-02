# Issue #459 adoption contract

Status: pre-adoption; production reuse remains disabled. This contract is fixed before
new timing results. Source baseline: develop 8ecd72f0. Historical #447 results are
context only and are not reruns or adoption evidence.

## Deployment

`Dockerfile` has no USER instruction; the maintained Docker launcher supplies no
`--user` unless the operator adds DOCKER_EXTRA_ARGS. The canonical image Config.User
is empty: default deployment is root, with writable image-owned site bytecode.
The #447 launcher instead hard-coded the host UID/GID. Its gain does not establish
the default deployment gain. The launcher now accepts explicit UID/GID and an issue
artifact root; the default behavior remains the #447 behavior.

## Frozen experiment

Use one immutable compatible production image for every arm, no trace, one GPU,
no competing GPU compute process, and the same source/model digests. Multi-page inputs
are Shostakovich-Sym5-Va page_012, page_013, page_014 in order; single is page_013.
Compare production B against `--source-workers 1 --omr-reuse` O.
Run B,O,O,B for each UID (0:0 and 1000:1000), scope (multi/single), and
compiler state (cold/warm). Each arm therefore has two repetitions per cell.
Record median, min/max and each individual observation, not just the best run.

Cold means an empty private Inductor/Triton directory for every run. Warm means
identical private copies of a hash-inventoried seed for every run. Do not share mutable
compiler directories across arms. Default interpreter bytecode policy must be preserved
inside each fresh container: root can reuse/write image site caches, UID1000 may not.
Optional PYTHONPYCACHEPREFIX experiments are separate diagnostics. OS/driver caches
are not flushed: compiler-cold is not machine-cold. Record physical I/O accordingly.

Primary gate: trace-OFF root multi warm median wall time at least 3% below B.
Root cold and single-page medians must regress by no more than 3% in each cell.
Report all non-root cells; no non-root cell may regress more than 3%.
Retain CPU work, cgroup RAM peak, GPU utilization/VRAM, I/O and actual OMR process
counts alongside wall time. Unknown provenance or GPU contention invalidates a run.

Quality gates: compare source predictions, decoded masks, final geometry, ordered page,
number/movement metadata, MMR mappings/targets/skips and real correction/filter replay
on equivalent inputs. All required comparisons must pass. Test different shapes,
long documents and memory growth separately; three pages alone cannot establish these.

Before adoption, test nonzero exit, missing/malformed/tampered/mixed-run results,
partial success, OOM, hang/timeout, cancel and kill; verify child termination, retained
diagnostics and fresh-run recovery. Complete publication must bind ordered inputs,
fresh SR, model bytes and predictions to a single run after successful worker exit.
No silent retry, fallback, threshold changes or reuse of unknown outputs is allowed.

## Execution

Example root compiler-cold control (use a new label and cache path each time):

```sh
python3 tools/issue447/run_experiment.py --issue-id 459 --uid 0 --gid 0 \
  --label root-multi-cold-b1 --scope multi --image <immutable-sha256> \
  --compile-cache "$PWD/logs/issue459/cache/root-multi-cold-b1"
```

For O add `--source-workers 1 --omr-reuse`. All artifacts belong beneath
`logs/issue459/`; snapshots and provenance are retained by the launcher. These are
research routes; the PoC is not a production worker protocol. Performance success
alone never authorizes integration before all quality and recovery gates pass.
