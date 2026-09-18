---
name: issue-creation
description: Use only when the user explicitly asks to draft or create a PDFScoreBar GitHub Issue. Apply the repository Issue template and branch-policy conventions; do not create an Issue for unrelated maintenance just because this skill exists.
---

# issue-creation

## Purpose

Draft or create a repository Issue using the current `.github/ISSUE_TEMPLATE/` structure.

## Procedure

1. Read the matching Issue template and `docs/BRANCH_POLICY.md`.
2. Draft a concise Goal, Scope, Acceptance Criteria/Done items, and How to test when relevant.
3. Use `develop` as the normal base/PR base unless the task is explicitly release/hotfix/promotion work.
4. If the user asked only for a draft, return the draft and do not write to GitHub.
5. If the user explicitly asked to create the Issue, create it and report the URL.

## Notes

- Do not invent an Issue solely to satisfy an agent workflow.
- Keep acceptance criteria verifiable and avoid embedding transient branch HEADs, container state, or
  run-specific paths unless they are genuinely part of the task contract.
- Respond in Japanese unless the user requests another language.
