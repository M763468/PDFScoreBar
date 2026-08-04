#!/usr/bin/env bash
set -euo pipefail

# Temporary Issue #255 experiment wrapper. It reuses the valid fresh public
# baseline A/B artifacts and reruns only dense/filter/Issue53/CNN Stage E work.

usage() {
  cat <<'USAGE'
Usage: bash scripts/run_issue255_public_baseline_stage_e.sh [OPTIONS]

Options:
  --run-tag TAG            Required unique tag.
  --public-batch PATH      Completed public-baseline batch.
  --output-root PATH       Default: logs/issue255_stage_e_public_baseline
  --container NAME         Default: pdfscore_pipeline_gpu
  --container-python PATH  Default: /opt/venv_pipeline/bin/python
  --host-python PATH       Default: $PYTHON or python3
  --verbose-dense-logs     Retain verbose dense reconstruction logs.
  -h, --help               Show this help.

The wrapper does not run HOMR, SR HOMR, OMR-DLN, or consensus. It consumes the
retained fresh public-baseline sources, reconstructs Issue36 dense candidates,
applies the historical clef filter and Issue53 route, and runs CNN scoring with
NMS disabled.
USAGE
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(realpath "${script_dir}/..")"
run_tag=""
public_batch="logs/issue255_public_baseline_ab/issue255_public_baseline_ab_02/issue255_public_baseline_batch_issue255_public_baseline_ab_02.json"
output_root="logs/issue255_stage_e_public_baseline"
container_name="${ISSUE255_CONTAINER:-pdfscore_pipeline_gpu}"
container_python="/opt/venv_pipeline/bin/python"
host_python="${PYTHON:-python3}"
verbose_dense_logs=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-tag)
      [[ $# -ge 2 ]] || { echo "--run-tag requires a value" >&2; exit 2; }
      run_tag="$2"; shift 2 ;;
    --public-batch)
      [[ $# -ge 2 ]] || { echo "--public-batch requires a path" >&2; exit 2; }
      public_batch="$2"; shift 2 ;;
    --output-root)
      [[ $# -ge 2 ]] || { echo "--output-root requires a path" >&2; exit 2; }
      output_root="$2"; shift 2 ;;
    --container)
      [[ $# -ge 2 ]] || { echo "--container requires a name" >&2; exit 2; }
      container_name="$2"; shift 2 ;;
    --container-python)
      [[ $# -ge 2 ]] || {
        echo "--container-python requires a path" >&2
        exit 2
      }
      container_python="$2"; shift 2 ;;
    --host-python)
      [[ $# -ge 2 ]] || { echo "--host-python requires a path" >&2; exit 2; }
      host_python="$2"; shift 2 ;;
    --verbose-dense-logs)
      verbose_dense_logs=1; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2 ;;
  esac
done

[[ -n "$run_tag" ]] || { echo "--run-tag is required" >&2; exit 2; }
[[ "$run_tag" =~ ^[A-Za-z0-9._-]+$ ]] || {
  echo "--run-tag contains unsupported characters" >&2
  exit 2
}

cd "$repo_root"
expected_branch="fix/issue255-fresh-detector-production-recovery"
actual_branch="$(git branch --show-current)"
if [[ "$actual_branch" != "$expected_branch" ]]; then
  echo "Wrong branch: expected=$expected_branch actual=$actual_branch" >&2
  exit 2
fi
if [[ -n "$(git status --short)" ]]; then
  echo "Working tree must be clean before a provenance run." >&2
  git status --short >&2
  exit 2
fi
host_head="$(git rev-parse HEAD)"

for command in docker realpath sha256sum tar; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "Required command not found: $command" >&2
    exit 2
  }
done
if ! command -v "$host_python" >/dev/null 2>&1 && [[ ! -x "$host_python" ]]; then
  echo "Host Python not found: $host_python" >&2
  exit 2
fi
if ! docker ps --format '{{.Names}}' | grep -Fxq "$container_name"; then
  echo "Maintained production container is not running: $container_name" >&2
  exit 2
fi
if ! docker exec "$container_name" test -x "$container_python"; then
  echo "Container Python unavailable: ${container_name}:${container_python}" >&2
  exit 2
fi

container_head="$({
  docker exec \
    -w /workspace \
    -e GIT_CONFIG_COUNT=1 \
    -e GIT_CONFIG_KEY_0=safe.directory \
    -e GIT_CONFIG_VALUE_0=/workspace \
    "$container_name" git rev-parse HEAD
} 2>/dev/null || true)"
if [[ "$container_head" != "$host_head" ]]; then
  echo "Container /workspace HEAD differs from host." >&2
  echo "  host:      $host_head" >&2
  echo "  container: ${container_head:-<unavailable>}" >&2
  exit 2
fi

public_batch="$(realpath "$public_batch")"
case "$public_batch" in
  "$repo_root"/*) ;;
  *)
    echo "--public-batch must be inside the repository: $public_batch" >&2
    exit 2 ;;
esac
[[ -f "$public_batch" ]] || {
  echo "Public-baseline batch missing: $public_batch" >&2
  exit 2
}
container_public_batch="/workspace/${public_batch#"$repo_root"/}"

output_root="$(realpath -m "$output_root")"
case "$output_root" in
  "$repo_root"/*) ;;
  *)
    echo "--output-root must be inside the repository: $output_root" >&2
    exit 2 ;;
esac
run_root="${output_root}/${run_tag}"
archive="${run_root}.tar.gz"
for path in "$run_root" "$archive" "${archive}.sha256"; do
  [[ ! -e "$path" ]] || {
    echo "Refusing to overwrite: $path" >&2
    exit 2
  }
done
mkdir -p "$output_root"
container_output_root="/workspace/${output_root#"$repo_root"/}"

uid_gid="$(id -u):$(id -g)"
runner_args=(
  tools/issue255/run_public_baseline_stage_e_reconstruction.py
  --run-tag "$run_tag"
  --public-batch "$container_public_batch"
  --output-root "$container_output_root"
  --expected-commit "$host_head"
)
if [[ "$verbose_dense_logs" -eq 1 ]]; then
  runner_args+=(--verbose-dense-logs)
fi

docker exec \
  --user "$uid_gid" \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  -e HOME=/tmp \
  -e YOLO_CONFIG_DIR=/tmp/issue255_public_stage_e_ultralytics \
  -e GIT_CONFIG_COUNT=1 \
  -e GIT_CONFIG_KEY_0=safe.directory \
  -e GIT_CONFIG_VALUE_0=/workspace \
  "$container_name" \
  "$container_python" \
  "${runner_args[@]}"

report="${run_root}/public_baseline_stage_e_reconstruction_report.json"
"$host_python" - "$report" "$host_head" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

report_path = Path(sys.argv[1])
expected_commit = sys.argv[2]
report = json.loads(report_path.read_text(encoding="utf-8"))
if report.get("status") != "completed":
    raise SystemExit(f"Stage E replay did not complete: {report}")
if report.get("repository", {}).get("commit") != expected_commit:
    raise SystemExit("Report commit does not match executed HEAD")
contract = report.get("reconstruction_contract", {})
expected = {
    "mode": "fresh_upstream",
    "fresh_upstream_authoritative": True,
    "override_keys": [],
    "upstream_inference_repeated": False,
    "historical_detector_candidate_runtime_inputs": [],
    "accepted_reference_runtime_input": False,
}
for key, value in expected.items():
    if contract.get(key) != value:
        raise SystemExit(f"Replay contract mismatch for {key}: {contract.get(key)!r}")
print(
    json.dumps(
        {
            "status": report["status"],
            "gates": report["gates"],
            "report": str(report_path),
        },
        indent=2,
        ensure_ascii=False,
    )
)
PY

tar -czf "$archive" -C "$output_root" "$run_tag"
sha256sum "$archive" > "${archive}.sha256"
echo "Stage E replay package: $archive"
echo "Stage E replay package SHA-256: ${archive}.sha256"
