---
name: graphify
description: Optional workflow for querying or explicitly refreshing the PDFScoreBar Graphify graph.
---

# Workflow: graphify

1. Read `docs/ai-workflow/GRAPHIFY.md`.
2. For a query, use the existing graph:

   ```bash
   scripts/graphify_query.sh "<focused question>"
   ```

3. Verify material results in current source/tests.
4. Refresh/rebuild only when explicitly requested or when the current task includes updating Graphify
   after a material architecture change.
5. Fall back to direct source inspection when the graph is stale, missing, or insufficient.
