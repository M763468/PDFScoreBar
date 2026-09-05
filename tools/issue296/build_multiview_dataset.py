#!/usr/bin/env python3
"""Build paired tight/context views from the clean-v6 Issue #296 dataset.

For eval2 rows, the context view is regenerated from the original page image
using the same vertical FOV as the tight crop and twice the horizontal FOV
(square aspect ratio). For retained DeepScores rows, original page coordinates
are not preserved in the clean lineage metadata, so the context input is a
neutral white-padded square containing the exact tight crop. This keeps every
historical DeepScores sample without inventing unavailable context.

Diagnostic-only. Delete before PR preparation.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from tools.cnn_classifier.build_cnn_dataset import center_crop, crop_size_from_bbox

ROOT = Path(__file__).resolve().parents[2]
IMAGE_ROOT = ROOT / "data/evaluation2/images"
TARGET_SCORE = "Va__Prokofiev_Symphony5"
TARGET_PAGE = "page_015"
TARGET = (580, 4005, 584, 4115)

TIGHT_ASPECT = 0.5
CONTEXT_ASPECT = 1.0
CROP_SCALE = 3.0
MIN_H = 48
MAX_H = 256
TIGHT_MIN_W = 16
TIGHT_MAX_W = 128
CONTEXT_MIN_W = 48
CONTEXT_MAX_W = 256


def parse_bbox(raw: str) -> tuple[int, int, int, int] | None:
    if not raw:
        return None
    value: Any = json.loads(raw)
    if not isinstance(value, list) or len(value) < 4:
        return None
    return tuple(int(round(float(v))) for v in value[:4])


def parse_eval2_group(group: str) -> tuple[str, str]:
    if "_page_" not in group:
        raise ValueError(f"unparseable eval2 group: {group}")
    score, page_no = group.rsplit("_page_", 1)
    return score, f"page_{page_no}"


def square_pad_tight(path: Path) -> np.ndarray:
    image = cv2.imread(str(path))
    if image is None:
        raise FileNotFoundError(path)
    h, w = image.shape[:2]
    side = max(h, w)
    canvas = np.full((side, side, 3), 255, dtype=np.uint8)
    y = (side - h) // 2
    x = (side - w) // 2
    canvas[y : y + h, x : x + w] = image
    return canvas


def eval2_context(group: str, bbox: tuple[int, int, int, int]) -> np.ndarray:
    score, page = parse_eval2_group(group)
    image_path = IMAGE_ROOT / score / f"{page}.png"
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(image_path)
    x1, y1, x2, y2 = bbox
    cx = int(round((x1 + x2) / 2))
    cy = int(round((y1 + y2) / 2))
    crop_w, crop_h = crop_size_from_bbox(
        bbox,
        CROP_SCALE,
        CONTEXT_ASPECT,
        MIN_H,
        MAX_H,
        CONTEXT_MIN_W,
        CONTEXT_MAX_W,
    )
    return center_crop(image, cx, cy, crop_w, crop_h)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    metadata_path = args.source / "metadata/samples.csv"
    if not metadata_path.is_file():
        raise FileNotFoundError(metadata_path)

    if args.output.exists():
        shutil.rmtree(args.output)
    (args.output / "context").mkdir(parents=True, exist_ok=True)
    (args.output / "metadata").mkdir(parents=True, exist_ok=True)

    with metadata_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    written = []
    counts = Counter()
    target_rows = []
    for idx, row in enumerate(rows):
        tight_path = Path(row["path"])
        if not tight_path.is_absolute():
            tight_path = ROOT / tight_path
        if not tight_path.is_file():
            raise FileNotFoundError(tight_path)

        source = row["source"]
        bbox = parse_bbox(row.get("bbox", ""))
        if source == "eval2":
            if bbox is None:
                raise RuntimeError(f"eval2 row lacks bbox: {row}")
            context = eval2_context(row["group"], bbox)
            context_policy = "real_eval2_square_context"
        elif source == "deepscores":
            context = square_pad_tight(tight_path)
            context_policy = "neutral_padded_tight_no_extra_context"
        else:
            raise RuntimeError(f"unexpected source in clean-v6 metadata: {source}")

        sample_id = row["sample_id"]
        context_path = args.output / "context" / f"{idx:06d}_{Path(sample_id).name}"
        if not cv2.imwrite(str(context_path), context):
            raise RuntimeError(f"failed to write {context_path}")

        item = {
            "sample_id": sample_id,
            "tight_path": str(tight_path.resolve()),
            "context_path": str(context_path.resolve()),
            "label": int(row["label"]),
            "source": source,
            "group": row["group"],
            "split": row["split"],
            "bbox": "" if bbox is None else json.dumps(list(bbox)),
            "context_policy": context_policy,
        }
        written.append(item)
        counts[(row["split"], source, context_policy)] += 1

        if (
            source == "eval2"
            and row["group"] == f"{TARGET_SCORE}_{TARGET_PAGE}"
            and bbox == TARGET
        ):
            target_rows.append(item)

    out_csv = args.output / "metadata/samples.csv"
    fieldnames = [
        "sample_id",
        "tight_path",
        "context_path",
        "label",
        "source",
        "group",
        "split",
        "bbox",
        "context_policy",
    ]
    with out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(written)

    target_ok = (
        len(target_rows) == 1
        and target_rows[0]["label"] == 0
        and target_rows[0]["split"] == "train"
        and target_rows[0]["context_policy"] == "real_eval2_square_context"
    )
    report = {
        "schema_version": "issue296.multiview_dataset.v1",
        "source_dataset": str(args.source),
        "rows": len(written),
        "tight_view": "historical clean-v6 crop, resized to 256x128 at load time",
        "context_view": "same vertical FOV, square horizontal FOV for eval2; neutral padded tight fallback for DeepScores",
        "counts": {
            f"{split}:{source}:{policy}": count
            for (split, source, policy), count in sorted(counts.items())
        },
        "target_rows": target_rows,
        "target_invariant_ok": target_ok,
        "production_checkpoint_used": False,
    }
    if not target_ok:
        raise RuntimeError(f"target invariant failed: {json.dumps(report, indent=2)}")
    (args.output / "metadata/manifest.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
