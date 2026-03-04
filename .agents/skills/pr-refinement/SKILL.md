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
1) Fetch PR details and all review feedback (including inline comments) using `gh pr view <number> --json title,body,comments,reviews`.
2) Analyze the feedback and identify specific code changes required.
3) **Identify the correct execution environment** by referring to `docs/ENVIRONMENTS.md` (Docker vs Host).
4) Plan the modifications (files to edit, logic to change).
5) Implement the changes according to the repository standards in `AGENTS.md`.
6) Verify the fixes:
    - Run project-specific tests.
    - Run `make format` and `make lint` to ensure style compliance.
7) If behavior changes, update the corresponding documentation (refer to `docs/ai-workflow/WORKFLOW.md`).
8) (Optional) Push changes or comment on the PR summarizing the fixes.

## Required commands/permissions
- gh: to view PR details and reviews (`gh pr view --json`)
- git: to checkout branch, commit, and push changes
- make: to run `make format`, `make lint`

## Example commands
- `gh pr view 123 --json title,body,comments,reviews`
- `gh pr checkout 123`
- `make format && make lint`

## Notes
- Focus on addressing the reviewer's specific concerns.
- Always refer to `docs/ai-workflow/LESSONS.md` to avoid known anti-patterns during refinement.
- If a comment is unclear, ask for clarification before changing code.
