---
name: codex-delegation
description: Standardize Gemini<->Codex delegation flow for deep-repo reasoning, precise implementation, and sandbox verification.
---

# codex-delegation

## Purpose
Use `codex` as an implementation specialist and repository navigator to perform surgical file edits, run tests, and verify reasoning locally without consuming excessive context in the main Gemini session.

## Input
- Delegation objective (`implementation`, `test-generation`, `repo-audit`, `read-only-review`)
- Target files or components
- Clear instructions on what to implement or verify
- Sandbox constraints (`--sandbox read-only` or default)

## Output (respond in Japanese)
- Prompt sent to Codex
- Execution result summary (3-5 lines)
- Evidence (test passed/failed, logs generated)
- Follow-up action if failed (e.g., adjusting prompt, rethinking design)
- Knowledge update target (`CODEX_GEMINI_COLLAB.md` and/or `LESSONS.md`)

## Steps
1. **Define Intent:** Clarify the architectural intent or the multi-modal evidence that justifies the change.
2. **Determine Mode:** Decide if Codex should edit files or just audit them (use `--sandbox read-only` for non-destructive auditing/review).
3. **Execute:** Run `codex exec` with a clear, self-contained instruction. Include specific context limits if needed.
4. **Review:** Wait for Codex to complete. Review its summary, diffs, and test results.
5. **Iterate:** If tests fail, analyze the failure (potentially delegating the debugging to Codex again) before modifying the broader plan.
6. **Record Decisions:** Record significant decisions, trade-offs, or useful collaboration patterns in `docs/ai-workflow/CODEX_GEMINI_COLLAB.md`.
7. **Extract Lessons:** Add one reusable rule or anti-pattern to `docs/ai-workflow/LESSONS.md` when applicable.

## Required commands/permissions
- `codex exec "..."`: For implementation, tests, and active repository changes.
- `codex exec --sandbox read-only "..."`: For non-destructive codebase audit and risk analysis.

## Example commands
- `codex exec "src/pipeline/logic.py に、設計で決まった境界条件のチェックを追加し、テストを実行してください。"`
- `codex exec "tests/ 以下の関連テストを実行し、エラー原因を調査して修正案を提示してください。"`
- `codex exec --sandbox read-only "この設計案のリスクを既存の barline_matcher.py の実装と照らし合わせて評価してください。"`

## Notes
- Do not let Codex make architectural decisions independently; Gemini must provide the "why" and "what".
- Codex should handle the "how" (syntax, local repo conventions, type safety).
- Treat Codex's verification as final evidence for implementation success.
- Use `codex-delegation` to keep the main Gemini context window clean when tasks involve many files or repetitive testing loops.
