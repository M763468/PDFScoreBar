---
name: pr-viewer
description: Fetch and display the details, comments, and reviews of a specific Pull Request.
---

# pr-viewer

## Purpose
Use this skill when the user asks to quickly check, view, or read the context of a specific PR (e.g., "PR#??を確認して").
It fetches the PR details, comments, review threads, and diff without generating a heavy explanation or formal review.

## Input
- PR number (e.g., 69)

## Output (respond in Japanese)
- Summary of the PR state, title, and recent discussions/comments.
- If requested, specific parts of the PR body or diff.
- **Artifacts**: `artifacts/pr_data_<number>.json`, `artifacts/pr_diff_<number>.patch`

## Steps

Run commands from the repository root.
1) Run `bash .agents/skills/pr-viewer/run.sh <pr_number>` to fetch PR details and diff into artifacts.
2) Read the generated `artifacts/pr_data_<number>.json` to check title, body, state, comments, and review threads.
3) Read `artifacts/pr_diff_<number>.patch` if code changes need to be inspected.
4) Provide a clear and concise summary to the user in Japanese, or answer their specific question about the PR.

## Required commands/permissions
- `bash .agents/skills/pr-viewer/run.sh`: script to fetch PR data into `artifacts/`
- gh: to view PR

## Example commands
- `bash .agents/skills/pr-viewer/run.sh 69`

## Notes
- Ensure you read the comments and reviewThreads carefully, as they often contain the latest feedback or blockers.
- This skill simply retrieves information and summarizes it; do not attempt to write a full PR review unless specifically requested.
