---
name: issue-creation
description: Draft a clear issue with Goal/Scope/Acceptance Criteria so AI can implement it.
---

# issue-creation

## Purpose
Draft a clear issue with Goal/Scope/Acceptance Criteria so AI can implement it, aligned with the project's GitHub Issue Templates.

## Input
- Background/goal
- Expected outcome
- Constraints
- Issue type (Bug / Feature / Task)

## Output (respond in Japanese)
Generate the content for one of the following templates located in `.github/ISSUE_TEMPLATE/` and log the result to artifacts.
- **Artifact**: `artifacts/issue_creation_result.txt`

- **Feature**: For new features or implementation tasks.
- **Bug**: For bug reports and fixes.
- **Task**: For small chores, refactoring, or documentation.

- Template headers (must match `.github/ISSUE_TEMPLATE/*.yml`)
  - Base branch
  - Branch name
  - PR base
  - Goal
  - Done
  - Notes
- Optional detail sections (project custom)
  - Scope (In / Out)
  - Acceptance Criteria (checklist)
  - How to test (if needed)

## Steps

Run commands from the repository root.
1) Identify the issue type (Bug, Feature, or Task) and summarize the goal in 1-2 lines.
2) Refer to the corresponding template in `.github/ISSUE_TEMPLATE/` (e.g. `task.yml`) and mirror required headers in the issue body.
3) Draft the content:
   - **Goal/Background**: Clear statement of what and why.
   - **Scope (In / Out)**: Explicitly define boundaries.
   - **Acceptance Criteria**: Verifiable checklist. Fill `Done` with verifiable checklist items (machine-checkable when possible).
   - **Branch Operations**: Suggest `base_branch` and `branch_name` (e.g., `feature/xxx` or `fix/xxx`).
4) Add How to test if necessary.
5) Run `bash .agents/skills/issue-creation/run.sh <template_file> "<title>" <body_file>` to create the issue via CLI and log the result.

## Required commands/permissions
- `bash .agents/skills/issue-creation/run.sh`: script to create GitHub issue and log to `artifacts/`

## Example commands
- `bash .agents/skills/issue-creation/run.sh task.yml "[Task] Update documentation" drafted_issue.md`

## Notes
- Always include Out-of-scope items to prevent scope creep.
- Before posting, run a header presence check against template labels (at minimum: `Base branch`, `Branch name`, `PR base`, `Goal`, `Done`).
- Ensure the `branch_name` follows the project's naming convention.
