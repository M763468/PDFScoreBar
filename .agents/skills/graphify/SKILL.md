---
name: graphify
description: Use the existing PDFScoreBar Graphify graph only when the user explicitly asks for Graphify or when a difficult cross-module dependency/call-path question would materially benefit from graph traversal. Direct source/tests are authoritative. Do not install, refresh, rebuild, or run semantic extraction merely because a codebase question was asked.
---

# graphify

## Purpose

Use the committed Graphify graph as an optional navigation aid for complex architecture, dependency,
and call-path questions.

## Default query flow

1. Confirm `graphify-out/graph.json` exists and is relevant to the current branch/revision.
2. Run:

   ```bash
   scripts/graphify_query.sh "<focused question>"
   ```

3. Treat the result as navigation, not authority.
4. Verify material conclusions in current source/tests and canonical architecture docs.
5. If the graph is missing, stale, or insufficient, fall back directly to source search/inspection.

## Refresh/rebuild

Do not refresh or rebuild by default. Only do so when the user/task explicitly requests it or when a
material architecture change requires updating committed Graphify artifacts as part of the change.
Follow `docs/ai-workflow/GRAPHIFY.md` for the refresh contract.

## Semantic extraction

Document/image semantic extraction is opt-in only. Never enable it merely because an API key is
available. Confirm the requested scope and data-safety constraints first.

## References

- `docs/ai-workflow/GRAPHIFY.md`
- `docs/PIPELINE_ARCHITECTURE.md`
