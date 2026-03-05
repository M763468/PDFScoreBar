---
name: issue-post-mortem
description: Review the completed work against the original issue to identify leftovers or new sub-tasks, and comment on the issue.
---

# issue-post-mortem

## Purpose
After completing a task, use this skill to evaluate the changes against the original issue's Acceptance Criteria. This helps identify remaining tasks, unhandled edge cases, or new issues that should be extracted into separate tickets, and records the final status on GitHub.

## Output (respond in Japanese)
- Completion status (Done / Partial / New Issue needed)
- Summary of what was achieved vs what remains
- Proposal for new issues to be created
- **Artifact**: `artifacts/issue_post_mortem.txt`
- **GitHub Comment**: A summary comment posted to the issue.

## Steps
1) Run `./run.sh <issue_number> [base_branch]` to generate the review data.
2) Read `artifacts/issue_post_mortem.txt` to compare original goals with implemented diffs.
3) Check for any "TODO" comments left in the new code.
4) Draft a summary comment (e.g., `artifacts/issue_post_mortem_comment.md`) that covers:
    - Achieved goals (vs AC)
    - Any deferred tasks or newly discovered issues
    - Next steps (Closing the issue or creating a follow-up)
5) Post the comment to the issue using `gh issue comment <issue_number> --body-file artifacts/issue_post_mortem_comment.md`.
6) If complete, propose closing the issue or creating a PR.

## Required commands/permissions
- `./run.sh`: script to gather post-mortem data into `artifacts/`
- gh: to fetch issue details and post comments

## Example commands
- `./run.sh 42 main`
- `gh issue comment 42 --body-file artifacts/issue_post_mortem_comment.md`
