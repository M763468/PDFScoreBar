---
name: issue-post-mortem
description: Review completed work against an issue and MANDATORILY post a post-mortem summary to the issue. Use after a task is finished to identify leftovers or new sub-tasks.
---

# issue-post-mortem

## Purpose
Review completed work against the original issue to identify any discrepancies, leftovers, or new tasks, and ensure these are documented on the issue.

## Input
- Issue number
- Current codebase state (completed changes)

## Output (respond in Japanese)
- Comparison of AC vs Implementation
- Identified leftovers or next steps
- Created Comment URL (Mandatory)
- **Artifact**: `artifacts/issue_post_mortem_summary.md`

## Steps

Run commands from the repository root.
1) Run `bash .agents/skills/issue-post-mortem/run.sh <issue_number>` to fetch issue and context.
2) Analyze the implementation against the original Goal and Acceptance Criteria.
3) Identify any missed requirements or technical debt introduced.
4) Draft a post-mortem summary in Japanese.
5) **MANDATORY: Post the post-mortem summary to the Issue** using `gh issue comment <issue_number> --body-file artifacts/issue_post_mortem_summary.md`.
6) Report the URL of the created comment.

## Required commands/permissions
- `bash .agents/skills/issue-post-mortem/run.sh`: script to fetch issue data
- gh: CLI tool for issue commenting

## Example commands
- `bash .agents/skills/issue-post-mortem/run.sh 42`
- `gh issue comment 42 --body-file artifacts/issue_post_mortem_summary.md`

## Notes
- Be objective and thorough in the review.
- **CRITICAL**: Documenting the outcome on GitHub is essential for team visibility.
