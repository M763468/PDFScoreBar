# Project Documentation Index

Use this document as the entry point when onboarding a new contributor or wrapping up a work session. It explains what each artefact under `docs/` covers and when to update it so information stays consistent.

## Quick Navigation
- **Day-to-day work:** `docs/NEXT_SESSION_NOTES.md` (daily start checklist, delta summary, handover log)
- **Development history:** `docs/DEVELOPMENT_LOG.md`
- **Environment reference:** `docs/ENVIRONMENTS.md`
- **Assistant playbook:** `docs/AGENTS.md`
- **Algorithm specs:** `docs/BARLINE_MATCHER.md`

## When to Update What

| Document | Primary Purpose | Update Trigger |
| --- | --- | --- |
| `docs/NEXT_SESSION_NOTES.md` | Daily start checklist and latest deltas | End of focused work blocks or planning discussions |
| `docs/DEVELOPMENT_LOG.md` | Chronological record of major phases and decisions (historical archive) | When a milestone finishes or a new approach is adopted |
| `docs/ENVIRONMENTS.md` | Runtime container facts, data layout, logging policy | Whenever container images, dependencies, or directory policies change |
| `docs/AGENTS.md` | Checklist for AI assistants and automation guidelines | When the bootstrap or execution policy changes |
| `docs/BARLINE_MATCHER.md` | Specification for the shared barline matcher | After algorithm updates that affect matcher behaviour |

## Notes for Contributors
- Keep dated sections in reverse-chronological order so the most recent information is easy to find.
- For `docs/NEXT_SESSION_NOTES.md`, maintain the **最近の差分サマリ**（最新3件）を最新状態にし、詳細な出来事は `docs/DEVELOPMENT_LOG.md` の該当フェーズへ記録する。
- Link back to artefacts (logs, scripts, configs) using repository-relative paths.
- Prefer updating an existing document over duplicating content. If a new document is unavoidable, add it to the table above.
