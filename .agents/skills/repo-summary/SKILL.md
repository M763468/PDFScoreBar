---
name: repo-summary
description: Gather repository structure, dependencies, and logs for session initialization.
---

# repo-summary

## Purpose
Quickly gather the current state of the repository, including structure, dependencies, and recent logs, to initialize or resume a session with full context.

## Output (respond in Japanese)
- Repository status overview
- Structure and dependency summary
- **Artifact**: `artifacts/repo_summary.txt`

## Steps
1) Run `./run.sh` (or `make repo-summary`) to generate the summary artifact.
2) Read `artifacts/repo_summary.txt` to understand the current state.
3) Use the information to plan next steps or identify blockers.

## Required commands/permissions
- `./run.sh`: script to gather repo status into `artifacts/`
- make: to run `make repo-summary`

## Example commands
- `./run.sh`
- `make repo-summary`
