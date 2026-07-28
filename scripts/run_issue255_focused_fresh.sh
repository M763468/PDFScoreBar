#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: bash scripts/run_issue255_focused_fresh.sh [OPTIONS]

Runs new canonical fresh detector executions for the two Issue #255 focus pages.
Each page receives a distinct run ID. The script writes per-run console logs and a
batch summary that validates the fresh contracts and repository provenance.

Options:
  --python PATH       Python executable. Defaults to $PYTHON or python3.
  --output-root PATH  Output root. Defaults to logs/issue255_focused_fresh.
  --run-tag TAG       Suffix shared by the two run IDs. Defaults to UTC timestamp.
  -h, --help          Show this help.

The current branch must be fix/issue255-fresh-detector-production-recovery and the
tracked working tree must be clean. Existing run directories are never reused.
USAGE
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
python_bin="${PYTHON:-python3}"
output_root="logs/issue255_focused_fresh"
run_tag="$(date -u +%Y%m%dT%H%M%SZ)"
expected_branch="fix/issue255-fresh-detector-production-recovery"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --python)
      [[ $# -ge 2 ]] || { echo "--python requires a path" >&2; exit 2; }
      python_bin="$2"
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

cd "$repo_root"

if [[ ! -x "$python_bin" ]] && ! command -v "$python_bin" >/dev/null 2>&1; then
  echo "Python executable not found: $python_bin" >&2
  exit 2
fi

current_branch="$(git branch --show-current)"
if [[ "$current_branch" != "$expected_branch" ]]; then
  echo "Expected branch ${expected_branch}, got ${current_branch:-<detached>}" >&2
  exit 2
fi

tracked_status="$(git status --short --untracked-files=no)"
if [[ -n "$tracked_status" ]]; then
  echo "Tracked working tree must be clean before authoritative fresh execution:" >&2
  printf '%s\n' "$tracked_status" >&2
  exit 2
fi

if [[ ! "$run_tag" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "--run-tag may contain only letters, digits, dot, underscore and hyphen" >&2
  exit 2
fi

output_root="$(realpath -m "$output_root")"
mkdir -p "$output_root"
status_file="${output_root}/.issue255_focused_fresh_${run_tag}.tsv"
summary_file="${output_root}/issue255_focused_fresh_batch_${run_tag}.json"
: >"$status_file"

head_commit="$(git rev-parse HEAD)"
overall_status=0

runs=(
  "prokofiev|Va_Prokofiev_Symphony1|page_004|data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png"
  "shostakovich|Shostakovich-Sym5-Va|page_014|data/evaluation2/images/Shostakovich-Sym5-Va/page_014.png"
)

for specification in "${runs[@]}"; do
  IFS='|' read -r label score page image <<<"$specification"
  if [[ ! -f "$image" ]]; then
    echo "Focused image not found: $image" >&2
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$label" "$score" "$page" "" "2" "missing image: $image" >>"$status_file"
    overall_status=1
    continue
  fi

  run_id="issue255_${label}_${page}_${run_tag}"
  run_dir="${output_root}/${run_id}"
  console_log="${output_root}/${run_id}.console.log"
  if [[ -e "$run_dir" || -e "$console_log" ]]; then
    echo "Refusing to reuse focused run output: $run_id" >&2
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$label" "$score" "$page" "$run_id" "2" "output already exists" >>"$status_file"
    overall_status=1
    continue
  fi

  echo "==> ${score}/${page}: ${run_id}"
  set +e
  PYTHONPATH=. "$python_bin" tools/issue255/run_focused_fresh_detector.py \
    --image "$image" \
    --score "$score" \
    --page "$page" \
    --run-id "$run_id" \
    --output-root "$output_root" \
    2>&1 | tee "$console_log"
  run_status=${PIPESTATUS[0]}
  set -e

  printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$label" "$score" "$page" "$run_id" "$run_status" "$console_log" >>"$status_file"
  if [[ "$run_status" -ne 0 ]]; then
    overall_status=1
  fi
done

set +e
"$python_bin" - "$status_file" "$summary_file" "$head_commit" "$current_branch" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

status_path = Path(sys.argv[1])
summary_path = Path(sys.argv[2])
expected_commit = sys.argv[3]
expected_branch = sys.argv[4]
expected_fresh = {
    "mode": "fresh_upstream",
    "fresh_upstream_authoritative": True,
    "override_keys": [],
}

entries = []
errors = []
for raw in status_path.read_text(encoding="utf-8").splitlines():
    if not raw:
        continue
    label, score, page, run_id, exit_code_raw, detail = raw.split("\t", 5)
    exit_code = int(exit_code_raw)
    contract_path = status_path.parent / run_id / "issue255_focused_fresh_run_contract.json"
    contract = None
    if run_id and contract_path.is_file():
        contract = json.loads(contract_path.read_text(encoding="utf-8"))

    entry_errors = []
    if exit_code != 0:
        entry_errors.append(f"runner exit code {exit_code}")
    if not isinstance(contract, dict):
        entry_errors.append("missing or invalid run contract")
    else:
        if contract.get("status") != "completed":
            entry_errors.append(f"contract status {contract.get('status')!r}")
        fresh_contract = contract.get("detector_input_contract")
        for key, value in expected_fresh.items():
            if not isinstance(fresh_contract, dict) or fresh_contract.get(key) != value:
                entry_errors.append(f"fresh contract mismatch: {key}")
        repository = contract.get("repository")
        if not isinstance(repository, dict):
            entry_errors.append("repository provenance missing")
        else:
            if repository.get("commit") != expected_commit:
                entry_errors.append("repository commit mismatch")
            if repository.get("branch") != expected_branch:
                entry_errors.append("repository branch mismatch")
            if repository.get("status") not in (None, ""):
                entry_errors.append("repository was dirty during run")
        artifacts = contract.get("artifacts")
        if not isinstance(artifacts, dict):
            entry_errors.append("artifact inventory missing")
        else:
            missing = [
                name
                for name, record in artifacts.items()
                if name != "clef_mask"
                and (not isinstance(record, dict) or record.get("exists") is not True)
            ]
            if missing:
                entry_errors.append("missing artifacts: " + ", ".join(sorted(missing)))

    entries.append(
        {
            "label": label,
            "score": score,
            "page": page,
            "run_id": run_id or None,
            "runner_exit_code": exit_code,
            "detail": detail,
            "contract_path": str(contract_path) if run_id else None,
            "contract": contract,
            "errors": entry_errors,
        }
    )
    errors.extend(f"{score}/{page}: {error}" for error in entry_errors)

summary = {
    "schema_version": "issue255.focused_fresh_batch.v1",
    "status": "completed" if len(entries) == 2 and not errors else "failed",
    "expected_commit": expected_commit,
    "expected_branch": expected_branch,
    "runs": entries,
    "errors": errors,
}
summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps({"status": summary["status"], "summary": str(summary_path)}, ensure_ascii=False))
raise SystemExit(0 if summary["status"] == "completed" else 1)
PY
summary_status=$?
set -e
rm -f "$status_file"

if [[ "$summary_status" -ne 0 ]]; then
  overall_status=1
fi

echo
echo "Focused fresh batch summary: $summary_file"
echo "Repository commit: $head_commit"

if [[ "$overall_status" -ne 0 ]]; then
  echo "Issue #255 focused fresh execution failed. Inspect the batch summary and console logs." >&2
  exit "$overall_status"
fi

echo "Issue #255 focused fresh execution completed for both pages."
