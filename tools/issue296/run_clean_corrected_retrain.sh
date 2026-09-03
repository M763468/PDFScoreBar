#!/usr/bin/env bash
set -euo pipefail

# Temporary Issue #296 experiment helper. Delete before PR preparation.
#
# Diagnostic_06: contamination-free classifier reconstruction.
# - reuse the corrected current crops built by diagnostic_05
# - force the whole Va__Prokofiev_Symphony5/page_015 group into train
#   so the corrected x=580 negative is actually learnable
# - DO NOT duplicate/oversample x=580
# - initialize ResNet18 from ImageNet, not any Issue #44 checkpoint
# - use the historical Iter5 20-epoch training schedule
# - keep production threshold=0.1
# - evaluate the same frozen 36-case matched guard set
#
# Retained/container-created source files may be root-owned. Split files are
# therefore symbolic links; this experiment never hard-links or mutates them.

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

PYTHON="${PYTHON:-$ROOT/.venv_cnn_classifier/bin/python}"
SRC_DATASET="$ROOT/datasets/issue296_corrected_finetune"
SRC_AUDIT="$ROOT/logs/issue296/diagnostic_05_corrected_finetune/dataset_audit.json"
DATASET="$ROOT/datasets/issue296_clean_retrain"
OUT="$ROOT/logs/issue296/diagnostic_06_clean_retrain"
WORK="$ROOT/logs/cnn_barline_classification/issue296_clean_retrain_v1"
BASE_GUARDS="$ROOT/logs/issue296/diagnostic_04_matched_guards/matched_guard_set.json"
NEW_GUARDS="$OUT/new_guards/matched_guard_set.json"
TRAIN_CONFIG="$ROOT/configs/cnn_barline_runs/issue44_iter5_rescue/train.yaml"
TARGET_GROUP="Va__Prokofiev_Symphony5_page_015"

if [[ "${1:-}" == "--force" ]]; then
  rm -rf "$DATASET" "$OUT" "$WORK"
elif [[ -e "$DATASET" || -e "$OUT" || -e "$WORK" ]]; then
  echo "Refusing to overwrite prior outputs. Re-run with --force for an intentional rerun." >&2
  exit 2
fi

for required in "$PYTHON" "$SRC_AUDIT" "$BASE_GUARDS" "$TRAIN_CONFIG"; do
  if [[ ! -f "$required" ]]; then
    echo "Required file missing: $required" >&2
    exit 3
  fi
done
for required_dir in "$SRC_DATASET/eval2" "$SRC_DATASET/deepscores"; do
  if [[ ! -d "$required_dir" ]]; then
    echo "Required corrected crop source missing: $required_dir" >&2
    exit 3
  fi
done

mkdir -p "$OUT" "$DATASET"
ln -s "$SRC_DATASET/eval2" "$DATASET/eval2"
ln -s "$SRC_DATASET/deepscores" "$DATASET/deepscores"
if [[ -d "$SRC_DATASET/deepscores_probe" ]]; then
  ln -s "$SRC_DATASET/deepscores_probe" "$DATASET/deepscores_probe"
fi

echo "==> audit diagnostic_05 target split, then rebuild splits with target page in train"
PYTHONPATH=. "$PYTHON" - "$SRC_DATASET" "$SRC_AUDIT" "$DATASET" "$TARGET_GROUP" \
  > "$OUT/split_audit.json" <<'PY'
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from tools.cnn_classifier.build_cnn_dataset import assign_splits, build_samples

src_dataset = Path(sys.argv[1])
src_audit = json.loads(Path(sys.argv[2]).read_text())
out_dataset = Path(sys.argv[3])
target_group = sys.argv[4]

target_crops = [Path(p) for p in src_audit.get("target_fp_crops", [])]
if len(target_crops) != 1:
    raise SystemExit(f"expected exactly one x=580 corrected FP crop, got {target_crops}")
target_crop = target_crops[0].resolve()

old_rows = []
old_csv = src_dataset / "metadata/samples.csv"
if old_csv.is_file():
    with old_csv.open(newline="") as f:
        for row in csv.DictReader(f):
            try:
                candidate = Path(row["path"]).resolve()
            except Exception:
                continue
            if candidate == target_crop:
                old_rows.append(row)

samples = build_samples(out_dataset)
assignments = assign_splits(
    samples,
    {"train": 0.8, "val": 0.1, "test": 0.1},
    seed=44,
    force_train=[target_group],
)

splits_root = out_dataset / "splits"
metadata_root = out_dataset / "metadata"
metadata_root.mkdir(parents=True, exist_ok=True)

rows = []
stats = {"train": {"tp": 0, "fp": 0}, "val": {"tp": 0, "fp": 0}, "test": {"tp": 0, "fp": 0}}
target_new_rows = []
for idx, sample in enumerate(samples):
    split = assignments[sample["path"]]
    label = int(sample["label"])
    kind = "tp" if label == 1 else "fp"
    suffix = sample["path"].suffix
    sample_id = f"{sample['source']}_{sample['group']}_{idx:06d}{suffix}"
    dst = splits_root / split / kind / sample_id
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.symlink_to(sample["path"].resolve())
    row = {
        "sample_id": sample_id,
        "path": str(sample["path"].resolve()),
        "label": label,
        "source": sample["source"],
        "group": sample["group"],
        "split": split,
    }
    rows.append(row)
    stats[split][kind] += 1
    if sample["path"].resolve() == target_crop:
        target_new_rows.append(row)

with (metadata_root / "samples.csv").open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["sample_id", "path", "label", "source", "group", "split"])
    writer.writeheader()
    writer.writerows(rows)
(metadata_root / "stats.json").write_text(json.dumps(stats, indent=2) + "\n")

payload = {
    "target_crop": str(target_crop),
    "diagnostic_05_target_rows": old_rows,
    "clean_retrain_target_rows": target_new_rows,
    "target_group": target_group,
    "stats": stats,
    "sample_count": len(rows),
    "symlink_split_files": True,
}
print(json.dumps(payload, indent=2))

if len(target_new_rows) != 1:
    raise SystemExit(f"expected one target sample in rebuilt split, got {target_new_rows}")
row = target_new_rows[0]
if row["label"] != 0 or row["split"] != "train" or row["group"] != target_group:
    raise SystemExit(f"target is not a single corrected train negative: {row}")
PY
cat "$OUT/split_audit.json"

echo "==> clean ImageNet-initialized ResNet18 retrain (Iter5 schedule, 20 epochs)"
env CNN_DATASET_ROOT="$DATASET" PYTHONPATH=. \
  "$PYTHON" experiments/cnn_classifier/train.py \
    --config "$TRAIN_CONFIG" \
    --work-dir "$WORK" \
  > "$OUT/01_train.log" 2>&1

NEW_CKPT="$WORK/cnn_classifier_best.pth"
if [[ ! -f "$NEW_CKPT" ]]; then
  echo "Training completed without expected best checkpoint: $NEW_CKPT" >&2
  tail -n 100 "$OUT/01_train.log" >&2 || true
  exit 5
fi

echo "==> rescore frozen matched guards"
PYTHONPATH=. "$PYTHON" \
  tools/issue296/rescore_matched_guards.py \
  --checkpoint "$NEW_CKPT" \
  --output "$OUT/new_guards" \
  > "$OUT/02_guard_rescore.log" 2>&1

echo "==> summarize clean-retrain focused A/B"
PYTHONPATH=. "$PYTHON" - "$BASE_GUARDS" "$NEW_GUARDS" "$OUT/split_audit.json" "$NEW_CKPT" \
  > "$OUT/clean_retrain_summary.json" <<'PY'
import json
import sys
from pathlib import Path

old_path, new_path, split_audit_path, checkpoint = map(Path, sys.argv[1:])
old = json.loads(old_path.read_text())
new = json.loads(new_path.read_text())
split_audit = json.loads(split_audit_path.read_text())
threshold = 0.1

old_map = {c["case_id"]: c for c in old["cases"]}
new_map = {c["case_id"]: c for c in new["cases"]}
rows = []
for case_id, before in old_map.items():
    after = new_map[case_id]
    old_score = before.get("rescored_current_checkpoint")
    new_score = after.get("rescored_current_checkpoint")
    rows.append({
        "case_id": case_id,
        "category": before["category"],
        "expected_detector_role": before["expected_detector_role"],
        "old_score": old_score,
        "new_score": new_score,
        "delta": None if old_score is None or new_score is None else new_score - old_score,
        "old_accept": None if old_score is None else old_score > threshold,
        "new_accept": None if new_score is None else new_score > threshold,
    })

target = next(r for r in rows if r["case_id"] == "target_page015_x580")
rescue = next(r for r in rows if r["case_id"] == "iter7_rescue_sibelius_p006")
true_failures = [r for r in rows if r["expected_detector_role"] == "true_barline" and not r["new_accept"]]
new_negative_accepts = [
    r for r in rows
    if r["expected_detector_role"] == "negative"
    and r["case_id"] != "target_page015_x580"
    and r["old_accept"] is False
    and r["new_accept"] is True
]
previously_accepted_negative_changes = [
    r for r in rows
    if r["expected_detector_role"] == "negative" and r["old_accept"] is True
]
focused_pass = (
    target["new_accept"] is False
    and not true_failures
    and not new_negative_accepts
    and rescue["new_accept"] is True
)
payload = {
    "schema_version": "issue296.clean_corrected_retrain_ab.v1",
    "checkpoint": str(checkpoint),
    "initialization": "torchvision ImageNet ResNet18 (no Issue44 init_weights)",
    "training_schedule": "Issue44 Iter5: 20 epochs, lr=1e-4, batch=256, seed=44",
    "threshold": threshold,
    "split_audit": split_audit,
    "target": target,
    "iter7_rescue_control": rescue,
    "true_guard_failures": true_failures,
    "newly_accepted_negative_guards": new_negative_accepts,
    "previously_accepted_negative_changes": previously_accepted_negative_changes,
    "focused_guard_pass": focused_pass,
    "cases": rows,
}
print(json.dumps(payload, indent=2))
PY
cat "$OUT/clean_retrain_summary.json"
echo
echo "RESULT=$OUT/clean_retrain_summary.json"
echo "TRAIN_LOG=$OUT/01_train.log"
echo "GUARDS=$NEW_GUARDS"
