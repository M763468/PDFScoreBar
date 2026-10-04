---
name: issue-triage
description: Use when the user asks to prioritize or map dependencies across the open PDFScoreBar Issue backlog.
---

# issue-triage

Run `bash .agents/skills/issue-triage/run.sh` to capture the current open Issue list and a rough
priority/dependency summary in `artifacts/issue_triage.txt`. The script's label and text heuristics
are hints only; verify proposed priority and dependencies against the live Issue descriptions
before recommending an execution order. This is read-only and does not update Issues.
