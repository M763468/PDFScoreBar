---
name: gemini-consultation
description: Standardize Codex<->Gemini consultation flow with long-timeout, network-enabled execution, and evidence logging.
---

# gemini-consultation

## Purpose
Use `gemini-cli` as a structured second opinion during design/debug/mid-review, then convert the result into local decisions and reusable knowledge.

## Input
- Consultation objective (`design`, `debug`, `mid-review`)
- Scope constraints (issue AC, out-of-scope rules)
- Minimal context summary (changed files, logs, assumptions)

## Output (respond in Japanese)
- Prompt sent to Gemini (short summary)
- Gemini answer summary (3-5 lines)
- Adoption decision (`adopted` / `partially_adopted` / `rejected`)
- Evidence note (test/log/reference)
- Knowledge update target (`CODEX_GEMINI_COLLAB.md` and/or `LESSONS.md`)

## Steps
1) Define one focused question and success criteria.
2) Prepare compact context (avoid full-doc paste unless necessary).
3) Run Gemini with network-enabled execution from the start and long timeout.
4) While Gemini is reasoning, continue parallel local thinking (risk list, test plan draft).
5) Summarize Gemini output and validate against local code/tests/logs.
6) Record outcome in `docs/ai-workflow/CODEX_GEMINI_COLLAB.md` log.
7) Add one reusable rule to `docs/ai-workflow/LESSONS.md` when applicable.

## Required commands/permissions
- `gemini -p`: non-interactive consultation
- `timeout`: prevent hanging sessions while allowing deep reasoning
- network-enabled execution path (outside sandbox when required)

## Example commands
- `timeout 180s gemini -p "設計案A/Bのトレードオフを、回帰リスク中心に比較して"`
- `timeout 180s gemini -p "この不具合の原因仮説を優先度順に5つ、切り分け手順つきで挙げて"`

## Notes
- Do not include known-failing first step (e.g., sandbox-first then fallback) as default procedure.
- Treat Gemini output as hypothesis until local evidence confirms it.
- Keep `Single Writer Rule` when applying code edits from consultation outcomes.
