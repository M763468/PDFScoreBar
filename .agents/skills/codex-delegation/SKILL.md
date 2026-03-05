---
name: codex-delegation
description: Standardize Gemini<->Codex delegation flow for deep-repo reasoning, precise implementation, and sandbox verification.
---

# codex-delegation

## Purpose
Use `codex` as an implementation specialist and repository navigator to perform surgical file edits, run tests, and verify reasoning locally without consuming excessive context in the main Gemini session. Also, utilize Codex for critical reviews of architecture when deeply tied to the repository state.

## Input
- Delegation objective:
  - `implementation`: For writing code or making surgical file edits.
  - `test-generation`: For creating or updating tests.
  - `repo-audit`: For deep, non-destructive navigation and analysis of the codebase.
  - `read-only-review`: For non-destructive code review of a specific file or component.
  - `critical-review`: For finding flaws and risks in architectural plans or design documents.
- Target files or components (including documentation if for review)
- Clear instructions on what to implement, verify, or review
- Sandbox constraints (`--sandbox read-only` or default)

## Output (respond in Japanese)
- Prompt sent to Codex
## Output (respond in Japanese)
- Prompt sent to Codex
- Execution result summary (3-5 lines)
- Evidence (test passed/failed, logs generated, or review feedback)
- Follow-up action if failed
- Knowledge update target
- **Artifact**: `artifacts/codex_result.txt`

## Steps
1. **Check Usage Permission:** Verify restrictions.
2. **Environment & Writer Check:** Review `docs/ENVIRONMENTS.md`.
3. **Define Intent:** Clarify architectural intent.
4. **Determine Mode & Seek Approval:** If file edits, seek approval.
5. **Execute:** Run `./run.sh "instruction" [--sandbox read-only]` to execute via Codex and log to artifacts.
6. **Review Result:** Read `artifacts/codex_result.txt` to verify execution.
7. **Iterate:** Analyze failures before modifying the plan.
8. **Record Decisions:** Update `docs/ai-workflow/CODEX_GEMINI_COLLAB.md`.
9. **Extract Lessons:** Update `docs/ai-workflow/LESSONS.md`.

## Required commands/permissions
- `./run.sh "instruction"`: for implementation and active changes.
- `./run.sh "instruction" --sandbox read-only`: for read-only audits and reviews.

## Example commands
- `./run.sh "src/pipeline/logic.py に、設計で決まった境界条件のチェックを追加し、テストを実行してください。"`
- `./run.sh "この設計案のリスクを既存の実装と照らし合わせて評価してください。" --sandbox read-only`

- `codex exec "src/pipeline/logic.py に、設計で決まった境界条件のチェックを追加し、テストを実行してください。" > artifacts/codex-delegation_results.txt`

## Notes
- Respect user directives regarding API usage limits. Always pause to consider if a task can be done by Gemini alone if Codex usage is constrained.
- While Gemini usually provides the "why" and "what", Codex can act as a critical reviewer of Gemini's architectural plans when provided with design documentation.
- Codex should handle the "how" (syntax, local repo conventions, type safety).
- Treat Codex's verification as strong evidence for implementation success, but final validation remains with the user's manual local tests.
- Use `codex-delegation` to keep the main Gemini context window clean when tasks involve many files or repetitive testing loops.

