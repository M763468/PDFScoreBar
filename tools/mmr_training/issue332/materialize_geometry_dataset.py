#!/usr/bin/env python3
"""Materialize split-safe Issue #332 MMR geometry-training datasets.

This experiment-only tool freezes semantic splits before generating source-page
crop siblings. The existing classifier training path performs final direct
224x224 resize/normalization after these fixed-margin crops.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any, Sequence

import cv2

from tools.mmr_training.issue332_geometry_benchmark import (
    DEFAULT_DELTAS_PX,
    _validated_bbox,
    crop_measure,
    generate_geometry_variants,
    sha256_file,
)

DEFAULT_SPLIT_SEED = 42
DEFAULT_EXCLUDED_TAGS = ("acceptance-control", "issue277-control", "zero-fixture", "one-bar")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def load_samples(path: Path) -> list[dict[str, Any]]:
    raw_samples = _load_json(path).get("samples")
    if not isinstance(raw_samples, list) or not raw_samples:
        raise ValueError("manifest must contain a non-empty 'samples' list")
    required = {"sample_id", "score_id", "page_id", "image_path", "bbox", "label"}
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_samples):
        if not isinstance(raw, dict):
            raise ValueError(f"samples[{index}] must be an object")
        missing = required - raw.keys()
        if missing:
            raise ValueError(f"samples[{index}] missing fields: {sorted(missing)}")
        sample = dict(raw)
        sample_id = str(sample["sample_id"])
        if sample_id in seen:
            raise ValueError(f"duplicate sample_id: {sample_id}")
        seen.add(sample_id)
        label = int(sample["label"])
        if label not in (0, 1):
            raise ValueError(f"sample {sample_id}: label must be 0 or 1")
        sample.update(
            sample_id=sample_id,
            score_id=str(sample["score_id"]),
            page_id=str(sample["page_id"]),
            bbox=list(_validated_bbox(sample["bbox"])),
            label=label,
            tags=[str(tag) for tag in sample.get("tags", [])],
        )
        result.append(sample)
    return result


def _group_key(sample: dict[str, Any], group_level: str) -> str:
    if group_level == "score":
        return sample["score_id"]
    if group_level == "page":
        return f"{sample['score_id']}::{sample['page_id']}"
    if group_level == "sample":
        return sample["sample_id"]
    raise ValueError("group_level must be one of: score, page, sample")


def freeze_split(
    samples: Sequence[dict[str, Any]],
    *,
    seed: int = DEFAULT_SPLIT_SEED,
    validation_ratio: float = 0.2,
    group_level: str = "score",
) -> dict[str, str]:
    """Assign complete score/page groups before any augmentation is generated."""
    if not 0.0 < validation_ratio < 1.0:
        raise ValueError("validation_ratio must be between 0 and 1")
    groups: dict[str, list[dict[str, Any]]] = {}
    for sample in samples:
        groups.setdefault(_group_key(sample, group_level), []).append(sample)
    names = list(groups)
    random.Random(seed).shuffle(names)
    target_validation = max(1, round(len(samples) * validation_ratio))
    validation_count = 0
    assignments: dict[str, str] = {}
    for name in names:
        group = groups[name]
        split = "validation" if validation_count < target_validation else "train"
        if split == "validation":
            validation_count += len(group)
        for sample in group:
            assignments[sample["sample_id"]] = split
    return assignments


def _is_excluded(sample: dict[str, Any], excluded_tags: set[str], excluded_ids: set[str]) -> bool:
    return sample["sample_id"] in excluded_ids or bool(set(sample["tags"]) & excluded_tags)


def _resolve_image(manifest_path: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    return path.resolve() if path.is_absolute() else (manifest_path.parent / path).resolve()


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in value)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def materialize(
    *,
    manifest_path: Path,
    output_root: Path,
    config_path: Path | None = None,
    acceptance_manifest_path: Path | None = None,
) -> dict[str, Any]:
    config = _load_json(config_path) if config_path else {}
    samples = load_samples(manifest_path)
    acceptance_ids = (
        {sample["sample_id"] for sample in load_samples(acceptance_manifest_path)}
        if acceptance_manifest_path
        else set()
    )
    excluded_tags = set(config.get("acceptance_excluded_tags", DEFAULT_EXCLUDED_TAGS))
    split_config = config.get("split", {})
    seed = int(split_config.get("seed", DEFAULT_SPLIT_SEED))
    group_level = str(split_config.get("group_level", "score"))
    validation_ratio = float(split_config.get("validation_ratio", 0.2))
    assignments = freeze_split(
        samples,
        seed=seed,
        validation_ratio=validation_ratio,
        group_level=group_level,
    )
    deltas = tuple(int(value) for value in config.get("deltas_px", DEFAULT_DELTAS_PX))
    if str(config.get("candidate_variants", "geometry")) != "geometry":
        raise ValueError("candidate_variants currently supports only 'geometry'")
    margin_px = int(config.get("margin_px", 20))
    if margin_px < 0:
        raise ValueError("margin_px must be non-negative")

    output_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for sample in samples:
        image_path = _resolve_image(manifest_path, sample["image_path"])
        if not image_path.is_file():
            raise FileNotFoundError(
                f"source image not found for {sample['sample_id']}: {image_path}"
            )
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"could not decode source image: {image_path}")
        split = assignments[sample["sample_id"]]
        excluded = _is_excluded(sample, excluded_tags, acceptance_ids)
        if excluded:
            # Keep controls in frozen provenance, but never put them under
            # train/validation directories consumed by the trainer.
            continue
        base = {
            **sample,
            "split": split,
            "training_excluded": False,
            "source_image_path": str(image_path),
        }
        dataset_variants = {"baseline": [("native", sample["bbox"])]}
        dataset_variants["candidate"] = [
            (variant.name, list(variant.bbox))
            for variant in generate_geometry_variants(sample["bbox"], deltas)
        ]
        for dataset_name, variants in dataset_variants.items():
            for variant_name, bbox in variants:
                crop = crop_measure(image, bbox, margin_px=margin_px)
                relative = Path(dataset_name) / split / str(sample["label"])
                destination = (
                    output_root
                    / relative
                    / f"{_safe_name(sample['sample_id'])}__{variant_name}.jpg"
                )
                destination.parent.mkdir(parents=True, exist_ok=True)
                if not cv2.imwrite(str(destination), crop):
                    raise OSError(f"could not write crop: {destination}")
                rows.append(
                    {
                        **base,
                        "dataset": dataset_name,
                        "variant": variant_name,
                        "bbox": bbox,
                        "crop_path": str(destination.relative_to(output_root)),
                        "crop_sha256": sha256_file(destination),
                    }
                )

    training_rows = [row for row in rows if not row["training_excluded"]]
    payload = {
        "provenance": {
            "issue": 332,
            "source_manifest": str(manifest_path.resolve()),
            "source_manifest_sha256": sha256_file(manifest_path),
            "config": str(config_path.resolve()) if config_path else None,
            "config_sha256": sha256_file(config_path) if config_path else None,
            "acceptance_manifest": str(acceptance_manifest_path.resolve())
            if acceptance_manifest_path
            else None,
            "acceptance_manifest_sha256": sha256_file(acceptance_manifest_path)
            if acceptance_manifest_path
            else None,
        },
        "split_contract": {
            "group_level": group_level,
            "seed": seed,
            "validation_ratio": validation_ratio,
            "assignments": assignments,
            "frozen_before_augmentation": True,
            "sibling_leakage_checked": True,
        },
        "data_contract": {
            "margin_px": margin_px,
            "preprocessing": "existing direct 224x224 resize/normalize at training time",
            "source_space_bbox": True,
            "labels": "generic manifest label applied identically to positive and negative samples",
            "acceptance_controls_excluded_from_training": True,
            "excluded_sample_ids": sorted(
                sample["sample_id"]
                for sample in samples
                if _is_excluded(sample, excluded_tags, acceptance_ids)
            ),
        },
        "counts": {
            "semantic_samples": len(samples),
            "training_crop_rows": len(training_rows),
            "all_materialized_rows": len(rows),
        },
        "rows": rows,
    }
    _write_json(output_root / "dataset_manifest.json", payload)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--acceptance-manifest", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = materialize(
        manifest_path=args.manifest,
        output_root=args.output_root,
        config_path=args.config,
        acceptance_manifest_path=args.acceptance_manifest,
    )
    print(json.dumps(result["counts"], indent=2, sort_keys=True))
    print(f"wrote {args.output_root / 'dataset_manifest.json'}")


if __name__ == "__main__":
    main()
