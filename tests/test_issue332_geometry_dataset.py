import json
import random
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
import torch
from torchvision import transforms

import tools.mmr_training.issue332.geometry_training as geometry_training
from tools.mmr_training.create_mmr_train_data import create_dataset_from_configs
from tools.mmr_training.issue332.dual_view_diagnosis import _staff_bbox_variants
from tools.mmr_training.issue332.dual_view_fusion import (
    fit_fusion_head,
    fuse_probabilities,
)
from tools.mmr_training.issue332.final_candidate_validation import (
    FullOnlyBias,
    ZeroBiasDualView,
    _envelope_summary,
)
from tools.mmr_training.issue332.geometry_training import (
    DEFAULT_GEOMETRY_AUGMENTATION_PROBABILITY,
    GEOMETRY_FAMILIES,
    WITHIN_SCORE_SPLIT_MODE,
    SemanticMMRDataset,
    StaffRelativeMMRDataset,
    choose_geometry_bbox,
    clear_source_page_cache,
    collate_staff_relative_batch,
    prepare_score_level_folds,
    prepare_split_contract,
    source_page_cache_info,
)
from tools.mmr_training.issue332.staff_failure_diagnosis import staff_band_full_width_rois
from tools.mmr_training.issue332.staff_model import StaffRelativeResNet18
from tools.mmr_training.issue332.staff_view import (
    STAFF_CORE_CENTER_VIEW,
    staff_relative_roi_bboxes,
)
from tools.mmr_training.issue332_geometry_benchmark import generate_geometry_variants
from tools.mmr_training.issue332_score_evaluation import summarize_native_rows
from tools.mmr_training.train_mmr_classifier import (
    _legacy_datasets,
    _manifest_datasets,
    _train_pos_weight,
)


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
    samples.append(
        {
            **_sample("control", "control-score", "page_010", 0),
            "system_index": 2,
            "measure_index": 1,
        }
    )
    samples.append(
        {
            **_sample("renamed-control", "control-score", "page_010", 0),
            "system_index": 2,
            "measure_index": 1,
        }
    )
    manifest = tmp_path / "source.json"
    manifest.write_text(json.dumps({"samples": samples}), encoding="utf-8")
    acceptance = tmp_path / "acceptance.json"
    acceptance.write_text(
        json.dumps({"samples": [_sample("page_010_s2_m1", "control-score", "page_010", 0)]}),
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

    assert {"control", "renamed-control"}.isdisjoint({sample["sample_id"] for sample in eligible})
    assert "control" not in contract["assignments"]
    assert contract["excluded_before_split"] is True
    assert contract["excluded_sample_ids"] == ["control", "renamed-control"]

    score_splits = {}
    for sample in eligible:
        score_splits.setdefault(sample["score_id"], set()).add(
            contract["assignments"][sample["sample_id"]]
        )
    assert all(len(splits) == 1 for splits in score_splits.values())


def test_all_seven_acceptance_controls_match_semantic_identity(tmp_path: Path):
    controls = [
        ("score-a", "page_010", 2, 1),
        ("score-b", "page_011", 8, 0),
        ("score-c", "page_033", 0, 0),
        ("score-d", "page_025", 0, 0),
        ("score-c", "page_033", 2, 7),
        ("score-e", "page_042", 8, 0),
        ("score-f", "page_055", 1, 1),
    ]
    samples = []
    acceptance_samples = []
    for index, (score, page, system, measure) in enumerate(controls):
        samples.append(
            {
                **_sample(f"source-{index}", score, page, 0),
                "system_index": system,
                "measure_index": measure,
            }
        )
        acceptance_samples.append(_sample(f"{page}_s{system}_m{measure}", score, page, 0))
    # Add non-control samples so score-level splitting has enough groups.
    samples.extend(_balanced_samples())
    manifest = tmp_path / "source.json"
    manifest.write_text(json.dumps({"samples": samples}), encoding="utf-8")
    acceptance = tmp_path / "acceptance.json"
    acceptance.write_text(json.dumps({"samples": acceptance_samples}), encoding="utf-8")

    eligible, contract = prepare_split_contract(
        manifest_path=manifest,
        split_path=tmp_path / "split.json",
        acceptance_manifest_path=acceptance,
        seed=42,
        validation_ratio=0.2,
        test_ratio=0.2,
    )

    assert len(contract["excluded_semantic_identities"]) == 7
    assert len(contract["excluded_sample_ids"]) == 7
    assert len(eligible) == len(samples) - 7


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


def test_within_score_split_keeps_pages_together_and_covers_each_score(tmp_path: Path):
    samples = []
    for score_index in range(5):
        score = f"score-{score_index}"
        for page_index in range(6):
            page = f"page-{page_index}"
            samples.append(_sample(f"{score}-{page}-neg", score, page, 0))
            samples.append(_sample(f"{score}-{page}-pos", score, page, 1))
    manifest = tmp_path / "source.json"
    manifest.write_text(json.dumps({"samples": samples}), encoding="utf-8")

    eligible, contract = prepare_split_contract(
        manifest_path=manifest,
        split_path=tmp_path / "within.json",
        seed=42,
        validation_ratio=0.125,
        test_ratio=0.125,
        group_level="page",
        fallback_group_level="system",
        split_mode=WITHIN_SCORE_SPLIT_MODE,
    )

    assert contract["split_mode"] == WITHIN_SCORE_SPLIT_MODE
    assert all(
        set(info["scores"]) == {f"score-{index}" for index in range(5)}
        for info in contract["counts"].values()
    )
    assert all(
        info["selected_group_level"] == "page" for info in contract["score_coverage"].values()
    )
    page_splits = {}
    for sample in eligible:
        key = (sample["score_id"], sample["page_id"])
        page_splits.setdefault(key, set()).add(contract["assignments"][sample["sample_id"]])
    assert all(len(splits) == 1 for splits in page_splits.values())
    for score_info in contract["score_coverage"].values():
        assert score_info["selected"]["complete"] is True


def test_within_score_split_records_minimal_system_fallback(tmp_path: Path):
    samples = []
    for score_index in range(5):
        score = f"score-{score_index}"
        if score_index == 0:
            for system_index in range(6):
                samples.append(
                    {
                        **_sample(f"{score}-s{system_index}-neg", score, "page-1", 0),
                        "system_index": system_index,
                        "measure_index": 0,
                    }
                )
                samples.append(
                    {
                        **_sample(f"{score}-s{system_index}-pos", score, "page-1", 1),
                        "system_index": system_index,
                        "measure_index": 1,
                    }
                )
        else:
            for page_index in range(6):
                page = f"page-{page_index}"
                samples.append(_sample(f"{score}-{page}-neg", score, page, 0))
                samples.append(_sample(f"{score}-{page}-pos", score, page, 1))
    manifest = tmp_path / "source.json"
    manifest.write_text(json.dumps({"samples": samples}), encoding="utf-8")

    _, contract = prepare_split_contract(
        manifest_path=manifest,
        split_path=tmp_path / "within.json",
        seed=42,
        validation_ratio=0.125,
        test_ratio=0.125,
        group_level="page",
        fallback_group_level="system",
        split_mode=WITHIN_SCORE_SPLIT_MODE,
    )

    score_info = contract["score_coverage"]["score-0"]
    assert score_info["selected_group_level"] == "system"
    assert score_info["fallback"]["from"] == "page"
    assert score_info["fallback"]["to"] == "system"
    assert score_info["selected"]["complete"] is True


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


def test_staff_core_center_roi_uses_source_staff_bbox_and_measure_center():
    sample = {
        **_sample("staff", "score-a", "page-1", 1),
        "bbox": [100, 200, 500, 400],
        "staff_bboxes": [[80, 220, 700, 320], [80, 500, 700, 600]],
    }
    rois = staff_relative_roi_bboxes(sample)
    assert rois == ((150.0, 220.0, 450.0, 320.0), (150.0, 500.0, 450.0, 600.0))

    perturbed = staff_relative_roi_bboxes(sample, [120, 200, 520, 400])
    assert perturbed == ((170.0, 220.0, 470.0, 320.0), (170.0, 500.0, 470.0, 600.0))
    assert STAFF_CORE_CENTER_VIEW == "staff-core-center-3h"


def test_diagnostic_staff_band_full_width_keeps_measure_x_and_staff_y():
    sample = {
        **_sample("staff", "score-a", "page-1", 0),
        "bbox": [100, 200, 500, 400],
        "staff_bboxes": [[80, 220, 700, 320], [80, 500, 700, 600]],
    }
    assert staff_band_full_width_rois(sample) == (
        (100.0, 220.0, 500.0, 320.0),
        (100.0, 500.0, 500.0, 600.0),
    )


def test_diagnostic_staff_bbox_sensitivity_variants_keep_x_and_apply_signed_y_rules():
    variants = dict(_staff_bbox_variants([[10, 20, 100, 60]], deltas=(1,)))
    assert variants["staff_translate_y_plus_1px"] == [[10.0, 21.0, 100.0, 61.0]]
    assert variants["staff_top_plus_1px"] == [[10.0, 21.0, 100.0, 60.0]]
    assert variants["staff_bottom_plus_1px"] == [[10.0, 20.0, 100.0, 61.0]]
    assert variants["staff_height_plus_1px"] == [[10.0, 19.0, 100.0, 61.0]]


def test_staff_relative_dataset_is_one_measure_item_with_variable_staff_count(tmp_path: Path):
    image_path = tmp_path / "page.png"
    cv2.imwrite(str(image_path), np.full((160, 240, 3), 255, dtype=np.uint8))
    sample = {
        **_sample("staff", "score-a", "page-1", 1, image_path=str(image_path)),
        "bbox": [40, 20, 200, 140],
        "staff_bboxes": [[20, 30, 220, 70], [20, 90, 220, 130]],
    }
    dataset = StaffRelativeMMRDataset(
        [sample], manifest_path=tmp_path / "manifest.json", transform=transforms.ToTensor()
    )
    staff_images, label = dataset[0]
    batch_images, staff_mask, labels = collate_staff_relative_batch([(staff_images, label)])
    assert len(dataset) == 1
    assert tuple(staff_images.shape) == (2, 3, 40, 120)
    assert tuple(batch_images.shape) == (1, 2, 3, 40, 120)
    assert staff_mask.tolist() == [[True, True]]
    assert labels.tolist() == [1.0]


def test_staff_relative_model_aggregates_to_one_measure_logit(monkeypatch):
    class FakeEncoder(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.fc = torch.nn.Linear(3, 1, bias=False)
            torch.nn.init.constant_(self.fc.weight, 1.0)

        def forward(self, images):
            return images.mean(dim=(2, 3)).sum(dim=1, keepdim=True)

    monkeypatch.setattr(
        "tools.mmr_training.issue332.staff_model.models.resnet18",
        lambda weights: FakeEncoder(),
    )
    model = StaffRelativeResNet18(weights=None)
    images = torch.zeros((2, 2, 3, 4, 4))
    images[0, 1] = 1.0
    images[1, 1] = 1.0
    mask = torch.tensor([[True, True], [True, False]])
    logits = model(images, mask)
    assert logits.shape == (2, 1)
    assert logits[0].item() == 3.0
    assert logits[1].item() == 0.0


def test_geometry_augmentation_probability_controls_native_exposure():
    sample = _sample("x", "score-a", "page-1", 1)
    assert (
        choose_geometry_bbox(
            sample,
            policy="absolute",
            deltas_px=(1, 2, 4),
            rng=random.Random(42),
            geometry_augmentation_probability=0.0,
        )[0]
        == "native"
    )

    rng = random.Random(42)
    names = [
        choose_geometry_bbox(
            sample,
            policy="absolute",
            deltas_px=(1, 2, 4),
            rng=rng,
            geometry_augmentation_probability=1.0,
        )[0]
        for _ in range(1000)
    ]
    assert "native" not in names
    assert all(
        any(name.startswith(family + "_") for family in GEOMETRY_FAMILIES[1:]) for name in names
    )
    assert DEFAULT_GEOMETRY_AUGMENTATION_PROBABILITY == 5 / 6

    rng = random.Random(332)
    names = [
        choose_geometry_bbox(
            sample,
            policy="absolute",
            deltas_px=(1, 2, 4),
            rng=rng,
            geometry_augmentation_probability=0.25,
        )[0]
        for _ in range(4000)
    ]
    native_count = names.count("native")
    assert 2850 <= native_count <= 3150


def test_geometry_augmentation_can_restrict_to_one_family():
    sample = _sample("x", "score-a", "page-1", 1)
    rng = random.Random(332)
    names = [
        choose_geometry_bbox(
            sample,
            policy="absolute",
            deltas_px=(1, 2, 4),
            rng=rng,
            geometry_augmentation_probability=1.0,
            geometry_families=("translate_y",),
        )[0]
        for _ in range(1000)
    ]
    assert all(name.startswith("translate_y_") for name in names)
    assert {name.rsplit("_", 2)[-2] for name in names} == {"minus", "plus"}
    assert {name.rsplit("_", 1)[-1] for name in names} == {"1px", "2px", "4px"}


def test_geometry_family_coordinates_match_benchmark_contract():
    variants = {
        variant.name: variant.bbox for variant in generate_geometry_variants((10, 20, 30, 40), (2,))
    }
    assert variants["x1_plus_2px"] == (12, 20, 30, 40)
    assert variants["x2_plus_2px"] == (10, 20, 32, 40)
    assert variants["translate_x_plus_2px"] == (12, 20, 32, 40)
    assert variants["translate_y_plus_2px"] == (10, 22, 30, 42)
    assert variants["expand_contract_x_plus_2px"] == (8, 20, 32, 40)
    assert variants["expand_contract_x_minus_2px"] == (12, 20, 28, 40)


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
    assert train.geometry_augmentation_probability == 5 / 6
    assert validation.geometry_augmentation_probability == 0.0
    assert test.geometry_augmentation_probability == 0.0
    assert class_counts == {
        "train": {"0": 4, "1": 4},
        "val": {"0": 1, "1": 1},
        "test": {"0": 1, "1": 1},
    }
    assert _train_pos_weight(class_counts) == 1.0
    assert (
        _train_pos_weight(
            {
                "train": {"0": 3, "1": 1},
                "val": {"0": 100, "1": 1},
                "test": {"0": 1, "1": 100},
            }
        )
        == 3.0
    )


def test_source_page_decode_is_cached_and_unused_staff_mask_is_not_read(tmp_path, monkeypatch):
    image_path = tmp_path / "page.png"
    cv2.imwrite(str(image_path), np.full((100, 100, 3), 255, dtype=np.uint8))
    sample = {
        **_sample("cached", "score-a", "page-1", 1, image_path=str(image_path)),
        "staff_mask_path": "missing-staff-mask.png",
    }
    clear_source_page_cache()
    original_imread = geometry_training.cv2.imread
    calls = []

    def counting_imread(path, flags):
        calls.append((path, flags))
        return original_imread(path, flags)

    monkeypatch.setattr(geometry_training.cv2, "imread", counting_imread)
    dataset = SemanticMMRDataset(
        [sample],
        manifest_path=tmp_path / "manifest.json",
        transform=transforms.ToTensor(),
        text_noise=None,
    )

    dataset[0]
    dataset[0]

    assert len(calls) == 1
    assert calls[0][0] == str(image_path.resolve())
    assert source_page_cache_info().maxsize == 4
    assert source_page_cache_info().hits >= 1


def test_legacy_mode_retains_full_corpus_pos_weight_counts(tmp_path):
    data_root = tmp_path / "legacy"
    for label in (0, 1):
        class_root = data_root / "train" / str(label)
        class_root.mkdir(parents=True)
        for index in range(5):
            cv2.imwrite(
                str(class_root / f"sample-{index}.jpg"),
                np.full((32, 32, 3), 255, dtype=np.uint8),
            )
    args = SimpleNamespace(
        data_root=str(data_root),
        seed=42,
        staff_mask_root=None,
        staff_mask_suffix="_staff",
        staff_mask_ext=".png",
    )

    train, _validation, _test, _labels, _split, class_counts = _legacy_datasets(
        args,
        transforms.ToTensor(),
        transforms.ToTensor(),
        text_noise=None,
    )

    assert class_counts == {
        "train": {"0": 4, "1": 4},
        "val": {"0": 1, "1": 1},
        "test": {"0": 0, "1": 0},
    }
    assert train.full_corpus_class_counts == {"0": 5, "1": 5}


def test_formal_generator_emits_semantic_manifest_with_provenance(tmp_path: Path):
    image_path = tmp_path / "page.png"
    cv2.imwrite(str(image_path), np.full((100, 100, 3), 255, dtype=np.uint8))
    numbering_path = tmp_path / "numbering.json"
    numbering_path.write_text(
        json.dumps(
            {
                "pages": [
                    {
                        "systems": [
                            {"measures": [{"bbox": [10, 10, 50, 50]}, {"bbox": [50, 10, 90, 50]}]}
                        ]
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    gt_path = tmp_path / "rest_gt.json"
    gt_path.write_text(
        json.dumps({"overrides": [{"measure_index": 1, "rest_count": 2}]}), encoding="utf-8"
    )
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "pages": [
                    {
                        "name": "score-a_page_001",
                        "score_id": "explicit-score",
                        "page_id": "explicit-page-001",
                        "image": "page.png",
                        "numbering": "numbering.json",
                        "rest_gt": "rest_gt.json",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "manifest.json"
    create_dataset_from_configs(
        [config_path],
        tmp_path / "dataset",
        manifest_output=manifest_path,
        source_root=tmp_path,
    )

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(payload["samples"]) == 2
    assert payload["samples"][0]["score_id"] == "explicit-score"
    assert payload["samples"][0]["page_id"] == "explicit-page-001"
    assert payload["samples"][0]["system_index"] == 0
    assert payload["samples"][0]["measure_index"] == 0
    assert payload["samples"][1]["global_measure_index"] == 1
    assert [sample["label"] for sample in payload["samples"]] == [0, 1]
    assert payload["samples"][0]["provenance"]["numbering_sha256"]


def test_score_level_folds_are_cyclic_and_have_class_coverage(tmp_path: Path):
    samples = []
    for score_index in range(5):
        score = f"score-{score_index}"
        for local_index, label in enumerate((0, 0, 1, 1)):
            samples.append(_sample(f"{score}-{local_index}", score, f"page-{local_index}", label))
    manifest = tmp_path / "source.json"
    manifest.write_text(json.dumps({"samples": samples}), encoding="utf-8")
    acceptance = tmp_path / "acceptance.json"
    acceptance.write_text(json.dumps({"samples": [samples[2]]}), encoding="utf-8")

    folds = prepare_score_level_folds(
        manifest_path=manifest,
        output_dir=tmp_path / "folds",
        acceptance_manifest_path=acceptance,
        seed=42,
        training_profile="historical",
    )

    assert len(folds) == 5
    assert (tmp_path / "folds" / "index.json").is_file()
    score_order = sorted({sample["score_id"] for sample in samples})
    for index, fold in enumerate(folds):
        assert fold["test_score"] == score_order[index]
        assert fold["validation_score"] == score_order[(index + 1) % 5]
        assert fold["train_scores"] == [
            score
            for score in score_order
            if score not in {fold["test_score"], fold["validation_score"]}
        ]
        assert all(
            counts["0"] > 0 and counts["1"] > 0
            for counts in (
                fold["counts"][name]["classes"] for name in ("train", "validation", "test")
            )
        )
        assert samples[2]["sample_id"] not in fold["assignments"]
        assert fold["provenance"]["source_manifest_sha256"]
        assert fold["provenance"]["acceptance_manifest_sha256"]
        assert fold["provenance"]["fold_payload_sha256"]


def test_score_level_summary_reports_confusion_and_metrics():
    rows = [
        {"score_id": "a", "label": 1, "prediction": 1},
        {"score_id": "a", "label": 0, "prediction": 1},
        {"score_id": "b", "label": 0, "prediction": 0},
        {"score_id": "b", "label": 1, "prediction": 0},
    ]
    summary = summarize_native_rows(rows)
    assert summary["pooled"]["confusion_matrix"] == {"tn": 1, "fp": 1, "fn": 1, "tp": 1}
    assert summary["pooled"]["precision"] == 0.5
    assert summary["pooled"]["recall"] == 0.5
    assert summary["by_score"]["a"]["confusion_matrix"] == {
        "tn": 0,
        "fp": 1,
        "fn": 0,
        "tp": 1,
    }


def test_dual_view_fusion_is_monotonic_in_each_probability():
    common = {"weights": [0.75, 1.25], "bias": -0.3}
    base = fuse_probabilities(0.2, 0.3, **common)
    assert fuse_probabilities(0.4, 0.3, **common) > base
    assert fuse_probabilities(0.2, 0.6, **common) > base


def test_dual_view_fusion_rejects_negative_weights():
    with pytest.raises(ValueError, match="non-negative"):
        fuse_probabilities(0.2, 0.3, weights=[1.0, -0.1], bias=0.0)


def test_frozen_logit_fusion_fits_complementary_views_deterministically():
    # Positives are high in both views.  Each negative is high in only one,
    # matching the complementarity observed in the retained Issue #332 data.
    features = torch.tensor([[4.0, 4.0], [3.0, 3.0], [4.0, -4.0], [-4.0, 4.0], [-3.0, -3.0]])
    labels = torch.tensor([[1.0], [1.0], [0.0], [0.0], [0.0]])
    torch.manual_seed(42)
    model, fit = fit_fusion_head(
        features,
        labels,
        features,
        labels,
        epochs=200,
        learning_rate=0.03,
    )
    probabilities = torch.sigmoid(model(features)).reshape(-1)
    assert ((probabilities >= 0.5).to(torch.float32) == labels.reshape(-1)).all()
    weights = [float(value) for value in model.effective_weights().detach()]
    assert min(weights) >= 0.0
    assert sum(weights) == pytest.approx(1.0)
    assert fit["best"]["validation_f1"] == 1.0


def test_final_causal_control_heads_preserve_their_constraints():
    features = torch.tensor([[2.0, -4.0], [-1.0, 3.0]])
    full_only = FullOnlyBias()
    full_only.bias.data.fill_(0.25)
    assert torch.allclose(full_only(features).reshape(-1), features[:, 0] + 0.25)

    zero_bias = ZeroBiasDualView()
    weights = zero_bias.effective_weights()
    assert min(float(value) for value in weights.detach()) >= 0.0
    assert float(weights.detach().sum()) == pytest.approx(1.0)
    assert torch.allclose(zero_bias(features).reshape(-1), features.mean(dim=1))


def test_final_envelope_records_unique_crossings_and_direction():
    rows = [
        {"sample_id": "negative", "label": 0, "variant": "native", "probability": 0.05},
        {"sample_id": "negative", "label": 0, "variant": "joint-a", "probability": 0.2},
        {"sample_id": "negative", "label": 0, "variant": "joint-b", "probability": 0.6},
        {"sample_id": "positive", "label": 1, "variant": "native", "probability": 0.8},
        {"sample_id": "positive", "label": 1, "variant": "joint-a", "probability": 0.4},
    ]
    summary = _envelope_summary(rows)
    assert summary["main"]["unique_crossing_count"] == 2
    assert summary["main"]["negative_to_positive"] == ["negative"]
    assert summary["main"]["positive_to_negative"] == ["positive"]
    assert summary["rescue"]["unique_crossing_count"] == 1
    assert summary["samples"]["negative"]["probability_range"] == pytest.approx(0.55)
