# Issue 163 local HOMR phase A/B/C result

This note records the final small HOMR-only mechanism-isolation experiment for Issue #163.

The experiment compared:

| Condition | Runner mode | Meaning |
| --- | --- | --- |
| A | `default_sequential` | existing HOMR baseline, then existing HOMR SR route |
| B | `phase_split_sequential` | baseline full route, then SR preparation only, then SR HOMR inference |
| C | `phase_split_overlap` | baseline full route overlapped with SR preparation, then SR HOMR inference |

The fixed subset contained 10 images. All A/B/C summaries reported `image_count=10`, and B/C SR preparation and SR inference also reported `image_count=10`.

## Result

| Metric | A default | B phase-split sequential | C phase-split overlap |
| --- | ---: | ---: | ---: |
| total runtime | 1215.02 sec | 1217.86 sec | 1234.45 sec |
| baseline duration | 279.96 sec | 281.30 sec | 383.47 sec |
| SR full route | 935.05 sec | n/a | n/a |
| SR preparation | n/a | 190.34 sec | 454.67 sec |
| SR inference | n/a | 746.22 sec | 779.69 sec |
| peak GPU memory | 4715 MB | 4712 MB | 5400 MB |
| peak process-tree RSS | 5279535104 bytes | 5540466688 bytes | 5762867200 bytes |

## Interpretation

- A and B were effectively equivalent for runtime. Phase splitting alone did not improve runtime.
- B had nearly the same peak GPU memory as A, but higher process-tree RSS.
- C was slower than both A and B.
- C increased peak GPU memory by about 688 MB compared with B.
- C did overlap baseline and SR preparation mechanically, but baseline and SR preparation slowed substantially under overlap. The contention erased the expected benefit.

## Decision

The local A/B/C result does not identify a useful phase-split or overlap mechanism.

Do not adopt the Issue #163 overlap modes. Do not create a follow-up adoption issue from these results. Keep default sequential behavior as the recommendation for #163.

Further runtime work, if needed, should move to separate issues focused on cache/reuse or duplicate-preparation reduction rather than route/phase overlap scheduling.
