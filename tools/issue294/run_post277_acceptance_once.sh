#!/usr/bin/env bash
set -euo pipefail

# Issue #294 one-shot entrypoint that keeps harness-only failures out of GitHub.
# The existing canonical runner/recorder still writes local logs and records, but
# GitHub API calls are suppressed during execution. A real Issue record is emitted
# only after focused/full68 acceptance evidence actually exists.

PROJECT_ROOT="$(git rev-parse --show-toplevel)"
cd "$PROJECT_ROOT"

CANONICAL="tools/issue294/run_post277_canonical_once.sh"
RECORDER="tools/issue294/record_post277_attempt.sh"
LOG_ROOT="$PROJECT_ROOT/logs/issue294"
REAL_PATH="$PATH"
FAKE_BIN="$(mktemp -d)"

cleanup() {
  rm -rf "$FAKE_BIN"
}
trap cleanup EXIT

cat >"$FAKE_BIN/gh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "auth" && "${2:-}" == "status" ]]; then
  exit 0
fi

if [[ "${1:-}" == "api" ]]; then
  joined=" $* "

  # Comment lookup: expose the newest local record as a synthetic existing comment
  # so the recorder remains idempotent without touching GitHub.
  if [[ "$joined" == *"issues/294/comments?per_page="* ]]; then
    python3 - <<'PY'
from __future__ import annotations

import json
from pathlib import Path

records = list(Path("logs/issue294").rglob("post277_attempt_record.md"))
if not records:
    print("[]")
else:
    record = max(records, key=lambda path: path.stat().st_mtime)
    body = record.read_text(encoding="utf-8")
    print(json.dumps([{"id": 0, "html_url": "suppressed://issue294", "body": body}]))
PY
    exit 0
  fi

  # Synthetic POST/PATCH responses. Consume stdin because the real calls use
  # --input -, but do not send anything to GitHub.
  if [[ "$joined" == *" --method POST "* && "$joined" == *"issues/294/comments"* ]]; then
    cat >/dev/null || true
    printf '%s\n' '{"id":0,"html_url":"suppressed://issue294"}'
    exit 0
  fi
  if [[ "$joined" == *" --method PATCH "* && "$joined" == *"issues/comments/"* ]]; then
    cat >/dev/null || true
    printf '%s\n' '{}'
    exit 0
  fi
fi

echo "ERROR: unsupported suppressed gh invocation: $*" >&2
exit 2
EOF
chmod +x "$FAKE_BIN/gh"

set +e
PATH="$FAKE_BIN:$REAL_PATH" bash "$CANONICAL"
runner_status=$?
set -e

latest_run_log="$(find "$LOG_ROOT" -maxdepth 1 -type f -name 'issue294_post277_full68_*_resume_local.log' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)"
if [[ -z "$latest_run_log" || ! -f "$latest_run_log" ]]; then
  echo "Issue #294 record skipped: no canonical runner log found."
  exit "$runner_status"
fi

run_tag="$(basename "$latest_run_log" _resume_local.log)"
suffix="${run_tag#issue294_post277_full68_}"
focused="$LOG_ROOT/issue294_post277_focused_${suffix}.json"
full68_mmr="$LOG_ROOT/$run_tag/post277_mapping_guarded_mmr.json"

# A focused MMR artifact or a full68 MMR artifact is substantive acceptance
# evidence. Pure container/provenance/lint/setup failures remain local-only.
if [[ -f "$focused" || -f "$full68_mmr" ]]; then
  printf 'Issue #294 acceptance evidence found; publishing canonical run record.\n'
  PATH="$REAL_PATH" bash "$RECORDER"
else
  printf 'Issue #294 record skipped: no focused/full68 acceptance artifact for %s.\n' "$run_tag"
fi

exit "$runner_status"
