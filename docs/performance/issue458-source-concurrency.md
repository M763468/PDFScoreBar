# Resource-bounded source concurrency

The dense detector accepts `detection.source_concurrency`. The default remains
`workers: 1`. The SR batch subprocess must exit successfully before source jobs
start; source results are consumed in input order. At most `workers` unconsumed
jobs exist, including running and completed jobs. Models remain disposable per
page, with no OMR reuse or persistent inference pool.

The owner approved integrating this feature into the production code path in
[PR467 comment6578962019](https://github.com/M763468/PDFScoreBar/pull/467#issuecomment-6578962019).
The following explicit opt-in configuration is approved for the measured
environment, supported by the [practical reassessment](issue458-reassessment.md).
The generic production configuration remains one worker. The [original >=5% result](issue458-results.md) remains Failed. It
applies only to the measured non-root, single RTX 4060 deployment:

```yaml
detection:
  source_concurrency:
    workers: 2
    validated_workers: 2
    threads_per_worker: 4
    timeout_sec: 300
    device: NVIDIA GeForce RTX 4060
    ram_gib: 12
    vram_gib: 7
    max_input_pixels: 16848000
    allowed_input_shapes: [[2960, 4210], [3600, 4680]]
    on_unavailable: error
```

`workers` is any positive integer; larger machines can use a higher value after
validating a matching envelope and increasing `validated_workers` (default 2).
Resource budgets describe the whole source phase for that count, not each child.
Admission checks free host RAM capped by remaining cgroup-v2 memory allowance,
free device VRAM, exact device name and original-image pixel area. SR x4 pixels
are sixteen times original area. These checks are conservative screens, not
memory reservations or protection against another workload allocating later.
`allowed_input_shapes`, when provided, must list positive integer [width,height]
pairs; an unlisted shape rejects even if its area fits. The validated proposal
uses this exact-shape restriction. Only a single GPU is supported by automatic
resource discovery. Unknown devices
and resources fail closed. Use dedicated GPU scheduling and a container memory
limit; do not treat sampled VRAM on a few pages as a universal bound.

`on_unavailable: serial` explicitly permits choosing one worker before source
execution, and records why. Default `error` rejects the request. A single-page
input uses one worker. There is no retry or serial fallback after a running job
fails. `threads_per_worker` optionally sets OMP/MKL thread counts in source
children; otherwise inherited thread settings remain in effect.

Each source process owns a Linux process group. Timeout, failed sibling,
KeyboardInterrupt, and SIGTERM abort outstanding jobs, kill their process groups,
and join direct children before returning. No new job starts after cancellation.
A nonzero exit, invalid identity, duplicate SR result, missing result or artifact
aborts detection. Existing final-publication gates remain authoritative.
Partial requests, full worker logs, admission/failure JSON and consumed-input
schedule remain below `source_page_workers`; the detector result includes the
selected policy. Existing bounded failure-log retention is preserved.

SIGKILL cannot run Python cleanup. Operators must terminate the entire job
container/cgroup when forcibly killing a supervisor. Descendants that deliberately
escape their session group are outside this process-group contract. Resource
exhaustion that kills the whole container requires container/cgroup cleanup.
A simulated nonzero OOM-like exit is not evidence of real GPU OOM recovery.

Use private compiler caches writable by the deployment UID. Never share a root-
owned cache with a non-root job or change retained caches in place. Performance
claims apply only to the UID, input shapes and cache policy in the results.

## Integration scope and operational follow-up

This exact-shape/error-policy example is specific to the verified deployment;
it is not a common configuration for all users. Comprehensive operational
fail-safe selection/rejection, resource budgets, timeouts and coordination with
other runtime settings require separate design work. This PR preserves the
existing explicit pre-start selection/rejection and no-silent-retry contracts;
it does not redesign the production configuration system. Integration into
`develop` is separate from release promotion to `main` and service deployment.

To roll back new jobs, restore the generic `workers: 1` block (timeout900s,
unavailable:error, removing the opt-in envelope/thread settings). Retain a failed
run and its diagnosis; do not silently rerun it or relabel it successful.
