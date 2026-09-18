---
description: Use Graphify only for explicit or genuinely complex cross-module navigation; verify current source directly.
---

## Graphify guidance

- Use `scripts/graphify_query.sh "<question>"` when the user explicitly requests Graphify or a
  difficult dependency/call-path question materially benefits from the existing graph.
- Do not make Graphify a prerequisite for ordinary source inspection.
- Do not install, refresh, rebuild, or semantically enrich Graphify by default.
- Verify important Graphify conclusions against current source/tests.
- If the graph is stale, unavailable, or insufficient, use direct repository search and source
  inspection instead.
