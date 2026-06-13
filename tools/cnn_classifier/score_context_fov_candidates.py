#!/usr/bin/env python3
"""Score one candidate JSON with issue #206 crop-contract variants.

This helper is for controlled Context-FOV experiments. It does not train or
retrain a model. It reads an existing image, candidate boxes, and checkpoint,
then emits per-variant scored/filtered JSON files under an output directory.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
from PIL import Image
from torchvision import models, transforms

from crop_contract import crop_candidate, resolve_contracts


IMG_SIZE = (256, 128)  # H, W
MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]
DEFAULT_VARIANTS = ["current_like", "wider_x", "square_context"]


class GPUNormalize(torch.nn.Module):
    def __init__(self, mean: list[float], std: list[float]):
        super().__init__()
        self.register_buffer("mean", torch.tensor(mean).view(1, 3, 1, 1))
        self.register_buffer("std", torch.tensor(std).view(1, 3, 1, 1))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return (x - self.mean) / self.std


def load_model(model_path: Path, model_name: str, device: torch.device) -> torch.nn.Module:
    if model_name != "resnet18":
        raise ValueError(f"unsupported model_name for this experiment helper: {model_name}")
    model = models.resnet18(weights=None)
    model.fc = torch.nn.Linear(model.fc.in_features, 1)
    state_dict = torch.load(model_path, map_location=device)
    if any(k.startswith("_orig_mod.") for k in state_dict.keys()):
        state_dict = {
            (k[len("_orig_mod.") :] if k.startswith("_orig_mod.") else k): v
            for k, v in state_dict.items()
        }
    model.load_state_dict(state_dict)
    model.to(device)
    model.eval()
    return model


def load_candidates(path: Path) -> list[list[float]]:
    with path.open("r") as f:
        data = json.load(f)
    if isinstance(data, dict):
        if "scores" in data:
            data = data["scores"]
        elif "candidates" in data:
            data = data["candidates"]
        elif "boxes" in data:
            data = data["boxes"]
    boxes: list[list[float]] = []
    if not isinstance(data, list):
        raise ValueError(f"unsupported candidate JSON structure: {path}")
    for item in data:
        box: Any = item.get("bbox") if isinstance(item, dict) else item
        if isinstance(box, list | tuple) and len(box) == 4:
            boxes.append([float(v) for v in box])
    return boxes


def tensor_from_crop(crop: np.ndarray) -> torch.Tensor:
    crop_pil = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
    return transforms.ToTensor()(crop_pil.resize((IMG_SIZE[1], IMG_SIZE[0]), Image.BILINEAR))


def score_variant(
    *,
    img: np.ndarray,
    boxes: list[list[float]],
    model: torch.nn.Module,
    normalizer: GPUNormalize,
    device: torch.device,
    variant: str,
    batch_size: int,
) -> list[dict[str, Any]]:
    contract = resolve_contracts([variant])[0]
    tensors = [tensor_from_crop(crop_candidate(img, box, contract).crop) for box in boxes]
    scores: list[float] = []
    for idx in range(0, len(tensors), batch_size):
        batch = torch.stack(tensors[idx : idx + batch_size]).to(device)
        batch = normalizer(batch)
        with torch.no_grad():
            logits = model(batch)
            scores.extend(torch.sigmoid(logits).cpu().numpy().flatten().astype(float).tolist())
    rows = []
    for box, score in zip(boxes, scores, strict=True):
        rows.append({"bbox": [int(round(v)) for v in box], "score": float(score)})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--variant", action="append", dest="variants")
    parser.add_argument("--model-name", default="resnet18")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()

    img = cv2.imread(str(args.image))
    if img is None:
        raise FileNotFoundError(f"image not found or unreadable: {args.image}")
    boxes = load_candidates(args.candidates)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = load_model(args.model, args.model_name, device)
    normalizer = GPUNormalize(MEAN, STD).to(device)
    variants = args.variants or DEFAULT_VARIANTS

    summary = {
        "image": str(args.image),
        "candidates": str(args.candidates),
        "model": str(args.model),
        "threshold": args.threshold,
        "device": str(device),
        "candidate_count": len(boxes),
        "variants": {},
    }

    for variant in variants:
        rows = score_variant(
            img=img,
            boxes=boxes,
            model=model,
            normalizer=normalizer,
            device=device,
            variant=variant,
            batch_size=args.batch_size,
        )
        filtered = [row["bbox"] for row in rows if row["score"] >= args.threshold]
        (args.output_dir / f"{variant}_scored.json").write_text(json.dumps(rows, indent=2) + "\n")
        (args.output_dir / f"{variant}_filtered.json").write_text(json.dumps(filtered, indent=2) + "\n")
        scores = [row["score"] for row in rows]
        summary["variants"][variant] = {
            "max_score": max(scores) if scores else None,
            "min_score": min(scores) if scores else None,
            "mean_score": float(np.mean(scores)) if scores else None,
            "filtered_count": len(filtered),
        }

    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
