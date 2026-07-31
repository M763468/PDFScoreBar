#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -eq 0 ]; then
    echo 'Usage: scripts/graphify_query.sh "<question>"' >&2
    exit 2
fi

if ROOT=$(git rev-parse --show-toplevel 2>/dev/null); then
    cd "$ROOT"
fi

GRAPH="graphify-out/graph.json"
MANIFEST="graphify-out/MANIFEST.json"
QUESTION="$*"

if command -v graphify >/dev/null 2>&1; then
    GRAPHIFY=(graphify)
elif command -v uv >/dev/null 2>&1; then
    GRAPHIFY=(uv tool run --from graphifyy graphify)
else
    echo "Graphify is unavailable. Install it with: uv tool install graphifyy" >&2
    exit 127
fi

rebuild_code_graph() {
    "${GRAPHIFY[@]}" extract . --code-only --force
    "${GRAPHIFY[@]}" cluster-only . --wiki --no-viz
}

if [ "${GRAPHIFY_REBUILD:-0}" = "1" ]; then
    rebuild_code_graph
elif [ ! -s "$GRAPH" ]; then
    echo "Shared Graphify graph is missing; creating a local code-only graph." >&2
    rebuild_code_graph
elif [ "${GRAPHIFY_REFRESH:-0}" = "1" ]; then
    # Shared caches are intentionally not committed. A portable local refresh is
    # therefore a deterministic code-only rebuild rather than a cache-dependent update.
    rebuild_code_graph
fi

if [ -f "$MANIFEST" ]; then
    GENERATED_FROM=$(python - "$MANIFEST" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(data.get("generated_from_commit", ""))
PY
    )
    CURRENT_COMMIT=$(git rev-parse HEAD 2>/dev/null || true)
    if [ -n "$GENERATED_FROM" ] && [ -n "$CURRENT_COMMIT" ] && [ "$GENERATED_FROM" != "$CURRENT_COMMIT" ]; then
        echo "Graphify graph was generated from $GENERATED_FROM; verify branch changes directly or set GRAPHIFY_REFRESH=1." >&2
    fi
fi

"${GRAPHIFY[@]}" query "$QUESTION" --graph "$GRAPH"
