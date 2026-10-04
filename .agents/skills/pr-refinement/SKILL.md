---
name: pr-refinement
description: Use when reviewing requested changes or feedback on a specific PDFScoreBar pull request.
---

# pr-refinement

Fetches the selected PR description, reviews, comments, and diff for focused refinement. Run
`bash .agents/skills/pr-refinement/run.sh <pr-number>`; artifacts are written under
`artifacts/pr<N>/`.

Classify each feedback item as a question, suggestion, nit, or clear change request. Only implement
clear change requests or changes the user explicitly asks for; ask about ambiguous feedback.
Follow root `AGENTS.md` and `docs/dev/VALIDATION_POLICY.md` to choose checks. Do not post comments,
push, or otherwise write to GitHub unless the user or the explicit workflow asks for that action.
Never stage with `git add .`.
