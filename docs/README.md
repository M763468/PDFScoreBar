# PDFScoreBar Documentation Index

This index separates **current durable guidance** from **historical investigation records**.
When a historical Issue document conflicts with current source or the canonical architecture,
use the current source/tests and the documents in the first section below.

## Start here: current durable guidance

| Document | Role |
| --- | --- |
| [`PIPELINE_ARCHITECTURE.md`](PIPELINE_ARCHITECTURE.md) | **Canonical current production architecture**: dense route, stage ownership, coordinate spaces, process/memory boundaries, fallbacks |
| [`TWO_HOMR_MILESTONE.md`](TWO_HOMR_MILESTONE.md) | Accepted Issue #274 / PR #279 two-HOMR accuracy/performance milestone and reproduction contract |
| [`DOCUMENTATION_INVENTORY.md`](DOCUMENTATION_INVENTORY.md) | Audit classification of durable docs and cleanup/maintenance rules |
| [`ENVIRONMENTS.md`](ENVIRONMENTS.md) | Maintained runtime/development environments |
| [`BRANCH_POLICY.md`](BRANCH_POLICY.md) | Branch/base/promotion policy |
| [`dev/VALIDATION_POLICY.md`](dev/VALIDATION_POLICY.md) | Validation requirements by change type |
| [`REGRESSION_TEST_WORKFLOW.md`](REGRESSION_TEST_WORKFLOW.md) | Regression-test workflow |
| [`GT_PREPARATION_POLICY.md`](GT_PREPARATION_POLICY.md) | Ground-truth labeling policy |
| [`BARLINE_MATCHER.md`](BARLINE_MATCHER.md) | Barline matching/evaluation contract |
| [`manual_correction_review_package.md`](manual_correction_review_package.md) | Current internal manual-correction review-package handoff |
| [`ai-workflow/GRAPHIFY.md`](ai-workflow/GRAPHIFY.md) | Graphify query, refresh, retention, and staleness rules |

The root [`README.md`](../README.md), [`AGENTS.md`](../AGENTS.md), and repository `Makefile`
are also current entry points.

## Execution and output guidance

Use `src/pipeline/main.py` through the Makefile instead of old phase-specific orchestration
documents:

```bash
make run-pipeline CONFIG=configs/dense_full_pipeline.yaml
```

The public/output-profile design records under `docs/refactors/issue226/` through
`docs/refactors/issue229/` remain useful for their scoped contracts. They are not a second
source of truth for the detector/MMR architecture. The currently connected internal review
package is documented in `manual_correction_review_package.md`.

## Detector, numbering, and training reference

These remain useful durable references when working in their domains:

- `CNN_RETRAINING_GUIDE.md`
- `GT_PREPARATION_POLICY.md`
- `BARLINE_MATCHER.md`
- `DEVLOG_MEASURE_NUMBERING.md` — development history/reference; verify current behavior
  against source before treating old decisions as current.
- `DEVLOG_CNN_TRAINING.md` — training history/reference.

## Historical / forensic records

Documents named for a specific Issue, experiment, phase, or dated investigation are kept as
historical evidence unless explicitly promoted into the current durable set. Examples include:

- top-level `ISSUE*.md` files;
- `docs/refactors/issue*/` design/investigation records;
- `docs/notes/`, `docs/future/`, `docs/model_experiments/`, and similar experiment/planning
  material;
- `performance_comparison.md`, which is a dated optimization history, **not** the current
  performance baseline. Use `TWO_HOMR_MILESTONE.md` for the current milestone.

Historical records should normally be preserved rather than rewritten to match current code.
If a historical file is still linked as a current guide, fix the index/link or add an explicit
historical marker.

## Retired current-guide documents

Issue #280 consolidated and removed documents that still presented obsolete architecture as
current guidance:

- `PIPELINE_DATAFLOW.md` — old Phase-2 architecture narrative;
- `FULL_PIPELINE_README.md` — old Phase-1 orchestrator guide;
- `best_configuration_summary.md` — January 2026 detector experiment labeled “Production
  Ready”, superseded by the verified dense production route and current milestone.

Their historical context is recoverable from Git history and related Issue records; keeping
them in the active docs tree would create competing current specifications.

## Maintenance rule

When production stage ownership, authoritative geometry, coordinate contracts, or major
process/memory boundaries change:

1. update `PIPELINE_ARCHITECTURE.md` in the same change;
2. update `TWO_HOMR_MILESTONE.md` only when the accepted comparison milestone itself changes;
3. check this index and `DOCUMENTATION_INVENTORY.md` for newly stale guidance;
4. after stable docs are settled, refresh Graphify according to `ai-workflow/GRAPHIFY.md`.

Issue-specific forensic notes do not need mechanical rewrites for every architecture change.
