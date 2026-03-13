---
name: pr-refinement
description: Analyze PR feedback, implement fixes, and MANDATORILY post a summary comment to GitHub. Use when a PR has review comments that need addressing and the user wants to close the feedback loop.
---

# pr-refinement

## Purpose
Analyze PR comments and reviews to plan and implement necessary code fixes or improvements, and ensure the reviewer is notified of the changes.

## Input
- PR number or URL
- Review comments (inline or general)
- Current codebase state

## Output (respond in Japanese)
- Summary of required changes based on feedback
- Plan of action
- Implemented fixes
- Verification results
- **Created PR Comment URL** (Mandatory)
- **Artifact**: `artifacts/pr_refinement_data.json`

## Steps
1) Run `./run.sh <pr_number>` to fetch PR comments and status into an artifact.
2) Read `artifacts/pr_refinement_data.json` to analyze the review feedback.
3) Identify specific code changes required.
4) **Identify the correct execution environment** by referring to `docs/ENVIRONMENTS.md`.
5) Plan and implement modifications according to `AGENTS.md`.
6) Verify the fixes with `make test`, `make format`, and `make lint`.
7) Update documentation if necessary.
8) **MANDATORY: Post a comment to the PR** using `gh pr comment <pr_number> --body "..."`. 
   **Note**: To prevent shell expansion issues (e.g., backticks in the comment body), it is **STRONGLY RECOMMENDED** to use `--body-file` or the `tools/utils/safe_gh_comment.sh` utility for comments containing code or special characters.
   The comment MUST summarize the implemented fixes and explicitly request a re-review. This is the final and most important step to close the task.

## Required commands/permissions
- `./run.sh`: script to fetch PR refinement data into `artifacts/`
- gh: to view PR details, reviews, and post comments
- git: to checkout branch and commit/push changes
- make: to run `make format`, `make lint`, `make test`

## Example commands
- `./run.sh 123`
- `gh pr checkout 123`
- `make test`
- `gh pr comment 123 --body "修正内容のサマリー..."`

## Notes
- Focus on addressing the reviewer's specific concerns.
- Always refer to `docs/ai-workflow/LESSONS.md` to avoid known anti-patterns.
- If a comment is unclear, ask for clarification.
- **CRITICAL**: The task is NOT complete until the summary comment is posted on GitHub. Do not wait for the user to ask for the report; post it as the final action of the skill workflow.
