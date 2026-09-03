#!/usr/bin/env bash
set -euo pipefail

# Temporary Issue #296 experiment helper. Delete before PR preparation.
#
# Controlled experiment:
# - current canonical GT
# - current retained Stage-E candidate distribution
# - historical non-eval2 (DeepScores) source crops reused without regeneration
# - current production ResNet18/crop contract
# - production checkpoint as initialization
# - no x=580-specific oversampling
# - no threshold change
#
# This is deliberately a small corrected-data fine-tune first. If it cannot
# safely repair x=580, the issue moves to a richer model/input experiment.
#
# Retained artifacts under logs/ may have been created by a root-running
# container. Linux fs.protected_hardlinks can therefore reject hard links made
# by the host user even when those files are readable. All retained inputs in
# this experiment are read-only, so mirrors reuse them through symbolic links
# rather than hard links.

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

PYTHON="${PYTHON:-$ROOT/.venv_cnn_classifier/bin/python}"
OUT="$ROOT/logs/issue296/diagnostic_05_corrected_finetune"
DATASET="$ROOT/datasets/issue296_corrected_finetune"
WORK="$ROOT/logs/cnn_barline_classification/issue296_corrected_finetune_v1"
MIRROR="$OUT/current_candidate_mirror"
BASE_GUARDS="$ROOT/logs/issue296/diagnostic_04_matched_guards/matched_guard_set.json"
NEW_GUARDS="$OUT/new_guards/matched_guard_set.json"
PROD_CKPT="$ROOT/logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth"
TRAIN_CONFIG="$ROOT/configs/cnn_barline_runs/issue44_iter7_final_rescue/train.yaml"
RUN_ROOT="$ROOT/logs/issue274_homr_unification_analysis/issue274_two_homr_full68_fresh_01"

if [[ "${1:-}" == "--force" ]]; then
  rm -rf "$OUT" "$DATASET" "$WORK"
elif [[ -e "$OUT" || -e "$DATASET" || -e "$WORK" ]]; then
  echo "Refusing to overwrite prior outputs. Re-run with --force for an intentional rerun." >&2
  exit 2
fi

for required in "$PYTHON" "$BASE_GUARDS" "$PROD_CKPT" "$TRAIN_CONFIG"; do
  if [[ ! -f "$required" ]]; then
    echo "Required file missing: $required" >&2
    exit 3
  fi
done
if [[ ! -d "$RUN_ROOT/runs" ]]; then
  echo "Retained Issue #274 run missing: $RUN_ROOT" >&2
  exit 3
fi

mkdir -p "$OUT" "$MIRROR"

echo "==> preflight canonical GT"
PYTHONPATH=. "$PYTHON" - <<'PY'
import json
from pathlib import Path

root = Path.cwd()
files = sorted((root / "data/evaluation2/annotations").glob("*/page_*/boxes_sorted.json"))
total = sum(len(json.loads(p.read_text())) for p in files)
target_path = root / "data/evaluation2/annotations/Va__Prokofiev_Symphony5/page_015/boxes_sorted.json"
target = [580, 4005, 584, 4115]
rows = json.loads(target_path.read_text())
boxes = [r["barline_location"] for r in rows]
print({"pages": len(files), "gt": total, "target_in_gt": target in boxes})
if len(files) != 68 or total != 3567 or target in boxes:
    raise SystemExit("canonical GT preflight failed")
PY

echo "==> mirror current retained Stage-E scored candidates (read-only symlinks)"
count=0
while IFS= read -r src; do
  page_dir="$(basename "$(dirname "$src")")"
  dst_dir="$MIRROR/$page_dir"
  mkdir -p "$dst_dir"
  ln -s "$src" "$dst_dir/pipeline2_no_peak_scored.json"
  count=$((count + 1))
done < <(
  find "$RUN_ROOT/runs" \
    -path '*/dense_candidate_reconstruction/probe_rescue_candidates/eval2_*/pipeline2_no_peak_scored.json' \
    -type f | sort
)
echo "candidate_pages=$count"
if [[ "$count" -ne 68 ]]; then
  echo "Expected 68 retained candidate pages, got $count" >&2
  exit 4
fi

TARGET_CAND="$MIRROR/eval2_Va__Prokofiev_Symphony5_page_015/pipeline2_no_peak_scored.json"
PYTHONPATH=. "$PYTHON" - "$TARGET_CAND" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
target = [580, 4005, 584, 4115]
data = json.loads(p.read_text())
boxes = [x.get("bbox") if isinstance(x, dict) else x for x in data]
print({"target_candidate_present": target in boxes, "candidate_count": len(boxes)})
if target not in boxes:
    raise SystemExit("target missing from retained current candidate set")
PY

echo "==> reuse historical non-eval2 source crops"
SOURCE_DATASET=""
for candidate in \
  "$ROOT/datasets/cnn_classifier_v6_base" \
  "$ROOT/datasets/cnn_classifier_v5_rescue_iter1"
do
  if [[ -d "$candidate/deepscores" ]]; then
    SOURCE_DATASET="$candidate"
    break
  fi
done
if [[ -z "$SOURCE_DATASET" ]]; then
  echo "No retained Iter5/Iter6 DeepScores source crop directory found." >&2
  echo "Refusing to silently change the training-source distribution." >&2
  exit 5
fi
mkdir -p "$DATASET"
ln -s "$SOURCE_DATASET/deepscores" "$DATASET/deepscores"
if [[ -d "$SOURCE_DATASET/deepscores_probe" ]]; then
  ln -s "$SOURCE_DATASET/deepscores_probe" "$DATASET/deepscores_probe"
fi
echo "non_eval2_source=$SOURCE_DATASET"

echo "==> rebuild evaluation2 crops from current canonical GT"
PYTHONPATH=. "$PYTHON" \
  tools/cnn_classifier/build_cnn_dataset.py \
  --config configs/cnn_barline_runs/issue44_iter6_hard_mining/dataset_build.yaml \
  --output-root "$DATASET" \
  --eval2-candidates-root "$MIRROR" \
  --skip-local \
  --skip-deepscores \
  > "$OUT/01_dataset_build.log" 2>&1

echo "==> audit corrected dataset and x=580 negative materialization"
PYTHONPATH=. "$PYTHON" - "$DATASET" "$TARGET_CAND" "$SOURCE_DATASET" > "$OUT/dataset_audit.json" <<'PY'
import json, sys
from pathlib import Path
from tools.cnn_classifier.build_cnn_dataset import barline_iou

root = Path.cwd()
dataset = Path(sys.argv[1])
cand_path = Path(sys.argv[2])
source_dataset = Path(sys.argv[3])
target = [580, 4005, 584, 4115]

gt_path = root / "data/evaluation2/annotations/Va__Prokofiev_Symphony5/page_015/boxes_sorted.json"
gt = [r["barline_location"] for r in json.loads(gt_path.read_text())]
data = json.loads(cand_path.read_text())
cands = [x["bbox"] if isinstance(x, dict) else x for x in data]

fp = []
target_indices = []
for cand in cands:
    matched = any(barline_iou(g, cand) > 0.5 for g in gt)
    if not matched:
        idx = len(fp)
        fp.append(cand)
        if cand == target:
            target_indices.append(idx)

target_paths = [
    dataset / "eval2/fp" / f"Va__Prokofiev_Symphony5_page_015_fp_{idx:05d}.png"
    for idx in target_indices
]
payload = {
    "eval2_tp": len(list((dataset / "eval2/tp").glob("*.png"))),
    "eval2_fp": len(list((dataset / "eval2/fp").glob("*.png"))),
    "target_fp_indices": target_indices,
    "target_fp_crops": [str(p) for p in target_paths],
    "target_fp_crops_exist": [p.is_file() for p in target_paths],
    "metadata_stats": json.loads((dataset / "metadata/stats.json").read_text()),
    "non_eval2_source": str(source_dataset),
    "deepscores_tp": len(list((dataset / "deepscores/tp").glob("*.png"))),
    "deepscores_fp": len(list((dataset / "deepscores/fp").glob("*.png"))),
}
print(json.dumps(payload, indent=2))
if payload["eval2_tp"] != 3567:
    raise SystemExit(f"expected 3567 eval2 TP crops, got {payload['eval2_tp']}")
if not target_indices or not all(payload["target_fp_crops_exist"]):
    raise SystemExit("x=580 was not materialized as a corrected negative crop")
PY
cat "$OUT/dataset_audit.json"

echo "==> corrected-data fine-tune (no target-specific weighting)"
env CNN_DATASET_ROOT="$DATASET" PYTHONPATH=. \
  "$PYTHON" experiments/cnn_classifier/train.py \
    --config "$TRAIN_CONFIG" \
    --work-dir "$WORK" \
    --init-weights "$PROD_CKPT" \
  > "$OUT/02_train.log" 2>&1

NEW_CKPT="$WORK/cnn_classifier_best.pth"
if [[ ! -f "$NEW_CKPT" ]]; then
  echo "Training completed without expected best checkpoint: $NEW_CKPT" >&2
  tail -n 80 "$OUT/02_train.log" >&2 || true
  exit 6
fi

echo "==> rescore frozen matched guards"
PYTHONPATH=. "$PYTHON" \
  tools/issue296/rescore_matched_guards.py \
  --checkpoint "$NEW_CKPT" \
  --output "$OUT/new_guards" \
  > "$OUT/03_guard_rescore.log" 2>&1

echo "==> summarize focused A/B"
PYTHONPATH=. "$PYTHON" - "$BASE_GUARDS" "$NEW_GUARDS" "$OUT/dataset_audit.json" "$NEW_CKPT" \
  > "$OUT/corrected_finetune_summary.json" <<'PY'
import json, sys
from pathlib import Path

old_path, new_path, dataset_audit_path, checkpoint = map(Path, sys.argv[1:])
old = json.loads(old_path.read_text())
new = json.loads(new_path.read_text())
audit = json.loads(dataset_audit_path.read_text())
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
true_failures = [
    r for r in rows
    if r["expected_detector_role"] == "true_barline" and not r["new_accept"]
]
new_negative_accepts = [
    r for r in rows
    if r["expected_detector_role"] == "negative"
    and r["case_id"] != "target_page015_x580"
    and r["old_accept"] is False
    and r["new_accept"] is True
]
rescue = next(r for r in rows if r["case_id"] == "iter7_rescue_sibelius_p006")
p007 = [r for r in rows if r["category"] == "benign_current_fp"]

focused_pass = (
    target["new_accept"] is False
    and not true_failures
    and not new_negative_accepts
    and rescue["new_accept"] is True
)
payload = {
    "schema_version": "issue296.corrected_finetune_ab.v1",
    "checkpoint": str(checkpoint),
    "threshold": threshold,
    "dataset_audit": audit,
    "target": target,
    "iter7_rescue_control": rescue,
    "true_guard_failures": true_failures,
    "newly_accepted_negative_guards": new_negative_accepts,
    "p007_benign_fp": p007,
    "focused_guard_pass": focused_pass,
    "cases": rows,
}
print(json.dumps(payload, indent=2))
PY

cat "$OUT/corrected_finetune_summary.json"
echo
echo "RESULT=$OUT/corrected_finetune_summary.json"
echo "GUARDS=$NEW_GUARDS"
