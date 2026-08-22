# Durable Documentation Inventory

Issue #280 audited the repository documentation against `develop` at PR #279's accepted
production state. This file records the durable classification and the rule used for future
audits; it is not intended to enumerate every Issue-specific forensic note individually.

## Classification rule

- **canonical/current:** intended to describe how the repository should be used now.
- **current/reference:** still accurate within a narrower domain, but not the global
  architecture source.
- **historical:** useful evidence or rationale from a past Issue/experiment; preserve unless
  it creates a current-navigation problem.
- **retire:** duplicates or contradicts current guidance and has no reason to remain in the
  active docs tree; Git history retains it.
- **separate cleanup:** a real implementation/config cleanup that is outside Issue #280's
  documentation/metadata scope and is explicitly routed to an existing cleanup track.

## Inventory

| Document / area | Role | Classification | #280 action |
| --- | --- | --- | --- |
| `README.md` | repository entry | current | update to point to canonical architecture/milestone |
| `AGENTS.md` | repository agent constitution | current | keep; existing Graphify/validation/environment links remain valid |
| `docs/README.md` | documentation index | canonical/current | rewrite current vs historical navigation |
| `docs/PIPELINE_ARCHITECTURE.md` | production architecture | canonical/current | add; global architecture source |
| `docs/TWO_HOMR_MILESTONE.md` | accepted architecture/accuracy/performance milestone | canonical/current | add and complete local/external asset staging contract |
| `docs/ENVIRONMENTS.md` | execution/runtime guidance | current/reference | clarify unified container vs legacy compatibility fallback |
| `docs/BRANCH_POLICY.md` | branch policy | current/reference | keep |
| `docs/dev/VALIDATION_POLICY.md` | validation policy | current/reference | keep |
| `docs/REGRESSION_TEST_WORKFLOW.md` | regression workflow | current/reference | keep |
| `docs/GT_PREPARATION_POLICY.md` | GT policy | current/reference | keep |
| `docs/BARLINE_MATCHER.md` | matching/evaluation rules | current/reference | keep |
| `docs/CNN_RETRAINING_GUIDE.md` | CNN training guide | current/reference | keep; not a production architecture source |
| `docs/manual_correction_review_package.md` | internal review handoff | current/reference | keep |
| `docs/corrected_final_output.md` | corrected-output workflow | scoped/reference | keep; verify against its source path when modifying output workflow |
| `docs/ai-workflow/GRAPHIFY.md` | Graphify operation | current/reference | update staleness/refresh verification rule |
| `.agents/skills/graphify/**` | agent Graphify skill | current/reference | keep; generated/installed skill remains discoverable |
| `graphify-out/**` durable set | generated navigation graph/wiki/report/manifest | current only when provenance is fresh | refresh after stable architecture changes; stale source base must not be treated as architecture truth |
| `docs/PIPELINE_DATAFLOW.md` | old Phase-2 current architecture | stale | retire; merged into canonical architecture |
| `docs/FULL_PIPELINE_README.md` | old Phase-1 orchestration guide | stale | retire; merged into canonical execution/architecture docs |
| `docs/best_configuration_summary.md` | Jan-2026 detector experiment labeled Production Ready | stale/misleading | retire; superseded by current dense route/milestone |
| `docs/performance_comparison.md` | dated optimization history | historical | keep; index explicitly labels historical |
| `docs/DEVELOPMENT_LOG.md` | development history | historical | keep |
| `docs/DEVLOG_*.md` | component development history | historical/reference | keep; verify old claims against source |
| top-level `docs/ISSUE*.md` | Issue forensic/reproduction records | historical | keep by default; do not rewrite merely to match current code |
| `docs/refactors/issue*/**` | scoped design/history | historical/scoped | keep by default; current global architecture lives elsewhere |
| `docs/notes/**`, `docs/future/**` | notes/plans | historical/planning | keep unless separately superseded/approved for deletion |
| `docs/model_experiments/**`, `docs/fp_reduction/**` | experiment records | historical | keep |
| `configs/dense_full_pipeline.yaml` | canonical dense production config | current runtime input, not prose | reference from canonical docs; do not alter under docs-only Issue #280 |
| `configs/detector_profiles/stage_e_verified_homr.json` | pinned profile provenance | canonical machine-readable reference | reference from milestone doc |

## Dead/stale-path audit findings

The two retired architecture guides were specifically problematic because they described old
phase plans as present behavior. `FULL_PIPELINE_README.md` called the orchestrator a “Phase
1” thin wrapper and deferred I/O/parallelism to a future “Phase 2”; the current orchestrator
already contains in-process rendering and a substantially different dense detector route.
`PIPELINE_DATAFLOW.md` likewise mixed old subprocess/persistence claims with architecture
that predates the verified two-HOMR route.

`best_configuration_summary.md` documented an older geometric+CNN detector experiment and
labeled it “Production Ready”. Its metrics/config are historical, not the current production
contract, so keeping it active would compete with the verified Stage-E profile and Issue #274
milestone.

## Reproduction boundary resolved in #280

The two-HOMR milestone deliberately does not commit large evaluation images or the Issue #44
CNN checkpoint. `docs/TWO_HOMR_MILESTONE.md` now records the staging/recovery contract
instead:

- the canonical 68-page work/page identity is the committed `SCORES` mapping in
  `tools/issue120/eval_full68_from_intermediates.py`;
- the corresponding images must be staged under `data/evaluation2/images/<score>/<page>.png`
  and are checked against the tracked annotation pages before a comparison run;
- the production CNN checkpoint is the Issue #44 / PR #57 Iter 7 final-rescue artifact at
  `logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth`;
- `docs/ISSUE44_ITER7_FINAL_REPORT.md` is the committed reconstruction procedure for that
  training contract;
- future comparison runs record the staged checkpoint SHA-256 in their small provenance
  summary.

The historical large checkpoint did not have a durable SHA-256 committed at creation time.
#280 does not manufacture one after the fact. If the retained local checkpoint exists, its
hash identifies the comparison run; if it has been lost, the committed Iter 7 training
procedure is the canonical reconstruction route and the rebuilt checkpoint must be labelled
as reconstructed rather than falsely claimed byte-identical.

This satisfies the repository's intended reproducibility level for the immediately preceding
large refactor: accepted source/config/profile, canonical page selection, external-asset
staging checks, model reconstruction path, and accuracy/performance contracts are all
recorded without retaining enormous artifacts in Git.

## Separate cleanup routed outside #280

`docs/ENVIRONMENTS.md` correctly treats `sr_eval_gpu` as non-canonical, while
`src/pipeline/core/python_env.py` still contains a compatibility fallback and
`configs/dense_full_pipeline.yaml` contains the legacy-looking
`container_name: sr_eval_gpu_exp` key.

These are small implementation/config cleanup items, not documentation blockers. They are
tracked with the existing repository-surface cleanup work (#230, parent #225) so they can be
removed together with other legacy/debug surface after verifying that no maintained path
still depends on them. Issue #280 intentionally does not change production runtime/config
semantics.

Graphify refresh itself requires a local environment with `graphifyy` installed. That is an
operational prerequisite, not an outstanding repository change; the durable generated
outputs and provenance manifest were refreshed in #280.

## Future audit rule

A new durable document should answer one of three questions clearly: “how the system works
now”, “how to operate it now”, or “what happened in a past investigation”. If it mixes those
roles, split or label it. Current global architecture must be reachable from the root README
without reading Issue history.
