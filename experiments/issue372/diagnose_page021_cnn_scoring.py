#!/usr/bin/env python3
"""Focused Issue #372 diagnostic for the three Shostakovich page_021 CNN FNs.

Scores the exact retained candidates with the immutable D27 checkpoint under:
- bbox-centered crop (the Issue #296 D27 training/evaluation crop contract);
- current ink-recentered crop.

The report records crop centers, pixel/tensor hashes, scores, model digest, and
runtime library versions so host-vs-container runs can be compared mechanically.

No candidate generation, HOMR, threshold tuning, or downstream inference occurs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cv2
import numpy as np
import PIL
import torch
import torchvision
from PIL import Image
from torchvision import transforms

from src.pipeline.steps.cnn_scoring import (
    GPUNormalize,
    IMG_SIZE,
    MEAN,
    STD,
    _center_crop,
    _compute_bbox_ink_center_x,
    _crop_size_from_bbox,
    _load_model,
)

TARGETS = (
    (1333, 798, 1340, 894),
    (1769, 798, 1778, 896),
    (2749, 802, 2756, 900),
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_array(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def _sha256_tensor(tensor: torch.Tensor) -> str:
    array = tensor.detach().cpu().contiguous().numpy()
    return _sha256_array(array)


def _score_tensor(
    tensor: torch.Tensor,
    *,
    model: torch.nn.Module,
    norm: GPUNormalize,
    device: torch.device,
) -> float:
    batch = tensor.unsqueeze(0).to(device)
    batch = norm(batch)
    with torch.no_grad():
        value = torch.sigmoid(model(batch)).reshape(-1)[0]
    return float(value.detach().cpu().item())


def _crop_variant(
    image: np.ndarray,
    box: Sequence[int],
    *,
    recenter: bool,
    max_shift_unit_ratio: float,
) -> dict[str, Any]:
    x1, y1, x2, y2 = [int(v) for v in box]
    base_cx = int((x1 + x2) / 2)
    cy = int((y1 + y2) / 2)
    cx = base_cx
    adjusted = None
    if recenter:
        adjusted = _compute_bbox_ink_center_x(
            image,
            box,
            max_shift_unit_ratio=max_shift_unit_ratio,
        )
        if adjusted is not None:
            cx = int(adjusted)

    crop_w, crop_h = _crop_size_from_bbox(box)
    crop = _center_crop(image, cx, cy, crop_w, crop_h)
    resize_filter = (
        Image.Resampling.BILINEAR
        if hasattr(Image, "Resampling")
        else Image.BILINEAR
    )
    rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    resized = Image.fromarray(rgb).resize(
        (IMG_SIZE[1], IMG_SIZE[0]),
        resize_filter,
    )
    tensor = transforms.ToTensor()(resized)
    resized_np = np.asarray(resized)
    return {
        "base_cx": base_cx,
        "effective_cx": cx,
        "recenter_return": adjusted,
        "shift_px": cx - base_cx,
        "cy": cy,
        "crop_width": crop_w,
        "crop_height": crop_h,
        "crop_bgr": crop,
        "resized_rgb": resized_np,
        "tensor": tensor,
        "crop_sha256": _sha256_array(crop),
        "resized_sha256": _sha256_array(resized_np),
        "tensor_sha256": _sha256_tensor(tensor),
    }


def _write_png(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), image):
        raise RuntimeError(f"Failed to write {path}")


def run(args: argparse.Namespace) -> dict[str, Any]:
    image_path = args.image.resolve()
    model_path = args.model.resolve()
    output = args.output.resolve()
    crop_dir = args.crop_dir.resolve()

    if not image_path.is_file():
        raise FileNotFoundError(image_path)
    if not model_path.is_file():
        raise FileNotFoundError(model_path)
    if output.exists():
        raise FileExistsError(output)
    if crop_dir.exists():
        raise FileExistsError(crop_dir)

    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"OpenCV failed to read {image_path}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if args.require_cuda and device.type != "cuda":
        raise RuntimeError("CUDA required for this diagnostic")

    model = _load_model(model_path, device)
    norm = GPUNormalize(MEAN, STD).to(device)

    rows: list[dict[str, Any]] = []
    for index, box in enumerate(TARGETS, 1):
        variants: dict[str, Any] = {}
        for label, recenter in (("centered", False), ("recentered", True)):
            detail = _crop_variant(
                image,
                box,
                recenter=recenter,
                max_shift_unit_ratio=float(args.max_shift_unit_ratio),
            )
            score = _score_tensor(
                detail["tensor"],
                model=model,
                norm=norm,
                device=device,
            )
            crop_path = crop_dir / f"target_{index:02d}_{label}_crop.png"
            resized_path = crop_dir / f"target_{index:02d}_{label}_resized.png"
            _write_png(crop_path, detail["crop_bgr"])
            _write_png(
                resized_path,
                cv2.cvtColor(detail["resized_rgb"], cv2.COLOR_RGB2BGR),
            )
            variants[label] = {
                key: value
                for key, value in detail.items()
                if key not in {"crop_bgr", "resized_rgb", "tensor"}
            }
            variants[label].update(
                {
                    "score": score,
                    "crop_path": str(crop_path),
                    "resized_path": str(resized_path),
                }
            )

        rows.append(
            {
                "index": index,
                "bbox": list(box),
                "centered_score": variants["centered"]["score"],
                "recentered_score": variants["recentered"]["score"],
                "score_delta_recenter_minus_center": (
                    variants["recentered"]["score"]
                    - variants["centered"]["score"]
                ),
                "variants": variants,
            }
        )

    payload = {
        "schema_version": "issue372.page021_cnn_scoring_diagnostic.v1",
        "contract": {
            "targets": [list(box) for box in TARGETS],
            "threshold": 0.4965248107910156,
            "centered_contract": "Issue296 D27 dataset/evaluator bbox-centered crop",
            "recentered_contract": "current production crop_recenter_on_bbox_ink",
            "max_shift_unit_ratio": float(args.max_shift_unit_ratio),
        },
        "runtime": {
            "python": sys.version,
            "platform": platform.platform(),
            "torch": torch.__version__,
            "torchvision": torchvision.__version__,
            "opencv": cv2.__version__,
            "numpy": np.__version__,
            "pillow": PIL.__version__,
            "device": str(device),
            "cuda_available": torch.cuda.is_available(),
            "cuda_device_name": (
                torch.cuda.get_device_name(0)
                if torch.cuda.is_available()
                else None
            ),
        },
        "image": {
            "path": str(image_path),
            "sha256": _sha256_file(image_path),
            "shape": list(image.shape),
        },
        "model": {
            "path": str(model_path),
            "sha256": _sha256_file(model_path),
            "size": model_path.stat().st_size,
        },
        "rows": rows,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("=== Issue #372 page_021 CNN scoring diagnostic ===")
    print(json.dumps(payload["runtime"], indent=2, ensure_ascii=False))
    print(f"image_sha256={payload['image']['sha256']}")
    print(f"model_sha256={payload['model']['sha256']}")
    for row in rows:
        recentered = row["variants"]["recentered"]
        print(
            f"bbox={row['bbox']} "
            f"centered={row['centered_score']:.12f} "
            f"recentered={row['recentered_score']:.12f} "
            f"shift={recentered['shift_px']} "
            f"center_hash={row['variants']['centered']['tensor_sha256'][:16]} "
            f"recenter_hash={recentered['tensor_sha256'][:16]}"
        )
    print(f"OUTPUT={output}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--crop-dir", type=Path, required=True)
    parser.add_argument("--max-shift-unit-ratio", type=float, default=0.35)
    parser.add_argument("--require-cuda", action="store_true")
    args = parser.parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
