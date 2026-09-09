# PDFScoreBar History Index

This document is a navigation layer, not a second source of truth.

## Purpose

PDFScoreBar has a long investigation history. This index helps maintainers and AI agents find the right historical evidence without treating old Issue state, handoff notes, or experiment logs as current repository state.

Use current source/tests and current durable documentation first. Follow historical links only when they explain a requirement, accepted contract, regression guard, or prior decision.

## Reading order

For a current task:

1. identify the active Issue / PR from the current request;
2. inspect current source/tests and that target's GitHub state;
3. read canonical/current docs relevant to the subsystem;
4. use the lineage below only for necessary historical evidence;
5. treat branch HEADs, run tags, local paths, blockers, and `next step` text in historical records as stale until revalidated.

A newer comment on an unrelated Issue does not supersede the current task's accepted contract merely because it is newer.

## Canonical current entry points

- [`docs/PIPELINE_ARCHITECTURE.md`](PIPELINE_ARCHITECTURE.md) — current production architecture
- [`docs/TWO_HOMR_MILESTONE.md`](TWO_HOMR_MILESTONE.md) — accepted #274 / [PR #279](https://github.com/M763468/PDFScoreBar/pull/279) comparison milestone
- [`docs/DOCUMENTATION_INVENTORY.md`](DOCUMENTATION_INVENTORY.md) — documentation classification
- [`docs/ENVIRONMENTS.md`](ENVIRONMENTS.md) — maintained execution environments
- [`docs/BRANCH_POLICY.md`](BRANCH_POLICY.md) — branch policy
- [`docs/dev/VALIDATION_POLICY.md`](dev/VALIDATION_POLICY.md) — validation policy
- [`docs/BARLINE_MATCHER.md`](BARLINE_MATCHER.md) — detector matching/evaluation contract
- [`docs/GT_PREPARATION_POLICY.md`](GT_PREPARATION_POLICY.md) — GT policy

## Historical lineages

### Stage-E / detector reconstruction

Primary lineage:

#117 → #119 / #120 → #133–#163

Start with:

- [Issue #120](https://github.com/M763468/PDFScoreBar/issues/120) and its accepted follow-up Issue comments for forensic reconstruction history
- [Issue #136](https://github.com/M763468/PDFScoreBar/issues/136) for the Stage-B scoring/NMS causal boundary
- [Issue #141](https://github.com/M763468/PDFScoreBar/issues/141) for the Stage-E full-pipeline validation record
- [`docs/ISSUE120_EVALUATION_CONTRACT.md`](ISSUE120_EVALUATION_CONTRACT.md)
- [`docs/ISSUE120_ARTIFACT_RETENTION.md`](ISSUE120_ARTIFACT_RETENTION.md)
- [`docs/ISSUE120_NMS_POLICY.md`](ISSUE120_NMS_POLICY.md)
- [`docs/refactors/issue120/`](refactors/issue120/)

Use Issue threads for forensic detail. Do not interpret the old rebuild branch model or old `next step` sections as current branch state.

### Measure numbering / MMR

Primary lineage:

#94 → #194 / #197 → #200 / #208 / #212 / #213 → #221 / #223 / #224 → #244 / #257 / #264 → #276 / #277

Start with:

- [`docs/DEVLOG_MEASURE_NUMBERING.md`](DEVLOG_MEASURE_NUMBERING.md) for early development history only
- [`docs/refactors/issue94/`](refactors/issue94/)
- [`docs/refactors/issue194/`](refactors/issue194/)
- [`docs/refactors/issue201/`](refactors/issue201/)
- current source/tests for present behavior
- #264 / #274 records for the accepted geometry-rebased downstream contract

[`docs/DEVLOG_MEASURE_NUMBERING.md`](DEVLOG_MEASURE_NUMBERING.md) is historical/reference material, not the current specification.

### Fresh detector restoration / connector-aware grouping / HOMR support reuse

Primary lineage:

#245 → #252 / #254 / #255 → #264 → #274 / [PR #279](https://github.com/M763468/PDFScoreBar/pull/279) → #280

Start with:

- [`docs/PIPELINE_ARCHITECTURE.md`](PIPELINE_ARCHITECTURE.md)
- [`docs/TWO_HOMR_MILESTONE.md`](TWO_HOMR_MILESTONE.md)
- #245 / #255 / #264 / #274 Issue records when forensic detail is required

The accepted [PR #279](https://github.com/M763468/PDFScoreBar/pull/279) milestone is the comparison anchor. Earlier producer counts and temporary Phase-A/Phase-B arrangements are historical.

### Performance optimization

Primary lineage:

#281 → #283 / #284 → #293 → #294

Start with:

- #281 for the first post-#274 attribution framework
- #283 for current-x4 HOMR optimization
- #284 / [PR #292](https://github.com/M763468/PDFScoreBar/pull/292) for Real-ESRGAN optimization
- #293 for the post-#292 measured backlog
- #294 only when the active task actually concerns baseline-HOMR replacement

Do not permanently privilege #294. If another Issue is active, resolve that Issue first.

### Downstream-impacting x=580 false barline

Primary lineage:

#196 → #202 → #205 / #206 → #296

For new work, #296 is the preferred historical entry because its Issue body explicitly reclassifies older experiments as evidence rather than permanent design constraints.

### Productization / user-facing workflow

Primary lineage:

#225 → #226 / #227 / #228 / #229 → #236, with related #230 / #280

Start with:

- [`docs/refactors/issue226/`](refactors/issue226/)
- [`docs/refactors/issue227/`](refactors/issue227/)
- [`docs/refactors/issue228/`](refactors/issue228/)
- [`docs/refactors/issue229/`](refactors/issue229/)
- [`docs/manual_correction_review_package.md`](manual_correction_review_package.md)
- [`docs/corrected_final_output.md`](corrected_final_output.md)

Use current source and current user-facing docs for present behavior.

### Development operations / AI workflow

Useful anchors:

#168 / #173 / #190 / #230 / #241 / #258 / #261 / #280

Start with:

- [`AGENTS.md`](../AGENTS.md)
- [`docs/BRANCH_POLICY.md`](BRANCH_POLICY.md)
- [`docs/ENVIRONMENTS.md`](ENVIRONMENTS.md)
- [`docs/dev/VALIDATION_POLICY.md`](dev/VALIDATION_POLICY.md)
- [`docs/ai-workflow/`](ai-workflow/)
- [`docs/DOCUMENTATION_INVENTORY.md`](DOCUMENTATION_INVENTORY.md)

Temporary recovery commands and machine-local paths in old Issues are historical evidence only.

## Experiment provenance rule

For an important investigation, the durable record should make this relationship recoverable:

`hypothesis -> script/command -> source/candidate commit -> fixed inputs/provenance -> result -> disposition`

A result invalidated by a harness, environment, provenance, coordinate/index, or serialization-contract defect must remain labelled invalid/superseded. Do not average it with the corrected result.

## Session / handoff retention rule

Chat transcripts and restart prompts are not durable repository documentation.

Once an Issue's important decisions, experiment provenance, accepted/rejected results, and follow-ups are recoverable from GitHub / source / tests / durable docs, old chat sessions and handoff prompts do not need to be retained as active AI context.

Do not copy full chat transcripts into this repository.
