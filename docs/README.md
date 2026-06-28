# Documentation Index

This directory contains project documentation that is intended to outlive a
single interactive session. Some files are issue-scoped design handoffs; those
should be migrated into permanent user/developer documentation once their
implementation has landed.

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
  for the user-facing pipeline, plus a structured contract spec, current-output
  mapping, implementation handoff checklist, and JSON examples for root summary
  and manual-correction handoff files.

### Issue #120 / Stage E / Detector Contract Documentation

- **Issue #120 Artifact Retention Policy**  
  [`docs/ISSUE120_ARTIFACT_RETENTION.md`](ISSUE120_ARTIFACT_RETENTION.md)  
  Defines which Issue #120 artifacts are retained in Git and which generated
  outputs must remain under ignored `logs/` paths.

- **Issue #120 Evaluation Contract**  
  [`docs/ISSUE120_EVALUATION_CONTRACT.md`](ISSUE120_EVALUATION_CONTRACT.md)  
  Describes the Stage E detector-contract evaluation expectations and metrics.

- **Stage E Full-Pipeline Report**  
  [`docs/ISSUE141_STAGE_E_FULL_PIPELINE_REPORT.md`](ISSUE141_STAGE_E_FULL_PIPELINE_REPORT.md)  
  Historical report for Stage E full-pipeline recovery.

### Historical / Archived Investigation Notes

- **CNN Script Inventory**  
  [`docs/ISSUE45_CNN_SCRIPT_INVENTORY.md`](ISSUE45_CNN_SCRIPT_INVENTORY.md)

- **FP Reduction Final Summary**  
  [`docs/fp_reduction/FINAL_SUMMARY.md`](fp_reduction/FINAL_SUMMARY.md)
