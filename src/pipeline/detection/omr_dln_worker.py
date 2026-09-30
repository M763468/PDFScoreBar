"""Run the production OMR-DLN measure detector on precomputed SR page images.

The dense production route owns SR generation separately.  This worker therefore
accepts only persisted precomputed-SR input and emits the source-coordinate
barline predictions consumed by hybrid consensus.  Evaluation, visualization,
and internal-SR experiment features intentionally stay outside this runtime
module.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

import cv2

from src.pipeline.detection.omr_dln_model import (
    omr_dln_model_missing_message,
    resolve_omr_dln_model_path,
)

BARLINE_WIDTH = 4


def infer_barlines_from_measures(
    measure_boxes: Iterable[tuple[int, int, int, int]],
) -> list[tuple[int, int, int, int]]:
    """Convert measure boxes into left/right barline boxes."""
    barlines: list[tuple[int, int, int, int]] = []
    half_width = BARLINE_WIDTH // 2
    for x1, y1, x2, y2 in measure_boxes:
        barlines.append((x1 - half_width, y1, x1 + half_width, y2))
        barlines.append((x2 - half_width, y1, x2 + half_width, y2))
    return barlines


def resolve_precomputed_sr(sr_base: Path, image: Path) -> Path:
    """Resolve the persisted SR layout produced by the current x4 worker."""
    stem = image.stem
    candidates = (
        sr_base / stem / stem / f"{stem}.png",
        sr_base / stem / f"{stem}.png",
        sr_base / f"{stem}.png",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    if sr_base.is_file():
        return sr_base.resolve()
    raise FileNotFoundError(f"No precomputed SR image for {image}: base={sr_base}")


def _scale_to_source(
    boxes: Iterable[tuple[int, int, int, int]],
    *,
    scale: int,
) -> list[tuple[int, int, int, int]]:
    return [
        (int(x1 / scale), int(y1 / scale), int(x2 / scale), int(y2 / scale))
        for x1, y1, x2, y2 in boxes
    ]


def run(
    images: list[Path],
    *,
    output_dir: Path,
    precomputed_sr: Path,
    confidence: float = 0.25,
    model: Any | None = None,
) -> list[Path]:
    """Run OMR-DLN for pages using the already-generated x4 image contract."""
    if not images:
        raise ValueError("OMR-DLN runtime requires at least one image")

    if model is None:
        from ultralytics import YOLO

        model_path = resolve_omr_dln_model_path()
        if not model_path.is_file():
            raise FileNotFoundError(omr_dln_model_missing_message(model_path))
        model = YOLO(model_path)

    outputs: list[Path] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    for image in images:
        source = image.resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        original = cv2.imread(str(source))
        if original is None:
            raise RuntimeError(f"Failed to read OMR-DLN source image: {source}")

        sr_image = resolve_precomputed_sr(precomputed_sr.resolve(), source)
        sr = cv2.imread(str(sr_image))
        if sr is None:
            raise RuntimeError(f"Failed to read precomputed SR image: {sr_image}")

        original_h, original_w = original.shape[:2]
        sr_h, sr_w = sr.shape[:2]
        if not original_w or not original_h:
            raise ValueError(f"Invalid source image dimensions: {source}")
        scale_x = sr_w / original_w
        scale_y = sr_h / original_h
        inferred_scale = round(scale_x)
        if inferred_scale < 2 or abs(scale_x - inferred_scale) > 0.05:
            raise ValueError(
                f"OMR-DLN precomputed SR has unexpected x scale: {scale_x:.4f} for {source}"
            )
        if abs(scale_y - inferred_scale) > 0.05:
            raise ValueError(
                f"OMR-DLN precomputed SR has unexpected y scale: {scale_y:.4f} for {source}"
            )

        results = model.predict(sr, conf=confidence, save=False, verbose=False)
        if not results:
            raise RuntimeError(f"OMR-DLN returned no result object for {source}")

        measure_boxes: list[tuple[int, int, int, int]] = []
        for box in results[0].boxes:
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            measure_boxes.append((int(x1), int(y1), int(x2), int(y2)))

        source_barlines = _scale_to_source(
            infer_barlines_from_measures(measure_boxes),
            scale=inferred_scale,
        )
        page_dir = output_dir / source.stem
        page_dir.mkdir(parents=True, exist_ok=True)
        predictions = page_dir / "predictions.json"
        predictions.write_text(json.dumps(source_barlines) + "\n", encoding="utf-8")
        outputs.append(predictions)

    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", nargs="+", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--pre-computed-sr", type=Path, required=True)
    parser.add_argument("--conf", type=float, default=0.25)
    args = parser.parse_args()
    try:
        outputs = run(
            args.images,
            output_dir=args.output_dir,
            precomputed_sr=args.pre_computed_sr,
            confidence=args.conf,
        )
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1
    print(
        json.dumps(
            {"status": "completed", "outputs": [str(path) for path in outputs]},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
