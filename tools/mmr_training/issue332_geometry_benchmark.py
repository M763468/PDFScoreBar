#!/usr/bin/env python3
"""Classifier-only geometry robustness benchmark for Issue #332.

Crops source-page images from semantic measure geometry, applies bounded
perturbations, and records classifier probabilities. RapidOCR is not involved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


import cv2
import numpy as np
import torch
import torch.nn as nn
from PIL import Image, ImageOps
from torchvision import models, transforms

DEFAULT_MAIN_THRESHOLD = 0.5
DEFAULT_RESCUE_THRESHOLD = 0.1
DEFAULT_MARGIN_PX = 20
DEFAULT_DELTAS_PX = (1, 2, 4)
DEFAULT_DPI_SCALES = (0.8, 1.0, 1.25)

# Experiment-local mirror of src.measure_numbering.mmr.MMRClassifier.
#
# Keep this deliberately small: Issue #332 is classifier-only, and the documented
# CNN classifier environment does not carry RapidOCR. Importing the production
# mmr.py module would pull in RapidOCR even though classifier inference does not use it.
# Phase-0 reproduction against retained #277 probabilities validates that this mirror
# remains behaviorally equivalent to the production classifier contract.
PRODUCTION_TRANSFORM = transforms.Compose(
    [
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(
            [0.485, 0.456, 0.406],
            [0.229, 0.224, 0.225],
        ),
    ]
)


class ProductionMMRClassifierMirror:
    """Classifier-only mirror of the production MMRClassifier inference contract."""

    def __init__(self, model_path: Path, device: torch.device):
        self.device = device
        self.transform = PRODUCTION_TRANSFORM

        model = models.resnet18(weights=None)
        model.fc = nn.Linear(model.fc.in_features, 1)

        state_dict = torch.load(
            model_path,
            map_location=self.device,
            weights_only=True,
        )
        if any(key.startswith("_orig_mod.") for key in state_dict):
            state_dict = {
                key.replace("_orig_mod.", ""): value
                for key, value in state_dict.items()
            }

        model.load_state_dict(state_dict)
        self.model = model.to(self.device)
        self.model.eval()

    def predict(self, cv2_img: np.ndarray) -> float:
        if cv2_img is None or cv2_img.size == 0:
            return 0.0

        rgb = cv2.cvtColor(cv2_img, cv2.COLOR_BGR2RGB)
        tensor = (
            self.transform(Image.fromarray(rgb))
            .unsqueeze(0)
            .to(self.device)
        )

        with torch.no_grad():
            return float(torch.sigmoid(self.model(tensor)).item())


@dataclass(frozen=True)
class Variant:
    name: str
    bbox: tuple[float, float, float, float]
    dpi_scale: float = 1.0


def _git_head() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validated_bbox(raw: Sequence[float]) -> tuple[float, float, float, float]:
    if len(raw) != 4:
        raise ValueError(f"bbox must contain four coordinates, got {raw!r}")
    x1, y1, x2, y2 = (float(value) for value in raw)
    if not all(math.isfinite(value) for value in (x1, y1, x2, y2)):
        raise ValueError(f"bbox contains non-finite values: {raw!r}")
    if x2 <= x1 or y2 <= y1:
        raise ValueError(f"bbox must have positive area: {raw!r}")
    return x1, y1, x2, y2


def generate_geometry_variants(
    bbox: Sequence[float], deltas_px: Iterable[int]
) -> list[Variant]:
    """Return native plus bounded source-space geometry perturbations."""
    x1, y1, x2, y2 = _validated_bbox(bbox)
    variants = [Variant("native", (x1, y1, x2, y2))]
    for delta in deltas_px:
        delta = int(delta)
        if delta <= 0:
            raise ValueError(f"geometry deltas must be positive, got {delta}")
        for sign, suffix in ((-1, "minus"), (1, "plus")):
            shift = sign * delta
            candidates = (
                (f"x1_{suffix}_{delta}px", (x1 + shift, y1, x2, y2)),
                (f"x2_{suffix}_{delta}px", (x1, y1, x2 + shift, y2)),
                (f"translate_x_{suffix}_{delta}px", (x1 + shift, y1, x2 + shift, y2)),
                (f"translate_y_{suffix}_{delta}px", (x1, y1 + shift, x2, y2 + shift)),
                (f"expand_contract_x_{suffix}_{delta}px", (x1 - shift, y1, x2 + shift, y2)),
            )
            for name, candidate in candidates:
                try:
                    variants.append(Variant(name, _validated_bbox(candidate)))
                except ValueError:
                    continue
    return variants


def add_dpi_variants(
    variants: Sequence[Variant], dpi_scales: Iterable[float]
) -> list[Variant]:
    result: list[Variant] = []
    for scale in dpi_scales:
        scale = float(scale)
        if scale <= 0 or not math.isfinite(scale):
            raise ValueError(f"dpi scale must be positive and finite, got {scale}")
        for variant in variants:
            result.append(Variant(variant.name, variant.bbox, scale))
    return result


def _scale_page_and_bbox(
    image: np.ndarray,
    bbox: tuple[float, float, float, float],
    scale: float,
) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    if scale == 1.0:
        return image, bbox
    height, width = image.shape[:2]
    scaled_width = max(1, int(round(width * scale)))
    scaled_height = max(1, int(round(height * scale)))
    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
    scaled_image = cv2.resize(image, (scaled_width, scaled_height), interpolation=interpolation)
    scaled_bbox = tuple(float(value) * scale for value in bbox)
    return scaled_image, scaled_bbox  # type: ignore[return-value]


def crop_measure(image: np.ndarray, bbox: Sequence[float], margin_px: int) -> np.ndarray:
    """Mirror production's fixed source-pixel margin and integer slicing."""
    x1, y1, x2, y2 = _validated_bbox(bbox)
    height, width = image.shape[:2]
    cx1 = max(0, int(x1 - margin_px))
    cy1 = max(0, int(y1 - margin_px))
    cx2 = min(width, int(x2 + margin_px))
    cy2 = min(height, int(y2 + margin_px))
    if cx2 <= cx1 or cy2 <= cy1:
        raise ValueError(
            f"crop is empty after clipping: bbox={bbox!r}, margin={margin_px}, image={width}x{height}"
        )
    crop = image[cy1:cy2, cx1:cx2]
    if crop.size == 0:
        raise ValueError("crop unexpectedly has zero size")
    return crop


def _letterbox_transform() -> transforms.Compose:
    def letterbox(image: Image.Image) -> Image.Image:
        image = image.convert("RGB")
        contained = ImageOps.contain(image, (224, 224), method=Image.Resampling.BILINEAR)
        canvas = Image.new("RGB", (224, 224), (255, 255, 255))
        canvas.paste(contained, ((224 - contained.width) // 2, (224 - contained.height) // 2))
        return canvas

    return transforms.Compose(
        [
            transforms.Lambda(letterbox),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]
    )


class Predictor:
    def __init__(self, model_path: Path, device: torch.device, resize_mode: str):
        self.classifier = ProductionMMRClassifierMirror(model_path, device)
        self.device = device
        self.resize_mode = resize_mode
        self.letterbox_transform = _letterbox_transform()

    def predict(self, crop: np.ndarray) -> float:
        if self.resize_mode == "direct":
            return float(self.classifier.predict(crop))
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        tensor = self.letterbox_transform(Image.fromarray(rgb)).unsqueeze(0).to(self.device)
        with torch.no_grad():
            return float(torch.sigmoid(self.classifier.model(tensor)).item())


def _load_config(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("benchmark config must be a JSON object")
    return payload


def _parse_numbers(raw: Any, *, cast: type) -> tuple[Any, ...]:
    if isinstance(raw, str):
        values = [item.strip() for item in raw.split(",") if item.strip()]
    elif isinstance(raw, list):
        values = raw
    else:
        raise ValueError(f"expected comma-separated string or JSON list, got {raw!r}")
    return tuple(cast(value) for value in values)


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    samples = payload.get("samples") if isinstance(payload, dict) else None
    if not isinstance(samples, list) or not samples:
        raise ValueError("manifest must contain a non-empty 'samples' list")
    required = {"sample_id", "score_id", "page_id", "image_path", "bbox", "label"}
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(samples):
        if not isinstance(raw, dict):
            raise ValueError(f"samples[{index}] must be an object")
        missing = required - raw.keys()
        if missing:
            raise ValueError(f"samples[{index}] missing fields: {sorted(missing)}")
        sample_id = str(raw["sample_id"])
        if sample_id in seen:
            raise ValueError(f"duplicate sample_id: {sample_id}")
        seen.add(sample_id)
        label = int(raw["label"])
        if label not in (0, 1):
            raise ValueError(f"sample {sample_id}: label must be 0 or 1")
        item = dict(raw)
        item["sample_id"] = sample_id
        item["score_id"] = str(raw["score_id"])
        item["page_id"] = str(raw["page_id"])
        item["bbox"] = list(_validated_bbox(raw["bbox"]))
        item["label"] = label
        item["tags"] = [str(tag) for tag in raw.get("tags", [])]
        normalized.append(item)
    return normalized


def _decision(probability: float, threshold: float) -> bool:
    return probability >= threshold


def _summary(rows: Sequence[dict[str, Any]], main_threshold: float, rescue_threshold: float) -> dict[str, Any]:
    by_sample: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_sample.setdefault(row["sample_id"], []).append(row)
    samples: dict[str, Any] = {}
    crossings_main = 0
    crossings_rescue = 0
    for sample_id, sample_rows in sorted(by_sample.items()):
        native_candidates = [
            row for row in sample_rows
            if row["variant"] == "native" and float(row["dpi_scale"]) == 1.0
        ]
        if len(native_candidates) != 1:
            raise ValueError(f"sample {sample_id}: expected one native 1.0x row")
        native_prob = float(native_candidates[0]["probability"])
        probs = [float(row["probability"]) for row in sample_rows]
        main_cross = len({_decision(prob, main_threshold) for prob in probs}) > 1
        rescue_cross = len({_decision(prob, rescue_threshold) for prob in probs}) > 1
        crossings_main += int(main_cross)
        crossings_rescue += int(rescue_cross)
        samples[sample_id] = {
            "label": int(sample_rows[0]["label"]),
            "score_id": sample_rows[0]["score_id"],
            "page_id": sample_rows[0]["page_id"],
            "tags": sample_rows[0]["tags"],
            "native_probability": native_prob,
            "probability_min": min(probs),
            "probability_max": max(probs),
            "probability_range": max(probs) - min(probs),
            "max_abs_delta_from_native": max(abs(prob - native_prob) for prob in probs),
            "crosses_main_threshold": main_cross,
            "crosses_rescue_threshold": rescue_cross,
        }
    native_rows = [row for row in rows if row["variant"] == "native" and float(row["dpi_scale"]) == 1.0]
    all_correct = sum(
        int(_decision(float(row["probability"]), main_threshold) == bool(row["label"])) for row in rows
    )
    native_correct = sum(
        int(_decision(float(row["probability"]), main_threshold) == bool(row["label"])) for row in native_rows
    )
    return {
        "sample_count": len(samples),
        "row_count": len(rows),
        "samples_crossing_main_threshold": crossings_main,
        "samples_crossing_rescue_threshold": crossings_rescue,
        "native_accuracy": native_correct / len(native_rows) if native_rows else None,
        "perturbation_row_accuracy": all_correct / len(rows) if rows else None,
        "samples": samples,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    config = _load_config(args.config)
    main_threshold = float(config.get("main_threshold", DEFAULT_MAIN_THRESHOLD))
    rescue_threshold = float(config.get("rescue_threshold", DEFAULT_RESCUE_THRESHOLD))
    margin_px = int(config.get("margin_px", DEFAULT_MARGIN_PX))
    deltas_px = _parse_numbers(config.get("deltas_px", list(DEFAULT_DELTAS_PX)), cast=int)
    dpi_scales = _parse_numbers(config.get("dpi_scales", list(DEFAULT_DPI_SCALES)), cast=float)
    resize_modes = args.resize_mode or config.get("resize_modes", ["direct"])
    if isinstance(resize_modes, str):
        resize_modes = [resize_modes]
    invalid_modes = set(resize_modes) - {"direct", "letterbox"}
    if invalid_modes:
        raise ValueError(f"unsupported resize modes: {sorted(invalid_modes)}")
    if 1.0 not in dpi_scales:
        raise ValueError("dpi_scales must include 1.0 so native provenance is explicit")

    samples = _load_manifest(args.manifest)
    model_path = args.model.resolve()
    device = torch.device(args.device)
    predictors = {mode: Predictor(model_path, device, mode) for mode in resize_modes}
    rows: list[dict[str, Any]] = []
    started = time.perf_counter()
    for sample in samples:
        image_path = Path(sample["image_path"])
        if not image_path.is_absolute():
            image_path = (args.manifest.parent / image_path).resolve()
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(f"could not load source image: {image_path}")
        variants = add_dpi_variants(generate_geometry_variants(sample["bbox"], deltas_px), dpi_scales)
        for variant in variants:
            scaled_image, scaled_bbox = _scale_page_and_bbox(image, variant.bbox, variant.dpi_scale)
            crop = crop_measure(scaled_image, scaled_bbox, margin_px=margin_px)
            for mode, predictor in predictors.items():
                infer_started = time.perf_counter()
                probability = predictor.predict(crop)
                rows.append(
                    {
                        "sample_id": sample["sample_id"],
                        "score_id": sample["score_id"],
                        "page_id": sample["page_id"],
                        "label": sample["label"],
                        "tags": sample["tags"],
                        "variant": variant.name,
                        "dpi_scale": variant.dpi_scale,
                        "bbox": list(variant.bbox),
                        "scaled_bbox": list(scaled_bbox),
                        "crop_shape": list(crop.shape[:2]),
                        "resize_mode": mode,
                        "probability": probability,
                        "main_positive": _decision(probability, main_threshold),
                        "rescue_positive": _decision(probability, rescue_threshold),
                        "inference_ms": (time.perf_counter() - infer_started) * 1000.0,
                    }
                )

    summaries = {}
    for mode in resize_modes:
        mode_rows = [row for row in rows if row["resize_mode"] == mode]
        summaries[mode] = _summary(mode_rows, main_threshold, rescue_threshold)
        summaries[mode]["mean_inference_ms"] = (
            sum(float(row["inference_ms"]) for row in mode_rows) / len(mode_rows) if mode_rows else None
        )
    return {
        "provenance": {
            "issue": 332,
            "git_head": _git_head(),
            "model_path": str(model_path),
            "model_sha256": sha256_file(model_path),
            "manifest_path": str(args.manifest.resolve()),
            "manifest_sha256": sha256_file(args.manifest),
            "config_path": str(args.config.resolve()) if args.config else None,
            "config_sha256": sha256_file(args.config) if args.config else None,
            "device": str(device),
            "torch_version": torch.__version__,
            "opencv_version": cv2.__version__,
            "python_version": platform.python_version(),
        },
        "contract": {
            "main_threshold": main_threshold,
            "rescue_threshold": rescue_threshold,
            "margin_px": margin_px,
            "deltas_px": list(deltas_px),
            "dpi_scales": list(dpi_scales),
            "resize_modes": list(resize_modes),
            "staff_y_dependency": "none-direct: classifier crop derives from measure bbox only",
            "classifier_loader": "experiment-local production MMRClassifier mirror",
            "classifier_reference": "src/measure_numbering/mmr.py::MMRClassifier",
            "rapidocr_involved": False,
        },
        "elapsed_seconds": time.perf_counter() - started,
        "summary": summaries,
        "rows": rows,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument(
        "--resize-mode", action="append", choices=("direct", "letterbox"),
        help="May be repeated. Defaults to config resize_modes or direct.",
    )
    parser.add_argument(
        "--device", default="cuda" if torch.cuda.is_available() else "cpu",
        help="torch device (default: cuda when available, otherwise cpu)",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result["summary"], indent=2, sort_keys=True))
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
