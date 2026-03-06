---
name: pr-explanation
description: Analyze a PR diff and MANDATORILY update its description or post a summary comment. Use when a PR needs clear, concise explanation of changes and their rationale.
---

# pr-explanation

## Purpose
Analyze a PR diff and ensure its purpose and impact are clearly documented on GitHub.

## Input
- PR diff
- Related issue context

## Output (respond in Japanese)
- Summarized explanation of changes
- Update status or Comment URL (Mandatory)
- **Artifacts**: `artifacts/pr_explanation_data.json`, `artifacts/pr_diff.patch`

## Steps
1) Run `./run.sh <pr_number>` to fetch PR details and diff.
2) Analyze the diff and project context to understand the "What" and "Why".
3) Draft a concise explanation in Japanese, following the standard format (Goal, Changes, Impact).
4) **MANDATORY: Update the PR on GitHub** or post a summary comment.
    - Prefer updating the PR description: `gh pr edit <pr_number> --body "..."`
    - Or post a comment if the description should remain intact: `gh pr comment <pr_number> --body "..."`
5) Report the completion status and URL.

## Required commands/permissions
- `./run.sh`: script to fetch PR data
- gh: CLI tool for PR editing and commenting

## Example commands
- `./run.sh 123`
- `gh pr edit 123 --body "Refactored logic..."`

## Notes
- Focus on the "Why" as much as the "What".
- **CRITICAL**: Do not just display the explanation in the CLI. The goal is to document the PR on GitHub.
