---
name: status-check
description: Provide a clear and concise snapshot of work status and next actions.
---

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
- **Artifact**: `artifacts/status_check.txt`

## Steps
1) Run `./run.sh` to gather the repository status into an artifact.
2) Read `artifacts/status_check.txt` to identify the current branch and last commit.
3) Summarize recent changes and remaining tasks.
4) State the next action and any missing information.

## Required commands/permissions
- `./run.sh`: script to gather status into `artifacts/`
- git: check status/history

## Example commands
- `./run.sh`

## Notes
- Separate facts from assumptions.
- Mark out-of-scope suggestions explicitly as proposals.
