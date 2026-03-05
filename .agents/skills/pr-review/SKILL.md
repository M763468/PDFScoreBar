---
name: pr-review
description: Review a PR to identify risks, bugs, and scope drift early.
---

# pr-review

## Purpose
Review a PR to identify risks, bugs, and scope drift early.

## Input
- PR diff
- Acceptance Criteria
- Test results

## Output (respond in Japanese)
- Findings ordered by severity
- Assumptions or unknowns
- Additional tests/verification needed
- **Artifacts**: `artifacts/pr_review_data.json`, `artifacts/pr_diff.patch`

## Steps
1) Run `./run.sh <pr_number>` to fetch PR details and diff into artifacts.
2) Read `artifacts/pr_review_data.json` and `artifacts/pr_diff.patch` to analyze the PR.
3) Check Acceptance Criteria and scope drift.
4) List findings in severity order.
5) Include impact and reproducibility.
6) Suggest additional tests or checks.

## Required commands/permissions
- `./run.sh`: script to fetch PR data into `artifacts/`
- gh: CLI tool for PR management

## Example commands
- `./run.sh 123`

## Notes
- Base findings on evidence; label speculation clearly.
