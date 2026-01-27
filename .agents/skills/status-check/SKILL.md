# status-check

## Purpose
Provide a clear, concise snapshot of work status and the next actions.

## Input
- Current issue/task identifier
- Progress or blockers (optional)

## Output (respond in Japanese)
- Progress summary (Done / Doing / Next)
- Blockers (if any)
- Information needed (if any)

## Steps
1) Identify the target issue/PR/branch.
2) Summarize recent changes and remaining tasks.
3) State the next action and any missing information.

## Required commands/permissions
- git: check status/history (e.g., `git status`, `git log`)
- gh: view issues/PRs if needed (e.g., `gh issue view`, `gh pr view`)

## Example commands
- `git status -sb`
- `git log -1 --oneline`
- `gh issue view <number>`
- `gh pr view <number>`

## Notes
- Separate facts from assumptions.
- Mark out-of-scope suggestions explicitly as proposals.
