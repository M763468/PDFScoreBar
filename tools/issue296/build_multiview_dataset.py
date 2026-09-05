#!/usr/bin/env python3
"""Build paired tight/context views from the clean-v6 Issue #296 dataset.

For eval2 rows, the context view is regenerated from the original page image
using the same vertical FOV as the tight crop and twice the horizontal FOV
(square aspect ratio). Page images are cached one-at-a-time because clean-v6
metadata is page-grouped; this avoids re-reading a large page for every sample.

For retained DeepScores rows, original page coordinates are not preserved in
the clean lineage metadata. Their context is therefore represented as a lazy
neutral white-pad policy and is created in-memory by the training dataset from
the already-loaded tight image. No duplicate context PNG is written.

A completed paired dataset is reused when its source metadata hash and schema
match. Partial/stale outputs are deleted and rebuilt automatically.

Diagnostic-only. Delete before PR preparation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

import cv2

from tools.cnn_classifier.build_cnn_dataset import center_crop, crop_size_from_bbox

ROOT = Path(__file__).resolve().parents[2]
IMAGE_ROOT = ROOT / "data/evaluation2/images"
TARGET_SCORE = "Va__Prokofiev_Symphony5"
TARGET_PAGE = "page_015"
TARGET = (580, 4005, 584, 4115)
SCHEMA = "issue296.multiview_dataset.v2"

TIGHT_ASPECT = 0.5
CONTEXT_ASPECT = 1.0
CROP_SCALE = 3.0
MIN_H = 48
MAX_H = 256
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Eval2PageCache:
    """Keep only the current eval2 page in RAM.

    clean-v6 metadata stores eval2 rows grouped by page, so this changes page
    image reads from O(eval2 samples) to approximately O(68 pages) without
    retaining all x4 page images in memory.
    """

    def __init__(self) -> None:
        self.key: tuple[str, str] | None = None
        self.image = None
        self.loads = 0

    def get(self, group: str):
        score, page = parse_eval2_group(group)
        key = (score, page)
        if key != self.key:
            image_path = IMAGE_ROOT / score / f"{page}.png"
            image = cv2.imread(str(image_path))
            if image is None:
                raise FileNotFoundError(image_path)
            self.key = key
            self.image = image
            self.loads += 1
        return self.image


def eval2_context(
    group: str,
    bbox: tuple[int, int, int, int],
    page_cache: Eval2PageCache,
):
    image = page_cache.get(group)
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


def reusable_output(output: Path, source_hash: str) -> dict[str, Any] | None:
    manifest_path = output / "metadata/manifest.json"
    csv_path = output / "metadata/samples.csv"
    if not manifest_path.is_file() or not csv_path.is_file():
        return None
    try:
        report = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if (
        report.get("schema_version") == SCHEMA
        and report.get("source_metadata_sha256") == source_hash
        and report.get("build_complete") is True
    ):
        return report
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    metadata_path = args.source / "metadata/samples.csv"
    if not metadata_path.is_file():
        raise FileNotFoundError(metadata_path)

    source_hash = sha256_file(metadata_path)
    reused = reusable_output(args.output, source_hash)
    if reused is not None:
        print("Reusing completed paired dataset; source metadata hash is unchanged.")
        print(json.dumps(reused, indent=2, ensure_ascii=False))
        return 0

    if args.output.exists():
        shutil.rmtree(args.output)
    (args.output / "context").mkdir(parents=True, exist_ok=True)
    (args.output / "metadata").mkdir(parents=True, exist_ok=True)

    with metadata_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    written = []
    counts = Counter()
    target_rows = []
    page_cache = Eval2PageCache()
    eval2_context_files = 0
    lazy_context_rows = 0

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
            context = eval2_context(row["group"], bbox, page_cache)
            sample_id = row["sample_id"]
            context_path = args.output / "context" / f"{idx:06d}_{Path(sample_id).name}"
            if not cv2.imwrite(
                str(context_path),
                context,
                [cv2.IMWRITE_PNG_COMPRESSION, 1],
            ):
                raise RuntimeError(f"failed to write {context_path}")
            context_path_value = str(context_path.resolve())
            context_policy = "real_eval2_square_context"
            eval2_context_files += 1
        elif source == "deepscores":
            # No extra context exists for retained DeepScores metadata. Avoid
            # materializing tens of thousands of duplicate padded PNGs; the
            # loader pads the already-open tight image in memory.
            context_path_value = ""
            context_policy = "lazy_neutral_padded_tight_no_extra_context"
            lazy_context_rows += 1
        else:
            raise RuntimeError(f"unexpected source in clean-v6 metadata: {source}")

        item = {
            "sample_id": row["sample_id"],
            "tight_path": str(tight_path.resolve()),
            "context_path": context_path_value,
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

        if (idx + 1) % 2000 == 0 or idx + 1 == len(rows):
            print(
                f"paired {idx + 1}/{len(rows)} rows; "
                f"page_reads={page_cache.loads} eval2_context_files={eval2_context_files} "
                f"lazy_deepscores={lazy_context_rows}",
                flush=True,
            )

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
        "schema_version": SCHEMA,
        "source_dataset": str(args.source),
        "source_metadata_sha256": source_hash,
        "rows": len(written),
        "tight_view": "historical clean-v6 crop, resized to 256x128 at load time",
        "context_view": "same vertical FOV, square horizontal FOV for eval2; lazy neutral padded tight fallback for DeepScores",
        "eval2_page_image_reads": page_cache.loads,
        "eval2_context_files_written": eval2_context_files,
        "lazy_deepscores_context_rows": lazy_context_rows,
        "counts": {
            f"{split}:{source}:{policy}": count
            for (split, source, policy), count in sorted(counts.items())
        },
        "target_rows": target_rows,
        "target_invariant_ok": target_ok,
        "production_checkpoint_used": False,
        "build_complete": True,
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
