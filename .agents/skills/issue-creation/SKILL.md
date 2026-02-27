---
name: issue-creation
description: Draft a clear issue with Goal/Scope/Acceptance Criteria so AI can implement it.
---

# issue-creation

## Purpose
Draft a clear issue with Goal/Scope/Acceptance Criteria so AI can implement it.

## Input
- Background/goal
- Expected outcome
- Constraints

## Output (respond in Japanese)
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
1) Summarize the goal in 1-2 lines.
2) Open `.github/ISSUE_TEMPLATE/task.yml` (or matching template) and mirror required headers in issue body.
3) Fill `Done` with verifiable checklist items (machine-checkable when possible).
4) Define Scope (In / Out) and Acceptance Criteria as optional project detail.
5) Add How to test if necessary.

## Required commands/permissions
- gh: create issue if needed (e.g., `gh issue create`)
- git: not required in most cases

## Example commands
- `gh issue create --title \"[Task] <title>\" --body \"<body>\"`

## Notes
- Always include Out-of-scope items to prevent scope creep.
- Before posting, run a header presence check against template labels (at minimum: `Base branch`, `Branch name`, `PR base`, `Goal`, `Done`).
