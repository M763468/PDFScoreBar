#!/usr/bin/env bash
set -euo pipefail

# Temporary Issue #296 experiment helper. Delete before PR preparation.
#
# Reconstruct the Issue #44 v5 -> v6 -> v7 training lineage without inheriting
# any contaminated checkpoint.  Historical split exposure and DeepScores crops
# are preserved; eval2 is rebuilt from the historical Issue53 candidate set
# against current canonical GT.  Root-level hard-sample directories are NOT
# injected because the historical trainer reads splits/{train,val} only.

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

PYTHON="${PYTHON:-$ROOT/.venv_cnn_classifier/bin/python}"
BASE="$ROOT/datasets/issue296_clean_lineage"
POOL="$BASE/pool"
V5="$BASE/v5"
V6="$BASE/v6"
V7="$BASE/v7"
OUT="$ROOT/logs/issue296/diagnostic_10_clean_lineage"
WORK5="$ROOT/logs/cnn_barline_classification/issue296_clean_lineage_v5"
WORK6="$ROOT/logs/cnn_barline_classification/issue296_clean_lineage_v6"
WORK7="$ROOT/logs/cnn_barline_classification/issue296_clean_lineage_v7"
CANDIDATES="$ROOT/logs/issue53_full_eval_rescue_v1"
BASE_GUARDS="$ROOT/logs/issue296/diagnostic_04_matched_guards/matched_guard_set.json"
ITER5_AUDIT="$ROOT/logs/issue296/diagnostic_09_iter5_x580/iter5_x580_contamination.json"

if [[ "${1:-}" == "--force" ]]; then
  rm -rf "$BASE" "$OUT" "$WORK5" "$WORK6" "$WORK7"
elif [[ -e "$BASE" || -e "$OUT" || -e "$WORK5" || -e "$WORK6" || -e "$WORK7" ]]; then
  echo "Refusing to overwrite prior clean-lineage outputs. Re-run with --force for an intentional rerun." >&2
  exit 2
fi

required_files=(
  "$PYTHON"
  "$BASE_GUARDS"
  "$ITER5_AUDIT"
  "$ROOT/tools/issue296/build_clean_lineage_datasets.py"
  "$ROOT/tools/issue296/rescore_matched_guards.py"
  "$ROOT/tools/issue296/evaluate_clean_full68.py"
  "$ROOT/configs/cnn_barline_runs/issue44_iter5_rescue/train.yaml"
  "$ROOT/configs/cnn_barline_runs/issue44_iter6_hard_mining/train.yaml"
  "$ROOT/configs/cnn_barline_runs/issue44_iter7_final_rescue/train.yaml"
)
for required in "${required_files[@]}"; do
  if [[ ! -f "$required" ]]; then
    echo "Required file missing: $required" >&2
    exit 3
  fi
done

required_dirs=(
  "$CANDIDATES"
  "$ROOT/datasets/cnn_classifier_v5_rescue_iter1"
  "$ROOT/datasets/cnn_classifier_v6_base"
  "$ROOT/datasets/cnn_classifier_v7_base"
)
for required in "${required_dirs[@]}"; do
  if [[ ! -d "$required" ]]; then
    echo "Required retained directory missing: $required" >&2
    exit 3
  fi
done

mkdir -p "$OUT"

echo "==> preflight confirmed Iter5 contamination"
PYTHONPATH=. "$PYTHON" - "$ITER5_AUDIT" <<'PY'
import json, sys
from pathlib import Path
p = json.loads(Path(sys.argv[1]).read_text())
print({
    "iter5_positive_match_found": p.get("iter5_positive_match_found"),
    "iter5_train_positive_match_found": p.get("iter5_train_positive_match_found"),
    "reconstruction_start": p.get("reconstruction_start"),
})
if not p.get("iter5_train_positive_match_found"):
    raise SystemExit("Iter5 contamination precondition not confirmed")
if p.get("reconstruction_start") != "imagenet_before_iter5":
    raise SystemExit("unexpected reconstruction_start")
PY

echo "==> build corrected eval2 pool and historical-split v5/v6/v7 datasets"
PYTHONPATH=. "$PYTHON" \
  tools/issue296/build_clean_lineage_datasets.py \
    --pool "$POOL" \
    --v5 "$V5" \
    --v6 "$V6" \
    --v7 "$V7" \
    --candidates-root "$CANDIDATES" \
  | tee "$OUT/01_dataset_build.log"

DATASET_SUMMARY="$BASE/clean_lineage_dataset_summary.json"
if [[ ! -f "$DATASET_SUMMARY" ]]; then
  echo "Dataset reconstruction summary missing: $DATASET_SUMMARY" >&2
  exit 4
fi

echo "==> clean Iter5 from ImageNet initialization (20 epochs)"
env CNN_DATASET_ROOT="$V5" PYTHONPATH=. \
  "$PYTHON" experiments/cnn_classifier/train.py \
    --config configs/cnn_barline_runs/issue44_iter5_rescue/train.yaml \
    --work-dir "$WORK5" \
  > "$OUT/02_train_v5.log" 2>&1
CKPT5="$WORK5/cnn_classifier_best.pth"
if [[ ! -f "$CKPT5" ]]; then
  tail -n 100 "$OUT/02_train_v5.log" >&2 || true
  echo "Iter5 checkpoint missing: $CKPT5" >&2
  exit 5
fi

echo "==> clean Iter6 from clean Iter5 (5 epochs)"
env CNN_DATASET_ROOT="$V6" PYTHONPATH=. \
  "$PYTHON" experiments/cnn_classifier/train.py \
    --config configs/cnn_barline_runs/issue44_iter6_hard_mining/train.yaml \
    --work-dir "$WORK6" \
    --init-weights "$CKPT5" \
  > "$OUT/03_train_v6.log" 2>&1
CKPT6="$WORK6/cnn_classifier_best.pth"
if [[ ! -f "$CKPT6" ]]; then
  tail -n 100 "$OUT/03_train_v6.log" >&2 || true
  echo "Iter6 checkpoint missing: $CKPT6" >&2
  exit 5
fi

echo "==> clean Iter7 from clean Iter6 (3 epochs; no root-level 500x injection)"
env CNN_DATASET_ROOT="$V7" PYTHONPATH=. \
  "$PYTHON" experiments/cnn_classifier/train.py \
    --config configs/cnn_barline_runs/issue44_iter7_final_rescue/train.yaml \
    --work-dir "$WORK7" \
    --init-weights "$CKPT6" \
  > "$OUT/04_train_v7.log" 2>&1
CKPT7="$WORK7/cnn_classifier_best.pth"
if [[ ! -f "$CKPT7" ]]; then
  tail -n 100 "$OUT/04_train_v7.log" >&2 || true
  echo "Iter7 checkpoint missing: $CKPT7" >&2
  exit 5
fi

echo "==> rescore frozen matched guards at each clean stage"
for stage in v5 v6 v7; do
  case "$stage" in
    v5) checkpoint="$CKPT5" ;;
    v6) checkpoint="$CKPT6" ;;
    v7) checkpoint="$CKPT7" ;;
  esac
  PYTHONPATH=. "$PYTHON" \
    tools/issue296/rescore_matched_guards.py \
      --checkpoint "$checkpoint" \
      --output "$OUT/guards_$stage" \
    > "$OUT/05_guard_${stage}.log" 2>&1
done

echo "==> final clean-v7 full68 audit on current retained Stage-E candidates"
FULL68_OUT="$OUT/full68_v7"
mkdir -p "$FULL68_OUT"
PYTHONPATH=. "$PYTHON" - "$CKPT7" "$FULL68_OUT" > "$OUT/06_full68.log" 2>&1 <<'PY'
import sys
from pathlib import Path
import tools.issue296.evaluate_clean_full68 as audit

audit.CLEAN_CKPT = Path(sys.argv[1])
audit.OUT = Path(sys.argv[2])
raise SystemExit(audit.main())
PY
FULL68="$FULL68_OUT/clean_full68_summary.json"
if [[ ! -f "$FULL68" ]]; then
  tail -n 120 "$OUT/06_full68.log" >&2 || true
  echo "full68 summary missing: $FULL68" >&2
  exit 6
fi

echo "==> summarize clean-lineage experiment"
PYTHONPATH=. "$PYTHON" - \
  "$DATASET_SUMMARY" \
  "$OUT/guards_v5/matched_guard_set.json" \
  "$OUT/guards_v6/matched_guard_set.json" \
  "$OUT/guards_v7/matched_guard_set.json" \
  "$FULL68" \
  "$CKPT5" "$CKPT6" "$CKPT7" \
  > "$OUT/clean_lineage_summary.json" <<'PY'
import json
import sys
from pathlib import Path

dataset_path, g5_path, g6_path, g7_path, full68_path, c5, c6, c7 = map(Path, sys.argv[1:])
dataset = json.loads(dataset_path.read_text())
full68 = json.loads(full68_path.read_text())
threshold = 0.1

def read_guard(path):
    payload = json.loads(path.read_text())
    return {row["case_id"]: row for row in payload["cases"]}

def stage_summary(path):
    rows = read_guard(path)
    def score(case_id):
        return rows[case_id].get("rescored_current_checkpoint")
    target = score("target_page015_x580")
    rescue = score("iter7_rescue_sibelius_p006")
    true_failures = []
    for row in rows.values():
        value = row.get("rescored_current_checkpoint")
        if row.get("expected_detector_role") == "true_barline" and value is not None and value <= threshold:
            true_failures.append({"case_id": row["case_id"], "score": value})
    return {
        "target_score": target,
        "target_accept": None if target is None else target > threshold,
        "iter7_rescue_score": rescue,
        "iter7_rescue_accept": None if rescue is None else rescue > threshold,
        "true_guard_failures": true_failures,
    }

stages = {
    "v5": stage_summary(g5_path),
    "v6": stage_summary(g6_path),
    "v7": stage_summary(g7_path),
}
control = full68["control"]
clean = full68["clean"]
p3 = full68["p3"]
final_target_rejected = stages["v7"]["target_accept"] is False

detector_gate = (
    full68.get("control_reproduces_canonical_contract") is True
    and final_target_rejected
    and clean["tp"] >= control["tp"]
    and clean["hard_fp"] <= 2
    and clean["fn"] <= control["fn"]
    and p3["pair_count"] == 51
    and p3["clean_complete_pairs"] == 51
)

payload = {
    "schema_version": "issue296.clean_lineage_reconstruction.v1",
    "design": dataset["design"],
    "checkpoints": {"v5": str(c5), "v6": str(c6), "v7": str(c7)},
    "guard_stages": stages,
    "full68_control": control,
    "full68_clean_v7": clean,
    "delta_vs_control": full68["delta_vs_control"],
    "target_x580_acceptance_delta": full68.get("target_x580_acceptance_delta"),
    "p007_known_fp_acceptance_deltas": full68.get("p007_known_fp_acceptance_deltas"),
    "acceptance_delta_count": full68.get("acceptance_delta_count"),
    "p3": p3,
    "residuals": full68.get("residuals", []),
    "detector_gate_pass": detector_gate,
    "detector_gate_definition": {
        "canonical_control_reproduced": True,
        "x580_rejected": True,
        "tp_not_below_control": control["tp"],
        "hard_fp_at_most": 2,
        "fn_at_most": control["fn"],
        "p3_complete_pairs": 51,
    },
}
print(json.dumps(payload, indent=2, ensure_ascii=False))
PY

cat "$OUT/clean_lineage_summary.json"
echo
echo "RESULT=$OUT/clean_lineage_summary.json"
echo "FULL68=$FULL68"
echo "FINAL_CHECKPOINT=$CKPT7"
