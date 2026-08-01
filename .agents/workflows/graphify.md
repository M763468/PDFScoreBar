---
name: graphify
description: Query the committed repository graph before broad code searches and rebuild it only when explicitly needed.
---

# Workflow: graphify

1. Read `docs/ai-workflow/GRAPHIFY.md` for the repository policy.
2. For architecture, dependency, call-path, or relevant-file questions, run:

   ```bash
   scripts/graphify_query.sh "<question>"
   ```

3. Verify returned locations directly in source or tests.
4. Use `GRAPHIFY_REFRESH=1` only for a local worktree refresh and `GRAPHIFY_REBUILD=1` only for an explicit code-only rebuild.
5. Do not perform document semantic extraction unless the user explicitly selects the local coding-session or Gemini API route and approves the path scope.
6. Fall back to `rg`, `grep`, and direct source inspection when Graphify is stale, missing, or insufficient.
