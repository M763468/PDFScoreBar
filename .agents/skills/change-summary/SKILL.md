# change-summary

## Purpose
Summarize changes clearly and state impact and follow-up needs.

## Input
- Target branch/PR/diff
- Change rationale (optional)

## Output (respond in Japanese)
- Change summary (bulleted)
- Impact scope
- Follow-up actions (tests/docs) if any

## Steps
1) Extract and group changes by intent.
2) Separate user impact from technical impact.
3) State next required actions.

## Required commands/permissions
- git: inspect diffs/history (e.g., `git diff`, `git log`)
- gh: review PR diff if needed

## Example commands
- `git diff main...HEAD`
- `git log --oneline -5`
- `gh pr diff <number>`

## Notes
- Prefer meaningful grouping over raw lists.
