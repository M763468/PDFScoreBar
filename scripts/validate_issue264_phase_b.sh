#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

python_bin="${PYTHON:-$repo_root/.venv_pdf/bin/python}"
container="${CONTAINER:-issue264_phase_a_homr}"

echo "=== Phase B focused validation ==="
bash scripts/check_pr_slice.sh \
  issue264-phase-b-mmr-geometry \
  --python "$python_bin"

echo
echo "=== Phase B page_001 real-artifact acceptance ==="
docker exec \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  "$container" \
  /opt/venv_pipeline/bin/python \
  tools/issue264/run_phase_b_page001_acceptance.py
