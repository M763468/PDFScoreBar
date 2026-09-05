#!/usr/bin/env bash
set -euo pipefail

# Temporary Issue #296 architecture screen. Delete before PR preparation.
#
# Architecture-only comparison:
# - exact same contamination-free v6 dataset/splits for every model
# - ImageNet initialization only; no historical PDFScoreBar checkpoint
# - exact same 20-epoch Iter5 optimizer/augmentation/sampler contract
# - fixed production threshold 0.1 AND validation-derived threshold audit
# - full68 canonical regression + P3 audit
#
# Reruns do not refuse existing partial output: completed model summaries are
# reused, while an incomplete model's work/output is deleted and rerun.

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

PYTHON="${PYTHON:-$ROOT/.venv_cnn_classifier/bin/python}"
DATASET="$ROOT/datasets/issue296_clean_lineage/v6"
OUT="$ROOT/logs/issue296/diagnostic_13_clean_architecture_screen"
TRAIN_CONFIG="$ROOT/configs/cnn_barline_runs/issue44_iter5_rescue/train.yaml"
MODELS=(resnet18 mobilenet_v3_small mobilenet_v3_large efficientnet_b0)

for required in \
  "$PYTHON" \
  "$TRAIN_CONFIG" \
  "$ROOT/tools/issue296/train_architecture_variant.py" \
  "$ROOT/tools/issue296/evaluate_architecture_variant.py" \
  "$ROOT/tools/issue296/architecture_model_factory.py"
do
  if [[ ! -f "$required" ]]; then
    echo "Required file missing: $required" >&2
    exit 3
  fi
done
if [[ ! -d "$DATASET/splits/train/tp" || ! -d "$DATASET/splits/train/fp" || ! -d "$DATASET/splits/val/tp" || ! -d "$DATASET/splits/val/fp" ]]; then
  echo "Clean v6 dataset missing or incomplete: $DATASET" >&2
  exit 3
fi

mkdir -p "$OUT"

for model in "${MODELS[@]}"; do
  MODEL_OUT="$OUT/$model"
  WORK="$ROOT/logs/cnn_barline_classification/issue296_arch_${model}_v6clean"
  CKPT="$WORK/cnn_classifier_best.pth"
  SUMMARY="$MODEL_OUT/architecture_variant_summary.json"

  if [[ -f "$SUMMARY" && -f "$CKPT" ]]; then
    echo "==> $model already complete; reusing $SUMMARY"
    continue
  fi

  echo "==> $model: remove incomplete prior outputs"
  rm -rf "$MODEL_OUT" "$WORK"
  mkdir -p "$MODEL_OUT"

  echo "==> $model: train from ImageNet on corrected clean-v6 data"
  env CNN_DATASET_ROOT="$DATASET" PYTHONPATH=. \
    "$PYTHON" tools/issue296/train_architecture_variant.py \
      --config "$TRAIN_CONFIG" \
      --model-name "$model" \
      --work-dir "$WORK" \
    > "$MODEL_OUT/train.log" 2>&1

  if [[ ! -f "$CKPT" ]]; then
    tail -n 120 "$MODEL_OUT/train.log" >&2 || true
    echo "Expected best checkpoint missing: $CKPT" >&2
    exit 4
  fi

  echo "==> $model: validation calibration, benchmark, full68"
  PYTHONPATH=. "$PYTHON" \
    tools/issue296/evaluate_architecture_variant.py \
      --checkpoint "$CKPT" \
      --model-name "$model" \
      --dataset-root "$DATASET" \
      --output "$MODEL_OUT" \
    > "$MODEL_OUT/evaluate.log" 2>&1

  if [[ ! -f "$SUMMARY" ]]; then
    tail -n 160 "$MODEL_OUT/evaluate.log" >&2 || true
    echo "Architecture summary missing: $SUMMARY" >&2
    exit 5
  fi

done

echo "==> aggregate architecture screen"
PYTHONPATH=. "$PYTHON" - "$OUT" "${MODELS[@]}" > "$OUT/clean_architecture_screen_summary.json" <<'PY'
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
models = sys.argv[2:]
rows = {}
for model in models:
    path = out / model / "architecture_variant_summary.json"
    if not path.is_file():
        raise SystemExit(f"missing completed summary: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    fixed = payload["full68_fixed_0p1"]
    calibrated = payload["full68_val_calibrated"]
    rows[model] = {
        "checkpoint": payload["checkpoint"],
        "parameter_count": payload["benchmark"]["parameter_count"],
        "median_candidates_per_second": payload["benchmark"]["median_candidates_per_second"],
        "validation_best_threshold": payload["validation_calibration"]["best"]["threshold"],
        "validation_best_f1": payload["validation_calibration"]["best"]["f1"],
        "fixed_0p1": {
            "clean": fixed["clean"],
            "delta_vs_control": fixed["delta_vs_control"],
            "target_rejected": fixed["target_x580_acceptance_delta"] is not None
                and fixed["target_x580_acceptance_delta"]["clean_accept"] is False,
            "p3_complete_pairs": fixed["p3"]["clean_complete_pairs"],
            "detector_gate_pass": fixed["detector_gate_pass"],
        },
        "val_calibrated": {
            "threshold": calibrated["threshold"],
            "clean": calibrated["clean"],
            "delta_vs_control": calibrated["delta_vs_control"],
            "target_rejected": calibrated["target_x580_acceptance_delta"] is not None
                and calibrated["target_x580_acceptance_delta"]["clean_accept"] is False,
            "p3_complete_pairs": calibrated["p3"]["clean_complete_pairs"],
            "detector_gate_pass": calibrated["detector_gate_pass"],
        },
        "any_detector_gate_pass": payload["any_detector_gate_pass"],
    }

passing = [name for name, row in rows.items() if row["any_detector_gate_pass"]]
payload = {
    "schema_version": "issue296.clean_architecture_screen.v1",
    "design": {
        "dataset": "datasets/issue296_clean_lineage/v6",
        "labels": "current canonical corrected only",
        "initialization": "torchvision ImageNet only",
        "production_checkpoint_used_for_inference": False,
        "epochs": 20,
        "learning_rate": 1e-4,
        "seed": 44,
        "models": models,
        "thresholds": "fixed 0.1 and validation-derived; no full68/target threshold tuning",
    },
    "models": rows,
    "passing_models": passing,
    "any_model_passes": bool(passing),
}
print(json.dumps(payload, indent=2, ensure_ascii=False))
PY

cat "$OUT/clean_architecture_screen_summary.json"
echo
echo "RESULT=$OUT/clean_architecture_screen_summary.json"
