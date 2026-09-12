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

python "$RECORDER"

# The recorder is idempotent and may find an existing Issue comment for this run.
# Refresh that comment from the now fully-flushed local Markdown record so an
# earlier EXIT-trap snapshot cannot permanently preserve a truncated tee log.
python - <<'PY'
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

root = Path("logs/issue294")
records = list(root.rglob("post277_attempt_record.md"))
if not records:
    raise SystemExit("ERROR: no post277_attempt_record.md found after recorder run")
record = max(records, key=lambda path: path.stat().st_mtime)
body = record.read_text(encoding="utf-8")
marker = body.splitlines()[0] if body else ""
if not marker.startswith("<!-- issue294-post277-run-record:"):
    raise SystemExit(f"ERROR: invalid record marker in {record}: {marker!r}")

repo = "M763468/PDFScoreBar"
issue = 294
existing: dict[str, Any] | None = None
page = 1
while True:
    raw = subprocess.check_output(
        ["gh", "api", f"repos/{repo}/issues/{issue}/comments?per_page=100&page={page}"],
        text=True,
    )
    comments = json.loads(raw)
    for comment in comments:
        if marker in str(comment.get("body", "")):
            existing = comment
            break
    if existing is not None or len(comments) < 100:
        break
    page += 1

if existing is None:
    raise SystemExit(f"ERROR: recorder comment not found for marker {marker}")

if str(existing.get("body", "")) != body:
    payload = json.dumps({"body": body}, ensure_ascii=False)
    subprocess.run(
        [
            "gh",
            "api",
            "--method",
            "PATCH",
            "-H",
            "Content-Type: application/json",
            "--input",
            "-",
            f"repos/{repo}/issues/comments/{existing['id']}",
        ],
        input=payload,
        text=True,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    state = "updated"
else:
    state = "unchanged"

print(
    json.dumps(
        {
            "status": "completed",
            "record": str(record),
            "issue_comment": state,
            "comment_id": existing.get("id"),
        },
        ensure_ascii=False,
    )
)
PY
