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

## Steps
1) Fetch PR details and review comments using `gh pr view <number> --comments`.
2) Analyze the feedback and identify specific code changes required.
3) Plan the modifications (files to edit, logic to change).
4) Implement the changes.
5) Verify the fixes (run tests or linters).
6) (Optional) Push changes or comment on the PR summarizing the fixes.

## Required commands/permissions
- gh: to view PR comments (`gh pr view`)
- git: to checkout branch, commit, and push changes

## Example commands
- `gh pr view 123 --comments`
- `gh pr checkout 123`

## Notes
- Focus on addressing the reviewer's specific concerns.
- If a comment is unclear, ask for clarification before changing code.
