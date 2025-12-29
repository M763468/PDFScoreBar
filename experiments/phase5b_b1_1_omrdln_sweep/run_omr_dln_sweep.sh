#!/usr/bin/env bash
set -euo pipefail

RUN_ID=${1:-"$(date +%Y%m%dT%H%M%S)"}
RUN_ROOT="logs/phase5b/b1_1/omrdln_sweep/${RUN_ID}"
LOG_FILE="${RUN_ROOT}/omr_dln_commands.log"

conf_values=(0.1 0.2 0.3 0.4 0.5)
images=(
  "page_3|data/evaluation/images/page_3.png|data/evaluation/annotations/page_003/boxes_sorted.json"
  "page_10|data/training/images/page_10.png|data/training/annotations/page_010/fn_only.json"
  "page_15|data/training/images/page_15.png|data/training/annotations/page_015/fn_only.json"
  "page_001|data/evaluation2/images/Va_Prokofiev_Symphony1/page_001.png|data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_001/fn_only.json"
  "page_004|data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png|data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_004/fn_only.json"
)

mkdir -p "${RUN_ROOT}/omr_dln"

echo "Run ID: ${RUN_ID}" > "${LOG_FILE}"
echo "Conf sweep: ${conf_values[*]}" >> "${LOG_FILE}"

source .venv_omr_dln/bin/activate

for conf in "${conf_values[@]}"; do
  conf_tag=${conf/./p}
  for entry in "${images[@]}"; do
    IFS='|' read -r stem image gt <<< "${entry}"
    out_dir="${RUN_ROOT}/omr_dln/conf_${conf_tag}/${stem}"
    mkdir -p "${out_dir}"
    cmd="python experiments/models/eval_omr_dln.py --image ${image} --gt ${gt} --output-dir ${out_dir} --conf ${conf}"
    echo "CMD: ${cmd}" >> "${LOG_FILE}"
    /usr/bin/time -p bash -c "${cmd}" >> "${LOG_FILE}" 2>&1
  done
  echo "---" >> "${LOG_FILE}"
 done
