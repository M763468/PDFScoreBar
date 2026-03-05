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
- **Artifact**: `artifacts/investigation_results.txt`

## Steps
1) Run `./run.sh` to collect status and recent logs into an artifact.
2) Read `artifacts/investigation_results.txt` to analyze errors and logs.
3) Consolidate facts (logs, repro steps, errors).
4) **Identify the relevant execution environment** by referring to `docs/ENVIRONMENTS.md`.
5) Refer to `docs/ai-workflow/LESSONS.md` to see if the issue matches known failure patterns.
6) List multiple hypotheses and prioritize them.
7) Describe impact and risk.
8) Propose additional data collection or specific verification steps.

## Required commands/permissions
- `./run.sh`: script to collect logs and status into `artifacts/`
- git: inspect history
- gh: review issue/PR context if needed

## Example commands
- `./run.sh`

## Notes
- Clearly label speculation and pair it with a verification method.
- **If the task is investigation-only, Do Not modify any files**, as per `AGENTS.md`.
- Be mindful of sandbox limitations regarding CUDA as described in `AGENTS.md`.
