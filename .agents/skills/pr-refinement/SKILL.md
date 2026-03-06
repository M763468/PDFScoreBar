---
name: pr-refinement
description: Analyze PR feedback and implement targeted code fixes and improvements.
---

# pr-refinement

## Purpose
Analyze PR comments and reviews to plan and implement necessary code fixes or improvements.

## Input
- PR number or URL
- Review comments (inline or general)
- Current codebase state

## Output (respond in Japanese)
- Summary of required changes based on feedback
- Plan of action
- Implemented fixes
- Verification results
- **Artifact**: `artifacts/pr_refinement_data.json`

## Steps
1) Run `./run.sh <pr_number>` to fetch PR comments and status into an artifact.
2) Read `artifacts/pr_refinement_data.json` to analyze the review feedback.
3) Identify specific code changes required.
4) **Identify the correct execution environment** by referring to `docs/ENVIRONMENTS.md`.
5) Plan and implement modifications according to `AGENTS.md`.
6) Verify the fixes with `make test`, `make format`, and `make lint`.
7) Update documentation if necessary.
8) **Post a comment to the PR** summarizing the implemented fixes and requesting re-review.

## Required commands/permissions
- `./run.sh`: script to fetch PR refinement data into `artifacts/`
- gh: to view PR details, reviews, and post comments
- git: to checkout branch and commit/push changes
- make: to run `make format`, `make lint`, `make test`

## Example commands
- `./run.sh 123`
- `gh pr checkout 123`
- `make test`
- `gh pr comment 123 --body "Summary of fixes..."`

## Notes
- Focus on addressing the reviewer's specific concerns.
- Always refer to `docs/ai-workflow/LESSONS.md` to avoid known anti-patterns.
- If a comment is unclear, ask for clarification.
- **Critical**: Do not forget to notify the reviewer by commenting on the PR after pushing the fixes.
