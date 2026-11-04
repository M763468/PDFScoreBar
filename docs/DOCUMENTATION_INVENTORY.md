# Durable Documentation Inventory

[日本語](DOCUMENTATION_INVENTORY.ja.md)

Issue #280 established the repository documentation audit against the accepted #274-era production state. This file records documentation history and maintenance rules. It is not the entrypoint for the minimum runtime selection; use `MINIMAL_MAINLINE_SURFACE.md` for that question.

## Classification rule

- **canonical/current:** intended to describe how the repository should be used now.
- **current/reference:** still accurate within a narrower domain, but not the global architecture source.
- **future/roadmap:** durable intended architecture or responsibility boundary that is explicitly not a current-runtime source of truth.
- **historical:** useful evidence or rationale from a past Issue/experiment; keep only while it adds durable value not already recoverable from a self-contained Issue/PR/commit/source/test/tooling record.
- **retire:** duplicates or contradicts current guidance, consists mainly of completed task-control state, or has had its unique durable content migrated elsewhere; Git history retains the old body.
- **separate cleanup:** implementation/config cleanup that belongs to another existing track rather than this documentation audit.

## Inventory

| Document / area | Role | Classification | Current action |
| --- | --- | --- | --- |
| `README.md` | repository entry | current | point to canonical architecture and durable docs |
| `AGENTS.md` | repository agent constitution | current | keep |
| `docs/README.md` | documentation index | canonical/current | keep current-vs-historical navigation accurate |
| `docs/REPOSITORY_SURFACE_INVENTORY.md` | #230 development-repository audit and #100 input | historical/reference | retain for lineage; its old present-tense paths do not define the current extraction set |
| `docs/MINIMAL_MAINLINE_SURFACE.md` / `.json` | Issue #100 minimum executable selection and machine-readable drift definition | canonical/current for extraction | use as the single explanation and exact file list for the distributed runtime subset; per-candidate #409 acceptance evidence moved to `docs/releases/issue409/ACCEPTANCE_HISTORY.md` (#484) |
| `docs/HISTORY_INDEX.md` | historical lineage navigation | current/reference | point to Issues/PRs/commits and retained contracts without duplicating them |
| `docs/architecture/PIPELINE_ARCHITECTURE.md` / `.ja.md` | reader-oriented current production architecture | canonical/current (English original); Japanese reviewed | pipeline components, data flow, execution order and module responsibilities; precise contracts moved to reference |
| `docs/architecture/PIPELINE_ARCHITECTURE_REFERENCE.md` / `.ja.md` | production implementation reference | current/reference (English original); Japanese reviewed | detailed detector/numbering contracts and historical compatibility rationale; read from the architecture overview |
| `docs/architecture/FUTURE_SERVICE_ARCHITECTURE.md` | future engine/service responsibility boundary | future/roadmap | keep explicitly separate from current runtime; update when long-term engine/caller/correction/service-boundary intent changes materially |
| `docs/contracts/ENGINE_JOB_CONTRACT.md` / `.ja.md` | versioned one-job engine caller contract | current/reference (English original); Japanese reviewed | normative v1 serialized boundary and compatibility/correction semantics; `PipelineJobExecutor` is the reference adapter, while direct v1 `CorrectionSet` execution remains outside that adapter |
| `docs/contracts/ENGINE_JOB_LIFECYCLE.md` / `.ja.md` | #337 one-job lifecycle contract | current/reference (English original); Japanese reviewed | v1 lifecycle requirements and reusable control helpers; #337 audit is historical, while cancellation/deadline integration remains pending |
| `docs/contracts/ENGINE_INPUT_SAFETY.md` / `.ja.md` | #338 untrusted-PDF safety contract | current/reference (English original); Japanese reviewed | implemented bounded preflight and safe errors; hard quotas/process-tree/network isolation remain future worker requirements |
| `docs/contracts/ENGINE_TELEMETRY.md` / `.ja.md` | #339 structured progress/resource telemetry contract | current/reference (English original); Japanese reviewed | preserve the v1 stage/status vocabulary while defining additive elapsed/detail fields, page progress, compact summaries, and opt-in process/GPU sampling |
| `docs/contracts/ENGINE_SERVICE_READINESS.md` / `.ja.md` | #340 reference executor and compatibility gates | current/reference (English original); Japanese reviewed | supported succeeded/failed publication boundary; direct v1 corrections, lifecycle controls and public-service isolation remain outside current support |
| `docs/history/TWO_HOMR_MILESTONE.md` | accepted #274 architecture/accuracy/performance comparison | frozen milestone | keep as the #274 / PR #279 reproduction record; do not silently rewrite for later production changes |
| `docs/dev/ENVIRONMENTS.md` | execution/runtime guidance | current/reference | keep |
| `docs/dev/BRANCH_POLICY.md` | branch policy | current/reference | keep |
| `docs/dev/VALIDATION_POLICY.md` | validation policy | current/reference | keep |
| `docs/dev/REGRESSION_TEST_WORKFLOW.md` | regression workflow | current/reference | keep |
| `docs/dev/GT_PREPARATION_POLICY.md` | GT policy | current/reference | keep |
| `docs/contracts/BARLINE_MATCHER.md` | matching/evaluation rules | current/reference | keep |
| `docs/dev/SCRIPT_MANAGEMENT.md` | script placement/lifecycle policy | current/reference | keep compact; historical move/delete ledger belongs in #45 / PR #184 |
| `docs/dev/manual_correction_review_package.md` | internal review handoff | current/reference | keep |
| `docs/contracts/corrected_final_output.md` | corrected-output workflow | scoped/reference | keep; verify against source when modifying output workflow |
| `docs/ai-workflow/GRAPHIFY.md` | Graphify operation | current/reference | keep |
| `.agents/skills/graphify/**` | agent Graphify skill | current/reference | keep |
| `graphify-out/**` durable set | generated navigation graph/wiki/report/manifest | current only when provenance is fresh | refresh after stable architecture changes |
| `docs/PIPELINE_DATAFLOW.md`, `docs/FULL_PIPELINE_README.md`, `docs/best_configuration_summary.md` | obsolete current-guide narratives | retired | removed in earlier cleanup; recover through Git history |
| `docs/CNN_RETRAINING_GUIDE.md` | #44-era FP active-learning / ResNet18 plan | retired | historical core moved to #44; current verified CNN is #296 / PR #310 plus source/config/tests |
| `docs/performance_comparison.md` | dated Phase 1–6 performance narrative | retired | benchmark ledger distilled into #78; later performance lineage is in #281–#294 |
| `docs/history/DEVELOPMENT_LOG.md` | project-origin / pre-Issue history | historical/reference | compressed to a short legacy milestone ledger; exact old execution diary is Git-history only |
| `docs/DEVLOG_CNN_TRAINING.md` | CNN development diary | retired | durable early experiment ledger moved to Issue #44; current verified CNN is #296 / PR #310 plus source/config/tests |
| `docs/history/DEVLOG_MEASURE_NUMBERING.md` | early numbering/MMR development history | historical/reference | compressed to a short legacy milestone ledger; current/scoped MMR analysis is `docs/refactors/issue94/MMR_CURRENT_STATE.md` and Issue #94 |
| `docs/history/ISSUE*.md` (top-level before #492) | Issue forensic/reproduction records | historical | keep only while unique durable evidence or an active reproduction contract remains; otherwise distill and retire |
| `docs/refactors/issue*/**` | scoped design/history | historical/scoped | audit individually; keep current scoped contracts, retire temporary handoff/task-control bundles after distillation |
| `docs/long-horizon-tasks/**` | completed Prompt/Plan/Log/Benchmarks task bundles | retired | important #25/#60/#70 results moved to their Issue threads; active-looking task-control copies removed |
| `docs/notes/**`, `docs/future/**` | notes/plans | historical/planning | retire when superseded and decisions are recoverable elsewhere |
| `docs/GOALS.md` | pre-#446 project goals and "current" direction | retired | the owner decided in #446 that it no longer states current project direction; removed in #488 without translation; recover through Git history |
| `docs/model_experiments/*.md` | old model survey/future plans | retired when superseded | active-looking plan text is not a current model roadmap; accepted experiment evidence remains elsewhere |
| `docs/model_experiments/*.pdf` | pre-experiment literature/dataset/model surveys | retired | content-level audit under #308 found no unique project-specific operating/reproduction contract; project-specific experiment evidence remains under `experiments/models/`, and exact old survey prose remains in Git history |
| `docs/fp_reduction/**` | duplicate Dec-2025 FP-reduction narratives | retired | removed after reusable safety guidance moved to `docs/ai-workflow/LESSONS.md`; tooling remains under `experiments/fp_reduction/` |
| `configs/dense_full_pipeline.yaml` | canonical dense production config | current runtime input, not prose | authoritative for current selected model/threshold/runtime values |
| `configs/detector_profiles/stage_e_verified_homr.json` | pinned HOMR profile provenance | canonical machine-readable reference | keep |

## Bilingual coverage and translation scope

This inventory classifies document intent and observed language; it does **not** certify
that every claim matches current source/tests. For translation placement, source revisions,
review and drift handling, use the [language policy](DOCUMENTATION_LANGUAGE_POLICY.md)
([日本語](DOCUMENTATION_LANGUAGE_POLICY.ja.md)). This extends the existing audit instead
of replacing its history or creating a competing runtime/distribution manifest.

Language labels describe explanatory prose: **EN** = English, **JA** = Japanese,
**mixed** = substantial prose in both languages. Code, identifiers, Japanese UI examples,
and translated status labels alone do not establish a complete counterpart.
At the initial #452 audit, none of the documents in the table below had a separate,
reviewed full counterpart; that is the historical audit result, not current coverage.
Current counterpart states are recorded per row below. **JA needed** and **EN needed**
mean untranslated; **split/review** means the mixed original must first be reviewed as
a whole. A draft counterpart is not certified as reviewed or technically synchronized.

Priority expresses reading dependencies, not a requirement to finish all rows in one PR:
**P1** = entry points and core architecture/engine/model/operation/validation;
**P2** = supporting contracts and developer/agent guidance;
**P3** = future direction or optional references, translated when needed.
`current/reference` describes intended scope, with technical currency still to be checked
when translating. Historical and scoped records follow the exclusions below.

| Document | Intended role / authority | Language | Counterpart action | Priority |
| --- | --- | --- | --- | --- |
| [../README.md](../README.md) | canonical/current | EN | [JA reviewed](../README.ja.md) | P1 |
| [../AGENTS.md](../AGENTS.md) | canonical/current; agent instructions | EN | not required (agent-only) | N/A |
| [README.md](README.md) | canonical/current | EN | [JA reviewed](README.ja.md) | P1 |
| [DOCUMENTATION_INVENTORY.md](DOCUMENTATION_INVENTORY.md) | canonical/current | EN | [JA reviewed](DOCUMENTATION_INVENTORY.ja.md); #488 | P1 |
| [DOCUMENTATION_LANGUAGE_POLICY.md](DOCUMENTATION_LANGUAGE_POLICY.md) | current/reference; translation and documentation maintenance rules | EN | [JA reviewed](DOCUMENTATION_LANGUAGE_POLICY.ja.md); #489 | P1 |
| [PIPELINE_ARCHITECTURE.md](architecture/PIPELINE_ARCHITECTURE.md) | canonical/current overview | EN | [JA full reviewed](architecture/PIPELINE_ARCHITECTURE.ja.md); #456 review completed | P1 |
| [PIPELINE_ARCHITECTURE_REFERENCE.md](architecture/PIPELINE_ARCHITECTURE_REFERENCE.md) | current implementation-level reference | EN | [JA full reviewed](architecture/PIPELINE_ARCHITECTURE_REFERENCE.ja.md); #456 review completed | P1 |
| [ENGINE_JOB_CONTRACT.md](contracts/ENGINE_JOB_CONTRACT.md) | current/reference | EN / [JA](contracts/ENGINE_JOB_CONTRACT.ja.md) | reviewed; #463 implementation/meaning review | P1 |
| [ENGINE_JOB_LIFECYCLE.md](contracts/ENGINE_JOB_LIFECYCLE.md) | current/reference | EN / [JA](contracts/ENGINE_JOB_LIFECYCLE.ja.md) | reviewed; #463 implementation/meaning review | P1 |
| [ENGINE_INPUT_SAFETY.md](contracts/ENGINE_INPUT_SAFETY.md) | current/reference | EN / [JA](contracts/ENGINE_INPUT_SAFETY.ja.md) | reviewed; #463 implementation/meaning review | P1 |
| [ENGINE_TELEMETRY.md](contracts/ENGINE_TELEMETRY.md) | current/reference | EN / [JA](contracts/ENGINE_TELEMETRY.ja.md) | reviewed; #463 implementation/meaning review | P1 |
| [ENGINE_SERVICE_READINESS.md](contracts/ENGINE_SERVICE_READINESS.md) | current/reference | EN / [JA](contracts/ENGINE_SERVICE_READINESS.ja.md) | reviewed; #463 implementation/meaning review | P1 |
| [MODEL_ARTIFACT_CONTRACT.md](contracts/MODEL_ARTIFACT_CONTRACT.md) | current/reference | EN / [JA](contracts/MODEL_ARTIFACT_CONTRACT.ja.md) | reviewed | P1 |
| [MODEL_ARTIFACTS.md](dev/MODEL_ARTIFACTS.md) | current/reference | EN / [JA](dev/MODEL_ARTIFACTS.ja.md) | reviewed | P1 |
| [ENVIRONMENTS.md](dev/ENVIRONMENTS.md) | current/reference | EN / [JA](dev/ENVIRONMENTS.ja.md) | reviewed; #465 translation and meaning review | P1 |
| [USER_GUIDE.md](USER_GUIDE.md) | current/reference | EN | [JA reviewed](USER_GUIDE.ja.md) | P1 |
| [manual_correction_review_package.md](dev/manual_correction_review_package.md) | current/reference | EN | [JA reviewed](dev/manual_correction_review_package.ja.md) | P1 |
| [BRANCH_POLICY.md](dev/BRANCH_POLICY.md) | current/reference | EN / [JA](dev/BRANCH_POLICY.ja.md) | reviewed; #465 translation and meaning review | P1 |
| [dev/VALIDATION_POLICY.md](dev/VALIDATION_POLICY.md) | current/reference | EN / [JA](dev/VALIDATION_POLICY.ja.md) | reviewed; #465 translation and meaning review | P1 |
| [dev/LOCAL_VALIDATION.md](dev/LOCAL_VALIDATION.md) | current/reference | EN / [JA](dev/LOCAL_VALIDATION.ja.md) | reviewed; #465 translation and meaning review | P1 |
| [USER_CORRECTION_BOUNDARY.md](contracts/USER_CORRECTION_BOUNDARY.md) | current/reference | EN | [JA reviewed](contracts/USER_CORRECTION_BOUNDARY.ja.md) | P2 |
| [corrected_final_output.md](contracts/corrected_final_output.md) | current/reference | EN | [JA reviewed](contracts/corrected_final_output.ja.md) | P2 |
| [MOVEMENT_BOUNDARY_CONTRACT.md](contracts/MOVEMENT_BOUNDARY_CONTRACT.md) | current/reference | EN | [JA reviewed](contracts/MOVEMENT_BOUNDARY_CONTRACT.ja.md); #477 currency review | P2 |
| [NUMBERING_GEOMETRY_CONTRACT.md](contracts/NUMBERING_GEOMETRY_CONTRACT.md) | current/reference | EN | [JA reviewed](contracts/NUMBERING_GEOMETRY_CONTRACT.ja.md); #477 currency review | P2 |
| [GT_PREPARATION_POLICY.md](dev/GT_PREPARATION_POLICY.md) | current/reference | EN | [JA reviewed](dev/GT_PREPARATION_POLICY.ja.md); #475 currency review | P2 |
| [BARLINE_MATCHER.md](contracts/BARLINE_MATCHER.md) | current/reference | EN | [JA reviewed](contracts/BARLINE_MATCHER.ja.md); #475 currency review | P2 |
| [MAKEFILE_SURFACE.md](dev/MAKEFILE_SURFACE.md) | current/reference | EN / [JA](dev/MAKEFILE_SURFACE.ja.md) | reviewed; #465 translation and meaning review | P2 |
| [REGRESSION_TEST_WORKFLOW.md](dev/REGRESSION_TEST_WORKFLOW.md) | current/reference | EN / [JA](dev/REGRESSION_TEST_WORKFLOW.ja.md) | reviewed; #465 translation and meaning review | P2 |
| [dev/MMR_RAPIDOCR_PROVIDER.md](dev/MMR_RAPIDOCR_PROVIDER.md) | current/reference | EN | [JA reviewed](dev/MMR_RAPIDOCR_PROVIDER.ja.md); #477 currency review | P2 |
| [dev/REVIEW_ACCEPTANCE.md](dev/REVIEW_ACCEPTANCE.md) | current/reference | EN | [JA reviewed](dev/REVIEW_ACCEPTANCE.ja.md); #480 currency review | P2 |
| [dev/PR_SLICE_VALIDATION.md](dev/PR_SLICE_VALIDATION.md) | current/reference | EN | [JA reviewed](dev/PR_SLICE_VALIDATION.ja.md); #480 currency review | P2 |
| [dev/codex_local_automation.md](dev/codex_local_automation.md) | current/reference | EN | [JA reviewed](dev/codex_local_automation.ja.md); #480 currency review | P2 |
| [dev/local_worktree_data.md](dev/local_worktree_data.md) | current/reference | EN | [JA reviewed](dev/local_worktree_data.ja.md); #480 currency review | P2 |
| [agent-skills/EVAL.md](agent-skills/EVAL.md) | current/reference | EN | [JA reviewed](agent-skills/EVAL.ja.md); #482 | P2 |
| [dev/CONFIGURATION_REFERENCE.md](dev/CONFIGURATION_REFERENCE.md) | current/reference; canonical config keys and values guarded in PR CI by `tests/test_configuration_reference.py` | EN | [JA reviewed](dev/CONFIGURATION_REFERENCE.ja.md); #486 | P2 |
| [dev/EXPERIMENT_MODEL_SELECTION.md](dev/EXPERIMENT_MODEL_SELECTION.md) | current/reference | JA | [EN reviewed](dev/EXPERIMENT_MODEL_SELECTION.en.md); #475 | P1 |
| [SCRIPT_MANAGEMENT.md](dev/SCRIPT_MANAGEMENT.md) | current/reference | JA (designated original, #480) | [EN reviewed](dev/SCRIPT_MANAGEMENT.en.md) | P2 |
| [ai-workflow/README.md](ai-workflow/README.md) | current/reference | EN | [JA reviewed](ai-workflow/README.ja.md); #482 | P2 |
| [ai-workflow/WORKFLOW.md](ai-workflow/WORKFLOW.md) | current/reference | EN | [JA reviewed](ai-workflow/WORKFLOW.ja.md); #482 | P2 |
| [ai-workflow/GRAPHIFY.md](ai-workflow/GRAPHIFY.md) | current/reference | EN | [JA reviewed](ai-workflow/GRAPHIFY.ja.md); #482 | P2 |
| [ai-workflow/CODEX_GEMINI_COLLAB.md](ai-workflow/CODEX_GEMINI_COLLAB.md) | current/reference | EN | [JA reviewed](ai-workflow/CODEX_GEMINI_COLLAB.ja.md); #482 | P2 |
| [ai-workflow/LABELS.md](ai-workflow/LABELS.md) | current/reference | EN | [JA reviewed](ai-workflow/LABELS.ja.md); #482 | P2 |
| [ai-workflow/PROMPTS.md](ai-workflow/PROMPTS.md) | optional/reference | JA | EN needed | P3 |
| [FUTURE_SERVICE_ARCHITECTURE.md](architecture/FUTURE_SERVICE_ARCHITECTURE.md) | future/roadmap | EN | JA needed; deferred until #449 resumes (#484) | P3 |
| [MINIMAL_MAINLINE_SURFACE.md](MINIMAL_MAINLINE_SURFACE.md) | current extraction reference; frozen evidence moved to `releases/issue409/` | EN | [JA reviewed](MINIMAL_MAINLINE_SURFACE.ja.md); #484 | P2 |
| [HISTORY_INDEX.md](HISTORY_INDEX.md) | history navigation / retention rules | EN | [JA reviewed](HISTORY_INDEX.ja.md); #484 | P2 |
| [ai-workflow/LESSONS.md](ai-workflow/LESSONS.md) | historical heuristics; revalidate before use | EN | selective; no bulk translation | P3 |
| [ai-workflow/RUNNER_DESIGN.md](ai-workflow/RUNNER_DESIGN.md) | deprecated runner proposal (#482) | EN | not translated (deprecated) | N/A |

### Scope boundaries and review queue

- **Agent instructions:** keep `AGENTS.md` as the single English operational instruction
  source; it is excluded from the translation backlog. Reconsider a human reading aid only
  if a concrete future need arises. User/developer guide translation remains in scope.

- **Scoped contracts are not automatically obsolete.** `ISSUE120_EVALUATION_CONTRACT.md`,
  `ISSUE120_ARTIFACT_RETENTION.md`, `ISSUE158_DENSE_ROUTE_NAMING.md`, and
  `ISSUE162_PIPELINE_LOGGING_TAXONOMY.md` are English Issue-scoped references. Verify their
  current consumers and translate needed contracts selectively, preserving scope.
- **Frozen history:** `TWO_HOMR_MILESTONE.md`, `REPOSITORY_SURFACE_INVENTORY.md`,
  `DEVELOPMENT_LOG.md`, `DEVLOG_MEASURE_NUMBERING.md`, `ISSUE333_MOVEMENT_BOUNDARY_INVESTIGATION.md`,
  and `ISSUE363_RUNTIME_DEPENDENCY_REVIEW.md` are English historical/reference records;
  `ISSUE44_ITER7_FINAL_REPORT.md` is Japanese. No blanket translation is required.
- **Issue designs and experiments:** `refactors/**`, `history/ISSUE441_*.md`, and
  `releases/issue410/**` need individual authority/lifecycle review, not automatic promotion
  to current design. The #441 and #410 records are Japanese-centered; `refactors/**`
  is predominantly English with mixed Japanese records (notably #94 and the rebuild plan).
  Read through the history index only when the active task needs that evidence.
  Some of these records, notably `history/ISSUE441_*.md`, contain machine-specific absolute
  paths as part of their recorded commands. They are historical evidence, not reusable
  instructions; #488 kept them unchanged instead of rewriting the evidence.
- **Known review needs:** #226–#229 documents describe their own eventual migration into
  standing user/operation docs. Check unique surviving contracts before any retirement.
  `ai-workflow/RUNNER_DESIGN.md` required task bundles under `docs/refactors/`, which
  conflicts with current `AGENTS.md` / `ai-workflow/WORKFLOW.md`; #482 marked it deprecated
  and it is not translated. These are review items, not runtime fixes.
- **Archived/deprecated:** `archive/**`, `ai-workflow/AI_AGENT_STRATEGY_2026.md`, and
  `ai-workflow/LONG_HORIZON_WORKFLOW.md` remain historical pointers, not translation gates.
  `ai-workflow/templates/task/**` are optional English templates, not mandatory task setup.
- **Machine-readable and generated:** JSON/YAML contracts, examples, model manifests,
  configs, and `graphify-out/**` are not prose translation targets. Preserve keys, paths,
  hashes and schema values. Translate their explanatory docs; never create localized
  machine contracts or silently expand the distribution selection.
- **Adjacent documentation:** data, tools, experiments, skills and model-specific READMEs
  outside `docs/` are not exhaustively inventoried here. Audit the ones reached by a
  selected current guide when translating that guide. Their absence here is not a claim
  that they are obsolete or bilingual.

Under #446, the translation batches #452–#486 covered the P1 rows and the P2 rows marked
reviewed above, in small independently reviewed units. Rows still marked **JA needed**,
**EN needed**, deferred or not translated are intentional; translate them when a concrete
need arises. #488 decided not to relocate documents into new directories: the English and
Japanese indexes reach every current document, while moving files would change existing
links, tool references and the distribution manifest without a demonstrated reader benefit.
Whether new design layers are needed is reviewed separately (#489).
#492 re-evaluated that decision because indexes alone did not make the GitHub `docs/`
listing readable, and moved role groups as recorded in the next section. The #488 record is
kept as the decision at that time.

## Directory layout and #492 reorganization

Before #492 the `docs/` root held 66 Markdown files (plus the manifest JSON) that mixed
entry points, current architecture, engine/model contracts, developer procedures, frozen
Issue records and legacy ledgers; `docs/**` held 160 Markdown files counting each language
separately (`develop` at `c70c5f6d`). #492 moved 53 root Markdown files into role directories
with `git mv`, keeping each original with its counterparts. The root now holds 13 Markdown
files plus the manifest JSON. The moves neither added nor removed files; the `docs/**` total
became 165 only because #459 / PR #493 added five records under `performance/`. Moving a
file does not change its classification above: the future architecture stays a roadmap, and
Issue-scoped contracts under `history/` keep their scoped authority.

| Location | Role | Files moved or kept by #492 |
| --- | --- | --- |
| `docs/` root | entry, navigation, inventory and distribution contract | kept: `README`, `USER_GUIDE`, `MINIMAL_MAINLINE_SURFACE` (`.md` / `.ja.md` / `.json`), `DOCUMENTATION_INVENTORY`, `DOCUMENTATION_LANGUAGE_POLICY`, `HISTORY_INDEX`, `REPOSITORY_SURFACE_INVENTORY.md` |
| `architecture/` | current architecture overview and reference; explicitly future architecture | `PIPELINE_ARCHITECTURE`, `PIPELINE_ARCHITECTURE_REFERENCE`, `FUTURE_SERVICE_ARCHITECTURE.md` |
| `contracts/` | current engine, model, output, numbering, correction-boundary and matcher contracts | `ENGINE_JOB_CONTRACT`, `ENGINE_JOB_LIFECYCLE`, `ENGINE_INPUT_SAFETY`, `ENGINE_TELEMETRY`, `ENGINE_SERVICE_READINESS`, `MODEL_ARTIFACT_CONTRACT`, `corrected_final_output`, `NUMBERING_GEOMETRY_CONTRACT`, `MOVEMENT_BOUNDARY_CONTRACT`, `USER_CORRECTION_BOUNDARY`, `BARLINE_MATCHER` |
| `dev/` (existing) | developer and operator procedures and policies | added `BRANCH_POLICY`, `ENVIRONMENTS`, `MAKEFILE_SURFACE`, `REGRESSION_TEST_WORKFLOW`, `SCRIPT_MANAGEMENT` (`.md` / `.en.md`), `GT_PREPARATION_POLICY`, `MODEL_ARTIFACTS`, `manual_correction_review_package` |
| `history/` | frozen Issue-scoped records and legacy ledgers | `ISSUE44_ITER7_FINAL_REPORT.md`, `ISSUE120_EVALUATION_CONTRACT.md`, `ISSUE120_ARTIFACT_RETENTION.md`, `ISSUE158_DENSE_ROUTE_NAMING.md`, `ISSUE162_PIPELINE_LOGGING_TAXONOMY.md`, `ISSUE333_MOVEMENT_BOUNDARY_INVESTIGATION.md`, `ISSUE363_RUNTIME_DEPENDENCY_REVIEW.md`, `DEVELOPMENT_LOG.md`, `DEVLOG_MEASURE_NUMBERING.md`, `TWO_HOMR_MILESTONE.md` |
| `ai-workflow/`, `agent-skills/`, `performance/`, `refactors/`, `releases/`, `archive/` | existing areas | unchanged |

Unless a single file is named, each name covers its `.md` / `.ja.md` pair. The old path of
every moved file is `docs/<name>`; the new path is `docs/<location>/<name>`.

**Kept at the root.** `README` is the documentation entry. `USER_GUIDE` and
`MINIMAL_MAINLINE_SURFACE` (including the JSON read by `tools/check_repository_surface.py`,
the distribution tools and their tests) are distribution entries and contracts.
`DOCUMENTATION_INVENTORY`, `DOCUMENTATION_LANGUAGE_POLICY` and `HISTORY_INDEX` are the
navigation and maintenance layer that `AGENTS.md` and the indexes point to.
`REPOSITORY_SURFACE_INVENTORY.md` is a repository-wide audit consumed by the manifest's
`reference_checks`; it is not a `docs/history/` record of one Issue.

**References updated with the move.** All relative Markdown links and fragments; `docs/...`
path mentions in tracked Markdown, `AGENTS.md`, `.gemini/GEMINI.md`, the PR template, the
Graphify skill, `data/README.md`, `scripts/docker_container_preflight.sh`,
`tools/issue120/inventory_tracked_artifacts.py`; the engine-contract entries in
`documentation_patterns` and the advisory `documentation_audiences` in `MINIMAL_MAINLINE_SURFACE.json`;
and the tests that name moved files. Apart from this inventory, the language policy and the
documentation guide, originals changed only in link paths; their
counterparts received the same path changes and refreshed `same PR` SHA-256 identities.
No runtime, distribution selection, or translation state changed.

**Not updated.** Tracked `graphify-out/**` is generated output and still names old paths
until its next refresh under `ai-workflow/GRAPHIFY.md`. Past Issue/PR bodies and external
links to `blob/<branch>/docs/<name>` no longer resolve on `develop`; commit-pinned links
still resolve. Use this table to find the new location; old bodies are not rewritten.

**Follow-up (#496).** The #441 Markdown records and #160 naming audit moved from `dev/` to `history/`; #441 evidence remains at `dev/issue441/evidence/` to preserve recorded output paths. See the [placement audit](history/ISSUE496_PLACEMENT_AUDIT.md). Existing `performance/` and `refactors/` retain their purpose-based roles.

## Historical navigation and retirement rule

Historical records remain evidence, but agents should not scan or preload them indiscriminately. Use `docs/HISTORY_INDEX.md` to select the lineage relevant to the active Issue/PR, then open only the accepted milestone or forensic record needed for that task.

Historical ephemeral state is never authoritative without revalidation. Examples include branch/`develop` HEADs, worktree/container state, local artifact paths, current blockers, unfinished PASS/FAIL status, and `next step` instructions.

A historical document can be retired from the active tree when all of the following are true:

1. accepted/rejected decisions and important experiment provenance are recoverable from the relevant Issue/PR/commit/source/test or retained experiment tooling;
2. reusable cross-Issue rules have been moved to a current generic guide or architecture contract;
3. the file is not the sole current operating/reproduction contract;
4. surviving repository links are updated in the same cleanup change.

Completed `Prompt.md`, `Plan.md`, handoff, and execution-diary files should normally be retired once this gate is met. When a filename still serves as useful historical navigation, replacing a large diary with a compact, explicitly historical ledger is preferred to preserving stale run-by-run state.

For important experiments, prefer a recoverable chain of

`hypothesis -> script/command -> commit -> fixed provenance -> result -> disposition`

over retaining chat transcripts or copying the same result into another summary document. Invalidated or superseded results must stay labelled as such.

## Frozen #274 milestone versus current production

`docs/history/TWO_HOMR_MILESTONE.md` deliberately preserves the accepted #274 / PR #279 comparison contract. That comparison used the Issue #44 / PR #57 Iter 7 final-rescue CNN artifact at:

```text
logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth
```

`docs/history/ISSUE44_ITER7_FINAL_REPORT.md` remains the reconstruction procedure for **that historical comparison checkpoint**. This does not mean Iter 7 is the current production CNN.

The verified dense production route was later refreshed in Issue #296 / PR #310 to the current-producer candidate-aligned EfficientNet-B0 D27 checkpoint and validation-selected threshold. Current source/tests and `configs/dense_full_pipeline.yaml` are authoritative for the active production model contract.

Keeping these two layers distinct lets the project reproduce the accepted #274 comparison without turning a frozen milestone into competing current guidance.

## Cleanup history

The documentation-cleanup lineage progressively moved durable information out of redundant narratives before deleting or compressing them:

- #300 / PR #301: added historical navigation and active-context retention guidance;
- #302 / PR #305: retired the first redundant historical-doc batch and relocated a rerun CSV into a config-owned fixture location;
- #306 / PR #307: distilled #19/#46/FP-reduction conclusions and reusable safety guidance;
- #308 / PR #309: moved current detector-input provenance/NMS contracts into canonical architecture and retired duplicate #120/#163/#245 narratives;
- #308 / PR #314: retired completed task-control bundles, stale CNN/history guides, and duplicate historical narratives after Issue-side distillation;
- #308 / PR #316: compressed the remaining global and measure-numbering execution diaries into compact historical milestone ledgers;
- later #308 cleanup applies the same retirement gate to audited model-survey artifacts without creating a separate Issue.

## Separate implementation cleanup

Documentation cleanup must not silently change production runtime/config semantics. Legacy environment keys, compatibility fallbacks, model behavior, matcher semantics, or similar implementation concerns belong to their existing implementation Issues when they require code changes.

Graphify refresh requires a local environment with `graphifyy` installed. That operational prerequisite is not a reason to preserve stale prose in the active docs tree.

## Future audit rule

A durable document should answer one of four questions clearly: **how the system works now**, **how to operate it now**, **what explicitly future architecture/responsibility boundary is intended**, or **what durable evidence from a past investigation still needs a local repository contract**. If it mixes those roles, split, distill, or label it. Future/roadmap documents must identify themselves as non-current and point back to the current source of truth.

For historical investigations, prefer a compact navigation/index layer plus original Issue/PR/commit evidence over a second full narrative copy. This keeps historical knowledge recoverable without making every past investigation active context.
