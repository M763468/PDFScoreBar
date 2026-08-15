#!/usr/bin/env bash
# Preserve full-68 MMR stdout/stderr and the Python process exit status.
set -o pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <runner arguments>" >&2
  exit 2
fi

output_dir=""
for ((index = 1; index <= $#; index++)); do
  if [[ "${!index}" == "--output-dir" ]]; then
    next_index=$((index + 1))
    output_dir="${!next_index:-}"
    break
  fi
done
if [[ -z "$output_dir" ]]; then
  echo "--output-dir is required" >&2
  exit 2
fi

mkdir -p "$output_dir"
printf '%s\n' "$(date --iso-8601=seconds) full-68 MMR start" | tee "$output_dir/full68_stdout.log"
PYTHONUNBUFFERED=1 python -u tools/issue274/run_full68_mmr_reuse.py "$@" 2>&1 \
  | tee -a "$output_dir/full68_stdout.log"
status=${PIPESTATUS[0]}
printf '%s\n' "$status" > "$output_dir/full68_exit_code.txt"
printf '%s\n' "$(date --iso-8601=seconds) full-68 MMR end exit_code=$status" \
  | tee -a "$output_dir/full68_stdout.log"
exit "$status"
