---
name: problem-investigation
description: Clarify reproduction and root-cause hypotheses, then define impact and next steps.
---

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
1) Consolidate facts (logs in `logs/`, repro steps, errors).
2) **Identify the relevant execution environment** by referring to `docs/ENVIRONMENTS.md` (Docker vs Host) to ensure correct reproduction.
3) Refer to `docs/ai-workflow/LESSONS.md` to see if the issue matches known failure patterns or anti-patterns.
4) List multiple hypotheses and prioritize them based on codebase analysis and environment specifics.
5) Describe impact and risk.
6) Propose additional data collection or specific verification steps (e.g., checking GPU status if it's a model issue).

## Required commands/permissions
- git: inspect history (e.g., `git log`, `git blame`)
- gh: review issue/PR context if needed
- shell: to check logs and run diagnostic commands

## Example commands
- `rg \"error\" -n`
- `git blame <path>`
- `gh issue view <number>`
- `nvidia-smi` (if GPU related)
- `python3 -c \"import torch; print(torch.cuda.is_available())\"` (if CUDA related)

## Notes
- Clearly label speculation and pair it with a verification method.
- **If the task is investigation-only, Do Not modify any files**, as per `AGENTS.md`.
- Be mindful of sandbox limitations regarding CUDA as described in `AGENTS.md`.
