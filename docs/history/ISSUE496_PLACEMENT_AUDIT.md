# Issue #496: historical document placement audit

The #441 records describe dated experiments and PR #445 review decisions, not maintained
user instructions. Current source and tests remain authoritative. All ten Markdown files
move from `docs/dev/<name>` to `docs/history/<name>` at the same depth, preserving their
mutual and source links. The #160 audit follows the same mapping. Old Issue/PR links are
historical; use this mapping to find their current paths.

| File (old and new name) | Decision and role |
| --- | --- |
| `ISSUE441_PHASE0.md` | Move: initial PoC and historical decision. |
| `ISSUE441_METHOD_COMPARISON.md` | Move: dated alternatives and experimental constraints. |
| `ISSUE441_MOBILESHEETS_SAMPLE.md` | Move: supplied sample investigation. |
| `ISSUE441_ANNOTATED_RESUME.md` | Move: resume experiment and reproduction evidence. |
| `ISSUE441_PR445_REFINEMENT.md` | Move: PR review and typography experiment. |
| `ISSUE441_PRODUCT_INTEGRATION.md` | Move: integration history; architecture references are updated, while current behavior remains in source/tests. |
| `ISSUE441_MOBILESHEETS_ROUNDTRIP.md` | Move: single-sample roundtrip evidence. |
| `ISSUE441_FINAL_REVIEW.md` | Move: dated final-review validation. |
| `ISSUE441_ADDITIONAL_REVIEW.md` | Move: subsequent review and integration validation. |
| `ISSUE441_REVIEW.md` | Move: historical review entry linking the other records and snapshots. |
| `historical_stage_phase_naming_audit.md` | Move: #160 historical naming and validation boundary; current source remains authoritative. |
| `issue441/evidence/**` | Keep at `docs/dev/issue441/evidence/**`: retained snapshots and test logs, with recorded export commands specifying that location. Moving them would break those historical paths for little discovery benefit. |

The architecture reference and future-service architecture link to the integration record;
the history index now points to the review entry and naming audit. The #441 documents link
to each other, source/tests and evidence. Relative evidence links were adjusted; recorded
commands, machine-specific paths and snapshot contents were preserved. A repository search
found no path references to `docs/dev/issue441` within `tools/issue441` or the evidence
files themselves. Evidence JSON and text were not relocated or rewritten. Historical
commands describe the original environment and are not a promise of present reproducibility.

`docs/performance/` and `docs/refactors/` remain in place: they already group performance
and design lineages by purpose. This audit found no concrete misclassification warranting
additional moves, which would add link maintenance without a demonstrated discovery benefit.
