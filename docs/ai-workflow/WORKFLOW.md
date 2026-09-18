# AI-assisted development workflow

This document describes the lightweight repository workflow around `AGENTS.md`. It is not a
second instruction hierarchy and does not require a particular model, skill, or orchestration layer.

## Sources of truth

Use this order for active work:

1. latest user instruction;
2. current Issue/PR when the task is Issue/PR-driven;
3. current source, tests, and Git state;
4. canonical repository docs;
5. relevant historical Issues/PRs and history records.

Do not restore old session state, branch state, container state, or an old "next step" without
revalidation.

## Normal development flow

1. Identify the concrete task and scope.
2. Inspect only the source/docs/history needed for that task.
3. For normal work, branch from `develop`; see `docs/BRANCH_POLICY.md`.
4. Implement the smallest coherent change that satisfies the task.
5. Choose validation from `docs/dev/VALIDATION_POLICY.md`.
6. Review the diff for scope drift and unintended config/dependency/evaluation changes.
7. When requested or already authorized, push/open a PR to the correct base and use
   `.github/pull_request_template.md`.

An Issue is recommended for work that benefits from a durable Goal/Scope/Acceptance Criteria record,
but repository maintenance and other explicitly requested tasks do not require creating an Issue just
to satisfy the workflow.

## Skills

Skills are opt-in accelerators. Ordinary repository operations should use the agent's native
repository/GitHub capabilities unless a narrow project-specific skill is a better fit.

Current project-specific uses include:

- `issue-creation`: apply this repository's Issue-template conventions when the user asks to draft
  or create an Issue;
- `issue-post-mortem`: distill a completed investigation into durable evidence when that record is
  actually needed;
- `graphify`: query an existing graph for a difficult cross-module dependency/call-path question;
- `visual-diff-viewer`: collect relevant OMR images when visual comparison is useful;
- `worktree-manager`: repository-specific worktree setup/management where applicable.

Do not route routine status reporting, Issue/PR reading, PR creation/review, documentation updates,
test generation, dependency inspection, diff explanation, or generic debugging through a dedicated
skill solely because one exists.

## Graphify

Graphify is optional. Prefer direct source/test inspection for local questions. Use the existing
graph when a cross-module architecture or call-path question would benefit from it, then verify
material conclusions against current source. See `docs/ai-workflow/GRAPHIFY.md`.

Do not install, rebuild, refresh, or semantically enrich the graph merely because a codebase question
was asked.

## Cross-model consultation

Codex/Gemini consultation is not part of the default workflow. Use another model only when explicitly
requested or when a difficult task materially benefits from an independent second opinion. Do not
require a role declaration, single-writer ceremony, consultation artifact, session-end lesson, or
repository log for ordinary work.

## GitHub writes

Creating/editing Issues, comments, reviews, branches, and PRs is appropriate when the task requests or
authorizes those actions. A read-only question should not cause an automatic GitHub write.

When shell-based `gh` commands are used for bodies containing shell metacharacters, prefer a body file
or another quoting-safe mechanism. Native GitHub tools may be used directly when available.

## Durable experiment history

For substantial performance/evaluation investigations, preserve accepted/rejected decisions and
reproducible provenance in the relevant Issue/PR or repository history record. Do not preserve entire
chat transcripts or transient action queues.

See root `AGENTS.md` for the actual operational rules.
