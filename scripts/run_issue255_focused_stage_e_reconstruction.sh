#!/usr/bin/env bash
set -euo pipefail

# Temporary Issue #255 experiment wrapper. Keep only until the historical Stage E
# route is either promoted into the fresh production orchestrator or disproved.

usage() {
  cat <<'USAGE'
Usage: bash scripts/run_issue255_focused_stage_e_reconstruction.sh [OPTIONS]

Freshly runs HOMR/SR/OMR/consensus for the two Issue #255 focused pages, builds a
run-local dense inventory, reconstructs the Issue36 -> clef filter -> Issue53
route, scores it with CNN NMS disabled, traces all eight targets, and packages the
machine-readable evidence.

Options:
  --run-tag TAG            Required unique tag.
  --omr-model PATH         Official YOLOv8m_Measures.pt. If omitted, checks
                           $OMR_DLN_MODEL_PATH, repository default, then $HOME.
  --output-root PATH       Repository-local output root.
                           Default: logs/issue255_stage_e_focused
  --container NAME         Maintained GPU container.
                           Default: pdfscore_pipeline_gpu
  --container-python PATH  Pipeline Python in the container.
                           Default: /opt/venv_pipeline/bin/python
  --host-python PATH       Host Python for report validation. Default: $PYTHON or python3
  --verbose-dense-logs     Retain verbose dense generation/filter logs.
  -h, --help               Show this help.
USAGE
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(realpath "${script_dir}/..")"
run_tag=""
omr_model="${OMR_DLN_MODEL_PATH:-}"
output_root="logs/issue255_stage_e_focused"
container_name="${ISSUE255_CONTAINER:-pdfscore_pipeline_gpu}"
container_python="/opt/venv_pipeline/bin/python"
host_python="${PYTHON:-python3}"
verbose_dense_logs=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-tag)
      [[ $# -ge 2 ]] || { echo "--run-tag requires a value" >&2; exit 2; }
      run_tag="$2"; shift 2 ;;
    --omr-model)
      [[ $# -ge 2 ]] || { echo "--omr-model requires a path" >&2; exit 2; }
      omr_model="$2"; shift 2 ;;
    --output-root)
      [[ $# -ge 2 ]] || { echo "--output-root requires a path" >&2; exit 2; }
      output_root="$2"; shift 2 ;;
    --container)
      [[ $# -ge 2 ]] || { echo "--container requires a name" >&2; exit 2; }
      container_name="$2"; shift 2 ;;
    --container-python)
      [[ $# -ge 2 ]] || { echo "--container-python requires a path" >&2; exit 2; }
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
  echo "--run-tag must contain only letters, digits, '.', '_' or '-'" >&2
  exit 2
}

cd "$repo_root"

current_branch="$(git branch --show-current)"
expected_branch="fix/issue255-fresh-detector-production-recovery"
if [[ "$current_branch" != "$expected_branch" ]]; then
  echo "Wrong branch: expected=$expected_branch actual=$current_branch" >&2
  exit 2
fi
host_head="$(git rev-parse HEAD)"
if [[ -n "$(git status --short)" ]]; then
  echo "Working tree must be clean before a provenance run." >&2
  git status --short >&2
  exit 2
fi

for command in docker sha256sum realpath; do
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
  docker ps --format '  {{.Names}}\t{{.Image}}\t{{.Status}}' >&2
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

if [[ -z "$omr_model" ]]; then
  repository_default="external/omr_dln/models/public_models/YOLOv8m_Measures.pt"
  if [[ -f "$repository_default" ]]; then
    omr_model="$repository_default"
  else
    mapfile -t discovered_models < <(
      find "$HOME" -type f -name YOLOv8m_Measures.pt -print 2>/dev/null | head -n 10
    )
    if [[ "${#discovered_models[@]}" -eq 1 ]]; then
      omr_model="${discovered_models[0]}"
    elif [[ "${#discovered_models[@]}" -gt 1 ]]; then
      echo "Multiple OMR-DLN measure models found; select one with --omr-model:" >&2
      printf '  %s\n' "${discovered_models[@]}" >&2
      exit 2
    fi
  fi
fi
if [[ -z "$omr_model" || ! -f "$omr_model" ]]; then
  echo "Official YOLOv8m_Measures.pt was not found; pass --omr-model." >&2
  exit 2
fi
omr_model="$(realpath "$omr_model")"
[[ "$(basename "$omr_model")" == "YOLOv8m_Measures.pt" ]] || {
  echo "Unexpected OMR-DLN filename: $omr_model" >&2
  exit 2
}

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
  [[ ! -e "$path" ]] || { echo "Refusing to overwrite: $path" >&2; exit 2; }
done
mkdir -p "$output_root"
container_output_root="/workspace/${output_root#"$repo_root"/}"

copied_model_dir=""
case "$omr_model" in
  "$repo_root"/*)
    container_model="/workspace/${omr_model#"$repo_root"/}"
    docker exec "$container_name" test -f "$container_model" || {
      echo "Repository OMR model not visible in container: $container_model" >&2
      exit 2
    }
    ;;
  *)
    model_sha="$(sha256sum "$omr_model" | awk '{print $1}')"
    copied_model_dir="/tmp/issue255_stage_e_omr_${model_sha}"
    container_model="${copied_model_dir}/YOLOv8m_Measures.pt"
    docker exec "$container_name" mkdir -p "$copied_model_dir"
    docker cp "$omr_model" "${container_name}:${container_model}" >/dev/null
    docker exec "$container_name" chmod 0444 "$container_model"
    ;;
esac
cleanup() {
  if [[ -n "$copied_model_dir" ]]; then
    docker exec "$container_name" rm -rf "$copied_model_dir" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

uid_gid="$(id -u):$(id -g)"
common_exec=(
  docker exec
  --user "$uid_gid"
  -w /workspace
  -e PYTHONPATH=/workspace
  -e HOME=/tmp
  -e YOLO_CONFIG_DIR=/tmp/issue255_stage_e_ultralytics
  -e OMR_DLN_MODEL_PATH="$container_model"
  -e GIT_CONFIG_COUNT=1
  -e GIT_CONFIG_KEY_0=safe.directory
  -e GIT_CONFIG_VALUE_0=/workspace
)

preflight_host="${output_root}/issue255_stage_e_preflight_${run_tag}.json"
preflight_container="${container_output_root}/issue255_stage_e_preflight_${run_tag}.json"
"${common_exec[@]}" -i "$container_name" "$container_python" - \
  "$container_model" "$preflight_container" "$host_head" <<'PY'
from __future__ import annotations
import hashlib
import json
import subprocess
import sys
import traceback
from pathlib import Path

model_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
expected_commit = sys.argv[3]
report = {
    "schema_version": "issue255.focused_stage_e_preflight.v1",
    "status": "running",
    "expected_commit": expected_commit,
    "python": sys.executable,
    "model_path": str(model_path),
}
try:
    import torch
    from ultralytics import YOLO

    actual_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    if actual_commit != expected_commit:
        raise ValueError(f"Commit mismatch: {actual_commit} != {expected_commit}")
    digest = hashlib.sha256()
    with model_path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    model = YOLO(model_path)
    names_obj = model.names
    names = (
        [str(names_obj[key]) for key in sorted(names_obj)]
        if isinstance(names_obj, dict)
        else [str(value) for value in names_obj]
    )
    missing = sorted({"systemMeasure", "staffMeasure"} - set(names))
    if missing:
        raise ValueError(f"Wrong OMR model classes: missing={missing} classes={names}")
    required = [
        Path("data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png"),
        Path("data/evaluation2/images/Shostakovich-Sym5-Va/page_014.png"),
        Path("configs/dense_full_pipeline.yaml"),
        Path("tools/issue255/gate05_targets.json"),
        Path("logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth"),
    ]
    absent = [str(path) for path in required if not path.is_file()]
    if absent:
        raise FileNotFoundError(f"Required focused inputs missing: {absent}")
    targets = json.loads(Path("tools/issue255/gate05_targets.json").read_text())
    accepted = [Path(value["accepted_barlines"]) for value in targets["pages"].values()]
    absent_accepted = [str(path) for path in accepted if not path.is_file()]
    if absent_accepted:
        raise FileNotFoundError(
            "Evaluation-only historical Stage E references missing: " + str(absent_accepted)
        )
    report.update(
        {
            "status": "completed",
            "actual_commit": actual_commit,
            "model_sha256": digest.hexdigest(),
            "model_size_bytes": model_path.stat().st_size,
            "model_classes": names,
            "cuda_available": bool(torch.cuda.is_available()),
            "cuda_device_count": int(torch.cuda.device_count()),
            "required_inputs": [str(path) for path in required],
            "accepted_references": [
                {"path": str(path), "role": "evaluation_only_not_runtime_input"}
                for path in accepted
            ],
        }
    )
except Exception as error:  # noqa: BLE001
    report.update(
        {
            "status": "failed",
            "error_type": type(error).__name__,
            "error": str(error),
            "traceback": traceback.format_exc(),
        }
    )
output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
print(json.dumps({"status": report["status"], "output": str(output_path)}))
raise SystemExit(0 if report["status"] == "completed" else 1)
PY

echo "Preflight passed: $preflight_host"

runner_args=(
  tools/issue255/run_focused_stage_e_reconstruction.py
  --run-tag "$run_tag"
  --output-root "$container_output_root"
  --expected-commit "$host_head"
)
if [[ "$verbose_dense_logs" -eq 1 ]]; then
  runner_args+=(--verbose-dense-logs)
fi
"${common_exec[@]}" "$container_name" "$container_python" "${runner_args[@]}"

report="${run_root}/focused_stage_e_reconstruction_report.json"
"$host_python" - "$report" "$host_head" <<'PY'
from __future__ import annotations
import json
import sys
from pathlib import Path

report_path = Path(sys.argv[1])
expected_commit = sys.argv[2]
report = json.loads(report_path.read_text(encoding="utf-8"))
if report.get("status") != "completed":
    raise SystemExit(f"Focused Stage E report did not complete: {report}")
contract = report.get("detector_input_contract", {})
expected = {
    "mode": "fresh_upstream",
    "fresh_upstream_authoritative": True,
    "override_keys": [],
}
for key, value in expected.items():
    if contract.get(key) != value:
        raise SystemExit(f"Fresh contract mismatch for {key}: {contract.get(key)!r}")
if report.get("repository", {}).get("commit") != expected_commit:
    raise SystemExit("Report commit does not match executed HEAD")
print(json.dumps({
    "status": report["status"],
    "gates": report["gates"],
    "report": str(report_path),
}, indent=2, ensure_ascii=False))
PY

tar -czf "$archive" -C "$output_root" "$run_tag"
sha256sum "$archive" > "${archive}.sha256"
echo "Focused package: $archive"
echo "Focused package SHA-256: ${archive}.sha256"
