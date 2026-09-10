# PDFScoreBar Documentation Index

This index separates **current durable guidance** from **historical investigation records**.
When historical material conflicts with current source, tests, config, or canonical architecture,
use the current artifacts first.

## Start here: current durable guidance

| Document | Role |
| --- | --- |
| [`PIPELINE_ARCHITECTURE.md`](PIPELINE_ARCHITECTURE.md) | **Canonical current production architecture**: dense route, stage ownership, coordinate spaces, process/memory boundaries, detector-input provenance |
| [`TWO_HOMR_MILESTONE.md`](TWO_HOMR_MILESTONE.md) | Frozen accepted Issue #274 / PR #279 comparison milestone and reproduction contract |
| [`DOCUMENTATION_INVENTORY.md`](DOCUMENTATION_INVENTORY.md) | Audit classification of durable docs and cleanup/maintenance rules |
| [`HISTORY_INDEX.md`](HISTORY_INDEX.md) | Navigation across major historical Issue/experiment lineages; not a current-state source of truth |
| [`ENVIRONMENTS.md`](ENVIRONMENTS.md) | Maintained runtime/development environments |
| [`BRANCH_POLICY.md`](BRANCH_POLICY.md) | Branch/base/promotion policy |
| [`dev/VALIDATION_POLICY.md`](dev/VALIDATION_POLICY.md) | Validation requirements by change type |
| [`REGRESSION_TEST_WORKFLOW.md`](REGRESSION_TEST_WORKFLOW.md) | Regression-test workflow |
| [`GT_PREPARATION_POLICY.md`](GT_PREPARATION_POLICY.md) | Ground-truth labeling policy |
| [`BARLINE_MATCHER.md`](BARLINE_MATCHER.md) | Barline matching/evaluation contract |
| [`SCRIPT_MANAGEMENT.md`](SCRIPT_MANAGEMENT.md) | Current placement/lifecycle rules for production, tools, experiments, and scratch scripts |
| [`manual_correction_review_package.md`](manual_correction_review_package.md) | Current internal manual-correction review-package handoff |
| [`ai-workflow/GRAPHIFY.md`](ai-workflow/GRAPHIFY.md) | Graphify query, refresh, retention, and staleness rules |

The root [`README.md`](../README.md), [`AGENTS.md`](../AGENTS.md), and repository `Makefile`
are also current entry points.

## Execution and output guidance

Use `src/pipeline/main.py` through the Makefile instead of old phase-specific orchestration
or task-control documents:

```bash
make run-pipeline CONFIG=configs/dense_full_pipeline.yaml
```

The public/output-profile design records under `docs/refactors/issue226/` through
`docs/refactors/issue229/` remain useful for their scoped contracts. They are not a second
source of truth for detector/MMR architecture. The currently connected internal review
package is documented in `manual_correction_review_package.md`.

## Detector, numbering, and CNN reference

- Current detector and CNN runtime behavior is defined by source, tests, and the active config,
  especially `configs/dense_full_pipeline.yaml` and `PIPELINE_ARCHITECTURE.md`.
- The verified Stage-E CNN was refreshed in Issue #296 / PR #310 to the current-producer,
  candidate-aligned EfficientNet-B0 contract. Older ResNet18 retraining notes are historical.
- `GT_PREPARATION_POLICY.md` and `BARLINE_MATCHER.md` remain current labeling/evaluation references.
- `DEVLOG_MEASURE_NUMBERING.md` and `DEVLOG_CNN_TRAINING.md` are historical development logs pending
  separate compression under the documentation-cleanup umbrella; verify all old claims against
  current source before using them.

## Historical / forensic records

Use `HISTORY_INDEX.md` to locate the relevant lineage before opening old Issue-specific
records. Important decisions and experiment results should be recovered from the relevant
Issue/PR/commit and retained reproduction tooling rather than from old restart prompts,
plans, or execution diaries.

Completed task-control bundles (`Prompt.md`, `Plan.md`, `Implement.md`, dated execution
`Log.md`, and one-off benchmark summaries) are not durable current documentation once their
important results are captured in Issue/PR/commit history. Git history remains available for
archaeology.

The two PDFs under `docs/model_experiments/` remain historical artifacts pending content-level
audit. Their neighboring obsolete Markdown planning files are not current guidance.

## Frozen milestones versus current production

`TWO_HOMR_MILESTONE.md` intentionally freezes the accepted Issue #274 / PR #279 comparison
contract, including the CNN checkpoint used for that comparison. It should not be silently
rewritten whenever production later changes.

For **current** production model/config values, use `configs/dense_full_pipeline.yaml`, current
source/tests, and the active architecture document. For example, the production CNN changed
later in Issue #296 / PR #310 while the #274 milestone remains useful historical evidence.

## Maintenance rule

When production stage ownership, authoritative geometry, coordinate contracts, model contracts,
or major process/memory boundaries change:

1. update `PIPELINE_ARCHITECTURE.md` when the architecture contract changes;
2. update `TWO_HOMR_MILESTONE.md` only when that accepted comparison milestone itself is deliberately replaced;
3. check this index, `HISTORY_INDEX.md`, and `DOCUMENTATION_INVENTORY.md` for newly stale guidance;
4. move reusable lessons out of Issue-specific narratives before retiring redundant prose;
5. after stable docs are settled, refresh Graphify according to `ai-workflow/GRAPHIFY.md`.

Issue-specific forensic notes do not need mechanical rewrites for every architecture change,
but stale files should not remain linked as current operating guidance.
