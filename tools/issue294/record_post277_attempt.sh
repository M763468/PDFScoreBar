#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(git rev-parse --show-toplevel)"
cd "$PROJECT_ROOT"

# This wrapper intentionally has a unique filename so a stale local checkout cannot
# silently execute the pre-fix recorder. The required commit is the first version
# that records attempts without requiring the runner's final completed marker.
REQUIRED_RECORDER_COMMIT="8528471ec0012d57a1a5398f46c936754b6eb45f"
HEAD="$(git rev-parse HEAD)"

if ! git merge-base --is-ancestor "$REQUIRED_RECORDER_COMMIT" "$HEAD"; then
  echo "ERROR: stale Issue #294 recorder checkout: HEAD=$HEAD" >&2
  echo "Required recorder commit: $REQUIRED_RECORDER_COMMIT" >&2
  echo "Pull origin/perf/issue294-homr-baseline-refresh before executing this script." >&2
  exit 2
fi

RECORDER="tools/issue294/record_post277_acceptance.py"
if grep -q 'No completed Issue #294 post-#277 runner log' "$RECORDER"; then
  echo "ERROR: stale recorder source detected despite HEAD=$HEAD" >&2
  exit 2
fi

printf 'Issue #294 post-#277 attempt recorder\n'
printf 'collector_head=%s\n' "$HEAD"
printf 'required_recorder_commit=%s\n' "$REQUIRED_RECORDER_COMMIT"

exec python "$RECORDER"
