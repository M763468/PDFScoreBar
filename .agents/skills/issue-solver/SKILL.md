---
name: issue-solver
description: Resolve a GitHub issue and MANDATORILY post a completion summary to the issue. Use when an issue needs investigation, implementation, and verified closure.
---

# issue-solver

## Purpose
Autonomously resolve a GitHub Issue by implementing and verifying changes, and ensuring the progress is documented on the issue.

## Input
- Issue number or URL
- Codebase context

## Output (respond in Japanese)
- Plan of action
- Code changes (commits)
- Verification results
- Created Comment URL or PR URL (Mandatory)
- **Artifact**: `artifacts/issue_data.json`

## Steps

Run commands from the repository root.
1) Run `bash .agents/skills/issue-solver/run.sh <issue_number>` to fetch issue details.
2) Analyze the goal and create a plan.
3) Create a new branch and implement changes.
4) Verify the changes with `make format`, `make lint`, `make test-fast`, and any issue-specific pytest, smoke, or validation-policy commands required by the issue.
5) **MANDATORY: Report completion on the Issue** or create a PR.
    - If completing the task directly: `gh issue comment <issue_number> --body "修正内容と検証結果のサマリー..."`
    - If creating a PR: Ensure the PR references the issue (e.g., `Closes #42`).
6) Report the final URL to the user.

## Required commands/permissions
- `bash .agents/skills/issue-solver/run.sh`: script to fetch issue data
- gh: CLI tool for issue commenting and PR creation
- git: branch, commit, push

## Example commands
- `bash .agents/skills/issue-solver/run.sh 42`
- `gh issue comment 42 --body "Fix implemented and verified."`

## Notes
- **CRITICAL**: The task is only complete when the progress/result is reflected on GitHub.
- Refer to `docs/ai-workflow/LESSONS.md` to avoid regressions.
