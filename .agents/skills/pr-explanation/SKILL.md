# pr-explanation

## Purpose
Explain the PR intent and scope to make review efficient.

## Input
- PR diff
- Related issue
- Goal/context

## Output (respond in Japanese)
- Key changes
- Scope (In / Out)
- Test results
- Known trade-offs or concerns

## Steps
1) Summarize goal and context.
2) List key changes succinctly.
3) State scope (In / Out).
4) Include tests and caveats.

## Required commands/permissions
- gh: view PR details if needed (e.g., `gh pr view`, `gh pr diff`)
- git: review local diffs if needed

## Example commands
- `gh pr view <number>`
- `gh pr diff <number>`

## Notes
- Optimize for fast reader comprehension.
