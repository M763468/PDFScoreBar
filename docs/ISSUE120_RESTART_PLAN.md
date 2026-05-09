# Issue 120 Restart Plan

## Purpose

Issue #120 is being restarted as an audit-first recovery effort. The immediate goal is not to add more accuracy logic, but to make the repository operable again: define the trusted branch model, freeze experimental branches, establish one canonical evaluation entrypoint, clean generated artifacts from Git, and only then resume accuracy work under reproducible gates.

## Current Problem

Issue #120 originally targeted a clean rebuild from `90a278c` and restoration of the detector-level golden result `TP=3580 / FP=0 / FN=1`. The implementation history then diverged into multiple branches, generated artifacts, handoff documents, temporary reports, and partial evaluations.

The main failure mode is now operational rather than purely algorithmic:

- multiple documents claim incompatible metrics;
- partial 3-page, 57-page, and full 68-page results are mixed;
- generated JSON/CSV/PNG outputs are tracked alongside source code;
- `fix/probe_seeds` contains later experimental work that is useful as evidence but not safe as a direct merge source;
- `rebuild/issue120` has merged PRs #127-#132 and is the current Issue #120 integration branch, but its claims still need canonical reproduction.

## Branch Model

### Active audit/integration target

- Branch: `rebuild/issue120`
- Role: current Issue #120 integration branch built by PRs #127-#132.
- Policy: use as the base for restart/audit/cleanup work. Do not merge it to `main` until the restart issues are complete.

### Restart-plan branch

- Branch: `audit/issue120-restart-plan`
- Base: `rebuild/issue120`
- PR base: `rebuild/issue120`
- Scope: documentation and issue/branch audit only.

### Frozen experimental branch

- Branch: `fix/probe_seeds`
- Role: experimental/handoff branch containing later investigations, reports, and candidate fixes.
- Policy: do not merge wholesale. Cherry-pick or manually port only after evidence is reproduced through the canonical evaluation command.

### Default branch

- Branch: `main`
- Role: current public default branch.
- Policy: not the immediate target for restart work. Any eventual merge to `main` must happen only after `rebuild/issue120` is audited, cleaned, and validated.

## Issue Plan

### #133: Canonical status document and branch/issue audit

Base: `rebuild/issue120`  
Branch: `audit/issue120-restart-plan`  
PR base: `rebuild/issue120`

Purpose:

- Add this restart plan.
- Audit #120, #121-#124, and PRs #127-#132.
- Decide how to handle still-open #124.
- Classify existing documents as canonical, historical, or suspect.

### #134: Canonical full-68 evaluation entrypoint and metrics contract

Base: `rebuild/issue120`  
Branch: `task/issue120-canonical-eval`  
PR base: `rebuild/issue120`

Purpose:

- Add or fix one command, preferably `make eval-issue120-full`.
- Ensure it always uses the full 68-page manifest.
- Emit both detector metrics and downstream measure-count metrics.
- Prevent partial 3-page or 57-page results from being presented as canonical full results.

### #135: Generated artifact cleanup and retention policy

Base: `rebuild/issue120`  
Branch: `chore/issue120-artifact-cleanup`  
PR base: `rebuild/issue120`

Purpose:

- Inventory generated outputs tracked by Issue #120 work.
- Remove or relocate generated JSON/CSV/PNG/log artifacts from Git unless they are explicitly justified fixtures.
- Preserve reproducibility through scripts, manifests, and ignored output paths.

### #136: Historical best accuracy verification and clean transplant target

Base: `rebuild/issue120`  
Branch: `audit/issue120-best-accuracy`  
PR base: `rebuild/issue120`

Purpose:

- Determine whether `TP=3580 / FP=0 / FN=1` is reproducible from current source, inputs, and commands.
- Tie every claimed best result to a commit/ref, config, command, input set, and output artifact.
- Decide the clean target for future transplant/repair work.

### #137: Accuracy repair after audit

Base: `rebuild/issue120`  
Branch: `fix/issue120-accuracy-after-audit`  
PR base: `rebuild/issue120`

Purpose:

- Resume actual accuracy work only after #134-#136 are done.
- Reassess staff VOV filtering, active X-alignment rescue, double-bar fixes, and related logic under canonical full-68 gates.

## Existing Issue Alignment

### #120

Keep open as the parent Epic. Its current body should be treated as historical intent, not the current operational plan. Link this restart plan and issues #133-#137 from a comment or body update.

### #121, #122, #123

These are already closed as completed. Keep them closed. They are historical phase issues corresponding to merged PRs #127-#132.

### #124

Currently open. Do not complete as-is. It assumes final documentation and branch merge are the next step, but the current state requires audit and cleanup first.

Recommended handling:

- After #133 is merged, either update #124 to depend on #134-#136, or close #124 as superseded by #133-#137 and open a later finalization issue once the restart work is complete.

### #117, #44, #46, #48

Treat as evidence sources for historical accuracy claims and evaluation philosophy. Do not use their document claims as truth unless reproduced by #134/#136.

## Document Classification Policy

Use three classes.

### Canonical

Documents that describe the current source of truth.

Initial canonical document:

- `docs/ISSUE120_RESTART_PLAN.md`

Future canonical documents may include:

- `docs/ISSUE120_EVALUATION_CONTRACT.md`
- `docs/ISSUE120_CURRENT_STATUS.md`

### Historical

Documents that record useful past investigation but are not current truth.

Examples:

- old handoff reports;
- phase reports from #121-#123;
- Issue #44/#46/#48 analysis logs;
- `fix/probe_seeds` reports after they are referenced from the canonical audit.

### Suspect

Documents with unsupported or conflicting claims.

Examples:

- reports claiming full results without a reproducible command;
- partial 3-page or 57-page results presented near full-68 claims;
- documents whose config values do not match the actual checked-in config.

Suspect documents should not necessarily be deleted immediately. First mark or move them under an archive path, then remove only after their useful facts are captured elsewhere.

## Artifact Retention Policy

### Keep in Git

- Source code under `src/`, `tools/`, and tests.
- Small config templates under `configs/`.
- Reproducibility scripts.
- Documentation that describes canonical or historical processes.
- Tiny fixtures needed by tests, if explicitly documented.

### Do not keep in Git

- Full run logs.
- Generated JSON/CSV outputs from full evaluations.
- Crop images, overlay images, contact sheets.
- Temporary score-specific generated configs.
- Manual review CSVs unless they are small, stable, and explicitly treated as source annotations.

### Store outside Git or regenerate

- Full-68 evaluation outputs.
- Visual review artifacts.
- Large golden baseline output trees.

Preferred path for generated outputs:

```text
logs/issue120_e2e_recovery/latest_full_report/
```

This path must remain ignored.

## Evaluation Policy

A result is canonical only if all of the following are recorded:

- branch and commit SHA;
- command;
- config path and config hash or content snapshot;
- manifest path and page count;
- input image root;
- GT root;
- output path;
- detector metrics;
- downstream measure-count metrics;
- whether the run was full 68 pages or partial.

Detector metrics and measure-count metrics must be reported separately.

Required detector metrics:

- `TP`
- `FP`
- `FN`
- `FN_cnn`
- `FN_det`
- `GT`
- precision
- recall

Required downstream measure-count metrics:

- predicted measure count
- GT measure count
- net delta
- absolute delta sum
- pages with delta
- measure precision
- measure recall

## Accuracy Work Guardrails

Do not resume accuracy changes until #134 and #136 establish a reproducible baseline and target.

When accuracy work resumes:

- change one mechanism per PR;
- run canonical full-68 evaluation before and after;
- avoid broad low-score rescue without full evidence;
- avoid broad X-alignment rescue without full evidence;
- avoid fixed-pixel thresholds; prefer unit-scaled rules;
- do not accept a change that improves a local page subset but worsens the chosen canonical gate;
- explicitly separate detector-level improvement from measure-count improvement.

## Immediate Order of Operations

1. Merge #133 after reviewing this restart plan.
2. Resolve #124 status: update as blocked by restart work, or close as superseded.
3. Implement #134 to fix the canonical full-68 evaluation command.
4. Implement #135 to clean generated artifacts from Git.
5. Implement #136 to verify the historical best and define the clean target.
6. Only then implement #137 for accuracy repairs.

## Current Decision

Until #134 and #136 are complete, no metric claim from prior documents should be treated as authoritative. The working assumption is:

- `rebuild/issue120` is the integration branch to audit.
- `fix/probe_seeds` is a frozen evidence branch.
- `TP=3580 / FP=0 / FN=1` is a historical target, not yet the active canonical truth for future merges.
- generated artifacts should be removed from Git unless explicitly retained as small fixtures.
