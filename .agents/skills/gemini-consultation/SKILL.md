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
- Adoption decision
- Evidence note
- Knowledge update target
- **Artifact**: `artifacts/gemini_consultation.txt`

## Steps

Run commands from the repository root.
1) Define one focused question and success criteria.
2) Prepare compact context.
3) Run `bash .agents/skills/gemini-consultation/run.sh "prompt"` to consult Gemini and log output to artifacts.
4) While Gemini is reasoning, continue parallel local thinking.
5) Read `artifacts/gemini_consultation.txt` and validate results.
6) Record outcome in `docs/ai-workflow/CODEX_GEMINI_COLLAB.md`.
7) Add one reusable rule to `docs/ai-workflow/LESSONS.md`.

## Required commands/permissions
- `bash .agents/skills/gemini-consultation/run.sh "prompt"`: script to consult Gemini and log to `artifacts/`

## Example commands
- `bash .agents/skills/gemini-consultation/run.sh "設計案A/Bのトレードオフを、回帰リスク中心に比較して"`

## Notes
- Treat Gemini output as hypothesis until local evidence confirms it.
- Keep `Single Writer Rule` when applying code edits from consultation outcomes.
