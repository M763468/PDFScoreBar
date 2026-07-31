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

warn_if_code_changed_since_shared_graph() {
    [ -f "$MANIFEST" ] || return 0
    command -v git >/dev/null 2>&1 || return 0

    local source_base
    source_base=$(python - "$MANIFEST" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(data.get("source_base_commit", data.get("generated_from_commit", "")))
PY
    )
    [ -n "$source_base" ] || return 0

    if ! git cat-file -e "${source_base}^{commit}" 2>/dev/null; then
        echo "Graphify provenance commit $source_base is unavailable; verify relevant source directly." >&2
        return 0
    fi

    if ! git merge-base --is-ancestor "$source_base" HEAD 2>/dev/null; then
        echo "Current history diverges from Graphify base $source_base; verify branch changes directly or set GRAPHIFY_REFRESH=1." >&2
        return 0
    fi

    # The shared graph was generated after applying the Graphify integration files
    # but before committing the generated artifacts. Check only source-code formats,
    # avoiding a permanent false warning caused by the artifact commit itself.
    if ! git diff --quiet "$source_base"..HEAD -- \
        ':(glob)**/*.py' \
        ':(glob)**/*.pyi' \
        ':(glob)**/*.c' \
        ':(glob)**/*.cc' \
        ':(glob)**/*.cpp' \
        ':(glob)**/*.h' \
        ':(glob)**/*.hpp' \
        ':(glob)**/*.rs' \
        ':(glob)**/*.go' \
        ':(glob)**/*.java' \
        ':(glob)**/*.js' \
        ':(glob)**/*.jsx' \
        ':(glob)**/*.ts' \
        ':(glob)**/*.tsx'; then
        echo "Code has changed since the shared Graphify graph base $source_base; verify changed files directly or set GRAPHIFY_REFRESH=1." >&2
    fi
}

warn_if_code_changed_since_shared_graph
"${GRAPHIFY[@]}" query "$QUESTION" --graph "$GRAPH"
