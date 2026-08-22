# Graphify operating procedure

## Purpose

Graphify is the first-pass repository navigation aid for architecture, dependency, call-path,
and relevant-file questions. It narrows the search space; source files, tests, and
`docs/PIPELINE_ARCHITECTURE.md` remain authoritative. Never use a stale graph to override
newer source.

## Agent entry points

The project-scoped Agent Skill is tracked at `.agents/skills/graphify/`. The direct query
entry point is:

```bash
scripts/graphify_query.sh "<question>"
```

The wrapper uses the committed graph immediately. `GRAPHIFY_REFRESH=1` or
`GRAPHIFY_REBUILD=1` performs a local code-only rebuild before the query.

## Installation

Install the official package and project skill in an isolated environment:

```bash
uv tool install graphifyy
graphify install --project --platform agents
```

The committed `.agents/skills/graphify/` files allow compatible agents to discover the skill
without rerunning the installer.

## Shared durable outputs

Commit only portable outputs that improve later local and web-based navigation:

- `graphify-out/graph.json`
- `graphify-out/GRAPH_REPORT.md`
- `graphify-out/wiki/**`
- `graphify-out/MANIFEST.json`

Keep local/ignored:

- Graphify cache/state and `.graphify_*` sidecars;
- internal lowercase `manifest.json`;
- HTML/SVG/GraphML/database exports unless separately requested;
- dated scratch exports and other runtime-only analysis output.

## Code-only refresh

The default unattended path is deterministic local AST extraction only:

```bash
graphify extract . --code-only --force
graphify cluster-only . --no-viz --no-label
graphify export wiki
```

This path does not send source code, documents, PDFs, or images to an LLM API. `--no-label`
avoids LLM-backed community naming.

### Required refresh order for architecture changes

For a change that materially alters the production pipeline:

1. inspect current source/tests and settle the architecture change;
2. update stable/canonical docs, especially `docs/PIPELINE_ARCHITECTURE.md`;
3. commit or otherwise freeze the exact source revision to be graphed;
4. run the code-only Graphify commands above from that revision;
5. update `graphify-out/MANIFEST.json` so `source_base_commit` is the exact revision used;
6. review generated report/wiki/graph changes before committing them.

Do not refresh the graph first and then use it as evidence for the new architecture.

## Post-refresh verification

At minimum verify:

```bash
git rev-parse HEAD
scripts/graphify_query.sh "Trace the current dense production pipeline from detector source generation through MMR. Who owns x4 HOMR support?"
rg -n "current_support_worker|VerifiedProfileHybridDetector|mmr_support_reuse" \
  graphify-out/GRAPH_REPORT.md graphify-out/wiki graphify-out/graph.json
```

For the current two-HOMR architecture, the generated navigation output should lead to:

- `src/pipeline/detection/profile_hybrid.py` / `VerifiedProfileHybridDetector`;
- `src/pipeline/detection/current_support_worker.py` as the x4 HOMR support owner;
- `src/pipeline/mmr_geometry_handoff.py` and `src/pipeline/mmr_support_reuse.py` downstream;
- no current guidance to removed `mmr_staff_geometry_worker.py`, `mmr_geometry_layout.py`, or
  `mmr_staff_support.py`.

Inspect the diff for meaningful node/community/call-path changes rather than blindly
committing timestamp-only churn. If a Graphify version upgrade causes broad serialization
churn, record that fact in the manifest/PR.

## Staleness rule

Refresh shared Graphify artifacts after meaningful **code architecture** changes: stage
ownership, module/call boundaries, major dependency flow, or new/removed architectural
modules. Do not regenerate on every feature branch.

The code-only graph does not ingest Markdown, so a docs-only wording edit does not by itself
require a graph rebuild. However, a docs update that accompanies a code architecture change
must be settled **before** the rebuild so the generated artifacts and canonical docs are
reviewed against the same architecture state.

`MANIFEST.json.source_base_commit` must name the exact commit whose code was extracted. The
query wrapper warns when supported code extensions have changed since that base. A stale or
unavailable base is a signal to verify source directly or rebuild; it is never permission to
trust old graph content.

## Document semantic extraction

Document semantics are opt-in. Do not start them merely because an API key exists.

Permitted routes are:

1. an explicitly selected local coding session; or
2. an explicitly configured Gemini API route after confirming the intended plan/quota and
   project settings will not create unintended additional charges.

For either route, prepare an allowlist, exclude credentials/private data/datasets/logs/models,
record backend/model/scope/source revision in `MANIFEST.json`, and review semantic output
before replacing the shared graph. Commit only the durable merged outputs above.

## Web-based use

GitHub-connected web clients cannot execute the local Graphify CLI. They can use the
committed report/wiki/manifest as navigation aids and then verify current source through the
repository connection. A local Graphify refresh must be performed in an environment where
`graphifyy` is installed; generated outputs must not be hand-edited to simulate a refresh.
