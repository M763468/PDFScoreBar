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
Generate the content for templates in `.github/ISSUE_TEMPLATE/` and log the result to artifacts.
- **Artifact**: `artifacts/issue_creation_result.txt`

## Steps
1) Identify the issue type (Bug, Feature, or Task).
2) Refer to the corresponding template in `.github/ISSUE_TEMPLATE/`.
3) Draft the content (Goal, Scope, Acceptance Criteria, Branch).
4) Run `./run.sh template_file title body_file` to create the issue via CLI and log the result.

## Required commands/permissions
- `./run.sh`: script to create GitHub issue and log to `artifacts/`

## Example commands
- `./run.sh task.yml "[Task] Update documentation" drafted_issue.md`

## Notes
- Always include Out-of-scope items to prevent scope creep.
- Ensure the `branch_name` follows the project's naming convention.
