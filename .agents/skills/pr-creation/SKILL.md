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

Run commands from the repository root.
1) Read `.github/pull_request_template.md` to understand the exact required sections.
2) Draft the PR body in a temporary file (e.g., `artifacts/pr_body.md`).
    - **CRITICAL:** You MUST strictly follow the exact headings provided in `.github/pull_request_template.md` (e.g., `## Related Issue`, `## What`, `## Why`, `## Scope`, `## How to test`, `## Checklist`).
    - **DO NOT** invent custom headings like "Goal", "Done", or "Base branch".
    - Map the work done (goals, changes, verification) into the appropriate template sections.
    - Ensure checklist items (`- [ ]`) are checked (`- [x]`) where applicable.
3) Run `bash .agents/skills/pr-creation/run.sh "PR Title" artifacts/pr_body.md [base_branch]` to create the PR on GitHub.
4) Read `artifacts/pr_creation_result.txt` to confirm the PR URL.

## Required commands/permissions
- `bash .agents/skills/pr-creation/run.sh`: script to create PR and log result to `artifacts/`
- gh: to create the PR via CLI

## Example commands
- `bash .agents/skills/pr-creation/run.sh "feat: add pr-creation skill" artifacts/pr_body.md main`
