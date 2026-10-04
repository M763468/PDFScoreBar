---
name: issue-solver
description: Use when implementing a specific PDFScoreBar GitHub Issue and its acceptance criteria are not already available in the working context.
---

# issue-solver

Fetches the selected Issue as a local reference artifact. Read root `AGENTS.md`, the Issue, and
only the source/tests/docs relevant to its acceptance criteria. Use `develop` as the base for
normal work and work on a topic branch.

Run `bash .agents/skills/issue-solver/run.sh <issue-number>`. The script writes the Issue data to
`artifacts/issue<N>/issue.json`.

Treat the Issue as the scope and validation contract. Implement and validate the requested work,
then review the diff. Do not post comments, push, or otherwise write to GitHub unless the user or
the explicit workflow asks for that action. Never stage with `git add .`.
