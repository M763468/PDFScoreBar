#!/usr/bin/env python3
"""Final pre-production validation for the bounded Issue #332 candidate."""

from __future__ import annotations

import argparse
import json
import platform
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Sequence

import cv2
import numpy as np
import torch
import torch.nn as nn

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.mmr_training.issue332.dual_view_diagnosis import _staff_bbox_variants
from tools.mmr_training.issue332.dual_view_fusion import (
    MonotonicLogitFusion,
    _load_encoders,
    _tensor,
    fuse_logits,
    load_retained_native_logits,
    sha256_file,
)
from tools.mmr_training.issue332.staff_view import (
    crop_source_bbox,
    source_staff_bboxes,
    staff_relative_roi_bboxes,
)
from tools.mmr_training.issue332_geometry_benchmark import (
    _scale_page_and_bbox,
    crop_measure,
    generate_geometry_variants,
)


def _git_head() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


class FullOnlyBias(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.bias = nn.Parameter(torch.zeros(1))

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return features[:, :1] + self.bias


class ZeroBiasDualView(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.full_weight_logit = nn.Parameter(torch.zeros(1))

    def effective_weights(self) -> torch.Tensor:
        full_weight = torch.sigmoid(self.full_weight_logit).reshape(())
        return torch.stack((full_weight, 1.0 - full_weight))

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return features @ self.effective_weights().unsqueeze(1)


def _binary_metrics(labels: Sequence[int], probabilities: Sequence[float]) -> dict[str, Any]:
    tp = tn = fp = fn = 0
    for label, probability in zip(labels, probabilities):
        predicted = float(probability) >= 0.5
        if label and predicted:
            tp += 1
        elif not label and not predicted:
            tn += 1
        elif not label and predicted:
            fp += 1
        else:
            fn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "samples": len(labels),
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "confusion_matrix": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
    }


def _fit_control(
    model: nn.Module,
    train_features: torch.Tensor,
    train_labels: torch.Tensor,
    validation_features: torch.Tensor,
    validation_labels: torch.Tensor,
    *,
    epochs: int,
    learning_rate: float,
) -> tuple[nn.Module, dict[str, Any]]:
    positives = int((train_labels == 1).sum())
    negatives = int((train_labels == 0).sum())
    criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([negatives / positives]))
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    best = None
    history = []
    for epoch in range(1, epochs + 1):
        model.train()
        optimizer.zero_grad(set_to_none=True)
        train_loss = criterion(model(train_features), train_labels)
        train_loss.backward()
        optimizer.step()
        model.eval()
        with torch.inference_mode():
            validation_logits = model(validation_features)
            validation_probabilities = torch.sigmoid(validation_logits).reshape(-1).tolist()
            validation_loss = float(
                nn.functional.binary_cross_entropy_with_logits(validation_logits, validation_labels)
            )
        metrics = _binary_metrics(
            validation_labels.reshape(-1).to(torch.int64).tolist(), validation_probabilities
        )
        entry = {
            "epoch": epoch,
            "train_loss": float(train_loss.detach()),
            "validation_loss": validation_loss,
            "validation_f1": metrics["f1"],
        }
        history.append(entry)
        rank = (-metrics["f1"], validation_loss, epoch)
        if best is None or rank < best[0]:
            best = (
                rank,
                {key: value.detach().clone() for key, value in model.state_dict().items()},
                entry,
            )
    assert best is not None
    model.load_state_dict(best[1])
    return model, {"best": best[2], "history": history}


def _head_parameters(name: str, model: nn.Module) -> dict[str, Any]:
    if name == "bounded_dual_view":
        assert isinstance(model, MonotonicLogitFusion)
        weights = model.effective_weights().detach().tolist()
        return {
            "full_weight": weights[0],
            "staff_weight": weights[1],
            "bias": float(model.bias.detach()),
        }
    if name == "full_only_learned_bias":
        assert isinstance(model, FullOnlyBias)
        return {
            "full_weight": 1.0,
            "staff_weight": 0.0,
            "bias": float(model.bias.detach()),
        }
    assert isinstance(model, ZeroBiasDualView)
    weights = model.effective_weights().detach().tolist()
    return {"full_weight": weights[0], "staff_weight": weights[1], "bias": 0.0}


def _probability_fn(parameters: dict[str, float]) -> Callable[[float, float], float]:
    def predict(full_probability: float, staff_probability: float) -> float:
        values = torch.tensor([full_probability, staff_probability], dtype=torch.float64).clamp(
            1e-12, 1.0 - 1e-12
        )
        logit = fuse_logits(
            torch.logit(values[0]),
            torch.logit(values[1]),
            weights=[parameters["full_weight"], parameters["staff_weight"]],
            bias=parameters["bias"],
        )
        return float(torch.sigmoid(logit))

    return predict


def _native_summary(
    rows: Sequence[dict[str, Any]], probabilities: Sequence[float]
) -> dict[str, Any]:
    labels = [int(row["label"]) for row in rows]
    grouped: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        grouped.setdefault(str(row["score_id"]), []).append(index)
    positives = [prob for prob, label in zip(probabilities, labels) if label == 1]
    negatives = [prob for prob, label in zip(probabilities, labels) if label == 0]
    return {
        "metrics": _binary_metrics(labels, probabilities),
        "per_score": {
            score: _binary_metrics(
                [labels[index] for index in indices],
                [probabilities[index] for index in indices],
            )
            for score, indices in sorted(grouped.items())
        },
        "min_positive_probability": min(positives) if positives else None,
        "max_negative_probability": max(negatives) if negatives else None,
    }


def _artifact_rows(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))["rows"]


def _row_key(row: dict[str, Any]) -> tuple[str, str, float, str]:
    return (
        str(row["sample_id"]),
        str(row["variant"]),
        float(row.get("dpi_scale", 1.0)),
        str(row.get("resize_mode", "direct")),
    )


def _aligned_probabilities(
    full_path: Path,
    staff_path: Path,
    predict: Callable[[float, float], float],
) -> list[dict[str, Any]]:
    full = {_row_key(row): row for row in _artifact_rows(full_path)}
    staff = {_row_key(row): row for row in _artifact_rows(staff_path)}
    if set(full) != set(staff):
        raise ValueError("retained full/staff geometry artifacts do not align")
    return [
        {
            "sample_id": full[key]["sample_id"],
            "score_id": full[key]["score_id"],
            "label": int(full[key]["label"]),
            "tags": full[key].get("tags", []),
            "variant": full[key]["variant"],
            "probability": predict(full[key]["probability"], staff[key]["probability"]),
        }
        for key in sorted(full)
    ]


def _envelope_summary(
    rows: Sequence[dict[str, Any]],
    *,
    native_variant: str = "native",
    variant_key: str = "variant",
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["sample_id"]), []).append(row)
    per_sample = {}
    threshold_summaries = {}
    for threshold_name, threshold in (("main", 0.5), ("rescue", 0.1)):
        crossing_samples = []
        directions = {"positive_to_negative": [], "negative_to_positive": []}
        crossing_variants = []
        for sample_id, items in grouped.items():
            native = [row for row in items if row[variant_key] == native_variant]
            if len(native) != 1:
                raise ValueError(f"expected one native row for {sample_id}, got {len(native)}")
            native_decision = float(native[0]["probability"]) >= threshold
            sample_crossings = [
                row for row in items if (float(row["probability"]) >= threshold) != native_decision
            ]
            if sample_crossings:
                crossing_samples.append(sample_id)
                direction = "positive_to_negative" if native_decision else "negative_to_positive"
                directions[direction].append(sample_id)
                crossing_variants.extend(
                    {
                        "sample_id": sample_id,
                        "variant": row[variant_key],
                        "probability": row["probability"],
                        "direction": direction,
                    }
                    for row in sample_crossings
                )
        threshold_summaries[threshold_name] = {
            "threshold": threshold,
            "unique_crossing_count": len(crossing_samples),
            "unique_crossing_samples": sorted(crossing_samples),
            "positive_to_negative": sorted(directions["positive_to_negative"]),
            "negative_to_positive": sorted(directions["negative_to_positive"]),
            "crossing_variants": crossing_variants,
        }
    for sample_id, items in grouped.items():
        native = next(row for row in items if row[variant_key] == native_variant)
        probabilities = [float(row["probability"]) for row in items]
        per_sample[sample_id] = {
            "label": int(native["label"]),
            "native_probability": float(native["probability"]),
            "probability_min": min(probabilities),
            "probability_max": max(probabilities),
            "probability_range": max(probabilities) - min(probabilities),
            "max_abs_delta_from_native": max(
                abs(probability - float(native["probability"])) for probability in probabilities
            ),
        }
    return {**threshold_summaries, "samples": per_sample}


def _staff_sensitivity_rows(
    diagnosis_path: Path,
    scope: str,
    full_geometry_path: Path,
    predict: Callable[[float, float], float],
) -> list[dict[str, Any]]:
    diagnosis = json.loads(diagnosis_path.read_text(encoding="utf-8"))
    staff_rows = diagnosis["staff_bbox_sensitivity"][scope]["rows"]
    full_native = {
        row["sample_id"]: row
        for row in _artifact_rows(full_geometry_path)
        if row["variant"] == "native"
        and float(row.get("dpi_scale", 1.0)) == 1.0
        and row.get("resize_mode", "direct") == "direct"
    }
    return [
        {
            "sample_id": row["sample_id"],
            "score_id": row["score_id"],
            "label": int(row["label"]),
            "variant": row["variant"],
            "probability": predict(
                full_native[row["sample_id"]]["probability"], row["probability"]
            ),
        }
        for row in staff_rows
    ]


def _load_fusion(path: Path) -> MonotonicLogitFusion:
    payload = torch.load(path, map_location="cpu", weights_only=True)
    model = MonotonicLogitFusion()
    model.load_state_dict(payload["fusion_state_dict"])
    model.eval()
    return model


def causal_controls(args: argparse.Namespace, config: dict[str, Any]) -> dict[str, Any]:
    extracted = load_retained_native_logits(
        args.feature_artifact,
        manifest_sha256=config["manifest_sha256"],
        split_sha256=config["split_sha256"],
        full_model_sha256=config["full_model_sha256"],
        staff_model_sha256=config["staff_model_sha256"],
    )
    current = _load_fusion(args.fusion_model)
    torch.manual_seed(int(config["seed"]))
    full_bias, full_fit = _fit_control(
        FullOnlyBias(),
        extracted["train"][0],
        extracted["train"][1],
        extracted["validation"][0],
        extracted["validation"][1],
        epochs=int(config["epochs"]),
        learning_rate=float(config["learning_rate"]),
    )
    torch.manual_seed(int(config["seed"]))
    zero_bias, zero_fit = _fit_control(
        ZeroBiasDualView(),
        extracted["train"][0],
        extracted["train"][1],
        extracted["validation"][0],
        extracted["validation"][1],
        epochs=int(config["epochs"]),
        learning_rate=float(config["learning_rate"]),
    )
    heads = {
        "bounded_dual_view": (current, None),
        "full_only_learned_bias": (full_bias, full_fit),
        "dual_view_zero_bias": (zero_bias, zero_fit),
    }
    results = {}
    for name, (model, fit) in heads.items():
        parameters = _head_parameters(name, model)
        predict = _probability_fn(parameters)
        split_summaries = {}
        for split, (features, labels, rows) in extracted.items():
            with torch.inference_mode():
                probabilities = torch.sigmoid(model(features)).reshape(-1).tolist()
            split_summaries[split] = _native_summary(rows, probabilities)
        primary_geometry = _aligned_probabilities(args.full_primary, args.staff_primary, predict)
        control_geometry = _aligned_probabilities(args.full_controls, args.staff_controls, predict)
        primary_staff = _staff_sensitivity_rows(
            args.staff_diagnosis, "primary", args.full_primary, predict
        )
        control_staff = _staff_sensitivity_rows(
            args.staff_diagnosis, "controls", args.full_controls, predict
        )
        control_native = [row for row in control_geometry if row["variant"] == "native"]
        results[name] = {
            "parameters": parameters,
            "fit": fit,
            "native": split_summaries,
            "controls_native": _native_summary(
                control_native, [row["probability"] for row in control_native]
            ),
            "measure_geometry": {
                "primary": _envelope_summary(primary_geometry),
                "controls": _envelope_summary(control_geometry),
            },
            "staff_geometry": {
                "primary": _envelope_summary(primary_staff),
                "controls": _envelope_summary(control_staff),
            },
        }
    return results


def _resolve_image(sample: dict[str, Any], manifest_path: Path) -> np.ndarray:
    path = Path(str(sample["image_path"]))
    if not path.is_absolute():
        path = (manifest_path.parent / path).resolve()
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(path)
    return image


def _batched_encoder_logits(
    encoder: nn.Module,
    tensors: Sequence[torch.Tensor],
    device: torch.device,
    batch_size: int,
) -> list[float]:
    result = []
    with torch.inference_mode():
        for start in range(0, len(tensors), batch_size):
            batch = torch.stack(tensors[start : start + batch_size]).to(device)
            result.extend(encoder(batch).reshape(-1).detach().cpu().tolist())
    return result


def _joint_rows_for_sample(
    sample: dict[str, Any],
    image: np.ndarray,
    full_model: nn.Module,
    staff_model: nn.Module,
    device: torch.device,
    predict: Callable[[float, float], float],
    deltas: Sequence[int],
    margin_px: int,
    batch_size: int,
) -> list[dict[str, Any]]:
    measure_variants = generate_geometry_variants(sample["bbox"], deltas)
    staff_variants = _staff_bbox_variants(source_staff_bboxes(sample), deltas)
    full_tensors = [
        _tensor(crop_measure(image, variant.bbox, margin_px=margin_px))
        for variant in measure_variants
    ]
    full_logits = _batched_encoder_logits(full_model, full_tensors, device, batch_size)

    roi_keys: dict[tuple[int, int, int, int], tuple[float, float, float, float]] = {}
    pair_keys = {}
    for measure in measure_variants:
        for staff_name, staves in staff_variants:
            variant_sample = dict(sample)
            variant_sample["_staff_bboxes"] = staves
            keys = []
            for roi in staff_relative_roi_bboxes(variant_sample, measure.bbox):
                key = tuple(int(value) for value in roi)
                roi_keys.setdefault(key, roi)
                keys.append(key)
            pair_keys[(measure.name, staff_name)] = keys
    ordered_keys = list(roi_keys)
    staff_tensors = [_tensor(crop_source_bbox(image, roi_keys[key])) for key in ordered_keys]
    staff_logits = _batched_encoder_logits(staff_model, staff_tensors, device, batch_size)
    staff_by_key = dict(zip(ordered_keys, staff_logits))
    full_by_variant = dict(zip((variant.name for variant in measure_variants), full_logits))
    rows = []
    for measure in measure_variants:
        for staff_name, _staves in staff_variants:
            staff_logit = max(staff_by_key[key] for key in pair_keys[(measure.name, staff_name)])
            full_probability = float(torch.sigmoid(torch.tensor(full_by_variant[measure.name])))
            staff_probability = float(torch.sigmoid(torch.tensor(staff_logit)))
            rows.append(
                {
                    "sample_id": sample["sample_id"],
                    "score_id": sample["score_id"],
                    "label": int(sample["label"]),
                    "variant": f"measure={measure.name}|staff={staff_name}",
                    "probability": predict(full_probability, staff_probability),
                }
            )
    return rows


def _joint_scope(
    samples: Sequence[dict[str, Any]],
    manifest_path: Path,
    full_model: nn.Module,
    staff_model: nn.Module,
    device: torch.device,
    predict: Callable[[float, float], float],
    config: dict[str, Any],
    batch_size: int,
) -> dict[str, Any]:
    summaries = []
    threshold_crossings = {"main": [], "rescue": []}
    variant_counts = {"main": 0, "rescue": 0}
    any_misclassified = set()
    started = time.perf_counter()
    for index, sample in enumerate(samples):
        rows = _joint_rows_for_sample(
            sample,
            _resolve_image(sample, manifest_path),
            full_model,
            staff_model,
            device,
            predict,
            config["deltas_px"],
            int(config["margin_px"]),
            batch_size,
        )
        native = next(row for row in rows if row["variant"] == "measure=native|staff=native")
        probabilities = [row["probability"] for row in rows]
        item = {
            "sample_id": sample["sample_id"],
            "score_id": sample["score_id"],
            "label": int(sample["label"]),
            "native_probability": native["probability"],
            "probability_min": min(probabilities),
            "probability_max": max(probabilities),
            "probability_range": max(probabilities) - min(probabilities),
            "max_abs_delta_from_native": max(
                abs(probability - native["probability"]) for probability in probabilities
            ),
        }
        for threshold_name, threshold in (("main", 0.5), ("rescue", 0.1)):
            native_decision = native["probability"] >= threshold
            crossing_rows = [
                row for row in rows if (row["probability"] >= threshold) != native_decision
            ]
            item[f"{threshold_name}_crossing_variants"] = [
                {"variant": row["variant"], "probability": row["probability"]}
                for row in crossing_rows
            ]
            if crossing_rows:
                threshold_crossings[threshold_name].append(
                    {
                        "sample_id": sample["sample_id"],
                        "direction": (
                            "positive_to_negative" if native_decision else "negative_to_positive"
                        ),
                    }
                )
                variant_counts[threshold_name] += len(crossing_rows)
        if any((row["probability"] >= 0.5) != bool(sample["label"]) for row in rows):
            any_misclassified.add(sample["sample_id"])
        summaries.append(item)
        if (index + 1) % 25 == 0:
            print(f"joint geometry: {index + 1}/{len(samples)}")
    return {
        "sample_count": len(samples),
        "variants_per_sample": len(
            generate_geometry_variants(samples[0]["bbox"], config["deltas_px"])
        )
        * len(_staff_bbox_variants(source_staff_bboxes(samples[0]), config["deltas_px"])),
        "main": {
            "unique_crossing_count": len(threshold_crossings["main"]),
            "crossings": threshold_crossings["main"],
            "crossing_variant_count": variant_counts["main"],
        },
        "rescue": {
            "unique_crossing_count": len(threshold_crossings["rescue"]),
            "crossings": threshold_crossings["rescue"],
            "crossing_variant_count": variant_counts["rescue"],
        },
        "any_main_misclassification_sample_count": len(any_misclassified),
        "any_main_misclassification_samples": sorted(any_misclassified),
        "samples": summaries,
        "elapsed_seconds": time.perf_counter() - started,
    }


def _dpi_scope(
    samples: Sequence[dict[str, Any]],
    manifest_path: Path,
    full_model: nn.Module,
    staff_model: nn.Module,
    device: torch.device,
    predict: Callable[[float, float], float],
    config: dict[str, Any],
    batch_size: int,
) -> dict[str, Any]:
    rows = []
    for index, sample in enumerate(samples):
        image = _resolve_image(sample, manifest_path)
        full_tensors = []
        all_staff_tensors = []
        staff_slices = []
        for scale in config["dpi_scales"]:
            scaled_image, scaled_bbox = _scale_page_and_bbox(image, sample["bbox"], float(scale))
            full_tensors.append(
                _tensor(crop_measure(scaled_image, scaled_bbox, margin_px=config["margin_px"]))
            )
            scaled_sample = dict(sample)
            scaled_sample["_staff_bboxes"] = [
                [float(value) * float(scale) for value in bbox]
                for bbox in source_staff_bboxes(sample)
            ]
            start = len(all_staff_tensors)
            all_staff_tensors.extend(
                _tensor(crop_source_bbox(scaled_image, roi))
                for roi in staff_relative_roi_bboxes(scaled_sample, scaled_bbox)
            )
            staff_slices.append((start, len(all_staff_tensors)))
        full_logits = _batched_encoder_logits(full_model, full_tensors, device, batch_size)
        staff_logits = _batched_encoder_logits(staff_model, all_staff_tensors, device, batch_size)
        for scale_index, scale in enumerate(config["dpi_scales"]):
            start, end = staff_slices[scale_index]
            full_probability = float(torch.sigmoid(torch.tensor(full_logits[scale_index])))
            staff_probability = float(torch.sigmoid(torch.tensor(max(staff_logits[start:end]))))
            rows.append(
                {
                    "sample_id": sample["sample_id"],
                    "score_id": sample["score_id"],
                    "label": int(sample["label"]),
                    "variant": f"dpi_{float(scale):g}",
                    "dpi_scale": float(scale),
                    "full_probability": full_probability,
                    "staff_probability": staff_probability,
                    "probability": predict(full_probability, staff_probability),
                }
            )
        if (index + 1) % 100 == 0:
            print(f"coherent DPI: {index + 1}/{len(samples)}")
    summary = _envelope_summary(rows, native_variant="dpi_1")
    per_scale = {}
    for scale in config["dpi_scales"]:
        scale_rows = [row for row in rows if row["dpi_scale"] == float(scale)]
        per_scale[str(scale)] = _native_summary(
            scale_rows, [row["probability"] for row in scale_rows]
        )
    return {"summary": summary, "per_scale": per_scale, "rows": rows}


def joint_and_dpi(args: argparse.Namespace, config: dict[str, Any]) -> dict[str, Any]:
    device = torch.device(args.device)
    full_model, staff_model_wrapper = _load_encoders(args.full_model, args.staff_model, device)
    staff_model = staff_model_wrapper.encoder
    fusion = _load_fusion(args.fusion_model)
    parameters = _head_parameters("bounded_dual_view", fusion)
    predict = _probability_fn(parameters)
    primary_samples = json.loads(args.primary_manifest.read_text(encoding="utf-8"))["samples"]
    control_samples = json.loads(args.controls_manifest.read_text(encoding="utf-8"))["samples"]
    return {
        "joint_geometry": {
            "primary": _joint_scope(
                primary_samples,
                args.primary_manifest,
                full_model,
                staff_model,
                device,
                predict,
                config,
                args.batch_size,
            ),
            "controls": _joint_scope(
                control_samples,
                args.controls_manifest,
                full_model,
                staff_model,
                device,
                predict,
                config,
                args.batch_size,
            ),
        },
        "coherent_dpi": {
            "primary": _dpi_scope(
                primary_samples,
                args.primary_manifest,
                full_model,
                staff_model,
                device,
                predict,
                config,
                args.batch_size,
            ),
            "controls": _dpi_scope(
                control_samples,
                args.controls_manifest,
                full_model,
                staff_model,
                device,
                predict,
                config,
                args.batch_size,
            ),
        },
    }


def _validate_contract(args: argparse.Namespace, config: dict[str, Any]) -> None:
    paths = {
        "manifest_sha256": args.manifest,
        "split_sha256": args.split_manifest,
        "acceptance_manifest_sha256": args.acceptance_manifest,
        "full_model_sha256": args.full_model,
        "staff_model_sha256": args.staff_model,
        "fusion_model_sha256": args.fusion_model,
    }
    mismatches = {
        key: {"expected": config[key], "actual": sha256_file(path)}
        for key, path in paths.items()
        if sha256_file(path) != config[key]
    }
    if mismatches:
        raise ValueError(f"fixed contract SHA mismatch: {mismatches}")
    if config["main_threshold"] != 0.5 or config["threshold_rescue"] != 0.1:
        raise ValueError("fixed thresholds must remain 0.5 and 0.1")


def run(args: argparse.Namespace) -> dict[str, Any]:
    config = json.loads(args.config.read_text(encoding="utf-8"))
    _validate_contract(args, config)
    random.seed(config["seed"])
    np.random.seed(config["seed"])
    torch.manual_seed(config["seed"])
    started = time.perf_counter()
    output = {
        "provenance": {
            "git_head": _git_head(),
            "config_sha256": sha256_file(args.config),
            "feature_artifact_sha256": sha256_file(args.feature_artifact),
            "runtime": {
                "python": platform.python_version(),
                "torch": torch.__version__,
                "opencv": cv2.__version__,
                "device": args.device,
            },
        },
        "contract": config,
        "causal_controls": causal_controls(args, config),
    }
    if not args.causal_only:
        output.update(joint_and_dpi(args, config))
    output["elapsed_seconds"] = time.perf_counter() - started
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--acceptance-manifest", type=Path, required=True)
    parser.add_argument("--feature-artifact", type=Path, required=True)
    parser.add_argument("--full-model", type=Path, required=True)
    parser.add_argument("--staff-model", type=Path, required=True)
    parser.add_argument("--fusion-model", type=Path, required=True)
    parser.add_argument("--full-primary", type=Path, required=True)
    parser.add_argument("--staff-primary", type=Path, required=True)
    parser.add_argument("--full-controls", type=Path, required=True)
    parser.add_argument("--staff-controls", type=Path, required=True)
    parser.add_argument("--staff-diagnosis", type=Path, required=True)
    parser.add_argument("--primary-manifest", type=Path, required=True)
    parser.add_argument("--controls-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--causal-only", action="store_true")
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    return parser


if __name__ == "__main__":
    result = run(build_parser().parse_args())
    joint_summary = None
    if "joint_geometry" in result:
        joint_summary = {
            scope: {
                "main": value["main"],
                "rescue": value["rescue"],
                "misclassified_samples": value["any_main_misclassification_sample_count"],
            }
            for scope, value in result["joint_geometry"].items()
        }
    dpi_summary = None
    if "coherent_dpi" in result:
        dpi_summary = {
            scope: {
                "main_crossings": value["summary"]["main"]["unique_crossing_count"],
                "rescue_crossings": value["summary"]["rescue"]["unique_crossing_count"],
                "per_scale": value["per_scale"],
            }
            for scope, value in result["coherent_dpi"].items()
        }
    print(
        json.dumps(
            {
                "causal": {
                    name: {
                        "parameters": value["parameters"],
                        "test": value["native"]["test"],
                        "measure_main": value["measure_geometry"]["primary"]["main"][
                            "unique_crossing_count"
                        ],
                        "measure_rescue": value["measure_geometry"]["primary"]["rescue"][
                            "unique_crossing_count"
                        ],
                        "staff_main": value["staff_geometry"]["primary"]["main"][
                            "unique_crossing_count"
                        ],
                        "staff_rescue": value["staff_geometry"]["primary"]["rescue"][
                            "unique_crossing_count"
                        ],
                    }
                    for name, value in result["causal_controls"].items()
                },
                "joint": joint_summary,
                "dpi": dpi_summary,
            },
            indent=2,
        )
    )
