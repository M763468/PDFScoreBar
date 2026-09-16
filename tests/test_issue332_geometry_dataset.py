import json
import random
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
from torchvision import transforms

from tools.mmr_training.issue332.geometry_training import (
    GEOMETRY_FAMILIES,
    SemanticMMRDataset,
    choose_geometry_bbox,
    prepare_split_contract,
)
from tools.mmr_training.train_mmr_classifier import _manifest_datasets


def _sample(sample_id, score_id, page_id, label, image_path="page.png", tags=None):
    return {
        "sample_id": sample_id,
        "score_id": score_id,
        "page_id": page_id,
        "image_path": image_path,
        "bbox": [20, 20, 60, 60],
        "label": label,
        "tags": tags or [],
    }


def _balanced_samples():
    samples = []
    for score_index in range(6):
        score = f"score-{score_index}"
        samples.append(_sample(f"{score}-neg", score, "page-1", 0))
        samples.append(_sample(f"{score}-pos", score, "page-2", 1))
    return samples


def test_acceptance_controls_are_excluded_before_group_split(tmp_path: Path):
    samples = _balanced_samples()
    samples.append(_sample("control", "control-score", "page-1", 0))
    manifest = tmp_path / "source.json"
    manifest.write_text(json.dumps({"samples": samples}), encoding="utf-8")
    acceptance = tmp_path / "acceptance.json"
    acceptance.write_text(
        json.dumps({"samples": [_sample("control", "control-score", "page-1", 0)]}),
        encoding="utf-8",
    )

    eligible, contract = prepare_split_contract(
        manifest_path=manifest,
        split_path=tmp_path / "split.json",
        acceptance_manifest_path=acceptance,
        seed=42,
        validation_ratio=0.2,
        test_ratio=0.2,
    )

    assert "control" not in {sample["sample_id"] for sample in eligible}
    assert "control" not in contract["assignments"]
    assert contract["excluded_before_split"] is True
    assert contract["excluded_sample_ids"] == ["control"]

    score_splits = {}
    for sample in eligible:
        score_splits.setdefault(sample["score_id"], set()).add(
            contract["assignments"][sample["sample_id"]]
        )
    assert all(len(splits) == 1 for splits in score_splits.values())


def test_split_artifact_is_reused_and_deterministic(tmp_path: Path):
    manifest = tmp_path / "source.json"
    manifest.write_text(json.dumps({"samples": _balanced_samples()}), encoding="utf-8")
    split = tmp_path / "split.json"

    _, first = prepare_split_contract(
        manifest_path=manifest,
        split_path=split,
        seed=17,
        validation_ratio=0.2,
        test_ratio=0.2,
    )
    _, second = prepare_split_contract(
        manifest_path=manifest,
        split_path=split,
        seed=999,
        validation_ratio=0.3,
        test_ratio=0.3,
    )

    assert first == second
    assert set(first["assignments"].values()) == {"train", "validation", "test"}


def test_geometry_candidate_keeps_one_semantic_item_per_epoch(tmp_path: Path):
    image_path = tmp_path / "page.png"
    cv2.imwrite(str(image_path), np.full((100, 100, 3), 255, dtype=np.uint8))
    sample = _sample("x", "score-a", "page-1", 1, image_path=str(image_path))
    transform = transforms.ToTensor()

    baseline = SemanticMMRDataset(
        [sample],
        manifest_path=tmp_path / "manifest.json",
        transform=transform,
        geometry_policy="none",
        seed=42,
    )
    candidate = SemanticMMRDataset(
        [sample],
        manifest_path=tmp_path / "manifest.json",
        transform=transform,
        geometry_policy="absolute",
        deltas_px=(1, 2, 4),
        seed=42,
    )

    assert len(baseline) == len(candidate) == 1
    variants = {
        choose_geometry_bbox(
            sample,
            policy="absolute",
            deltas_px=(1, 2, 4),
            rng=random.Random(seed),
        )[0]
        for seed in range(100)
    }
    assert "native" in variants
    assert any(name.startswith("translate_x_") for name in variants)
    assert any(name.startswith("translate_y_") for name in variants)
    assert any(name.startswith("x1_") for name in variants)
    assert any(name.startswith("x2_") for name in variants)
    assert any(name.startswith("expand_contract_x_") for name in variants)


def test_absolute_geometry_sampling_balances_families_deltas_and_signs():
    sample = _sample("x", "score-a", "page-1", 1)
    rng = random.Random(332)
    names = [
        choose_geometry_bbox(sample, policy="absolute", deltas_px=(1, 2, 4), rng=rng)[0]
        for _ in range(6000)
    ]
    family_counts = {family: 0 for family in GEOMETRY_FAMILIES}
    delta_counts = {family: {delta: 0 for delta in (1, 2, 4)} for family in GEOMETRY_FAMILIES[1:]}
    sign_counts = {
        family: {sign: 0 for sign in ("minus", "plus")} for family in GEOMETRY_FAMILIES[1:]
    }
    for name in names:
        if name == "native":
            family_counts["native"] += 1
            continue
        family = next(family for family in GEOMETRY_FAMILIES[1:] if name.startswith(family + "_"))
        sign, delta_text = name[len(family) + 1 :].split("_", 1)
        delta = int(delta_text.removesuffix("px"))
        family_counts[family] += 1
        delta_counts[family][delta] += 1
        sign_counts[family][sign] += 1
    assert all(850 <= count <= 1150 for count in family_counts.values())
    assert all(275 <= count <= 400 for counts in delta_counts.values() for count in counts.values())
    assert all(425 <= count <= 575 for counts in sign_counts.values() for count in counts.values())


def test_manifest_trainer_uses_frozen_split_without_resplitting(tmp_path: Path):
    image_path = tmp_path / "page.png"
    cv2.imwrite(str(image_path), np.full((100, 100, 3), 255, dtype=np.uint8))
    samples = [{**sample, "image_path": str(image_path)} for sample in _balanced_samples()]
    manifest = tmp_path / "source.json"
    manifest.write_text(json.dumps({"samples": samples}), encoding="utf-8")

    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "margin_px": 20,
                "deltas_px": [1, 2, 4],
                "split": {
                    "seed": 42,
                    "group_level": "score",
                    "fallback_group_level": "page",
                    "validation_ratio": 0.2,
                    "test_ratio": 0.2,
                },
            }
        ),
        encoding="utf-8",
    )
    args = SimpleNamespace(
        manifest=str(manifest),
        split_manifest=str(tmp_path / "split.json"),
        geometry_config=str(config),
        acceptance_manifest=None,
        seed=42,
        geometry_augmentation="absolute",
    )

    train, validation, test, _, contract, class_counts = _manifest_datasets(
        args,
        transforms.ToTensor(),
        transforms.ToTensor(),
        text_noise=None,
    )

    expected = {
        split: {
            sample_id
            for sample_id, assigned in contract["assignments"].items()
            if assigned == split
        }
        for split in ("train", "validation", "test")
    }
    assert {sample["sample_id"] for sample in train.samples} == expected["train"]
    assert {sample["sample_id"] for sample in validation.samples} == expected["validation"]
    assert {sample["sample_id"] for sample in test.samples} == expected["test"]
    assert train.geometry_policy == "absolute"
    assert validation.geometry_policy == "none"
    assert test.geometry_policy == "none"
    assert class_counts == (6, 6)
