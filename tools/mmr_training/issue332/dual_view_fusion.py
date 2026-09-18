#!/usr/bin/env python3
"""Train the Issue #332 frozen-logit dual-view fusion candidate.

The two existing ResNet18 checkpoints remain frozen.  Only a monotonic convex
head over their measure-level logits is fitted, which isolates the causal
question of whether the observed view complementarity generalizes beyond the
diagnostic ``min(probability)`` rule.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torchvision import models, transforms

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.mmr_training.issue332.geometry_training import (
    DEFAULT_EXCLUDED_TAGS,
    prepare_split_contract,
    resolve_image_path,
    samples_for_split,
)
from tools.mmr_training.issue332.staff_model import StaffRelativeResNet18
from tools.mmr_training.issue332.staff_view import crop_source_bbox, staff_relative_roi_bboxes
from tools.mmr_training.issue332_geometry_benchmark import crop_measure

FUSION_VIEW = "frozen-logit-convex-mixture"
DIRECT_TRANSFORM = transforms.Compose(
    [
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ]
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_head() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


class MonotonicLogitFusion(nn.Module):
    """Convex logit mixture with a learned bias and bounded evidence scale."""

    def __init__(self) -> None:
        super().__init__()
        self.full_weight_logit = nn.Parameter(torch.zeros(1))
        self.bias = nn.Parameter(torch.zeros(1))

    def forward(self, logits: torch.Tensor) -> torch.Tensor:
        weights = self.effective_weights()
        return logits @ weights.unsqueeze(1) + self.bias

    def effective_weights(self) -> torch.Tensor:
        full_weight = torch.sigmoid(self.full_weight_logit).reshape(())
        return torch.stack((full_weight, 1.0 - full_weight))


def fuse_logits(
    full_logits: torch.Tensor,
    staff_logits: torch.Tensor,
    *,
    weights: Sequence[float],
    bias: float,
) -> torch.Tensor:
    """Apply a serialized monotonic affine head to aligned logits."""
    if len(weights) != 2 or min(float(value) for value in weights) < 0.0:
        raise ValueError("fusion weights must contain two non-negative values")
    return float(weights[0]) * full_logits + float(weights[1]) * staff_logits + float(bias)


def fuse_probabilities(
    full_probability: float,
    staff_probability: float,
    *,
    weights: Sequence[float],
    bias: float,
) -> float:
    probabilities = torch.tensor([full_probability, staff_probability], dtype=torch.float64).clamp(
        1e-12, 1.0 - 1e-12
    )
    logits = torch.logit(probabilities)
    return float(torch.sigmoid(fuse_logits(logits[0], logits[1], weights=weights, bias=bias)))


def _load_encoders(
    full_model_path: Path, staff_model_path: Path, device: torch.device
) -> tuple[nn.Module, StaffRelativeResNet18]:
    full = models.resnet18(weights=None)
    full.fc = nn.Linear(full.fc.in_features, 1)
    full.load_state_dict(torch.load(full_model_path, map_location=device, weights_only=True))
    staff = StaffRelativeResNet18(weights=None)
    staff.load_state_dict(torch.load(staff_model_path, map_location=device, weights_only=True))
    full.to(device).eval()
    staff.to(device).eval()
    for model in (full, staff):
        for parameter in model.parameters():
            parameter.requires_grad_(False)
    return full, staff


def _tensor(crop: np.ndarray) -> torch.Tensor:
    rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    return DIRECT_TRANSFORM(Image.fromarray(rgb))


def extract_native_logits(
    samples: Sequence[dict[str, Any]],
    *,
    manifest_path: Path,
    full_model: nn.Module,
    staff_model: StaffRelativeResNet18,
    device: torch.device,
    margin_px: int = 20,
) -> tuple[torch.Tensor, torch.Tensor, list[dict[str, Any]], float]:
    """Extract aligned native full/staff logits without training augmentation."""
    features: list[list[float]] = []
    labels: list[float] = []
    rows: list[dict[str, Any]] = []
    inference_seconds = 0.0
    for index, sample in enumerate(samples):
        image_path = resolve_image_path(manifest_path, str(sample["image_path"]))
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(image_path)
        full_tensor = _tensor(crop_measure(image, sample["bbox"], margin_px=margin_px))
        staff_tensors = torch.stack(
            [_tensor(crop_source_bbox(image, roi)) for roi in staff_relative_roi_bboxes(sample)]
        )
        started = time.perf_counter()
        with torch.inference_mode():
            full_logit = float(full_model(full_tensor.unsqueeze(0).to(device)).item())
            per_staff = staff_model.encoder(staff_tensors.to(device)).reshape(-1)
            staff_logit = float(per_staff.max().item())
        inference_seconds += time.perf_counter() - started
        features.append([full_logit, staff_logit])
        labels.append(float(sample["label"]))
        rows.append(
            {
                "sample_id": sample["sample_id"],
                "score_id": sample["score_id"],
                "page_id": sample["page_id"],
                "label": int(sample["label"]),
                "full_logit": full_logit,
                "staff_logit": staff_logit,
                "full_probability": float(torch.sigmoid(torch.tensor(full_logit))),
                "staff_probability": float(torch.sigmoid(torch.tensor(staff_logit))),
                "staff_count": int(len(staff_tensors)),
            }
        )
        if (index + 1) % 250 == 0:
            print(f"native feature extraction: {index + 1}/{len(samples)}")
    return (
        torch.tensor(features, dtype=torch.float32),
        torch.tensor(labels, dtype=torch.float32).unsqueeze(1),
        rows,
        inference_seconds,
    )


def _metrics(labels: torch.Tensor, probabilities: torch.Tensor) -> dict[str, Any]:
    actual = labels.reshape(-1).to(torch.int64)
    predicted = (probabilities.reshape(-1) >= 0.5).to(torch.int64)
    tp = int(((actual == 1) & (predicted == 1)).sum())
    tn = int(((actual == 0) & (predicted == 0)).sum())
    fp = int(((actual == 0) & (predicted == 1)).sum())
    fn = int(((actual == 1) & (predicted == 0)).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "samples": int(len(actual)),
        "positives": int((actual == 1).sum()),
        "negatives": int((actual == 0).sum()),
        "accuracy": (tp + tn) / len(actual) if len(actual) else 0.0,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "confusion_matrix": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
    }


def _evaluate_head(
    model: MonotonicLogitFusion, features: torch.Tensor, labels: torch.Tensor
) -> tuple[dict[str, Any], torch.Tensor, float]:
    model.eval()
    with torch.inference_mode():
        logits = model(features)
        probabilities = torch.sigmoid(logits)
        loss = float(nn.functional.binary_cross_entropy_with_logits(logits, labels))
    return _metrics(labels, probabilities), probabilities, loss


def fit_fusion_head(
    train_features: torch.Tensor,
    train_labels: torch.Tensor,
    validation_features: torch.Tensor,
    validation_labels: torch.Tensor,
    *,
    epochs: int,
    learning_rate: float,
) -> tuple[MonotonicLogitFusion, dict[str, Any]]:
    model = MonotonicLogitFusion()
    negatives = int((train_labels == 0).sum())
    positives = int((train_labels == 1).sum())
    pos_weight = negatives / positives
    criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([pos_weight]))
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    best: tuple[tuple[float, float, int], dict[str, torch.Tensor], dict[str, Any]] | None = None
    history = []
    for epoch in range(1, epochs + 1):
        model.train()
        optimizer.zero_grad(set_to_none=True)
        loss = criterion(model(train_features), train_labels)
        loss.backward()
        optimizer.step()
        validation_metrics, _probabilities, validation_loss = _evaluate_head(
            model, validation_features, validation_labels
        )
        entry = {
            "epoch": epoch,
            "train_loss": float(loss.detach()),
            "validation_loss": validation_loss,
            "validation_f1": validation_metrics["f1"],
            "weights": [float(value) for value in model.effective_weights().detach()],
            "bias": float(model.bias.detach()),
        }
        history.append(entry)
        rank = (-float(validation_metrics["f1"]), validation_loss, epoch)
        if best is None or rank < best[0]:
            best = (
                rank,
                {key: value.detach().clone() for key, value in model.state_dict().items()},
                entry,
            )
    assert best is not None
    model.load_state_dict(best[1])
    return model, {
        "pos_weight": pos_weight,
        "selection": "maximum validation F1; minimum unweighted validation BCE tie-break",
        "best": best[2],
        "history": history,
    }


def _per_score(
    rows: Sequence[dict[str, Any]], labels: torch.Tensor, probabilities: torch.Tensor
) -> dict[str, Any]:
    grouped: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        grouped.setdefault(str(row["score_id"]), []).append(index)
    return {
        score: _metrics(labels[indices], probabilities[indices])
        for score, indices in sorted(grouped.items())
    }


def load_retained_native_logits(
    path: Path,
    *,
    manifest_sha256: str,
    split_sha256: str,
    full_model_sha256: str,
    staff_model_sha256: str,
) -> dict[str, tuple[torch.Tensor, torch.Tensor, list[dict[str, Any]]]]:
    """Reuse immutable encoder outputs after validating their full provenance."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    provenance = payload["provenance"]
    expected = {
        "manifest_sha256": manifest_sha256,
        "split_sha256": split_sha256,
        "full_model_sha256": full_model_sha256,
        "staff_model_sha256": staff_model_sha256,
    }
    mismatches = {
        key: (provenance.get(key), value)
        for key, value in expected.items()
        if provenance.get(key) != value
    }
    if mismatches:
        raise ValueError(f"retained feature provenance mismatch: {mismatches}")
    result = {}
    for name in ("train", "validation", "test"):
        rows = payload["splits"][name]["rows"]
        result[name] = (
            torch.tensor(
                [[row["full_logit"], row["staff_logit"]] for row in rows],
                dtype=torch.float32,
            ),
            torch.tensor([row["label"] for row in rows], dtype=torch.float32).unsqueeze(1),
            [
                {key: value for key, value in row.items() if key != "fusion_probability"}
                for row in rows
            ],
        )
    return result


def run(args: argparse.Namespace) -> dict[str, Any]:
    config = json.loads(args.config.read_text(encoding="utf-8"))
    expected_contract = {
        "candidate": FUSION_VIEW,
        "main_threshold": 0.5,
        "rescue_threshold": 0.1,
        "seed": 42,
        "training_geometry": "native-only",
        "weight_constraint": "convex-combination",
    }
    mismatches = {
        key: (config.get(key), value)
        for key, value in expected_contract.items()
        if config.get(key) != value
    }
    if mismatches:
        raise ValueError(f"fusion config violates the fixed experiment contract: {mismatches}")
    seed = int(config["seed"])
    epochs = int(config["epochs"])
    learning_rate = float(config["learning_rate"])
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    device = torch.device(args.device)
    eligible, split_contract = prepare_split_contract(
        manifest_path=args.manifest,
        split_path=args.split_manifest,
        acceptance_manifest_path=args.acceptance_manifest,
        excluded_tags=DEFAULT_EXCLUDED_TAGS,
        seed=seed,
        validation_ratio=0.125,
        test_ratio=0.125,
        group_level="page",
        fallback_group_level="system",
        split_mode="within-score-grouped",
    )
    split_samples = {
        name: samples_for_split(eligible, split_contract, name)
        for name in ("train", "validation", "test")
    }
    source_hashes = {
        "manifest_sha256": sha256_file(args.manifest),
        "split_sha256": sha256_file(args.split_manifest),
        "full_model_sha256": sha256_file(args.full_model),
        "staff_model_sha256": sha256_file(args.staff_model),
    }
    total_inference_seconds = 0.0
    if args.feature_artifact:
        extracted = load_retained_native_logits(args.feature_artifact, **source_hashes)
    else:
        full_model, staff_model = _load_encoders(args.full_model, args.staff_model, device)
        extracted = {}
        for name in ("train", "validation", "test"):
            features, labels, rows, inference_seconds = extract_native_logits(
                split_samples[name],
                manifest_path=args.manifest,
                full_model=full_model,
                staff_model=staff_model,
                device=device,
            )
            extracted[name] = (features, labels, rows)
            total_inference_seconds += inference_seconds

    model, fit = fit_fusion_head(
        extracted["train"][0],
        extracted["train"][1],
        extracted["validation"][0],
        extracted["validation"][1],
        epochs=epochs,
        learning_rate=learning_rate,
    )
    state = {
        "fusion_state_dict": model.state_dict(),
        "fusion_view": FUSION_VIEW,
        "full_model_sha256": sha256_file(args.full_model),
        "staff_model_sha256": sha256_file(args.staff_model),
    }
    args.output_model.parent.mkdir(parents=True, exist_ok=True)
    torch.save(state, args.output_model)

    split_results = {}
    for name, (features, labels, rows) in extracted.items():
        metrics, probabilities, loss = _evaluate_head(model, features, labels)
        for row, probability in zip(rows, probabilities.reshape(-1).tolist()):
            row["fusion_probability"] = float(probability)
        split_results[name] = {
            "native": metrics,
            "native_bce": loss,
            "per_score": _per_score(rows, labels, probabilities),
            "rows": rows,
        }

    weights = [float(value) for value in model.effective_weights().detach()]
    output = {
        "provenance": {
            "issue": 332,
            "git_head": _git_head(),
            "manifest_sha256": sha256_file(args.manifest),
            "split_sha256": sha256_file(args.split_manifest),
            "acceptance_manifest_sha256": sha256_file(args.acceptance_manifest),
            "full_model_sha256": sha256_file(args.full_model),
            "staff_model_sha256": sha256_file(args.staff_model),
            "fusion_model_sha256": sha256_file(args.output_model),
            "feature_artifact": (
                str(args.feature_artifact.resolve()) if args.feature_artifact else None
            ),
            "feature_artifact_sha256": (
                sha256_file(args.feature_artifact) if args.feature_artifact else None
            ),
            "retained_native_logits_reused": bool(args.feature_artifact),
            "config_sha256": sha256_file(args.config),
            "seed": seed,
            "device": str(device),
            "torch_version": torch.__version__,
            "python_version": platform.python_version(),
        },
        "contract": {
            "view": FUSION_VIEW,
            "encoders": "frozen existing full-measure and staff-core-center-3h ResNet18",
            "features": ["full_measure_logit", "max_staff_logit"],
            "fusion": "convex mixture weights summing to one plus bias",
            "loss": "BCEWithLogitsLoss with training-split positive class weight",
            "thresholds": {"main": 0.5, "rescue": 0.1},
            "training_geometry": "native only",
            "rapidocr_involved": False,
        },
        "fit": fit,
        "selected_parameters": {"weights": weights, "bias": float(model.bias.detach())},
        "splits": split_results,
        "runtime": {
            "encoder_inference_seconds": (
                None if args.feature_artifact else total_inference_seconds
            ),
            "semantic_samples": sum(len(value) for value in split_samples.values()),
            "mean_encoder_inference_ms_per_measure": (
                None
                if args.feature_artifact
                else total_inference_seconds
                / sum(len(value) for value in split_samples.values())
                * 1000.0
            ),
            "retained_feature_runtime": (
                json.loads(args.feature_artifact.read_text(encoding="utf-8")).get("runtime")
                if args.feature_artifact
                else None
            ),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--acceptance-manifest", type=Path, required=True)
    parser.add_argument("--full-model", type=Path, required=True)
    parser.add_argument("--staff-model", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--feature-artifact",
        type=Path,
        help="Reuse retained native encoder logits after strict provenance validation.",
    )
    parser.add_argument("--output-model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    return parser


if __name__ == "__main__":
    result = run(build_parser().parse_args())
    print(
        json.dumps(
            {
                "selected_parameters": result["selected_parameters"],
                "native": {name: value["native"] for name, value in result["splits"].items()},
            },
            indent=2,
        )
    )
