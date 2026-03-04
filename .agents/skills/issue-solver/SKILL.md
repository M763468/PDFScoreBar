---
name: issue-solver
description: Resolve a GitHub issue by planning, implementing changes, and verifying results.
---

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
2) Create a new branch for the issue following the naming convention in `docs/ai-workflow/WORKFLOW.md`.
3) **Identify the correct execution environment** by referring to `docs/ENVIRONMENTS.md` (Docker vs Host).
4) Analyze the codebase to understand the context.
5) Formulate a plan to resolve the issue, strictly adhering to the `Scope` and `Acceptance Criteria` defined in the issue.
6) Implement the plan, following the coding standards in `AGENTS.md`.
7) Verify the changes:
    - Run project-specific tests.
    - Run `make format` and `make lint` to ensure style compliance.
8) Update relevant documentation in `docs/` if necessary.
9) Submit a PR (referencing the issue) or report completion.

## Required commands/permissions
- gh: to view issue (`gh issue view`), create PR (`gh pr create`)
- git: branch, commit, push
- make: to run `make format`, `make lint`

## Example commands
- `gh issue view 42`
- `git checkout -b feature/42-fix-bug`
- `make format && make lint`

## Notes
- Always confirm the scope before making large changes.
- Refer to `docs/ai-workflow/LESSONS.md` to avoid repeating past mistakes.
- Break down complex issues into smaller sub-tasks or consider using `long-horizon-task` skill.
