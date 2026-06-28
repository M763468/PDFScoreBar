# Project Documentation Index

> [!NOTE]
> This document is the entry point for understanding the current repository
> documentation map. It intentionally avoids session-specific instructions;
> use linked policy and issue documents for current operational decisions.

---

## How to Read This Repository

This repository contains multiple layers of documentation, each serving a
specific time scale and purpose. Before starting work, identify whether you
need a standing policy, a current issue decision, or historical context.

### Documentation by Time Scale

| Time Scale | Document | Purpose |
|----------|----------|---------|
| **Standing policy** | [`AGENTS.md`](../AGENTS.md), [`docs/BRANCH_POLICY.md`](BRANCH_POLICY.md), [`docs/dev/VALIDATION_POLICY.md`](dev/VALIDATION_POLICY.md) | Repository-wide operating rules for agents, branches, and validation |
| **Long term** | [`README.md`](../README.md) (repo root) | Ultimate project vision and scope |
| **Project map** | [`docs/README.md`](README.md) (this file) | Documentation index and navigation guide |
| **Issue-specific current state** | Active GitHub issues / PRs | Source of truth for current scope, base branch, and acceptance for that work |
| **Historical facts** | [`docs/DEVELOPMENT_LOG.md`](DEVELOPMENT_LOG.md), issue-specific reports under `docs/` | Confirmed past decisions, experiments, and results |

---

## Current Operational Status (2026-06-06)

- `develop` is the active integration branch.
- `main` is the stable/release branch.
- Normal feature, fix, refactor, documentation, and performance work should branch from `develop` and open PRs against `develop`.
- `develop -> main` promotion must be handled by a dedicated promotion PR with explicit validation results and promotion gates.
- Older issue bodies may still say `Base branch: main` or `PR base: main`; treat that text as stale unless the issue is explicitly about release, hotfix, or promotion work.

See [`docs/BRANCH_POLICY.md`](BRANCH_POLICY.md) for the standing branch policy.

---

## Where to Find Current Decisions and Artifacts

This project produces a large number of intermediate and final artifacts.
Use the table below to locate the relevant source without mistaking historical
notes for current instructions.

| What you want to see | Location |
|---------------------|----------|
| Branch roles and default PR base | [`docs/BRANCH_POLICY.md`](BRANCH_POLICY.md) |
| Agent operating rules | [`AGENTS.md`](../AGENTS.md) |
| Validation expectations by change type | [`docs/dev/VALIDATION_POLICY.md`](dev/VALIDATION_POLICY.md) |
| User-facing pipeline entrypoint design | [`docs/refactors/issue226/ISSUE226_USER_FACING_ENTRYPOINT.md`](refactors/issue226/ISSUE226_USER_FACING_ENTRYPOINT.md) |
| User-facing output profile contract package | [`docs/refactors/issue227/ISSUE227_OUTPUT_PROFILES.md`](refactors/issue227/ISSUE227_OUTPUT_PROFILES.md) |
| Issue #120 artifact retention rules | [`docs/ISSUE120_ARTIFACT_RETENTION.md`](ISSUE120_ARTIFACT_RETENTION.md) |
| Issue #120 evaluation contract | [`docs/ISSUE120_EVALUATION_CONTRACT.md`](ISSUE120_EVALUATION_CONTRACT.md) |
| Stage E full-pipeline report | [`docs/ISSUE141_STAGE_E_FULL_PIPELINE_REPORT.md`](ISSUE141_STAGE_E_FULL_PIPELINE_REPORT.md) |
| CNN script ownership and cleanup decisions | [`docs/ISSUE45_CNN_SCRIPT_INVENTORY.md`](ISSUE45_CNN_SCRIPT_INVENTORY.md) |
| Historical FP reduction report | [`docs/fp_reduction/FINAL_SUMMARY.md`](fp_reduction/FINAL_SUMMARY.md) |

---

## Documentation Modules

### Core Documentation

- **[`AGENTS.md`](../AGENTS.md)**  
  Repository-specific rules for AI agents and interactive work.

- **[`docs/BRANCH_POLICY.md`](BRANCH_POLICY.md)**  
  Standing branch policy. Defines `develop` as the active integration branch,
  `main` as the stable/release branch, and the dedicated promotion-PR rule.

- **[`docs/dev/VALIDATION_POLICY.md`](dev/VALIDATION_POLICY.md)**  
  Validation selection policy by change type. Use this when deciding which
  checks are required, skipped, or deferred.

- **[`docs/ENVIRONMENTS.md`](ENVIRONMENTS.md)**  
  Runtime containers, dependencies, and execution instructions.

- **[`docs/REGRESSION_TEST_WORKFLOW.md`](REGRESSION_TEST_WORKFLOW.md)**  
  Pre-commit / pre-PR verification workflow.

- **[`docs/DEVELOPMENT_LOG.md`](DEVELOPMENT_LOG.md)**  
  Authoritative historical record. Append-only unless explicitly scoped
  otherwise.

- **[`docs/GT_PREPARATION_POLICY.md`](GT_PREPARATION_POLICY.md)**  
  Mandatory policy for creating barline ground truth. Defines labeling for
  double/final barlines and resolution-independent scaling rules.

- **[`docs/BARLINE_MATCHER.md`](BARLINE_MATCHER.md)**  
  Detailed specification of the barline matching and deduplication logic.

### Issue #225 / User-facing Usability Cleanup

- **Issue #226 User-facing Pipeline Entrypoint Design**  
  [`docs/refactors/issue226/ISSUE226_USER_FACING_ENTRYPOINT.md`](refactors/issue226/ISSUE226_USER_FACING_ENTRYPOINT.md)  
  Defines the formal `pdfscorebar run INPUT.pdf --output-dir OUTPUT_DIR`
  user-facing entrypoint, its relationship to existing config-first and
  Makefile-driven routes, and the implementation handoff for the CLI wrapper.

- **Issue #227 User-facing Output Profile Contract Package**  
  [`docs/refactors/issue227/ISSUE227_OUTPUT_PROFILES.md`](refactors/issue227/ISSUE227_OUTPUT_PROFILES.md)  
  Defines the `final`, `review`, and `debug` output profile directory contract
  for the user-facing pipeline, including final-PDF-only output, score-specific
  final PDF naming, timestamped debug run directories, a structured contract
  spec, current-output mapping, implementation handoff checklist, and JSON
  examples for review summary and manual-correction handoff files.

### Issue #120 / Stage E / Detector Contract Documentation

- **Issue #120 Artifact Retention Policy**  
  [`docs/ISSUE120_ARTIFACT_RETENTION.md`](ISSUE120_ARTIFACT_RETENTION.md)  
  Defines which Issue #120 artifacts are retained in Git and which generated
  outputs must remain under ignored `logs/` paths.

- **Issue #120 Evaluation Contract**  
  [`docs/ISSUE120_EVALUATION_CONTRACT.md`](ISSUE120_EVALUATION_CONTRACT.md)  
  Canonical detector-level evaluation contract for the Issue #120 rebuild.

- **Issue #120 Roadmap and Historical Findings**  
  [`docs/ISSUE120_ROADMAP.md`](ISSUE120_ROADMAP.md)  
  [`docs/ISSUE120_HISTORICAL_BEST_AUDIT.md`](ISSUE120_HISTORICAL_BEST_AUDIT.md)  
  [`docs/refactors/issue120/`](refactors/issue120/)

- **Stage E Full Pipeline Report**  
  [`docs/ISSUE141_STAGE_E_FULL_PIPELINE_REPORT.md`](ISSUE141_STAGE_E_FULL_PIPELINE_REPORT.md)  
  Historical full-pipeline validation and runtime/resource reporting context.

- **Dense Route Naming / Logging / Parallelism Notes**  
  [`docs/ISSUE158_DENSE_ROUTE_NAMING.md`](ISSUE158_DENSE_ROUTE_NAMING.md)  
  [`docs/ISSUE162_PIPELINE_LOGGING_TAXONOMY.md`](ISSUE162_PIPELINE_LOGGING_TAXONOMY.md)  
  [`docs/ISSUE163_HOMR_SR_PARALLELISM_CONCLUSION.md`](ISSUE163_HOMR_SR_PARALLELISM_CONCLUSION.md)

### CNN Classifier / Detector Evaluation

- **Issue #45 CNN Script Inventory**  
  [`docs/ISSUE45_CNN_SCRIPT_INVENTORY.md`](ISSUE45_CNN_SCRIPT_INVENTORY.md)  
  Current script ownership, cleanup decisions, and placement rules for
  CNN-related `tools/` and `experiments/` scripts.

- **CNN Retraining Guide**  
  [`docs/CNN_RETRAINING_GUIDE.md`](CNN_RETRAINING_GUIDE.md)  
  Historical FP-based active-learning retraining procedure. Not part of the
  production pipeline runtime.

- **CNN Training Development Log**  
  [`docs/DEVLOG_CNN_TRAINING.md`](DEVLOG_CNN_TRAINING.md)  
  Historical CNN training and evaluation log. It may mention scripts that were
  later moved or deleted; use the inventory document for current paths.

### FP Reduction (Phase 1-3, Historical)

- **Final Summary**  
  [`docs/fp_reduction/FINAL_SUMMARY.md`](fp_reduction/FINAL_SUMMARY.md)  
  Executive summary of the FP reduction effort. Historical context only.

- **Development Log (Phase 1-2)**  
  [`docs/fp_reduction/development_log.md`](fp_reduction/development_log.md)  
  Detailed early-phase experimentation history.

- **Walkthrough**  
  [`docs/fp_reduction/walkthrough.md`](fp_reduction/walkthrough.md)  
  Phase-by-phase explanation of methodology and results.

---

## Logs and Experimental Outputs

Experimental outputs are stored under ignored `logs/` paths using structured
subdirectories. Do not commit generated run outputs unless an issue-specific
retention policy explicitly allows a narrow fixture.

General rules:

- Each run should produce its own directory under `logs/`.
- Scripts and configurations used for the run should be traceable from the log.
- Qualitative overlays and quantitative summaries should live next to each other.
- Generated summaries such as `evaluation_contract.json`, `manifest.json`,
  `detector_metrics.json`, and visual-review PNGs should remain out of Git
  unless a retention policy explicitly says otherwise.

For Issue #120 artifacts, use [`docs/ISSUE120_ARTIFACT_RETENTION.md`](ISSUE120_ARTIFACT_RETENTION.md) before
removing or adding files under `data/evaluation2/`.
