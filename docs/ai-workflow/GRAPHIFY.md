# Graphify operating procedure

## Scope

Graphify is used as a local code-navigation aid. Its output is supporting evidence only; source files and tests remain authoritative.

## Installation

Install the official PyPI package in an isolated tool environment:

```bash
uv tool install graphifyy
```

Verified in GitHub Actions on 2026-08-01 with:

```text
graphify 0.9.31
```

## Privacy-preserving build

This repository defaults to code-only extraction:

```bash
graphify extract . --code-only --force
```

This uses local AST parsing for code and skips documents, PDFs, and images. Do not run semantic extraction or configure an external API backend without explicit approval. A separately approved local backend may be used for document semantics when required.

## Query and update

```bash
graphify query "<question>" --graph graphify-out/graph.json
graphify update .
```

Use `graphify update .` only for an existing code-only graph. After major structural changes, regenerate with the code-only build command above.

## Tracked artifacts

- `graphify-out/GRAPH_REPORT.md`: tracked when generated.
- `graphify-out/wiki/**`: tracked for human and agent navigation.
- Graph data, caches, and local execution metadata remain ignored.

## Verification performed

The PR validation path installs the official `graphifyy` package, creates a code-only graph with no API keys provided, confirms that `graphify-out/graph.json` contains nodes, and executes a query against that graph.
