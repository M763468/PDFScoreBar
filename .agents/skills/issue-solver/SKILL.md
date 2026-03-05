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
- **Artifact**: `artifacts/issue_data.json`

## Steps
1) Run `./run.sh <issue_number>` to fetch issue details into an artifact.
2) Read `artifacts/issue_data.json` to understand the goal and acceptance criteria.
3) Create a new branch following the naming convention.
4) **Identify the correct execution environment** by referring to `docs/ENVIRONMENTS.md`.
5) Analyze the codebase and formulate a plan.
6) Implement the plan, following the coding standards in `AGENTS.md`.
7) Verify the changes with `make test`, `make format`, and `make lint`.
8) Update relevant documentation in `docs/`.
9) Submit a PR or report completion.

## Required commands/permissions
- `./run.sh`: script to fetch issue data into `artifacts/`
- gh: to view issue, create PR
- git: branch, commit, push
- make: to run `make format`, `make lint`, `make test`

## Example commands
- `./run.sh 42`
- `git checkout -b feature/42-fix-bug`
- `make test`

## Notes
- Always confirm the scope before making large changes.
- Refer to `docs/ai-workflow/LESSONS.md` to avoid past mistakes.
