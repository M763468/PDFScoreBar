# Graphify operating procedure

## Purpose

Graphify is an optional repository-navigation aid for complex architecture, dependency, and call-path
questions. Current source, tests, and canonical architecture documentation remain authoritative.

Do not use Graphify as a mandatory first step for ordinary code questions. Do not trust a stale graph
over newer source.

## Querying an existing graph

When Graphify is explicitly requested or materially useful, prefer the existing committed graph:

```bash
scripts/graphify_query.sh "<focused question>"
```

Use the answer to narrow source inspection, then verify important conclusions directly in current
source/tests.

If the graph is missing, stale, or insufficient, fall back to normal repository search immediately.

## Installation

Install Graphify only when the task explicitly requires local Graphify execution or maintenance:

```bash
uv tool install graphifyy
graphify install --project --platform agents
```

Installation is not required merely to answer repository questions.

## Shared durable outputs

Commit only portable outputs that improve later navigation:

- `graphify-out/graph.json`
- `graphify-out/GRAPH_REPORT.md`
- `graphify-out/wiki/**`
- `graphify-out/MANIFEST.json`

Keep cache/state, `.graphify_*` sidecars, internal manifests, and ad-hoc exports local unless a task
explicitly requires them.

## Refresh/rebuild

Refresh committed Graphify artifacts only when the task explicitly includes Graphify maintenance or
a material architecture change makes the committed graph misleading.

For unattended code-only refreshes:

```bash
graphify extract . --code-only --force
graphify cluster-only . --no-viz --no-label
graphify export wiki
```

Recommended order for architecture changes:

1. settle the source/test change;
2. update canonical architecture docs;
3. freeze the exact source revision to be graphed;
4. refresh Graphify from that revision;
5. set `graphify-out/MANIFEST.json.source_base_commit` to that revision;
6. review generated changes before committing them.

Do not refresh the graph first and then use the generated graph as evidence for the architecture
change that has not yet been verified in source.

## Staleness

A stale or unavailable `source_base_commit` is a reason to verify source directly or rebuild when the
task calls for it. It is never permission to treat old graph output as current state.

Do not regenerate Graphify for every feature branch or docs-only change.

## Semantic extraction

Document/image semantic extraction is opt-in. Do not start it because an API key happens to exist.
Confirm the intended scope, data-safety constraints, backend/model, and retention plan first.

## Web-based use

Web clients that cannot execute the local CLI may use committed Graphify output as navigation, then
verify current source through the repository connection. Generated outputs must not be hand-edited to
simulate a refresh.
