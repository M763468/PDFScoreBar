"""Split-safe semantic training helpers for the MMR classifier.

The helpers in this module keep Issue #332 geometry experiments on the regular
``train_mmr_classifier.py`` path. They freeze semantic train/validation/test
membership before augmentation and apply source-space geometry perturbations
on-the-fly so baseline and candidate see the same number of semantic samples
per epoch.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Sequence

import cv2
import torch
from PIL import Image
from torch.utils.data import Dataset

from tools.mmr_training.issue332_geometry_benchmark import (
    _validated_bbox,
    crop_measure,
    generate_geometry_variants,
)

DEFAULT_SPLIT_SEED = 42
DEFAULT_VALIDATION_RATIO = 0.2
DEFAULT_TEST_RATIO = 0.2
WITHIN_SCORE_SPLIT_MODE = "within-score-grouped"
DEFAULT_MARGIN_PX = 20
DEFAULT_DELTAS_PX = (1, 2, 4)
# The previous absolute policy sampled native plus five perturbation families
# uniformly, so its perturbation exposure was 5/6.
DEFAULT_GEOMETRY_AUGMENTATION_PROBABILITY = 5.0 / 6.0
DEFAULT_EXCLUDED_TAGS = (
    "acceptance-control",
    "issue277-control",
    "zero-fixture",
    "one-bar",
)
GEOMETRY_FAMILIES = (
    "native",
    "x1",
    "x2",
    "translate_x",
    "translate_y",
    "expand_contract_x",
)
# The canonical 68-page corpus has page-grouped samples: four cached pages
# retain the observed hit rate while keeping one worker below the measured RSS
# of larger 8/16-page caches.
SOURCE_PAGE_CACHE_SIZE = 4


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@lru_cache(maxsize=SOURCE_PAGE_CACHE_SIZE)
def _read_source_page(path: str):
    """Read one source page; the bounded cache is private to each worker process."""
    return cv2.imread(path, cv2.IMREAD_COLOR)


def clear_source_page_cache() -> None:
    _read_source_page.cache_clear()


def source_page_cache_info():
    return _read_source_page.cache_info()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _git_head() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def load_semantic_samples(path: Path) -> list[dict[str, Any]]:
    raw_samples = _load_json(path).get("samples")
    if not isinstance(raw_samples, list) or not raw_samples:
        raise ValueError("manifest must contain a non-empty 'samples' list")

    required = {"sample_id", "score_id", "page_id", "image_path", "bbox", "label"}
    samples: list[dict[str, Any]] = []
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

        sample["sample_id"] = sample_id
        sample["score_id"] = str(sample["score_id"])
        sample["page_id"] = str(sample["page_id"])
        sample["image_path"] = str(sample["image_path"])
        sample["bbox"] = list(_validated_bbox(sample["bbox"]))
        sample["label"] = label
        sample["tags"] = [str(tag) for tag in sample.get("tags", [])]
        samples.append(sample)
    return samples


def semantic_identity(sample: dict[str, Any]) -> tuple[str, str, int, int] | None:
    """Return the stable score/page/system/measure identity when available."""
    score_id = str(sample.get("score_id", ""))
    page_id = str(sample.get("page_id", ""))
    if "system_index" in sample and "measure_index" in sample:
        return score_id, page_id, int(sample["system_index"]), int(sample["measure_index"])
    match = re.search(
        r"(?:^|::)page_(\d+)(?:_|::)s(\d+)(?:_|::)m(\d+)$", str(sample.get("sample_id", ""))
    )
    if match:
        return score_id, f"page_{match.group(1)}", int(match.group(2)), int(match.group(3))
    return None


def _group_key(sample: dict[str, Any], group_level: str) -> str:
    if group_level == "score":
        return sample["score_id"]
    if group_level == "page":
        return f"{sample['score_id']}::{sample['page_id']}"
    if group_level == "system":
        if "system_index" not in sample:
            raise ValueError("system grouping requires system_index")
        return f"{sample['score_id']}::{sample['page_id']}::s{sample['system_index']}"
    raise ValueError("group_level must be 'score', 'page', or 'system'")


def _class_counts(samples: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = {"0": 0, "1": 0}
    for sample in samples:
        counts[str(int(sample["label"]))] += 1
    return counts


def _coverage_ok(
    split_samples: dict[str, list[dict[str, Any]]],
    all_samples: Sequence[dict[str, Any]],
) -> bool:
    total = _class_counts(all_samples)
    for name in ("train", "validation", "test"):
        if not split_samples[name]:
            return False
        counts = _class_counts(split_samples[name])
        for label in ("0", "1"):
            if total[label] >= 3 and counts[label] == 0:
                return False
    return True


def _eligible_samples(
    *,
    manifest_path: Path,
    acceptance_manifest_path: Path | None,
    excluded_tags: Sequence[str],
) -> tuple[list[dict[str, Any]], set[str], set[tuple[str, str, int, int] | None]]:
    samples = load_semantic_samples(manifest_path)
    acceptance_samples = (
        load_semantic_samples(acceptance_manifest_path) if acceptance_manifest_path else []
    )
    acceptance_ids = {sample["sample_id"] for sample in acceptance_samples}
    acceptance_semantic_ids = {
        identity
        for sample in acceptance_samples
        if (identity := semantic_identity(sample)) is not None
    }
    excluded_tag_set = {str(tag) for tag in excluded_tags}
    excluded_ids = {
        sample["sample_id"]
        for sample in samples
        if sample["sample_id"] in acceptance_ids
        or (
            semantic_identity(sample) is not None
            and semantic_identity(sample) in acceptance_semantic_ids
        )
        or bool(set(sample.get("tags", [])) & excluded_tag_set)
    }
    eligible = [sample for sample in samples if sample["sample_id"] not in excluded_ids]
    if not eligible:
        raise ValueError("all semantic samples were excluded from training")
    return eligible, excluded_ids, acceptance_semantic_ids


def _candidate_assignment(
    samples: Sequence[dict[str, Any]],
    *,
    group_level: str,
    seed: int,
    validation_ratio: float,
    test_ratio: float,
    attempt: int,
) -> dict[str, str]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for sample in samples:
        groups.setdefault(_group_key(sample, group_level), []).append(sample)

    names = list(groups)
    random.Random(seed + attempt * 1009).shuffle(names)
    if len(names) < 3:
        raise ValueError(f"{group_level} split requires at least three groups")

    target_test = max(1, round(len(samples) * test_ratio))
    target_validation = max(1, round(len(samples) * validation_ratio))
    counts = {"test": 0, "validation": 0}
    assignments: dict[str, str] = {}

    for name in names:
        group = groups[name]
        if counts["test"] < target_test:
            split = "test"
        elif counts["validation"] < target_validation:
            split = "validation"
        else:
            split = "train"
        if split in counts:
            counts[split] += len(group)
        for sample in group:
            assignments[sample["sample_id"]] = split
    return assignments


def freeze_split(
    samples: Sequence[dict[str, Any]],
    *,
    seed: int = DEFAULT_SPLIT_SEED,
    validation_ratio: float = DEFAULT_VALIDATION_RATIO,
    test_ratio: float = DEFAULT_TEST_RATIO,
    group_level: str = "score",
    fallback_group_level: str | None = "page",
) -> tuple[dict[str, str], str]:
    """Freeze train/validation/test groups before any augmentation is sampled."""

    if not 0.0 < validation_ratio < 1.0:
        raise ValueError("validation_ratio must be between 0 and 1")
    if not 0.0 < test_ratio < 1.0:
        raise ValueError("test_ratio must be between 0 and 1")
    if validation_ratio + test_ratio >= 1.0:
        raise ValueError("validation_ratio + test_ratio must be < 1")

    levels = [group_level]
    if fallback_group_level and fallback_group_level != group_level:
        levels.append(fallback_group_level)

    for level in levels:
        best: tuple[float, dict[str, str]] | None = None
        for attempt in range(256):
            try:
                assignments = _candidate_assignment(
                    samples,
                    group_level=level,
                    seed=seed,
                    validation_ratio=validation_ratio,
                    test_ratio=test_ratio,
                    attempt=attempt,
                )
            except ValueError:
                break

            split_samples = {
                name: [sample for sample in samples if assignments[sample["sample_id"]] == name]
                for name in ("train", "validation", "test")
            }
            if not _coverage_ok(split_samples, samples):
                continue

            expected = {
                "validation": len(samples) * validation_ratio,
                "test": len(samples) * test_ratio,
            }
            score = abs(len(split_samples["validation"]) - expected["validation"]) + abs(
                len(split_samples["test"]) - expected["test"]
            )
            if best is None or score < best[0]:
                best = (score, assignments)

        if best is not None:
            return best[1], level

    raise ValueError(
        "could not create leakage-safe train/validation/test split with class coverage "
        f"at levels {levels}"
    )


def _coverage_report(
    split_samples: dict[str, list[dict[str, Any]]],
    all_samples: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    total = _class_counts(all_samples)
    report: dict[str, Any] = {}
    for name in ("train", "validation", "test"):
        counts = _class_counts(split_samples[name])
        missing = [label for label in ("0", "1") if total[label] >= 3 and counts[label] == 0]
        report[name] = {"classes": counts, "missing_classes": missing}
    return {
        "overall_classes": total,
        "splits": report,
        "complete": all(not value["missing_classes"] for value in report.values()),
    }


def _best_grouped_assignment(
    samples: Sequence[dict[str, Any]],
    *,
    group_level: str,
    seed: int,
    validation_ratio: float,
    test_ratio: float,
    attempts: int = 4096,
) -> tuple[dict[str, str] | None, dict[str, Any]]:
    """Find a deterministic group assignment closest to the requested ratios.

    Coverage is scored before ratio error.  This keeps the page-level contract
    primary while making the result stable for small, imbalanced score corpora.
    """

    groups: dict[str, list[dict[str, Any]]] = {}
    for sample in samples:
        groups.setdefault(_group_key(sample, group_level), []).append(sample)
    if len(groups) < 3:
        return None, {
            "group_count": len(groups),
            "coverage": None,
            "reason": "fewer than three groups",
        }

    target = {
        "train": len(samples) * (1.0 - validation_ratio - test_ratio),
        "validation": len(samples) * validation_ratio,
        "test": len(samples) * test_ratio,
    }
    best: tuple[tuple[float, float, float], dict[str, str], dict[str, Any]] | None = None
    split_names = ("train", "validation", "test")
    for attempt in range(attempts):
        rng = random.Random(seed + attempt * 1009)
        names = list(groups)
        rng.shuffle(names)
        assignment_by_group: dict[str, str] = {}
        sizes = {name: 0 for name in split_names}
        # Seed each split with one group so every score is represented in all
        # three partitions, even when page groups are small.
        for name, split in zip(names[:3], split_names):
            assignment_by_group[name] = split
            sizes[split] += len(groups[name])
        for group_name in names[3:]:
            group_size = len(groups[group_name])
            deficits = {split: max(target[split] - sizes[split], 0.0) for split in split_names}
            max_deficit = max(deficits.values())
            candidates = [split for split in split_names if deficits[split] == max_deficit]
            split = rng.choice(candidates)
            assignment_by_group[group_name] = split
            sizes[split] += group_size

        assignments = {
            sample["sample_id"]: assignment_by_group[_group_key(sample, group_level)]
            for sample in samples
        }
        split_samples = {
            name: [sample for sample in samples if assignments[sample["sample_id"]] == name]
            for name in split_names
        }
        coverage = _coverage_report(split_samples, samples)
        missing = sum(len(value["missing_classes"]) for value in coverage["splits"].values())
        ratio_error = sum(abs(len(split_samples[name]) - target[name]) for name in split_names)
        # A small deterministic tie breaker avoids depending on dictionary order.
        score = (float(missing), ratio_error, rng.random())
        if best is None or score < best[0]:
            best = (score, assignments, coverage)
            if missing == 0 and ratio_error == 0:
                break

    assert best is not None
    _score, assignments, coverage = best
    return assignments, {
        "group_count": len(groups),
        "coverage": coverage,
        "sample_counts": {
            name: sum(1 for sample_id, split in assignments.items() if split == name)
            for name in split_names
        },
    }


def _prepare_within_score_split(
    samples: Sequence[dict[str, Any]],
    *,
    seed: int,
    validation_ratio: float,
    test_ratio: float,
    group_level: str,
    fallback_group_level: str | None,
) -> tuple[dict[str, str], dict[str, Any]]:
    scores = sorted({sample["score_id"] for sample in samples})
    if len(scores) != 5:
        raise ValueError(f"within-score split requires exactly five scores, got {scores}")
    if group_level != "page":
        raise ValueError("within-score grouped mode requires page as the primary group level")

    all_assignments: dict[str, str] = {}
    coverage: dict[str, Any] = {}
    for score_index, score_id in enumerate(scores):
        score_samples = [sample for sample in samples if sample["score_id"] == score_id]
        page_assignments, page_report = _best_grouped_assignment(
            score_samples,
            group_level=group_level,
            seed=seed + score_index * 100003,
            validation_ratio=validation_ratio,
            test_ratio=test_ratio,
        )
        if page_assignments is None:
            page_complete = False
            selected_assignments = None
        else:
            page_complete = bool(page_report["coverage"]["complete"])
            selected_assignments = page_assignments
        selected_level = group_level
        fallback = None
        if not page_complete and fallback_group_level:
            system_assignments, system_report = _best_grouped_assignment(
                score_samples,
                group_level=fallback_group_level,
                seed=seed + score_index * 100003,
                validation_ratio=validation_ratio,
                test_ratio=test_ratio,
            )
            if system_assignments is not None and system_report["coverage"]["complete"]:
                selected_assignments = system_assignments
                selected_level = fallback_group_level
                fallback = {
                    "from": group_level,
                    "to": fallback_group_level,
                    "reason": "page grouping could not establish class coverage",
                    "page_report": page_report,
                }
            else:
                fallback = {
                    "from": group_level,
                    "to": None,
                    "reason": "page and permitted fallback grouping could not establish class coverage",
                    "page_report": page_report,
                    "fallback_report": system_report if system_assignments is not None else None,
                }
        if selected_assignments is None:
            raise ValueError(f"score {score_id} cannot be split with the permitted group levels")
        for sample_id, split in selected_assignments.items():
            if sample_id in all_assignments:
                raise ValueError(f"duplicate assignment for sample {sample_id}")
            all_assignments[sample_id] = split
        selected_samples = {
            name: [
                sample
                for sample in score_samples
                if selected_assignments[sample["sample_id"]] == name
            ]
            for name in ("train", "validation", "test")
        }
        coverage[score_id] = {
            "selected_group_level": selected_level,
            "page": page_report,
            "fallback": fallback,
            "selected": _coverage_report(selected_samples, score_samples),
        }

    return all_assignments, coverage


def prepare_split_contract(
    *,
    manifest_path: Path,
    split_path: Path,
    acceptance_manifest_path: Path | None = None,
    excluded_tags: Sequence[str] = DEFAULT_EXCLUDED_TAGS,
    seed: int = DEFAULT_SPLIT_SEED,
    validation_ratio: float = DEFAULT_VALIDATION_RATIO,
    test_ratio: float = DEFAULT_TEST_RATIO,
    group_level: str = "score",
    fallback_group_level: str | None = "page",
    split_mode: str = "score-grouped",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Exclude acceptance controls, then create or validate a frozen split artifact."""

    eligible, excluded_ids, acceptance_semantic_ids = _eligible_samples(
        manifest_path=manifest_path,
        acceptance_manifest_path=acceptance_manifest_path,
        excluded_tags=excluded_tags,
    )

    source_sha = sha256_file(manifest_path)
    acceptance_sha = sha256_file(acceptance_manifest_path) if acceptance_manifest_path else None

    if split_path.exists():
        contract = _load_json(split_path)
        existing_mode = contract.get("split_mode", "score-grouped")
        if existing_mode != split_mode:
            raise ValueError(
                f"existing split mode {existing_mode!r} does not match requested {split_mode!r}"
            )
        provenance = contract.get("provenance", {})
        if provenance.get("source_manifest_sha256") != source_sha:
            raise ValueError("existing split source manifest SHA256 does not match")
        if provenance.get("acceptance_manifest_sha256") != acceptance_sha:
            raise ValueError("existing split acceptance manifest SHA256 does not match")
        if sorted(contract.get("excluded_sample_ids", [])) != sorted(excluded_ids):
            raise ValueError("existing split exclusion set does not match")
        assignments = contract.get("assignments")
        if not isinstance(assignments, dict):
            raise ValueError("existing split artifact lacks assignments")
        if set(assignments) != {sample["sample_id"] for sample in eligible}:
            raise ValueError("existing split assignments do not match eligible semantic samples")
        return eligible, contract

    if split_mode == WITHIN_SCORE_SPLIT_MODE:
        assignments, score_coverage = _prepare_within_score_split(
            eligible,
            seed=seed,
            validation_ratio=validation_ratio,
            test_ratio=test_ratio,
            group_level=group_level,
            fallback_group_level=fallback_group_level,
        )
        used_group_level = group_level
    elif split_mode == "score-grouped":
        assignments, used_group_level = freeze_split(
            eligible,
            seed=seed,
            validation_ratio=validation_ratio,
            test_ratio=test_ratio,
            group_level=group_level,
            fallback_group_level=fallback_group_level,
        )
        score_coverage = None
    else:
        raise ValueError(f"unsupported split mode: {split_mode}")

    split_samples = {
        name: [sample for sample in eligible if assignments[sample["sample_id"]] == name]
        for name in ("train", "validation", "test")
    }
    contract = {
        "schema": "issue332.mmr_training_split.v1",
        "split_mode": split_mode,
        "provenance": {
            "source_manifest": str(manifest_path.resolve()),
            "source_manifest_sha256": source_sha,
            "acceptance_manifest": str(acceptance_manifest_path.resolve())
            if acceptance_manifest_path
            else None,
            "acceptance_manifest_sha256": acceptance_sha,
            "training_code_commit": _git_head(),
        },
        "seed": seed,
        "requested_group_level": group_level,
        "used_group_level": used_group_level,
        "fallback_group_level": fallback_group_level,
        "score_coverage": score_coverage,
        "validation_ratio": validation_ratio,
        "test_ratio": test_ratio,
        "excluded_before_split": True,
        "excluded_sample_ids": sorted(excluded_ids),
        "excluded_semantic_identities": [
            list(identity) for identity in sorted(acceptance_semantic_ids)
        ],
        "assignments": assignments,
        "counts": {
            name: {
                "samples": len(split_samples[name]),
                "classes": _class_counts(split_samples[name]),
                "scores": sorted({sample["score_id"] for sample in split_samples[name]}),
                "pages": sorted(
                    {f"{sample['score_id']}::{sample['page_id']}" for sample in split_samples[name]}
                ),
            }
            for name in ("train", "validation", "test")
        },
    }
    split_path.parent.mkdir(parents=True, exist_ok=True)
    split_path.write_text(json.dumps(contract, indent=2, sort_keys=True), encoding="utf-8")
    return eligible, contract


def prepare_score_level_folds(
    *,
    manifest_path: Path,
    output_dir: Path,
    acceptance_manifest_path: Path | None = None,
    excluded_tags: Sequence[str] = DEFAULT_EXCLUDED_TAGS,
    seed: int = DEFAULT_SPLIT_SEED,
    training_profile: str = "historical",
) -> list[dict[str, Any]]:
    """Write five cyclic score-level train/validation/test split artifacts.

    The score order is deterministic. Fold ``i`` uses score ``i`` as test,
    score ``i + 1`` modulo five as validation, and the remaining three scores
    as train. Acceptance controls are removed before assignments are made.
    """

    eligible, excluded_ids, acceptance_semantic_ids = _eligible_samples(
        manifest_path=manifest_path,
        acceptance_manifest_path=acceptance_manifest_path,
        excluded_tags=excluded_tags,
    )
    scores = sorted({sample["score_id"] for sample in eligible})
    if len(scores) != 5:
        raise ValueError(f"score-level folds require exactly five scores, got {scores}")

    source_sha = sha256_file(manifest_path)
    acceptance_sha = sha256_file(acceptance_manifest_path) if acceptance_manifest_path else None
    output_dir.mkdir(parents=True, exist_ok=True)
    folds: list[dict[str, Any]] = []

    for fold_index, test_score in enumerate(scores):
        validation_score = scores[(fold_index + 1) % len(scores)]
        score_split = {
            test_score: "test",
            validation_score: "validation",
        }
        score_split.update({score: "train" for score in scores if score not in score_split})
        assignments = {sample["sample_id"]: score_split[sample["score_id"]] for sample in eligible}
        split_samples = {
            name: [sample for sample in eligible if assignments[sample["sample_id"]] == name]
            for name in ("train", "validation", "test")
        }
        counts = {name: _class_counts(items) for name, items in split_samples.items()}
        if any(counts[name]["0"] == 0 or counts[name]["1"] == 0 for name in counts):
            raise ValueError(f"fold {fold_index + 1} lacks class coverage: {counts}")

        fold_id = f"fold_{fold_index + 1}"
        contract: dict[str, Any] = {
            "schema": "issue332.mmr_training_score_fold.v1",
            "fold_id": fold_id,
            "score_order": scores,
            "test_score": test_score,
            "validation_score": validation_score,
            "train_scores": [
                score for score in scores if score not in {test_score, validation_score}
            ],
            "seed": seed,
            "training_profile": training_profile,
            "excluded_before_split": True,
            "excluded_sample_ids": sorted(excluded_ids),
            "excluded_semantic_identities": [
                list(identity)
                for identity in sorted(acceptance_semantic_ids)
                if identity is not None
            ],
            "assignments": assignments,
            "counts": {
                name: {
                    "samples": len(split_samples[name]),
                    "classes": counts[name],
                    "scores": sorted({sample["score_id"] for sample in split_samples[name]}),
                    "pages": sorted(
                        {
                            f"{sample['score_id']}::{sample['page_id']}"
                            for sample in split_samples[name]
                        }
                    ),
                }
                for name in ("train", "validation", "test")
            },
            "provenance": {
                "source_manifest": str(manifest_path.resolve()),
                "source_manifest_sha256": source_sha,
                "acceptance_manifest": str(acceptance_manifest_path.resolve())
                if acceptance_manifest_path
                else None,
                "acceptance_manifest_sha256": acceptance_sha,
                "training_code_commit": _git_head(),
            },
        }
        canonical = json.dumps(contract, indent=2, sort_keys=True).encode("utf-8")
        contract["provenance"]["fold_payload_sha256"] = hashlib.sha256(canonical).hexdigest()
        path = output_dir / f"{fold_id}.json"
        path.write_text(json.dumps(contract, indent=2, sort_keys=True), encoding="utf-8")
        folds.append({"fold_id": fold_id, "path": str(path), **contract})

    index = {
        "schema": "issue332.mmr_training_score_folds.v1",
        "score_order": scores,
        "seed": seed,
        "training_profile": training_profile,
        "provenance": {
            "source_manifest": str(manifest_path.resolve()),
            "source_manifest_sha256": source_sha,
            "acceptance_manifest": str(acceptance_manifest_path.resolve())
            if acceptance_manifest_path
            else None,
            "acceptance_manifest_sha256": acceptance_sha,
            "training_code_commit": _git_head(),
        },
        "folds": [
            {
                "fold_id": fold["fold_id"],
                "path": fold["path"],
                "test_score": fold["test_score"],
                "validation_score": fold["validation_score"],
                "train_scores": fold["train_scores"],
                "fold_payload_sha256": fold["provenance"]["fold_payload_sha256"],
            }
            for fold in folds
        ],
    }
    (output_dir / "index.json").write_text(
        json.dumps(index, indent=2, sort_keys=True), encoding="utf-8"
    )
    return folds


def samples_for_split(
    samples: Sequence[dict[str, Any]],
    contract: dict[str, Any],
    split: str,
) -> list[dict[str, Any]]:
    assignments = contract["assignments"]
    return [sample for sample in samples if assignments[sample["sample_id"]] == split]


def resolve_image_path(manifest_path: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    return path.resolve() if path.is_absolute() else (manifest_path.parent / path).resolve()


def choose_geometry_bbox(
    sample: dict[str, Any],
    *,
    policy: str,
    deltas_px: Sequence[int],
    rng: random.Random,
    geometry_augmentation_probability: float = DEFAULT_GEOMETRY_AUGMENTATION_PROBABILITY,
) -> tuple[str, list[float]]:
    bbox = list(_validated_bbox(sample["bbox"]))
    probability = float(geometry_augmentation_probability)
    if not 0.0 <= probability <= 1.0:
        raise ValueError("geometry_augmentation_probability must be between 0 and 1")
    if policy == "none":
        return "native", bbox
    if policy != "absolute":
        raise ValueError(f"unsupported geometry policy: {policy}")

    if rng.random() >= probability:
        return "native", bbox

    family = rng.choice(GEOMETRY_FAMILIES[1:])
    delta = int(rng.choice(tuple(deltas_px)))
    sign = int(rng.choice((-1, 1)))
    suffix = "minus" if sign < 0 else "plus"
    variant_name = f"{family}_{suffix}_{delta}px"
    variants = generate_geometry_variants(bbox, (delta,))
    variant = next(variant for variant in variants if variant.name == variant_name)
    return variant.name, list(variant.bbox)


class SemanticMMRDataset(Dataset):
    """One semantic measure per item; source-space jitter is sampled on-the-fly."""

    def __init__(
        self,
        samples: Sequence[dict[str, Any]],
        *,
        manifest_path: Path,
        transform=None,
        geometry_policy: str = "none",
        deltas_px: Sequence[int] = DEFAULT_DELTAS_PX,
        margin_px: int = DEFAULT_MARGIN_PX,
        seed: int = DEFAULT_SPLIT_SEED,
        text_noise=None,
        geometry_augmentation_probability: float = DEFAULT_GEOMETRY_AUGMENTATION_PROBABILITY,
    ):
        self.samples = list(samples)
        self.manifest_path = manifest_path
        self.transform = transform
        self.geometry_policy = geometry_policy
        self.deltas_px = tuple(int(value) for value in deltas_px)
        self.margin_px = int(margin_px)
        self.seed = int(seed)
        self.text_noise = text_noise
        self.geometry_augmentation_probability = float(geometry_augmentation_probability)
        if not 0.0 <= self.geometry_augmentation_probability <= 1.0:
            raise ValueError("geometry_augmentation_probability must be between 0 and 1")
        # A shared scalar keeps epoch-dependent geometry sampling correct when
        # persistent DataLoader workers retain their dataset copies.
        self._epoch_state = torch.zeros(1, dtype=torch.int64).share_memory_()

    def __len__(self) -> int:
        return len(self.samples)

    def set_epoch(self, epoch: int) -> None:
        self._epoch_state[0] = int(epoch)

    @property
    def labels(self) -> list[int]:
        return [int(sample["label"]) for sample in self.samples]

    def _rng(self, idx: int) -> random.Random:
        epoch = int(self._epoch_state[0].item())
        return random.Random(self.seed + epoch * 1_000_003 + idx * 1009)

    def __getitem__(self, idx: int):
        sample = self.samples[idx]
        image_path = resolve_image_path(self.manifest_path, sample["image_path"])
        image = _read_source_page(str(image_path))
        if image is None:
            raise FileNotFoundError(f"could not load source image: {image_path}")

        _variant_name, bbox = choose_geometry_bbox(
            sample,
            policy=self.geometry_policy,
            deltas_px=self.deltas_px,
            rng=self._rng(idx),
            geometry_augmentation_probability=self.geometry_augmentation_probability,
        )
        crop = crop_measure(image, bbox, margin_px=self.margin_px)
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb)
        label = int(sample["label"])

        staff_mask = None
        if label == 1 and self.text_noise is not None:
            raw_staff_mask = sample.get("staff_mask_path")
            if raw_staff_mask:
                staff_mask_path = resolve_image_path(self.manifest_path, str(raw_staff_mask))
                full_mask = cv2.imread(str(staff_mask_path), cv2.IMREAD_GRAYSCALE)
                if full_mask is None:
                    raise FileNotFoundError(f"could not load staff mask: {staff_mask_path}")
                staff_mask = crop_measure(full_mask, bbox, margin_px=self.margin_px)
            pil_image = self.text_noise(pil_image, staff_mask)
        if self.transform is not None:
            pil_image = self.transform(pil_image)
        return pil_image, torch.tensor(label, dtype=torch.float32)
