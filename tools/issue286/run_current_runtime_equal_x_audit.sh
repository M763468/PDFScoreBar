#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SOURCE_COMMIT="$(git -C "$PROJECT_ROOT" rev-parse HEAD)"
MANAGER_ROOT="${ISSUE286_RETAINED_ROOT:-$(dirname "$PROJECT_ROOT")/ws_PDFScoreBar}"
IMAGE_REF="${ISSUE286_CURRENT_IMAGE_REF:-pdfscore_pipeline_gpu}"
MANIFEST="${ISSUE286_RETAINED_MANIFEST:-$MANAGER_ROOT/logs/issue294/issue294_full68_fresh_0154e40c/full68_host.json}"
EXPECTED_MANIFEST_SHA="528033693819eee4e6d9913cb794922b3473bb7d4df7ea3ab92f2d7215603fc5"
RESULT="${ISSUE286_RESULT:-$PROJECT_ROOT/logs/issue286/eval/current_runtime_${SOURCE_COMMIT:0:12}/equal_x_audit.json}"

if [[ ! -e "$PROJECT_ROOT/.git" ]]; then
  echo "ERROR: project root is not a Git checkout: $PROJECT_ROOT" >&2
  exit 10
fi
if [[ ! -d "$MANAGER_ROOT/.git" ]]; then
  echo "ERROR: retained manager checkout not found: $MANAGER_ROOT" >&2
  exit 11
fi
if [[ ! -f "$MANIFEST" ]]; then
  echo "ERROR: retained manifest not found: $MANIFEST" >&2
  exit 12
fi

actual_manifest_sha="$(sha256sum "$MANIFEST" | awk '{print $1}')"
if [[ "$actual_manifest_sha" != "$EXPECTED_MANIFEST_SHA" ]]; then
  echo "ERROR: retained manifest SHA mismatch" >&2
  echo "expected=$EXPECTED_MANIFEST_SHA" >&2
  echo "actual=$actual_manifest_sha" >&2
  exit 13
fi

echo "=== Resolve current-compatible PDFScoreBar runtime image ==="
IMAGE_ID="$(python3 scripts/docker_image_resolver.py resolve \
  --repo-root "$PROJECT_ROOT" \
  --image-ref "$IMAGE_REF")"

if [[ -z "$IMAGE_ID" ]]; then
  echo "ERROR: image resolver returned no image ID" >&2
  exit 14
fi

mkdir -p "$(dirname "$RESULT")"

docker_args=(
  --rm
  --user "$(id -u):$(id -g)"
  --workdir "$PROJECT_ROOT"
  --env "HOME=/tmp"
  --env "PYTHONPATH=$PROJECT_ROOT"
  --env "ISSUE286_SOURCE_COMMIT=$SOURCE_COMMIT"
  --mount "type=bind,src=$PROJECT_ROOT,dst=$PROJECT_ROOT"
  --mount "type=bind,src=$MANAGER_ROOT,dst=$MANAGER_ROOT,readonly"
)

echo
echo "=== Issue #286 current-runtime audit provenance ==="
echo "project_root=$PROJECT_ROOT"
echo "manager_root=$MANAGER_ROOT"
echo "requested_image_ref=$IMAGE_REF"
echo "resolved_image_id=$IMAGE_ID"
echo "manifest=$MANIFEST"
echo "manifest_sha256=$actual_manifest_sha"
echo "result=$RESULT"
echo "source_commit=$SOURCE_COMMIT"

echo
echo "=== Current-compatible runtime identity ==="
docker run "${docker_args[@]}" \
  --entrypoint /opt/venv_pipeline/bin/python \
  "$IMAGE_ID" \
  -c 'import importlib.metadata as m, json, sys; names=("numpy","opencv-python-headless","scipy"); print(json.dumps({"python":sys.version,"python_executable":sys.executable,"packages":{name:m.version(name) for name in names}}, indent=2))'

echo
echo "=== Direct CLI smoke in current-compatible runtime ==="
docker run "${docker_args[@]}" \
  --entrypoint /opt/venv_pipeline/bin/python \
  "$IMAGE_ID" \
  tools/issue286/audit_issue294_retained_equal_x.py --help >/dev/null
echo "audit_issue294_retained_equal_x.py: OK"

echo
echo "=== Current-runtime equal-x audit ==="
docker run "${docker_args[@]}" \
  --entrypoint /opt/venv_pipeline/bin/python \
  "$IMAGE_ID" \
  tools/issue286/audit_issue294_retained_equal_x.py \
    --full68-manifest "$MANIFEST" \
    --result "$RESULT"

echo
echo "ISSUE286_CURRENT_RUNTIME_AUDIT_RC=0"
sha256sum "$RESULT"


echo
echo "=== Issue #286 acceptance gates ==="
python3 - "$RESULT" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
summary = data["summary"]

failures = []

if data.get("runtime_contract_drift"):
    failures.append(f"runtime_contract_drift={data['runtime_contract_drift']!r}")
if data.get("contract_drift"):
    failures.append(f"contract_drift={data['contract_drift']!r}")
if summary.get("page_count") != 68:
    failures.append(f"page_count={summary.get('page_count')!r}")
if summary.get("equal_x_tie_page_count") != 16:
    failures.append(
        f"equal_x_tie_page_count={summary.get('equal_x_tie_page_count')!r}"
    )
if summary.get("equal_x_tie_group_count") != 36:
    failures.append(
        f"equal_x_tie_group_count={summary.get('equal_x_tie_group_count')!r}"
    )

selectors = summary.get("selectors") or {}
wider = selectors.get("wider") or {}
if wider.get("logical_changed_from_current_replay_pages"):
    failures.append(
        "wider changed logical numbering/topology: "
        f"{wider.get('logical_changed_from_current_replay_pages')!r}"
    )
if wider.get("geometry_changed_from_current_replay_pages"):
    failures.append(
        "production replay does not match wider-first geometry: "
        f"{wider.get('geometry_changed_from_current_replay_pages')!r}"
    )

for name, selector in selectors.items():
    changed = selector.get("logical_changed_from_current_replay_pages") or []
    if changed:
        failures.append(f"{name} changed logical numbering/topology: {changed!r}")

page = (data.get("pages") or {}).get("Shostakovich-Sym5-Va/page_013") or {}
decisions = (
    ((page.get("selectors") or {}).get("wider") or {}).get("decisions")
    or []
)
target = [
    decision
    for decision in decisions
    if decision.get("x1") == 1788
]
if len(target) != 1:
    failures.append(
        "page_013 expected exactly one wider decision for x1=1788, "
        f"got {target!r}"
    )
elif target[0].get("selected_measure_left_x") != 1799:
    failures.append(
        "page_013 wider representative did not select x2=1799: "
        f"{target[0]!r}"
    )

print("page_count:", summary.get("page_count"))
print("equal_x_tie_page_count:", summary.get("equal_x_tie_page_count"))
print("equal_x_tie_group_count:", summary.get("equal_x_tie_group_count"))
print(
    "wider_logical_changed:",
    wider.get("logical_changed_from_current_replay_pages"),
)
print(
    "wider_geometry_changed:",
    wider.get("geometry_changed_from_current_replay_pages"),
)
print("page_013_x1788_wider_decision:", target)

if failures:
    print("ISSUE286_ACCEPTANCE=FAIL")
    for failure in failures:
        print("FAIL:", failure)
    raise SystemExit(31)

print("ISSUE286_ACCEPTANCE=PASS")
PY
