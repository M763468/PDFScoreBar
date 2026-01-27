# problem-investigation

## Purpose
Clarify reproduction, hypothesize root causes, and define impact and next investigation steps.

## Input
- Problem summary
- Reproduction steps (if any)
- Expected vs actual behavior

## Output (respond in Japanese)
- Reproduction conditions
- Root-cause hypotheses (prioritized)
- Impact/risk
- Next investigation steps

## Steps
1) Consolidate facts (logs, repro steps, errors).
2) List multiple hypotheses and prioritize them.
3) Describe impact and risk.
4) Propose additional data or verification steps.

## Required commands/permissions
- git: inspect history (e.g., `git log`, `git blame`)
- gh: review issue/PR context if needed

## Example commands
- `rg \"error\" -n`
- `git blame <path>`
- `gh issue view <number>`

## Notes
- Clearly label speculation and pair it with a verification method.
- If the task is investigation-only, do not modify files.
