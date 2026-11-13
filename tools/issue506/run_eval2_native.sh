#!/usr/bin/env bash
# Native evaluation2 run: every page of each evaluation2 PDF, one job per PDF.
. "$(dirname "$0")/env.sh"
SRC='S:\workspace\ws_PDFScoreBar\PDFScoreBar\.worktrees\issue506'
cd /s/workspace/ws_PDFScoreBar/PDFScoreBar/.worktrees/issue506
export PYTHONPATH="$SRC" PDFSCORE_HOST_SOURCE_COMMIT=$(git rev-parse HEAD)
L="$POC/logs/eval2_native_v2"; mkdir -p "$L"
git rev-parse HEAD > "$L/source_commit.txt"; git status --porcelain > "$L/source_status.txt"
i=0
for pdf in "$POC"/inputs/eval2/*.pdf; do
  i=$((i+1)); name=$(basename "$pdf" .pdf); out="S:/i5f/n$i"
  start=$(date +%s)
  "$POC/venv_cu126/Scripts/python.exe" -m docker.distribution_job "$(cygpath -w "$pdf")" --output "$out" > "$L/$name.log" 2>&1
  echo "$name rc=$? elapsed=$(( $(date +%s) - start ))s out=$out" | tee -a "$L/summary.txt"
done
