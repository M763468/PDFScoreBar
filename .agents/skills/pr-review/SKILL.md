---
name: pr-review
description: Review a PR to identify risks, bugs, and scope drift, and MANDATORILY post the review to GitHub. Use when a PR needs automated inspection against standards and requirements.
---

# pr-review

## Purpose
Review a PR to identify risks, bugs, and scope drift, and ensure the findings are communicated to the author via GitHub.

## Input
- PR diff
- Acceptance Criteria
- Test results

## Output (respond in Japanese)
- Findings ordered by severity
- Created Review Comment URL (Mandatory)
- **Artifacts**: `artifacts/pr_review_data.json`, `artifacts/pr_diff.patch`

## Steps
1) Run `./run.sh <pr_number>` to fetch PR details and diff into artifacts.
2) Read `artifacts/pr_review_data.json` and `artifacts/pr_diff.patch` to analyze the PR.
3) Check Acceptance Criteria and scope drift.
4) Formulate findings in Japanese, ordering by severity.
5) **MANDATORY: Post the review findings to GitHub** using `gh pr review <pr_number> --comment --body "..."`. The body should contain the ordered list of findings and suggestions.
6) Report the URL of the created comment.

## Required commands/permissions
- `./run.sh`: script to fetch PR data into `artifacts/`
- gh: CLI tool for PR management and commenting

## Example commands
- `./run.sh 123`
- `gh pr review 123 --comment --body "Review findings..."`

## Notes
- Base findings on evidence; label speculation clearly.
- **CRITICAL**: The task is only complete once the review is posted on GitHub. Do not just display the findings in the CLI.
