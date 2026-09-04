#!/usr/bin/env python3
"""Build corrected Issue #296 datasets while preserving historical split exposure.

Diagnostic-only. Delete before PR preparation.

The builder intentionally does NOT reuse historical eval2 labels.  It rebuilds
all eval2 TP/FP crops from the Issue #44 candidate set against the current
canonical boxes_sorted.json files, then maps each page group to the split that
was actually used by the retained historical v5/v6/v7 metadata.

Historical DeepScores rows/crops are reused read-only through symlinks.  The
root-level Iter6/Iter7 hard-sample directories are not included because the
Issue #44 trainer reads splits/{train,val}, not dataset-root train/val.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import cv2

from tools.cnn_classifier.build_cnn_dataset import barline_iou, center_crop, crop_size_from_bbox

ROOT = Path(__file__).resolve().parents[2]
GT_ROOT = ROOT / "data/evaluation2/annotations"
IMAGE_ROOT = ROOT / "data/evaluation2/images"
DEFAULT_CANDIDATES = ROOT / "logs/issue53_full_eval_rescue_v1"
TARGET_SCORE = "Va__Prokofiev_Symphony5"
TARGET_PAGE = "page_015"
TARGET = (580, 4005, 584, 4115)

CROP_W = 128
CROP_H = 256
CROP_SCALE = 3.0
MIN_H = 48
MAX_H = 256
MIN_W = max(16, int(round(MIN_H * (CROP_W / CROP_H))))
MAX_W = max(32, int(round(MAX_H * (CROP_W / CROP_H))))
IOU_THRESHOLD = 0.5

STAGES = {
    "v5": "cnn_classifier_v5_rescue_iter1",
    "v6": "cnn_classifier_v6_base",
    "v7": "cnn_classifier_v7_base",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def norm_box(raw: Any) -> tuple[int, int, int, int] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) < 4:
        return None
    return tuple(int(round(float(v))) for v in raw[:4])


def canonical_pages() -> list[tuple[str, str, Path]]:
    pages = []
    for path in sorted(GT_ROOT.glob("*/page_*/boxes_sorted.json")):
        pages.append((path.parent.parent.name, path.parent.name, path))
    return pages


def candidate_path(root: Path, score: str, page: str) -> Path:
    filename = "pipeline2_no_peak_scored.json"
    candidates = [
        root / f"eval2_{score}_{page}" / filename,
        root / score / page / filename,
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(f"candidate file missing for {score}/{page}: {candidates}")


def candidate_boxes(path: Path) -> list[tuple[int, int, int, int]]:
    payload = load_json(path)
    if isinstance(payload, dict) and "scores" in payload:
        payload = payload["scores"]
    if not isinstance(payload, list):
        raise ValueError(f"unexpected candidate JSON format: {path}")
    result = []
    for item in payload:
        raw = item.get("bbox") if isinstance(item, dict) else item
        box = norm_box(raw)
        if box is not None:
            result.append(box)
    return result


def crop_for_box(img, box: tuple[int, int, int, int]):
    x1, y1, x2, y2 = box
    cx = int(round((x1 + x2) / 2))
    cy = int(round((y1 + y2) / 2))
    local_w, local_h = crop_size_from_bbox(
        box,
        CROP_SCALE,
        CROP_W / CROP_H,
        MIN_H,
        MAX_H,
        MIN_W,
        MAX_W,
    )
    return center_crop(img, cx, cy, local_w, local_h)


def build_eval2_pool(pool: Path, candidates_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pages = canonical_pages()
    if len(pages) != 68:
        raise RuntimeError(f"expected 68 canonical pages, got {len(pages)}")

    total_gt = 0
    target_in_gt = False
    target_candidate = False
    target_negative_rows = []
    rows: list[dict[str, Any]] = []
    per_page = []

    for page_idx, (score, page, gt_path) in enumerate(pages, 1):
        gt_payload = load_json(gt_path)
        truths = []
        for row in gt_payload:
            box = norm_box(row.get("barline_location")) if isinstance(row, dict) else None
            if box is not None:
                truths.append(box)
        total_gt += len(truths)
        if score == TARGET_SCORE and page == TARGET_PAGE:
            target_in_gt = TARGET in truths

        image_path = IMAGE_ROOT / score / f"{page}.png"
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(image_path)

        group = f"{score}_{page}"
        tp_dir = pool / "eval2/tp"
        fp_dir = pool / "eval2/fp"
        tp_dir.mkdir(parents=True, exist_ok=True)
        fp_dir.mkdir(parents=True, exist_ok=True)

        for idx, box in enumerate(truths):
            path = tp_dir / f"{group}_tp_{idx:05d}.png"
            if not cv2.imwrite(str(path), crop_for_box(image, box)):
                raise RuntimeError(f"failed to write {path}")
            rows.append({
                "source": "eval2",
                "group": group,
                "label": 1,
                "path": str(path),
                "bbox": list(box),
            })

        cand_path = candidate_path(candidates_root, score, page)
        candidates = candidate_boxes(cand_path)
        if score == TARGET_SCORE and page == TARGET_PAGE:
            target_candidate = TARGET in candidates

        negatives = []
        for box in candidates:
            if any(barline_iou(gt, box) > IOU_THRESHOLD for gt in truths):
                continue
            negatives.append(box)

        for idx, box in enumerate(negatives):
            path = fp_dir / f"{group}_fp_{idx:05d}.png"
            if not cv2.imwrite(str(path), crop_for_box(image, box)):
                raise RuntimeError(f"failed to write {path}")
            row = {
                "source": "eval2",
                "group": group,
                "label": 0,
                "path": str(path),
                "bbox": list(box),
            }
            rows.append(row)
            if score == TARGET_SCORE and page == TARGET_PAGE and box == TARGET:
                target_negative_rows.append(row)

        per_page.append({
            "score": score,
            "page": page,
            "gt": len(truths),
            "candidates": len(candidates),
            "fp_crops": len(negatives),
        })
        print(f"[pool {page_idx:02d}/68] {score}/{page}: gt={len(truths)} cand={len(candidates)} fp={len(negatives)}")

    manifest = {
        "schema_version": "issue296.clean_lineage_eval2_pool.v1",
        "candidate_root": str(candidates_root),
        "canonical_gt_pages": len(pages),
        "canonical_gt_count": total_gt,
        "target_in_canonical_gt": target_in_gt,
        "target_in_historical_candidate_set": target_candidate,
        "target_negative_count": len(target_negative_rows),
        "target_negative_rows": target_negative_rows,
        "eval2_tp": sum(1 for r in rows if r["label"] == 1),
        "eval2_fp": sum(1 for r in rows if r["label"] == 0),
        "pages": per_page,
    }
    if total_gt != 3567 or target_in_gt or not target_candidate or len(target_negative_rows) != 1:
        raise RuntimeError(f"eval2 pool preflight failed: {json.dumps(manifest, indent=2)}")

    (pool / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return rows, manifest


def read_metadata(dataset: Path) -> list[dict[str, str]]:
    path = dataset / "metadata/samples.csv"
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def resolve_row_path(row: dict[str, str]) -> Path:
    path = Path(row["path"])
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def symlink_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    os.symlink(src.resolve(), dst)


def historical_group_splits(rows: list[dict[str, str]], source: str) -> dict[str, str]:
    seen: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row.get("source") == source:
            seen[row["group"]].add(row["split"])
    bad = {g: sorted(v) for g, v in seen.items() if len(v) != 1}
    if bad:
        raise RuntimeError(f"historical groups span multiple splits: {bad}")
    return {g: next(iter(v)) for g, v in seen.items()}


def compose_stage(stage: str, pool_rows: list[dict[str, Any]], output: Path) -> dict[str, Any]:
    historical_name = STAGES[stage]
    historical_root = ROOT / "datasets" / historical_name
    historical_rows = read_metadata(historical_root)
    eval2_splits = historical_group_splits(historical_rows, "eval2")

    written: list[dict[str, Any]] = []
    stats = Counter()
    missing_groups = set()
    target_rows = []

    # Current-canonical eval2 crops, historical page-group split assignment.
    for idx, row in enumerate(pool_rows):
        group = row["group"]
        split = eval2_splits.get(group)
        if split is None:
            missing_groups.add(group)
            continue
        label = int(row["label"])
        kind = "tp" if label == 1 else "fp"
        sample_id = f"eval2_{group}_{idx:06d}.png"
        src = Path(row["path"])
        dst = output / "splits" / split / kind / sample_id
        symlink_file(src, dst)
        item = {
            "sample_id": sample_id,
            "path": str(src.resolve()),
            "label": label,
            "source": "eval2",
            "group": group,
            "split": split,
            "bbox": row["bbox"],
        }
        written.append(item)
        stats[(split, kind, "eval2")] += 1
        if group == f"{TARGET_SCORE}_{TARGET_PAGE}" and tuple(row["bbox"]) == TARGET:
            target_rows.append(item)

    if missing_groups:
        raise RuntimeError(f"current eval2 groups missing from historical {stage}: {sorted(missing_groups)}")

    # Exact historical DeepScores samples and split assignment.
    for idx, row in enumerate(r for r in historical_rows if r.get("source") == "deepscores"):
        split = row["split"]
        label = int(row["label"])
        kind = "tp" if label == 1 else "fp"
        src = resolve_row_path(row)
        sample_id = f"deepscores_{idx:06d}_{Path(row['sample_id']).name}"
        dst = output / "splits" / split / kind / sample_id
        symlink_file(src, dst)
        written.append({
            "sample_id": sample_id,
            "path": str(src.resolve()),
            "label": label,
            "source": "deepscores",
            "group": row["group"],
            "split": split,
            "bbox": None,
        })
        stats[(split, kind, "deepscores")] += 1

    metadata = output / "metadata"
    metadata.mkdir(parents=True, exist_ok=True)
    csv_path = metadata / "samples.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        fieldnames = ["sample_id", "path", "label", "source", "group", "split", "bbox"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in written:
            out = dict(row)
            out["bbox"] = "" if out["bbox"] is None else json.dumps(out["bbox"])
            writer.writerow(out)

    simple_stats: dict[str, dict[str, int]] = {
        split: {"tp": 0, "fp": 0} for split in ("train", "val", "test")
    }
    for (split, kind, _source), count in stats.items():
        simple_stats.setdefault(split, {"tp": 0, "fp": 0})[kind] += count
    (metadata / "stats.json").write_text(json.dumps(simple_stats, indent=2) + "\n", encoding="utf-8")

    target_ok = (
        len(target_rows) == 1
        and target_rows[0]["label"] == 0
        and target_rows[0]["split"] == "train"
    )
    report = {
        "stage": stage,
        "historical_dataset": historical_name,
        "historical_metadata_rows": len(historical_rows),
        "historical_eval2_groups": len(eval2_splits),
        "output_rows": len(written),
        "stats": simple_stats,
        "by_source_split_kind": {
            f"{source}:{split}:{kind}": count
            for (split, kind, source), count in sorted(stats.items())
        },
        "target_rows": target_rows,
        "target_is_single_corrected_train_negative": target_ok,
        "root_level_hard_samples_included": False,
    }
    if not target_ok:
        raise RuntimeError(f"target exposure invariant failed for {stage}: {report}")
    (metadata / "issue296_stage_manifest.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", type=Path, required=True)
    parser.add_argument("--v5", type=Path, required=True)
    parser.add_argument("--v6", type=Path, required=True)
    parser.add_argument("--v7", type=Path, required=True)
    parser.add_argument("--candidates-root", type=Path, default=DEFAULT_CANDIDATES)
    args = parser.parse_args()

    if not args.candidates_root.is_dir():
        raise FileNotFoundError(args.candidates_root)
    for stage, historical in STAGES.items():
        root = ROOT / "datasets" / historical
        if not (root / "metadata/samples.csv").is_file():
            raise FileNotFoundError(f"retained historical {stage} metadata missing: {root}")

    args.pool.mkdir(parents=True, exist_ok=True)
    pool_rows, pool_manifest = build_eval2_pool(args.pool, args.candidates_root)
    reports = {}
    for stage, out in (("v5", args.v5), ("v6", args.v6), ("v7", args.v7)):
        out.mkdir(parents=True, exist_ok=True)
        reports[stage] = compose_stage(stage, pool_rows, out)
        print(json.dumps(reports[stage], indent=2))

    payload = {
        "schema_version": "issue296.clean_lineage_datasets.v1",
        "pool": pool_manifest,
        "stages": reports,
        "design": {
            "eval2": "historical Issue53 candidate set re-labeled with current canonical boxes_sorted.json",
            "deepscores": "exact retained historical rows/crops and split assignment",
            "split_policy": "historical retained metadata group split",
            "hard_sample_policy": "excluded because historical/current trainer reads splits/*, not root train/val",
        },
    }
    summary = args.pool.parent / "clean_lineage_dataset_summary.json"
    summary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"RESULT={summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
