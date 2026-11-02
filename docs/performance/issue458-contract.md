# Issue 458 validation contract (fixed before implementation)

Base: afa19333. Deployment for this attempt: Linux Docker, UID 1000/GID 1001,
RTX 4060 8 GiB, 8 logical CPUs. Parallel production activation remains opt-in
until the following gates pass. Root deployment is outside the measured claim;
root and non-root must use private writable compiler caches (no shared ownership).

Primary gate: at least 5% lower median fresh-container, trace-OFF warm E2E on
Shostakovich-Sym5-Va pages 012–014 versus this revision with one worker.
Run order: warm 1,2,2,1; cold 1,2; single-page warm 1,2 (page 013).
Warm means independent copies of the same compiler-warm seed; cold means empty
private compiler caches. OS caches are not flushed. Model manifests, compile mode,
thresholds and input bytes remain identical. Capture immutable image, source diff,
config, UID, cache identity, CPU/RAM/GPU/VRAM/I/O and median/range. Competition or
unknown runtime invalidates timing. Resource gates: cgroup RAM <=16 GiB and sampled
device VRAM <=7 GiB, no OOM. These are measured gates, not safety guarantees.

Strict semantic gates: ordered original/x4 predictions and decoded masks,
detector geometry, base/final numbering/movement metadata, MMR targets/skips,
filters; actual Phase A/C manual 0, movement reset, continuity and barline edit.
Use retained issue447 comparison/replay tools against new outputs where compatible.
Admission tests cover larger shapes, single/multiple pages, unsupported device,
insufficient RAM/VRAM. Fault tests cover nonzero/missing/duplicate results,
out-of-order completion, timeout, cancellation and process-group cleanup.
A SIGKILL to the supervisor cannot execute cleanup; deployment must kill its
container/cgroup, not a lone supervisor PID. No silent runtime retries.

Validation order: focused tests, fast tests, maintained GPU smoke, fixed E2E and
semantic replay. Full68 is not authorized by this contract and is not repeated
for timing alone. Any blocked/failed gate remains explicit; do not claim adoption.

Seed qualification: the first warm-1a launch prepares/qualifies the compiler seed
on current #454 cache policy; it is not part of the scored matrix. Freeze the
resulting seed and run the complete order above using new labels. Both scored
controls and candidates use OMP/MKL threads_per_worker=4, matching #447. This
was fixed before the seed run completed or any timing result was inspected.
