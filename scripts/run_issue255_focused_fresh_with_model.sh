#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: bash scripts/run_issue255_focused_fresh_with_model.sh [OPTIONS]

Locates and validates the official OMR-DLN measure detector weight before running the
Issue #255 two-page fresh detector batch. This prevents HOMR/SR work from being repeated
when the required external model is unavailable.

Options:
  --python PATH       Python executable. Defaults to $PYTHON or python3.
  --omr-model PATH    Official YOLOv8m_Measures.pt path. If omitted, checks
                      $OMR_DLN_MODEL_PATH, the repository default, then $HOME.
  --output-root PATH  Output root. Defaults to logs/issue255_focused_fresh.
  --run-tag TAG       Required run tag passed to the underlying batch runner.
  -h, --help          Show this help.
USAGE
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
python_bin="${PYTHON:-python3}"
omr_model="${OMR_DLN_MODEL_PATH:-}"
output_root="logs/issue255_focused_fresh"
run_tag=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --python)
      [[ $# -ge 2 ]] || { echo "--python requires a path" >&2; exit 2; }
      python_bin="$2"
      shift 2
      ;;
    --omr-model)
      [[ $# -ge 2 ]] || { echo "--omr-model requires a path" >&2; exit 2; }
      omr_model="$2"
      shift 2
      ;;
    --output-root)
      [[ $# -ge 2 ]] || { echo "--output-root requires a path" >&2; exit 2; }
      output_root="$2"
      shift 2
      ;;
    --run-tag)
      [[ $# -ge 2 ]] || { echo "--run-tag requires a value" >&2; exit 2; }
      run_tag="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

[[ -n "$run_tag" ]] || { echo "--run-tag is required" >&2; exit 2; }
cd "$repo_root"

if [[ ! -x "$python_bin" ]] && ! command -v "$python_bin" >/dev/null 2>&1; then
  echo "Python executable not found: $python_bin" >&2
  exit 2
fi

if [[ -z "$omr_model" ]]; then
  repository_default="external/omr_dln/models/public_models/YOLOv8m_Measures.pt"
  if [[ -f "$repository_default" ]]; then
    omr_model="$repository_default"
  else
    mapfile -t discovered_models < <(
      find "${HOME}" -type f -name 'YOLOv8m_Measures.pt' -print 2>/dev/null | head -n 10
    )
    if [[ "${#discovered_models[@]}" -eq 1 ]]; then
      omr_model="${discovered_models[0]}"
    elif [[ "${#discovered_models[@]}" -gt 1 ]]; then
      echo "Multiple YOLOv8m_Measures.pt files found; select one with --omr-model:" >&2
      printf '  %s\n' "${discovered_models[@]}" >&2
      exit 2
    fi
  fi
fi

if [[ -z "$omr_model" || ! -f "$omr_model" ]]; then
  cat >&2 <<'ERROR'
Official OMR-DLN measure detector weight was not found.

Use the YOLOv8m_Measures.pt measure-detection model from dmgonzalez8/OMR. Then rerun
with --omr-model /absolute/path/to/YOLOv8m_Measures.pt. Historical detector artifacts
must not be substituted for this fresh gate.
ERROR
  exit 2
fi

omr_model="$(realpath "$omr_model")"
if [[ "$(basename "$omr_model")" != "YOLOv8m_Measures.pt" ]]; then
  echo "Unexpected OMR-DLN filename: $omr_model" >&2
  exit 2
fi

output_root="$(realpath -m "$output_root")"
mkdir -p "$output_root"
preflight_json="${output_root}/issue255_omr_dln_preflight_${run_tag}.json"
if [[ -e "$preflight_json" ]]; then
  echo "Refusing to overwrite OMR-DLN preflight: $preflight_json" >&2
  exit 2
fi

set +e
OMR_DLN_MODEL_PATH="$omr_model" PYTHONPATH=. "$python_bin" - \
  "$omr_model" "$preflight_json" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
import traceback
from pathlib import Path

model_path = Path(sys.argv[1]).resolve()
output_path = Path(sys.argv[2]).resolve()
report = {
    "schema_version": "issue255.omr_dln_preflight.v1",
    "status": "running",
    "model_path": str(model_path),
    "python": sys.executable,
}

try:
    from ultralytics import YOLO

    digest = hashlib.sha256()
    with model_path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    model = YOLO(model_path)
    raw_names = model.names
    if isinstance(raw_names, dict):
        names = [str(raw_names[key]) for key in sorted(raw_names)]
    else:
        names = [str(value) for value in raw_names]
    required = {"systemMeasure", "staffMeasure"}
    missing = sorted(required - set(names))
    if missing:
        raise ValueError(
            "The selected weight is not the official OMR measure detector; "
            f"missing classes: {missing}; classes={names}"
        )
    report.update(
        {
            "status": "completed",
            "size_bytes": model_path.stat().st_size,
            "sha256": digest.hexdigest(),
            "task": getattr(model, "task", None),
            "class_names": names,
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

output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps({"status": report["status"], "preflight": str(output_path)}, ensure_ascii=False))
raise SystemExit(0 if report["status"] == "completed" else 1)
PY
preflight_status=$?
set -e

if [[ "$preflight_status" -ne 0 ]]; then
  echo "OMR-DLN preflight failed: $preflight_json" >&2
  exit "$preflight_status"
fi

echo "OMR-DLN preflight passed: $preflight_json"
echo "OMR-DLN model: $omr_model"

OMR_DLN_MODEL_PATH="$omr_model" \
PIPELINE_PYTHON="$python_bin" \
PYTHON="$python_bin" \
bash scripts/run_issue255_focused_fresh.sh \
  --python "$python_bin" \
  --output-root "$output_root" \
  --run-tag "$run_tag"
