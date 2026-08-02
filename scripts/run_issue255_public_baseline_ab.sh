#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(realpath "${script_dir}/..")"
python_bin="${PYTHON:-python3}"

cd "$repo_root"
exec env PYTHONPATH=. "$python_bin" tools/issue255/run_public_baseline_ab.py "$@"
