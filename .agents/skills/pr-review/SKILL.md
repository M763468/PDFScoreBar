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

## Steps
1) Check Acceptance Criteria and scope drift.
2) List findings in severity order.
3) Include impact and reproducibility.
4) Suggest additional tests or checks.

## Required commands/permissions
- gh: view PR details if needed (e.g., `gh pr view`, `gh pr diff`)
- git: review diffs if needed

## Example commands
- `gh pr diff <number>`
- `git diff main...HEAD`

## Notes
- Base findings on evidence; label speculation clearly.
