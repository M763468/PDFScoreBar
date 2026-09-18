---
name: issue-post-mortem
description: Use for a completed PDFScoreBar investigation when the user asks for a post-mortem or when durable experiment/provenance distillation is explicitly part of the task. Do not post to GitHub automatically.
---

# issue-post-mortem

## Purpose

Distill a completed investigation so later work can recover the accepted result without depending on
a chat transcript.

## Procedure

1. Read the target Issue/PR and the current source/history relevant to the completed work.
2. Record the final disposition and accepted contract.
3. For experiments, preserve the evidence chain:
   `hypothesis -> command/script -> source/candidate commit -> fixed inputs/runtime/model -> result -> disposition`.
4. Mark invalidated or superseded results and explain why they were invalidated.
5. Record unresolved follow-up questions only when they remain actionable.
6. Draft the durable summary in the location requested by the user/task.
7. Post or edit GitHub content only when that write is explicitly requested or already authorized.

## Notes

- Prefer Issue/PR records or a concise repository history document over session transcripts.
- Do not turn temporary action queues, local paths, current container state, or unfinished PASS/FAIL
  status into general project knowledge.
- Respond in Japanese unless the user requests another language.
