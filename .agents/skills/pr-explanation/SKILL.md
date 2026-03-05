---
name: pr-explanation
description: Explain PR intent and scope clearly to make review efficient.
---

# pr-explanation

## Purpose
Explain the PR intent and scope to make review efficient.

## Input
- PR diff
- Related issue
- Goal/context

## Output (respond in Japanese)
- Key changes
- Scope (In / Out)
- Test results
- Known trade-offs or concerns
- **Artifacts**: `artifacts/pr_explanation_data.json`, `artifacts/pr_diff.patch`

## Steps
1) Run `./run.sh <pr_number>` to fetch PR data and diff into artifacts.
2) Read `artifacts/pr_explanation_data.json` and `artifacts/pr_diff.patch` to analyze the PR.
3) Summarize goal and context.
4) List key changes succinctly.
5) State scope (In / Out).
6) Include tests and caveats.

## Required commands/permissions
- `./run.sh`: script to fetch PR data into `artifacts/`
- gh: view PR details and reviews

## Example commands
- `./run.sh 123`

## Notes
- Optimize for fast reader comprehension.
