# Issue 458 reassessment contract — 2026-11-01

Authority: PR467 comment6559450448 requests an independent adoption reassessment.
The original warm >=5% gate remains Failed (4.900958%); no historical run is
reclassified, pooled, excluded or replaced by this phase. Default workers=1 and
Draft status remain. This contract is fixed before new inference/timing results.

## Frozen comparison and practical improvement decision

Use a clean committed source for all runs, with before/after tracked-file digests
and commit checks; no source edits, tests or other agent evaluations during timed
runs. Current develop6d53c5c2 differs from the PR base only in documentation;
retain the PR's runtime lineage. UID1000/GID1001, RTX4060 8GiB, immutable image
5c5979a26f4b232bc93af6b2d040226a6e6f0c45557ccc8ad4db56153fa0398a,
private copies of the same retained qualified compiler seed, fresh containers,
trace OFF, production compile mode, OMP/MKL source threads=4 for both modes,
16GiB container memory limit. Models, thresholds and geometry are unchanged.
Source is mounted read-only with only the Issue evidence root writable. Record
input/model/seed digests and actual image/mount/UID/device/cgroup identities.

Primary: Shostakovich-Sym5-Va pages012–014, 2960×4210. Four adjacent matched
pairs, alternating which mode goes first: B/P, P/B, B/P, P/B (eight runs, four
per mode). B=workers1; P=workers2. No extra repetitions after inspecting results.
Report every time, paired reduction, median/range/MAD per mode and I/O/CPU/GPU.
A practically reproducible improvement requires all of:

- positive overall median reduction, with >=5 seconds saved per three-page job;
- at least3 of4 adjacent pairs faster with P;
- no matched P regression greater than3%;
- all required semantic, correction, failure and resource gates pass.

These are descriptive limited-deployment criteria, not a statistical confidence
claim and not a revised result under the original >=5% contract. A small/unstable
outcome is a valid negative decision. Cold is historical supplementary evidence;
no new cold matrix or full68 is required for this performance reassessment.

Host process CPU counters, Docker events/inventory and GPU samples are retained.
Record persistent unrelated CPU consumption (>=one logical core for >=10s) or
known GPU compute competition; affected timing cannot support adoption. Do not
silently omit/retry such runs: retain them and mark the phase Blocked for a new
explicitly defined experiment. Linux/WSL cannot prove absence of all host noise.

## Input and resource safety

After the primary matrix, run an unscored one-worker cache qualification followed
by one B/P pair on Va_Prokofiev_Symphony1 pages001–002 (3600×4680), using copies
of that qualified seed. This tests a larger shape and two-page count; its single
pair is a safety/semantic observation, not evidence of stable performance there.
Finally run one requested2-worker single-page primary input; selection must be1.
The original single-page pair remains historical evidence, not a new rerun.

Experimental policy: exact allowed_input_shapes of2960×4210 and3600×4680,
max_input_pixels16848000, validated_workers2, threads4, RAM screen12GiB,
VRAM screen7GiB, on_unavailable=error, source timeout300s. The larger shape is an
isolated validation candidate until it passes, never a production default.
Unknown shapes are rejected even when their area fits; resource shortfall and
unsupported device reject, unless explicit pre-start serial selection is tested.
Actual larger retained inputs (3640×5155 and3685×5174) must reject under this
policy without model inference. No universal device/shape safety claim follows.

All successful parallel runs must remain <=16GiB cgroup RAM and <=7GiB sampled
device VRAM, with no OOM. Samples are screens, not reservations/peak guarantees.
A shape failing these gates is ineligible for the two-shape profile. A separately
specified primary-only opt-in proposal may use ONLY2960×4210 if its own gates
pass; report the failed larger-shape result prominently without changing it.

## Correctness, cleanup and reporting

For every successful run compare ordered original/x4 predictions, decoded masks,
detector geometry, base/final numbering/movement metadata, MMR targets/skips and
filters to its same-input B reference. Run actual Phase A/C manual0/reset/
continuity/barline-edit replay for all eight primary outputs. No tolerance/model/
threshold changes or OMR reuse, SR overlap, other optimizations are permitted.

Before freezing, run focused admission/scheduling/engine-retention guards. After
timing, rerun six real process faults (including cgroup OOM, timeout/kill, no
final publication, diagnostic retention and original-error propagation), plus
maintained GPU/accuracy smoke at the frozen source. Record SIGTERM/descendant
cleanup tests and single-page/resource rejection checks. CUDA allocator OOM,
root performance, other devices and lone-supervisor SIGKILL are Not run unless
actually exercised; force-kill the job container/cgroup operationally.

If a supplemental run fails, retain it and do not silently retry; dependent
unrunnable checks are Blocked/Not run. All primary checks/results remain visible.
Report new phase separately in repository and PR467/Issue458, with exact commands,
commit/runtime/input/cache identities, all gates, limitations and resource margins.
A positive conclusion is a conditional opt-in proposal for measured shapes on
this UID/device only, with workers1 rollback; it does not authorize activation,
default changes, marking the PR ready or merging it.

An additional planned CUDA allocator OOM case runs after timing in a separate
GPU-enabled4GiB container: request16GiB on the8GiB device inside disposable
source children. Require the real CUDA out-of-memory diagnostic, child cleanup,
no final publication and retained original cause. Host OOM remains a separate
2GiB CPU-only test. These are fault injections, not performance observations.
