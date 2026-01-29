# issue-creation

## Purpose
Draft a clear issue with Goal/Scope/Acceptance Criteria so AI can implement it.

## Input
- Background/goal
- Expected outcome
- Constraints

## Output (respond in Japanese)
- Goal
- Scope (In / Out)
- Acceptance Criteria (checklist)
- How to test (if needed)

## Steps
1) Summarize the goal in 1-2 lines.
2) Define Scope (In / Out).
3) Write verifiable Acceptance Criteria.
4) Add How to test if necessary.

## Required commands/permissions
- gh: create issue if needed (e.g., `gh issue create`)
- git: not required in most cases

## Example commands
- `gh issue create --title \"[Task] <title>\" --body \"<body>\"`

## Notes
- Always include Out-of-scope items to prevent scope creep.
