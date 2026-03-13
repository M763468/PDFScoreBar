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
1) Run `./run.sh <issue_number>` to fetch issue details.
2) Analyze the goal and create a plan.
3) Create a new branch and implement changes.
4) Verify the changes with `make test`, `make format`, and `make lint`.
5) **MANDATORY: Report completion on the Issue** or create a PR.
    - If completing the task directly: Use `gh issue comment <issue_number> --body-file <temp_file>` or `tools/utils/safe_gh_post.sh issue <issue_number> "..."`.
    - **Note**: To prevent shell expansion issues (e.g., backticks in the comment body), it is **STRONGLY RECOMMENDED** to use a temporary file with `--body-file` or the `tools/utils/safe_gh_post.sh` utility.
    - If creating a PR: Ensure the PR references the issue (e.g., `Closes #42`).

6) Report the final URL to the user.

## Required commands/permissions
- `./run.sh`: script to fetch issue data
- gh: CLI tool for issue commenting and PR creation
- git: branch, commit, push

## Example commands
- `./run.sh 42`
- `gh issue comment 42 --body "Fix implemented and verified."`

## Notes
- **CRITICAL**: The task is only complete when the progress/result is reflected on GitHub.
- Refer to `docs/ai-workflow/LESSONS.md` to avoid regressions.
