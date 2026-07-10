# Issue 120 Roadmap — Archived

> [!WARNING]
> This roadmap is no longer an active planning document. Its staged recovery work
> was completed through the Issue #120 / Stage E sequence, and its former
> `current / next issues` section is intentionally removed because it referred to
> branches and issues that are no longer active. Use Git history when the detailed
> historical planning sequence is needed.

## Current source of truth

The current production detector and input contract is defined in:

- [`docs/dev/DETECTOR_BASELINE_MATRIX.md`](dev/DETECTOR_BASELINE_MATRIX.md)

The required production accuracy profile is an indivisible set:

```text
production_dense_v1
+ default dense candidate reconstruction
+ 360 dpi PDF raster input
+ current CNN with NMS disabled
+ current MMR
```

Historical Stage E and saved-intermediate evaluation remain useful as regression
references, but they are not production configuration sources:

- [`docs/ISSUE120_EVALUATION_CONTRACT.md`](ISSUE120_EVALUATION_CONTRACT.md)
- [`docs/ISSUE120_HISTORICAL_BEST_AUDIT.md`](ISSUE120_HISTORICAL_BEST_AUDIT.md)
- [`docs/ISSUE141_STAGE_E_FULL_PIPELINE_REPORT.md`](ISSUE141_STAGE_E_FULL_PIPELINE_REPORT.md)

## Retained historical milestones

The archived roadmap covered these completed layers:

1. saved scored intermediates and the canonical 68-page evaluator;
2. saved candidates through current CNN scoring;
3. regenerated dense and probe-rescue candidates;
4. slow upstream HOMR / OMR / SR regeneration diagnostics;
5. full 68-page Stage E validation;
6. productionization of the recovered dense route.

Issue #244 established that production correctness also depends on the 360 dpi
PDF input contract. A dense route running on the older 300 dpi raster preserved
physical measure counts but regressed MMR and final row-start numbering. New work
must therefore use the baseline matrix rather than reconstructing configuration
from this historical roadmap.
