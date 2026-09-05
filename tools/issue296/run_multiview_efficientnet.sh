#!/usr/bin/env bash
set -euo pipefail

# Temporary Issue #296 multi-view experiment. Delete before PR preparation.
# Rerun policy: never refuse prior output. Dataset/eval outputs are rebuilt;
# a completed training checkpoint is reused, while incomplete training is removed.

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

PYTHON="${PYTHON:-$ROOT/.venv_cnn_classifier/bin/python}"
SOURCE_DATASET="$ROOT/datasets/issue296_clean_lineage/v6"
PAIR_DATASET="$ROOT/datasets/issue296_multiview_v6"
WORK="$ROOT/logs/cnn_barline_classification/issue296_multiview_efficientnet_b0_v6clean"
OUT="$ROOT/logs/issue296/diagnostic_15_multiview_efficientnet"
BATCH_SIZE="${BATCH_SIZE:-128}"

for required in \
  "$PYTHON" \
  "$SOURCE_DATASET/metadata/samples.csv" \
  "$ROOT/tools/issue296/build_multiview_dataset.py" \
  "$ROOT/tools/issue296/train_multiview_efficientnet.py" \
  "$ROOT/tools/issue296/evaluate_multiview_efficientnet.py" \
  "$ROOT/tools/issue296/multiview_model.py"
do
  if [[ ! -e "$required" ]]; then
    echo "Required input missing: $required" >&2
    exit 3
  fi
done

mkdir -p "$OUT"

echo "==> rebuild paired tight/context dataset"
PYTHONPATH=. "$PYTHON" tools/issue296/build_multiview_dataset.py \
  --source "$SOURCE_DATASET" \
  --output "$PAIR_DATASET" \
  > "$OUT/build_dataset.log" 2>&1

CKPT="$WORK/cnn_classifier_best.pth"
COMPLETE="$WORK/TRAIN_COMPLETE"
if [[ -f "$CKPT" && -f "$COMPLETE" ]]; then
  echo "==> completed multi-view training found; reusing $CKPT"
else
  echo "==> remove incomplete multi-view training and train from ImageNet"
  rm -rf "$WORK"
  mkdir -p "$WORK"
  PYTHONPATH=. "$PYTHON" tools/issue296/train_multiview_efficientnet.py \
    --dataset "$PAIR_DATASET" \
    --work-dir "$WORK" \
    --epochs 20 \
    --batch-size "$BATCH_SIZE" \
    --learning-rate 0.0001 \
    --weight-decay 0.01 \
    --seed 44 \
    --num-workers 8 \
    --compile \
    > "$OUT/train.log" 2>&1
fi

if [[ ! -f "$CKPT" || ! -f "$COMPLETE" ]]; then
  tail -n 160 "$OUT/train.log" >&2 || true
  echo "Multi-view training did not complete." >&2
  exit 4
fi

echo "==> validation calibration + full68 audit"
rm -rf "$OUT/full68_threshold_0p1" "$OUT/full68_validation_selected"
PYTHONPATH=. "$PYTHON" tools/issue296/evaluate_multiview_efficientnet.py \
  --checkpoint "$CKPT" \
  --dataset "$PAIR_DATASET" \
  --output "$OUT" \
  > "$OUT/evaluate.log" 2>&1

SUMMARY="$OUT/multiview_efficientnet_summary.json"
if [[ ! -f "$SUMMARY" ]]; then
  tail -n 200 "$OUT/evaluate.log" >&2 || true
  echo "Expected summary missing: $SUMMARY" >&2
  exit 5
fi

cat "$SUMMARY"
echo
echo "RESULT=$SUMMARY"
