---
name: change-summary
description: Summarize changes clearly and state impact and follow-up needs.
---

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
- **Artifact**: `artifacts/change_summary.txt`

## Steps
1) Run `./run.sh [base_branch]` to generate the change summary artifact.
2) Read `artifacts/change_summary.txt` to understand the changes.
3) Extract and group changes by intent.
4) Separate user impact from technical impact.
5) State next required actions.

## Required commands/permissions
- `./run.sh`: script to generate change summary in `artifacts/`
- git: inspect diffs/history

## Example commands
- `./run.sh main`

## Notes
- Prefer meaningful grouping over raw lists.
