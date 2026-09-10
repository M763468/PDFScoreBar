# Durable Documentation Inventory

Issue #280 established the repository documentation audit against the accepted #274-era production state. This file now records the durable classification and the rule used for continuing audits; it is not intended to enumerate every Issue-specific forensic note individually.

## Classification rule

- **canonical/current:** intended to describe how the repository should be used now.
- **current/reference:** still accurate within a narrower domain, but not the global architecture source.
- **historical:** useful evidence or rationale from a past Issue/experiment; keep only while it adds durable value not already recoverable from a self-contained Issue/PR/commit/source/test/tooling record.
- **retire:** duplicates or contradicts current guidance, consists mainly of completed task-control state, or has had its unique durable content migrated elsewhere; Git history retains the old body.
- **separate cleanup:** implementation/config cleanup that belongs to another existing track rather than this documentation audit.

## Inventory

| Document / area | Role | Classification | Current action |
| --- | --- | --- | --- |
| `README.md` | repository entry | current | point to canonical architecture and durable docs |
| `AGENTS.md` | repository agent constitution | current | keep |
| `docs/README.md` | documentation index | canonical/current | keep current-vs-historical navigation accurate |
| `docs/HISTORY_INDEX.md` | historical lineage navigation | current/reference | point to Issues/PRs/commits and retained contracts without duplicating them |
| `docs/PIPELINE_ARCHITECTURE.md` | production architecture | canonical/current | global architecture source, including detector-input provenance |
| `docs/TWO_HOMR_MILESTONE.md` | accepted #274 architecture/accuracy/performance comparison | frozen milestone | keep as the #274 / PR #279 reproduction record; do not silently rewrite for later production changes |
| `docs/ENVIRONMENTS.md` | execution/runtime guidance | current/reference | keep |
| `docs/BRANCH_POLICY.md` | branch policy | current/reference | keep |
| `docs/dev/VALIDATION_POLICY.md` | validation policy | current/reference | keep |
| `docs/REGRESSION_TEST_WORKFLOW.md` | regression workflow | current/reference | keep |
| `docs/GT_PREPARATION_POLICY.md` | GT policy | current/reference | keep |
| `docs/BARLINE_MATCHER.md` | matching/evaluation rules | current/reference | keep |
| `docs/SCRIPT_MANAGEMENT.md` | script placement/lifecycle policy | current/reference | keep compact; historical move/delete ledger belongs in #45 / PR #184 |
| `docs/manual_correction_review_package.md` | internal review handoff | current/reference | keep |
| `docs/corrected_final_output.md` | corrected-output workflow | scoped/reference | keep; verify against source when modifying output workflow |
| `docs/ai-workflow/GRAPHIFY.md` | Graphify operation | current/reference | keep |
| `.agents/skills/graphify/**` | agent Graphify skill | current/reference | keep |
| `graphify-out/**` durable set | generated navigation graph/wiki/report/manifest | current only when provenance is fresh | refresh after stable architecture changes |
| `docs/PIPELINE_DATAFLOW.md`, `docs/FULL_PIPELINE_README.md`, `docs/best_configuration_summary.md` | obsolete current-guide narratives | retired | removed in earlier cleanup; recover through Git history |
| `docs/CNN_RETRAINING_GUIDE.md` | #44-era FP active-learning / ResNet18 plan | retire | historical core moved to #44; current verified CNN is #296 / PR #310 plus source/config/tests |
| `docs/performance_comparison.md` | dated Phase 1–6 performance narrative | retire | benchmark ledger distilled into #78; later performance lineage is in #281–#294 |
| `docs/DEVELOPMENT_LOG.md` | large pre-/early-Issue development diary | historical | pending section-level compression under #308 |
| `docs/DEVLOG_CNN_TRAINING.md` | CNN development diary | historical | pending compression now that #296 / PR #310 defines the current verified CNN contract |
| `docs/DEVLOG_MEASURE_NUMBERING.md` | numbering development diary | historical | pending compression; later Issue/refactor records carry current/scoped contracts |
| top-level `docs/ISSUE*.md` | Issue forensic/reproduction records | historical | keep only while unique durable evidence or an active reproduction contract remains; otherwise distill and retire |
| `docs/refactors/issue*/**` | scoped design/history | historical/scoped | audit individually; keep current scoped contracts, retire temporary handoff/task-control bundles after distillation |
| `docs/long-horizon-tasks/**` | completed Prompt/Plan/Log/Benchmarks task bundles | retire | important #25/#60/#70 results moved to their Issue threads; remove active-looking task-control copies |
| `docs/notes/**`, `docs/future/**` | notes/plans | historical/planning | retire when superseded and decisions are recoverable elsewhere |
| `docs/model_experiments/*.md` | old model survey/future plans | retire when superseded | active-looking plan text is not a current model roadmap; preserve accepted experiment evidence elsewhere |
| `docs/model_experiments/*.pdf` | historical model survey artifacts | historical / audit pending | do not delete without content-level audit |
| `docs/fp_reduction/**` | duplicate Dec-2025 FP-reduction narratives | retired | removed after reusable safety guidance moved to `docs/ai-workflow/LESSONS.md`; tooling remains under `experiments/fp_reduction/` |
| `configs/dense_full_pipeline.yaml` | canonical dense production config | current runtime input, not prose | authoritative for current selected model/threshold/runtime values |
| `configs/detector_profiles/stage_e_verified_homr.json` | pinned HOMR profile provenance | canonical machine-readable reference | keep |

## Historical navigation and retirement rule

Historical records remain evidence, but agents should not scan or preload them indiscriminately. Use `docs/HISTORY_INDEX.md` to select the lineage relevant to the active Issue/PR, then open only the accepted milestone or forensic record needed for that task.

Historical ephemeral state is never authoritative without revalidation. Examples include branch/`develop` HEADs, worktree/container state, local artifact paths, current blockers, unfinished PASS/FAIL status, and `next step` instructions.

A historical document can be retired from the active tree when all of the following are true:

1. accepted/rejected decisions and important experiment provenance are recoverable from the relevant Issue/PR/commit/source/test or retained experiment tooling;
2. reusable cross-Issue rules have been moved to a current generic guide or architecture contract;
3. the file is not the sole current operating/reproduction contract;
4. surviving repository links are updated in the same cleanup change.

Completed `Prompt.md`, `Plan.md`, handoff, and execution-diary files should normally be retired once this gate is met. Git history is sufficient for recovering their exact prose.

For important experiments, prefer a recoverable chain of

`hypothesis -> script/command -> commit -> fixed provenance -> result -> disposition`

over retaining chat transcripts or copying the same result into another summary document. Invalidated or superseded results must stay labelled as such.

## Frozen #274 milestone versus current production

`docs/TWO_HOMR_MILESTONE.md` deliberately preserves the accepted #274 / PR #279 comparison contract. That comparison used the Issue #44 / PR #57 Iter 7 final-rescue CNN artifact at:

```text
logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth
```

`docs/ISSUE44_ITER7_FINAL_REPORT.md` remains the reconstruction procedure for **that historical comparison checkpoint**. This does not mean Iter 7 is the current production CNN.

The verified dense production route was later refreshed in Issue #296 / PR #310 to the current-producer candidate-aligned EfficientNet-B0 D27 checkpoint and validation-selected threshold. Current source/tests and `configs/dense_full_pipeline.yaml` are authoritative for the active production model contract.

Keeping these two layers distinct lets the project reproduce the accepted #274 comparison without turning a frozen milestone into competing current guidance.

## Cleanup history

The documentation-cleanup lineage progressively moved durable information out of redundant narratives before deleting them:

- #300 / PR #301: added historical navigation and active-context retention guidance;
- #302 / PR #305: retired the first redundant historical-doc batch and relocated a rerun CSV into a config-owned fixture location;
- #306 / PR #307: distilled #19/#46/FP-reduction conclusions and reusable safety guidance;
- #308 / PR #309: moved current detector-input provenance/NMS contracts into canonical architecture and retired duplicate #120/#163/#245 narratives;
- later #308 PRs continue the same rule without creating a new Issue for each small docs-only slice.

## Separate implementation cleanup

Documentation cleanup must not silently change production runtime/config semantics. Legacy environment keys, compatibility fallbacks, model behavior, matcher semantics, or similar implementation concerns belong to their existing implementation Issues when they require code changes.

Graphify refresh requires a local environment with `graphifyy` installed. That operational prerequisite is not a reason to preserve stale prose in the active docs tree.

## Future audit rule

A durable document should answer one of three questions clearly: **how the system works now**, **how to operate it now**, or **what durable evidence from a past investigation still needs a local repository contract**. If it mixes those roles, split, distill, or label it.

For historical investigations, prefer a compact navigation/index layer plus original Issue/PR/commit evidence over a second full narrative copy. This keeps historical knowledge recoverable without making every past investigation active context.
