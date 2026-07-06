---
name: issue-viewer
description: Fetch and display the details and comments of a specific GitHub Issue.
---

# issue-viewer

## Purpose
Use this skill when the user asks to check or view a specific issue (e.g., "issue#??を確認して").
It fetches the issue details and comments using `gh` CLI and logs them to an artifact for analysis.

## Input
- Issue number (e.g., 59)

## Output (respond in Japanese)
- Summary of the issue (Title, State, Body, Comments)
- **Artifact**: `artifacts/issue_data_<number>.json`

## Steps

Run commands from the repository root.
1) Run `bash .agents/skills/issue-viewer/run.sh <issue_number>` to fetch issue details.
2) Read the generated `artifacts/issue_data_<number>.json`.
3) Analyze the title, body, state, and comments.
4) Provide a clear and concise summary to the user in Japanese.

## Required commands/permissions
- `bash .agents/skills/issue-viewer/run.sh`: script to fetch issue data into `artifacts/`
- gh: to view issue

## Example commands
- `bash .agents/skills/issue-viewer/run.sh 59`

## Notes
- Ensure you read the comments carefully, as they often contain the latest context or changes in requirements.
