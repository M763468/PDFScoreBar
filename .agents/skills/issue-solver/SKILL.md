# issue-solver

## Purpose
Autonomously resolve a GitHub Issue by understanding the goal, planning, implementing changes, and verifying the result.

## Input
- Issue number or URL
- Codebase context

## Output (respond in Japanese)
- Plan of action
- Code changes (commits)
- Verification results (test output)
- PR creation (optional)

## Steps
1) Read the issue details using `gh issue view <number>`.
2) Create a new branch for the issue.
3) Analyze the codebase to understand the context.
4) Formulate a plan to resolve the issue (coding, refactoring, fixing).
5) Implement the plan.
6) Verify the changes (run tests, linters).
7) Submit a PR or report completion.

## Required commands/permissions
- gh: to view issue (`gh issue view`)
- git: branch, commit, push

## Example commands
- `gh issue view 42`
- `git checkout -b feature/issue-42`

## Notes
- Always confirm the scope before making large changes.
- Break down complex issues into smaller sub-tasks.
