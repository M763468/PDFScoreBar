#!/usr/bin/env python3
"""Temporary Issue #296 audit of retained CNN training lineage.

Diagnostic-only. Delete before PR preparation.

Purpose:
- inspect retained Issue #44 v5/v6/v7 dataset/split artifacts
- trace current clean-full68 FN positive crops back to historical v6 splits by image hash
- verify historical Iter6/Iter7 hard-sample labels against current canonical GT
- report whether a corrected-label reconstruction can preserve historical exposure

This script is read-only with respect to all retained datasets.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from src.common.barline_evaluation import is_barline_match

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "logs/issue296/diagnostic_08_training_lineage_audit"
FULL68 = ROOT / "logs/issue296/diagnostic_07_clean_full68/clean_full68_summary.json"
DIAG05 = ROOT / "logs/issue296/diagnostic_05_corrected_finetune/dataset_audit.json"
GT_ROOT = ROOT / "data/evaluation2/annotations"

DATASETS = [
    "cnn_classifier_v5_rescue_iter1",
    "cnn_classifier_v6_base",
    "cnn_classifier_v6_hard_mining",
    "cnn_classifier_v7_base",
    "cnn_classifier_v7_hard_mining",
    "issue296_corrected_finetune",
    "issue296_clean_retrain",
]

# Historical hard-sample recipes from current source. These are audited only;
# this script does not recreate or oversample them.
HARD_SAMPLES = [
    {
        "stage": "iter6",
        "score": "Sibelius-Violin_Concerto-Viola",
        "page": "page_004",
        "bbox": [2713, 3166, 2720, 3274],
        "historical_label": "tp",
        "historical_multiplier": 100,
    },
    {
        "stage": "iter6",
        "score": "Shostakovich-Sym5-Va",
        "page": "page_003",
        "bbox": [948, 789, 952, 889],
        "historical_label": "fp",
        "historical_multiplier": 100,
    },
    {
        "stage": "iter6",
        "score": "Va_Prokofiev_Symphony1",
        "page": "page_005",
        "bbox": [1496, 3484, 1500, 3587],
        "historical_label": "fp",
        "historical_multiplier": 100,
    },
    {
        "stage": "iter7",
        "score": "Sibelius-Violin_Concerto-Viola",
        "page": "page_006",
        "bbox": [1919, 1580, 1923, 1687],
        "historical_label": "tp",
        "historical_multiplier": 500,
    },
]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_samples(dataset: Path) -> list[dict[str, str]]:
    path = dataset / "metadata/samples.csv"
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def count_pngs(root: Path) -> int:
    if not root.is_dir():
        return 0
    return sum(1 for _ in root.rglob("*.png"))


def dataset_summary(name: str) -> dict[str, Any]:
    root = ROOT / "datasets" / name
    rows = read_samples(root)
    by_split_label = Counter()
    by_source_split = Counter()
    groups_by_split: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        split = row.get("split", "")
        label = row.get("label", "")
        source = row.get("source", "")
        group = row.get("group", "")
        by_split_label[(split, label)] += 1
        by_source_split[(source, split)] += 1
        if split and group:
            groups_by_split[split].add(group)

    return {
        "name": name,
        "path": str(root),
        "exists": root.is_dir(),
        "metadata_rows": len(rows),
        "metadata_by_split_label": {
            f"{split}:{label}": count for (split, label), count in sorted(by_split_label.items())
        },
        "metadata_by_source_split": {
            f"{source}:{split}": count for (source, split), count in sorted(by_source_split.items())
        },
        "metadata_group_counts": {split: len(groups) for split, groups in sorted(groups_by_split.items())},
        "png_counts": {
            "all": count_pngs(root),
            "splits_train_tp": count_pngs(root / "splits/train/tp"),
            "splits_train_fp": count_pngs(root / "splits/train/fp"),
            "splits_val_tp": count_pngs(root / "splits/val/tp"),
            "splits_val_fp": count_pngs(root / "splits/val/fp"),
            "splits_test_tp": count_pngs(root / "splits/test/tp"),
            "splits_test_fp": count_pngs(root / "splits/test/fp"),
            "direct_train_tp": count_pngs(root / "train/tp"),
            "direct_train_fp": count_pngs(root / "train/fp"),
            "direct_val_tp": count_pngs(root / "val/tp"),
            "direct_val_fp": count_pngs(root / "val/fp"),
        },
    }


def gt_boxes(score: str, page: str) -> list[tuple[int, int, int, int]]:
    rows = load_json(GT_ROOT / score / page / "boxes_sorted.json")
    return [tuple(int(v) for v in row["barline_location"]) for row in rows]


def canonical_match(box: list[int] | tuple[int, int, int, int], truths: list[tuple[int, int, int, int]]) -> bool:
    pred = tuple(int(v) for v in box)
    return any(
        is_barline_match(
            pred,
            gt,
            "center_anchor",
            vov_threshold=0.5,
            xdist_threshold=12.0,
        )
        for gt in truths
    )


def group_rows(dataset_name: str, group: str, *, label: str | None = None) -> list[dict[str, str]]:
    rows = read_samples(ROOT / "datasets" / dataset_name)
    result = [row for row in rows if row.get("group") == group]
    if label is not None:
        result = [row for row in result if str(row.get("label")) == str(label)]
    return result


def current_gt_crop(score: str, page: str, bbox: list[int]) -> tuple[Path | None, int | None]:
    truths = gt_boxes(score, page)
    target = tuple(int(v) for v in bbox)
    try:
        idx = truths.index(target)
    except ValueError:
        return None, None
    path = (
        ROOT
        / "datasets/issue296_corrected_finetune/eval2/tp"
        / f"{score}_{page}_tp_{idx:05d}.png"
    )
    return path, idx


def historical_v6_hash_rows(group: str, target_hash: str | None) -> list[dict[str, Any]]:
    if not target_hash:
        return []
    result = []
    for row in group_rows("cnn_classifier_v6_base", group):
        try:
            path = Path(row["path"])
        except Exception:
            continue
        if not path.is_absolute():
            path = ROOT / path
        if sha256(path) == target_hash:
            result.append(
                {
                    "sample_id": row.get("sample_id"),
                    "path": str(path),
                    "label": row.get("label"),
                    "source": row.get("source"),
                    "group": row.get("group"),
                    "split": row.get("split"),
                }
            )
    return result


def trace_clean_fn(row: dict[str, Any]) -> dict[str, Any]:
    score = row["score"]
    page = row["page"]
    bbox = row["bbox"]
    group = f"{score}_{page}"
    crop, gt_index = current_gt_crop(score, page, bbox)
    crop_hash = sha256(crop) if crop else None
    clean_rows = []
    if crop:
        resolved = crop.resolve() if crop.exists() else crop
        for meta in read_samples(ROOT / "datasets/issue296_clean_retrain"):
            try:
                p = Path(meta["path"]).resolve()
            except Exception:
                continue
            if p == resolved:
                clean_rows.append(meta)
    return {
        "score": score,
        "page": page,
        "bbox": bbox,
        "group": group,
        "current_gt_index": gt_index,
        "current_corrected_crop": str(crop) if crop else None,
        "current_corrected_crop_exists": bool(crop and crop.is_file()),
        "current_corrected_crop_sha256": crop_hash,
        "clean_retrain_metadata_rows": clean_rows,
        "historical_v6_same_crop_rows_by_sha256": historical_v6_hash_rows(group, crop_hash),
        "historical_v6_group_split_counts": dict(Counter(r.get("split", "") for r in group_rows("cnn_classifier_v6_base", group))),
        "clean_retrain_group_split_counts": dict(Counter(r.get("split", "") for r in group_rows("issue296_clean_retrain", group))),
    }


def audit_hard_sample(sample: dict[str, Any]) -> dict[str, Any]:
    truths = gt_boxes(sample["score"], sample["page"])
    matched = canonical_match(sample["bbox"], truths)
    exact = tuple(sample["bbox"]) in truths
    current_role = "tp" if matched else "fp"
    return {
        **sample,
        "current_canonical_match": matched,
        "current_exact_gt": exact,
        "current_role": current_role,
        "label_still_valid": current_role == sample["historical_label"],
    }


def trace_x580() -> dict[str, Any]:
    if not DIAG05.is_file():
        return {"available": False}
    audit = load_json(DIAG05)
    crops = [Path(p) for p in audit.get("target_fp_crops", [])]
    if len(crops) != 1:
        return {"available": True, "error": f"expected one corrected x580 crop, got {crops}"}
    crop = crops[0]
    target_hash = sha256(crop)
    group = "Va__Prokofiev_Symphony5_page_015"
    old = historical_v6_hash_rows(group, target_hash)
    return {
        "available": True,
        "corrected_negative_crop": str(crop),
        "corrected_negative_crop_exists": crop.is_file(),
        "sha256": target_hash,
        "historical_v6_same_crop_rows_by_sha256": old,
        "historical_positive_match_found": any(str(row.get("label")) == "1" for row in old),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    if not FULL68.is_file():
        raise FileNotFoundError(FULL68)

    full68 = load_json(FULL68)
    clean_fns = [row for row in full68.get("residuals", []) if row.get("kind") == "clean_fn"]

    # The two canonical pre-existing FNs are kept in the trace too; downstream
    # analysis can distinguish them from the five newly introduced FNs.
    fn_traces = [trace_clean_fn(row) for row in clean_fns]
    hard = [audit_hard_sample(sample) for sample in HARD_SAMPLES]

    # Report whether hard-mining source directories appear to have been copied
    # into v7_base by comparing exact file hashes, without assuming filenames.
    v7_base = ROOT / "datasets/cnn_classifier_v7_base"
    v7_hashes: set[str] = set()
    if v7_base.is_dir():
        for p in v7_base.rglob("*.png"):
            value = sha256(p)
            if value:
                v7_hashes.add(value)
    hard_dir_membership = {}
    for name in ("cnn_classifier_v6_hard_mining", "cnn_classifier_v7_hard_mining"):
        root = ROOT / "datasets" / name
        hashes = [sha256(p) for p in root.rglob("*.png")] if root.is_dir() else []
        hashes = [h for h in hashes if h]
        hard_dir_membership[name] = {
            "exists": root.is_dir(),
            "png_count": len(hashes),
            "unique_hash_count": len(set(hashes)),
            "unique_hashes_present_in_v7_base": len(set(hashes) & v7_hashes),
        }

    payload = {
        "schema_version": "issue296.training_lineage_audit.v1",
        "purpose": "read-only audit before any further clean retraining",
        "datasets": [dataset_summary(name) for name in DATASETS],
        "x580_hash_trace": trace_x580(),
        "clean_full68_fn_traces": fn_traces,
        "historical_hard_sample_label_audit": hard,
        "all_historical_hard_sample_labels_still_valid": all(row["label_still_valid"] for row in hard),
        "hard_sample_directory_membership": hard_dir_membership,
        "notes": {
            "production_checkpoint_is_not_used_for_decision_fusion": True,
            "no_training_performed": True,
            "no_files_mutated_outside_output_json": True,
        },
    }

    out = OUT / "training_lineage_audit.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "x580_hash_trace": payload["x580_hash_trace"],
        "clean_fn_count": len(fn_traces),
        "fn_split_trace": [
            {
                "score": row["score"],
                "page": row["page"],
                "bbox": row["bbox"],
                "historical_v6_same_crop_rows_by_sha256": row["historical_v6_same_crop_rows_by_sha256"],
                "clean_retrain_metadata_rows": row["clean_retrain_metadata_rows"],
            }
            for row in fn_traces
        ],
        "hard_sample_label_audit": hard,
        "hard_sample_directory_membership": hard_dir_membership,
        "result": str(out),
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
