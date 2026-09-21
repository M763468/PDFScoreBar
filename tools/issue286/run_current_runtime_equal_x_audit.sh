#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MANAGER_ROOT="${ISSUE286_RETAINED_ROOT:-$(dirname "$PROJECT_ROOT")/ws_PDFScoreBar}"
IMAGE_REF="${ISSUE286_CURRENT_IMAGE_REF:-pdfscore_pipeline_gpu}"
MANIFEST="${ISSUE286_RETAINED_MANIFEST:-$MANAGER_ROOT/logs/issue294/issue294_full68_fresh_0154e40c/full68_host.json}"
EXPECTED_MANIFEST_SHA="528033693819eee4e6d9913cb794922b3473bb7d4df7ea3ab92f2d7215603fc5"
RESULT="${ISSUE286_RESULT:-$PROJECT_ROOT/logs/issue286/issue286_current_equal_x_current_runtime.json}"

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
