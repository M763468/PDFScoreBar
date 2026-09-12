---
name: issue-post-mortem
description: Review completed work against an issue and MANDATORILY post a durable post-mortem summary to the issue. Use after a task is finished to identify leftovers, preserve experiment provenance, and make transient session context disposable.
---

# issue-post-mortem

## Purpose

Review completed work against the original issue to identify discrepancies, leftovers, new tasks, and the durable evidence needed to understand the investigation later without relying on a chat/session transcript.

## Input

- Issue number
- Current codebase state (completed changes)
- Relevant PR / commit / experiment records

## Output (respond in Japanese)

- Comparison of AC vs Implementation
- Final disposition and accepted contract
- Identified leftovers or next steps
- Experiment/provenance summary when the issue contained experiments
- Invalidated/superseded-result summary when applicable
- Session-distillation check
- Created Comment URL (Mandatory)
- **Artifact**: `artifacts/issue_post_mortem_summary.md`

## Steps

Run commands from the repository root.

1. Run `bash .agents/skills/issue-post-mortem/run.sh <issue_number>` to fetch issue and context.
2. Analyze the implementation against the original Goal and Acceptance Criteria.
3. Identify any missed requirements or technical debt introduced.
4. Reconstruct the important durable evidence chain where applicable:
   `hypothesis -> script/command -> source/candidate commit -> fixed inputs/provenance -> result -> disposition`.
5. Mark results that were invalidated or superseded by harness, environment, provenance, coordinate/index, serialization-contract, or later-evidence corrections. Do not average them with the corrected result.
6. Verify that the final accepted PR/commit, validation result, and follow-up Issue(s) are explicit.
7. Check whether any important user decision or technical conclusion exists only in the current chat/session. If so, include it in the durable post-mortem before treating the session as disposable.
8. Draft the post-mortem summary in Japanese.
9. **MANDATORY: Post the post-mortem summary to the Issue** using `gh issue comment <issue_number> --body-file artifacts/issue_post_mortem_summary.md`.
10. Report the URL of the created comment.

## Required post-mortem fields

Use the fields that apply; do not manufacture values for work that did not occur.

- Issue / PR / final commit
- Final disposition: implemented / retained / rejected / superseded / investigation-only
- Acceptance-criteria status
- Canonical validation command/result
- Important experiment table or concise list:
  - purpose/hypothesis
  - script/command
  - commit/ref
  - fixed input/config/model/runtime provenance when material
  - result
  - disposition
- Invalidated/superseded evidence and reason
- Reusable regression guards / tests / durable docs
- Retained external artifacts and provenance rule, when required
- Follow-up Issues
- `session_distillation`:
  - `durable_state_complete: true|false`
  - `chat_only_decisions_remaining: true|false`
  - short explanation

`durable_state_complete=true` means the important technical history can be recovered from GitHub/source/tests/docs without the current chat transcript. It does **not** mean local logs or large generated artifacts must be committed.

## Required commands/permissions

- `bash .agents/skills/issue-post-mortem/run.sh`: script to fetch issue data
- `gh`: CLI tool for issue commenting

## Example commands

- `bash .agents/skills/issue-post-mortem/run.sh 42`
- `gh issue comment 42 --body-file artifacts/issue_post_mortem_summary.md`

## Notes

- Be objective and thorough in the review.
- **CRITICAL**: Documenting the outcome on GitHub is essential for team visibility.
- Prefer links/references to existing durable docs and Issue comments over copying entire forensic histories into another document.
- Chat transcripts, restart prompts, branch HEAD snapshots, run tags, local paths, and transient blockers are not durable project state by themselves.
- Do not mark a session disposable while important decisions remain only in that session.
