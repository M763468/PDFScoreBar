---
name: graphify
description: Query or rebuild the repository knowledge graph without external semantic extraction.
---

# Workflow: graphify

Use the existing graph first with `graphify query "<question>"`.

When a graph must be built or fully rebuilt, use:

```bash
graphify extract . --code-only --force
```

For an existing code-only graph, use `graphify update .` for incremental updates.

Do not run semantic extraction over documents, PDFs, or images, and do not configure an external API backend, unless the user explicitly approves that data flow. If Graphify is unavailable or the result is insufficient, fall back to `rg`, `grep`, and direct source inspection.
