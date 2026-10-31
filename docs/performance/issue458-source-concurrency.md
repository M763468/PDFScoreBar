# Resource-bounded source concurrency

The dense detector accepts `detection.source_concurrency`. The default remains
`workers: 1`. The SR batch subprocess must exit successfully before source jobs
start; source results are consumed in input order. At most `workers` unconsumed
jobs exist, including running and completed jobs. Models remain disposable per
page, with no OMR reuse or persistent inference pool.

An example opt-in envelope for the measured RTX 4060 deployment is below. Treat
it as a validation candidate until the [results](issue458-results.md) gates pass:

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
    max_input_pixels: 16000000
    on_unavailable: error
```

`workers` is any positive integer; larger machines can use a higher value after
validating a matching envelope and increasing `validated_workers` (default 2).
Resource budgets describe the whole source phase for that count, not each child.
Admission checks free host RAM capped by remaining cgroup-v2 memory allowance,
free device VRAM, exact device name and original-image pixel area. SR x4 pixels
are sixteen times original area. These checks are conservative screens, not
memory reservations or protection against another workload allocating later.
Only a single GPU is supported by automatic resource discovery. Unknown devices
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
