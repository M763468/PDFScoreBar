#!/usr/bin/env bash
# Run the PoC worktree natively. Usage: run_native.sh <run-name> [pages...]
. "$(dirname "$0")/env.sh"
NAME=$1; shift
SRC='S:\workspace\ws_PDFScoreBar\PDFScoreBar\.worktrees\issue506'
cd /s/workspace/ws_PDFScoreBar/PDFScoreBar/.worktrees/issue506
export PYTHONPATH="$SRC"
export PDFSCORE_HOST_SOURCE_COMMIT=$(git rev-parse HEAD)
git diff > "$POC/logs/$NAME.source.diff"
start=$(date +%s)
"$POC/venv_cu126/Scripts/python.exe" -m docker.distribution_job "$POCW/inputs/Va_Prokofiev_Symphony1.pdf" --output "${OUT_ROOT:-$POCW/runs}/$NAME" --pages "$@" > "$POC/logs/$NAME.log" 2>&1
rc=$?
echo "rc=$rc elapsed=$(( $(date +%s) - start ))s" | tee -a "$POC/logs/$NAME.log"
