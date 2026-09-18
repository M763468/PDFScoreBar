# Codex + Gemini consultation notes

This file is retained only as a historical/optional note. It is not part of the default
PDFScoreBar development workflow.

## Current rule

- Do not delegate to another model by default.
- Do not assign permanent roles such as "architect" or "implementation specialist" to models.
- Do not require a consultation log, mode declaration, single-writer ceremony, or session-end lesson
  for ordinary repository work.
- Use a second model only when the user explicitly asks for it or when an independent opinion
  materially helps with a difficult design/debug/review question.
- Treat any second-model answer as a hypothesis until current source, tests, logs, or runtime
  evidence supports it.

## When consultation can help

Examples include a genuinely ambiguous architecture choice, a difficult debugging problem with
multiple live hypotheses, or an independent review of a high-risk change. The primary agent remains
responsible for checking the repository and validating the result.

## Historical material

Older consultation procedures and logs remain available in Git history and in the Issues/PRs that
recorded the underlying engineering decisions. They should not be copied into new task context unless
they are directly relevant to the active target.
