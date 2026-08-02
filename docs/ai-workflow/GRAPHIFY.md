# Graphify operating procedure

## Purpose

Graphify is the first-pass repository navigation aid for architecture, dependency, call-path, and relevant-file questions. Its output narrows the search space; source files and tests remain authoritative.

## Agent entry points

The official project-scoped Agent Skill is tracked at `.agents/skills/graphify/`. Its description intentionally covers codebase architecture and file-relationship questions so compatible coding agents can select it proactively.

The repository-specific direct entry point is:

```bash
scripts/graphify_query.sh "<question>"
```

The script uses the committed graph immediately. This makes a fresh clone or worktree useful without first regenerating the graph. `GRAPHIFY_REFRESH=1` performs a local code-only rebuild; `GRAPHIFY_REBUILD=1` explicitly does the same even when a graph already exists.

## Installation

Install the official package and project skill in an isolated environment:

```bash
uv tool install graphifyy
graphify install --project --platform agents
```

The project installation creates `.agents/skills/graphify/SKILL.md` and its `references/` files. These files are committed so a new coding session can discover the skill without rerunning the installer.

## Shared durable outputs

Commit only portable results that improve later local and web-based repository navigation:

- `graphify-out/graph.json`: canonical queryable graph. It contains structural code results and, after an explicitly approved semantic refresh, merged semantic nodes and relationships.
- `graphify-out/GRAPH_REPORT.md`: human-readable graph and community summary.
- `graphify-out/wiki/**`: agent- and web-readable community/semantic map.
- `graphify-out/MANIFEST.json`: provenance, generation mode, semantic route and scope, version, size, and portability checks.

The following remain local and ignored:

- HTML/SVG/GraphML and database exports unless separately requested.
- `.graphify_*` analysis, label, root, interpreter, and temporary extraction files.
- `cache/`, converted sidecars, and Graphify's internal lowercase `manifest.json`.

The internal cache is useful in the workspace that generated it but is not necessary to query the committed graph. Not committing it avoids large, environment-specific churn.

## Code graph generation

The default and unattended path is local AST extraction only:

```bash
graphify extract . --code-only --force
graphify cluster-only . --wiki --no-viz
```

This path does not send source code, documents, PDFs, or images to an LLM API. It skips non-code files and then derives communities, `GRAPH_REPORT.md`, and the wiki from the existing code graph.

Refresh shared artifacts after meaningful architectural changes, not on every feature branch. Ordinary worktrees should use the committed graph first and inspect branch-specific changes directly.

## Document semantic extraction

Document semantics are opt-in. Do not start them merely because an API key exists in the environment.

Two routes are permitted when document understanding is needed:

1. **Local coding-session route**: explicitly assign extraction to a selected coding session. This may use the coding provider's model and data path; it is not necessarily offline. Apply the provider's data-handling policy and limit the input paths.
2. **Gemini API route**: explicitly set `GEMINI_API_KEY` or `GOOGLE_API_KEY` and use Graphify's Gemini backend only after confirming that the intended Google AI plan/quota and project settings will not create unintended additional charges. Never store the key in Git or repository files.

For either route:

- Prepare an allowlist of documentation paths before extraction.
- Exclude credentials, private notes, datasets, generated logs, model files, and other sensitive content.
- Record the route, backend/model, allowlisted scope, source revision, and Graphify version in `MANIFEST.json`.
- Review the semantic result before replacing the shared graph.
- Commit only the merged `graph.json`, `GRAPH_REPORT.md`, `wiki/**`, and provenance manifest. Keep semantic batch files and caches local.

A semantic refresh may be done in a dedicated session and PR when the output is substantial. The code-only graph remains a safe baseline.

## Web-based use

GitHub-connected web clients cannot execute the local Graphify CLI. They can still use the committed `GRAPH_REPORT.md`, wiki, provenance manifest, and repository-relative paths as navigation aids. The committed `graph.json` also remains available to environments that can download the repository and run Graphify.

## Verification rule

Treat Graphify output as navigation evidence, not final truth. Confirm relevant source and tests. If the graph is stale, unavailable, or too broad, fall back promptly to `rg`, `grep`, and direct inspection.
