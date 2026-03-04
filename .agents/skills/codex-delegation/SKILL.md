---
name: codex-delegation
description: Standardize Gemini<->Codex delegation flow for deep-repo reasoning, precise implementation, and sandbox verification.
---

# codex-delegation

## Purpose
Use `codex` as an implementation specialist and repository navigator to perform surgical file edits, run tests, and verify reasoning locally without consuming excessive context in the main Gemini session. Also, utilize Codex for critical reviews of architecture when deeply tied to the repository state.

## Input
- Delegation objective (`implementation`, `test-generation`, `repo-audit`, `read-only-review`, `critical-review`)
- Target files or components (including documentation if for review)
- Clear instructions on what to implement, verify, or review
- Sandbox constraints (`--sandbox read-only` or default)

## Output (respond in Japanese)
- Prompt sent to Codex
- Execution result summary (3-5 lines)
- Evidence (test passed/failed, logs generated, or review feedback)
- Follow-up action if failed (e.g., adjusting prompt, rethinking design)
- Knowledge update target (`CODEX_GEMINI_COLLAB.md` and/or `LESSONS.md`)

## Steps
1. **Check Usage Permission:** Verify if the user has explicitly restricted Codex usage (e.g., "今日はcodexを使わない" / "節約モード"). If restricted, **do not** use this skill unless explicitly overridden.
2. **Environment & Writer Check:** Review `docs/ENVIRONMENTS.md` to ensure you are instructing Codex in the correct context. Explicitly declare the `Single Writer Rule` (Codex will be the sole writer for this phase).
3. **Define Intent:** Clarify the architectural intent, the multi-modal evidence that justifies the change, or the specific architectural concern to be reviewed.
4. **Determine Mode & Seek Approval:** Decide if Codex should edit files or just audit them (use `--sandbox read-only` for non-destructive auditing, reading, or critical reviews). **If the operation will change state (file edits), you MUST present the plan to the user and gain approval before executing.**
5. **Execute:** Run `codex exec` with a clear, self-contained instruction. Include specific context limits if needed. If asking for a critical review, point Codex to the relevant design documentation.
6. **Review:** Wait for Codex to complete. Review its summary, diffs, test results, or feedback.
7. **Iterate:** If tests fail or the review exposes flaws, analyze the failure before modifying the broader plan.
8. **Record Decisions:** Record significant decisions, trade-offs, or useful collaboration patterns in `docs/ai-workflow/CODEX_GEMINI_COLLAB.md`.
9. **Extract Lessons:** Add one reusable rule or anti-pattern to `docs/ai-workflow/LESSONS.md` when applicable.

## Required commands/permissions
- `codex exec "..."`: For implementation, tests, and active repository changes.
- `codex exec --sandbox read-only "..."`: For non-destructive codebase audit, risk analysis, and architectural review.

## Example commands
- `codex exec "src/pipeline/logic.py に、設計で決まった境界条件のチェックを追加し、テストを実行してください。"`
- `codex exec "tests/ 以下の関連テストを実行し、エラー原因を調査して修正案を提示してください。"`
- `codex exec --sandbox read-only "この設計案のリスクを既存の barline_matcher.py の実装と照らし合わせて評価してください。"`
- `codex exec --sandbox read-only "docs/ai-workflow/ にある設計ドキュメントを読み、既存のアーキテクチャに対する批判的なレビューと懸念点を3つ挙げてください。"`

## Notes
- Respect user directives regarding API usage limits. Always pause to consider if a task can be done by Gemini alone if Codex usage is constrained.
- While Gemini usually provides the "why" and "what", Codex can act as a critical reviewer of Gemini's architectural plans when provided with design documentation.
- Codex should handle the "how" (syntax, local repo conventions, type safety).
- Treat Codex's verification as strong evidence for implementation success, but final validation remains with the user's manual local tests.
- Use `codex-delegation` to keep the main Gemini context window clean when tasks involve many files or repetitive testing loops.

