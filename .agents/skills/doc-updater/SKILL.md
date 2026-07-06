---
name: doc-updater
description: Update documentation to reflect code changes and keep it accurate.
---

# doc-updater

## Purpose
Update documentation (README, API docs, inline comments) to reflect code changes and maintain accuracy.

## Input
- Changed source code files
- Existing documentation (README.md, docs/*.md)
- PR description or change summary

## Output (respond in Japanese)
- Updated markdown files
- Updated docstrings
- Verification that docs match the code
- **Artifact**: `artifacts/documentation_status.txt`

## Steps

Run commands from the repository root.
1) Run `bash .agents/skills/doc-updater/run.sh` to gather the current documentation status (e.g., TODOs) into an artifact.
2) Read `artifacts/documentation_status.txt` to identify missing or outdated documentation.
3) Identify which parts of the code have changed.
4) Update `README.md`, `docs/`, and inline docstrings.
5) Verify formatting and clarity.

## Required commands/permissions
- `bash .agents/skills/doc-updater/run.sh`: script to gather documentation status into `artifacts/`
- file operations: to read and write documentation files

## Example commands
- `bash .agents/skills/doc-updater/run.sh`

## Notes
- Keep documentation concise and up-to-date.
- Check for broken links if filenames changed.
