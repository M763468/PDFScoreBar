---
name: issue-triage
description: Fetch GitHub issues, analyze their dependencies and priority, and propose the execution order.
---

# issue-triage

## Purpose
Gather open GitHub issues and analyze their title, labels, and body to identify priorities and dependencies (e.g., "Depends on #42"). This helps the agent and user decide which issue to tackle first.

## Output (respond in Japanese)
- Triage summary of open issues
- Recommended execution order based on priority and dependencies
- **Artifact**: `artifacts/issue_triage.txt`

## Steps
1) Run `./run.sh` to generate the triage artifact.
2) Read `artifacts/issue_triage.txt` to identify:
    - High-priority issues (labels like `HIGH`, `P0`, `Urgent`).
    - Logical dependencies (issues that mention other issues as requirements).
3) Propose an execution order that resolves dependencies first and prioritizes critical tasks.

## Required commands/permissions
- `./run.sh`: script to fetch and triage issues into `artifacts/`
- gh: to fetch issue data

## Example commands
- `./run.sh`
