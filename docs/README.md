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
| [`NUMBERING_GEOMETRY_CONTRACT.md`](NUMBERING_GEOMETRY_CONTRACT.md) | Resolution-independent measure-numbering/system-geometry thresholds and retained morphology pixel operations |
| [`SCRIPT_MANAGEMENT.md`](SCRIPT_MANAGEMENT.md) | Current placement/lifecycle rules for production, tools, experiments, and scratch scripts |
| [`manual_correction_review_package.md`](manual_correction_review_package.md) | Current config-first end-to-end manual-correction review workflow |
| [`ai-workflow/GRAPHIFY.md`](ai-workflow/GRAPHIFY.md) | Graphify query, refresh, retention, and staleness rules |

The root [`README.md`](../README.md), [`AGENTS.md`](../AGENTS.md), and repository `Makefile`
are also current entry points.

## Future / roadmap architecture

| Document | Role |
| --- | --- |
| [`FUTURE_SERVICE_ARCHITECTURE.md`](FUTURE_SERVICE_ARCHITECTURE.md) | **Future/roadmap only**: intended engine responsibility boundary, one-job service-readiness direction, correction flow, and separation from a future external service/control plane |

The future-service document is deliberately separate from current runtime guidance. It must not be
used to infer implemented pipeline behavior. When a future contract becomes implemented, update the
relevant current operating/architecture documentation as part of that implementation change.

## Execution and output guidance

Use `src/pipeline/main.py` through the Makefile instead of old phase-specific orchestration
or task-control documents:

```bash
make run-pipeline CONFIG=configs/dense_full_pipeline.yaml
```

The public/output-profile design records under `docs/refactors/issue226/` through
`docs/refactors/issue229/` remain useful for their scoped contracts. They are not a second
source of truth for detector/MMR architecture. The currently connected review-package, GUI, corrected-rerun, and corrected-final workflow is documented in
`manual_correction_review_package.md`.

## Detector, numbering, and CNN reference

- Current detector and CNN runtime behavior is defined by source, tests, and the active config,
  especially `configs/dense_full_pipeline.yaml` and `PIPELINE_ARCHITECTURE.md`.
- The verified Stage-E CNN was refreshed in Issue #296 / PR #310 to the current-producer,
  candidate-aligned EfficientNet-B0 contract. Older ResNet18 retraining notes are historical.
- Historical CNN training and active-learning results have been distilled into Issue #44;
  exact retired prose remains recoverable from Git history.
- `GT_PREPARATION_POLICY.md` and `BARLINE_MATCHER.md` remain current labeling/evaluation references.
- For MMR/measure-numbering maintenance, start with
  [`refactors/issue94/MMR_CURRENT_STATE.md`](refactors/issue94/MMR_CURRENT_STATE.md), current source/tests,
  and the Issue #94 lineage. [`DEVLOG_MEASURE_NUMBERING.md`](DEVLOG_MEASURE_NUMBERING.md) is now only a
  compact legacy milestone ledger.

## Historical / forensic records

Use `HISTORY_INDEX.md` to locate the relevant lineage before opening old Issue-specific
records. Important decisions and experiment results should be recovered from the relevant
Issue/PR/commit and retained reproduction tooling rather than from old restart prompts,
plans, or execution diaries.

`DEVELOPMENT_LOG.md` and `DEVLOG_MEASURE_NUMBERING.md` are compact historical milestone ledgers,
not active work logs. Their former detailed execution diaries remain recoverable through Git history.

Completed task-control bundles (`Prompt.md`, `Plan.md`, `Implement.md`, dated execution
`Log.md`, and one-off benchmark summaries) are not durable current documentation once their
important results are captured in Issue/PR/commit history. Git history remains available for
archaeology.

The two pre-experiment model-survey PDFs formerly under `docs/model_experiments/` were retired
after content-level audit in Issue #308. They contained exploratory literature/dataset recommendations
rather than accepted project-specific evidence. Durable experiment results remain under
`experiments/models/`, with exact retired survey prose recoverable from Git history.

## Frozen milestones versus current production

`TWO_HOMR_MILESTONE.md` intentionally freezes the accepted Issue #274 / PR #279 comparison
contract, including the CNN checkpoint used for that comparison. It should not be silently
rewritten whenever production later changes.

For **current** production model/config values, use `configs/dense_full_pipeline.yaml`, current
source/tests, and the active architecture document. For example, the production CNN changed
later in Issue #296 / PR #310 while the #274 milestone remains useful historical evidence.

## Maintenance rule

Architecture changes must review the current and future documents according to the boundary being
changed:

1. when production stage ownership, authoritative geometry, coordinate contracts, model/runtime
   ownership, route order, or major process/memory boundaries change, update
   `PIPELINE_ARCHITECTURE.md`;
2. for those current-runtime changes, also review `FUTURE_SERVICE_ARCHITECTURE.md` when the change
   affects assumptions visible at the engine/caller, artifact, correction, lifecycle, safety, or
   resource boundary;
3. when a future engine contract becomes implemented, update the applicable current operating docs
   in the same change instead of leaving the behavior described only as roadmap intent;
4. when final/review/correction semantics change, review both
   `manual_correction_review_package.md` and the future engine-boundary document;
5. update `TWO_HOMR_MILESTONE.md` only when that accepted comparison milestone itself is
   deliberately replaced;
6. check this index, `HISTORY_INDEX.md`, and `DOCUMENTATION_INVENTORY.md` for newly stale guidance;
7. move reusable lessons out of Issue-specific narratives before retiring redundant prose;
8. after stable current architecture docs are settled, refresh Graphify according to
   `ai-workflow/GRAPHIFY.md`.

The PR checklist asks authors to record whether the current and future architecture documents were
reviewed. This is a review trigger, not a reason to duplicate detailed current pipeline internals
into the future document.

Issue-specific forensic notes do not need mechanical rewrites for every architecture change,
but stale files should not remain linked as current operating guidance.
