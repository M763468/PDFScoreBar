---
name: pr-creation
description: Create a Pull Request by filling out the repository template.
---

# pr-creation

## Purpose
Streamline the creation of Pull Requests (PRs) by ensuring they follow the project's standard template (`.github/pull_request_template.md`).

## Output (respond in Japanese)
- Created PR URL
- PR creation status
- **Artifact**: `artifacts/pr_creation_result.txt`

## Steps
1) Read `.github/pull_request_template.md` to understand the required sections.
2) Draft the PR body in a temporary file (e.g., `artifacts/pr_body.md`) following the template.
    - Include Goal, Changes, and Verification results.
3) Run `./run.sh "PR Title" artifacts/pr_body.md [base_branch]` to create the PR on GitHub.
4) Read `artifacts/pr_creation_result.txt` to confirm the PR URL.

## Required commands/permissions
- `./run.sh`: script to create PR and log result to `artifacts/`
- gh: to create the PR via CLI

## Example commands
- `./run.sh "feat: add pr-creation skill" artifacts/pr_body.md main`
