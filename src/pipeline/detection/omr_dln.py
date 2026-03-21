"""OMR-DLN (YOLO) detection module."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

import cv2
from ultralytics import YOLO

from src.pipeline.utils.images import load_image

logger = logging.getLogger(__name__)

# Cache model globally
_MODEL = None
_MODEL_PATH = Path(__file__).resolve().parents[3] / "external/omr_dln/models/public_models/YOLOv8m_Measures.pt"
BARLINE_WIDTH = 4


def _get_model() -> YOLO:
    global _MODEL
    if _MODEL is None:
        if not _MODEL_PATH.exists():
            raise FileNotFoundError(f"OMR-DLN model not found at {_MODEL_PATH}. Please download it.")
        logger.info(f"Loading OMR-DLN model from {_MODEL_PATH}")
        _MODEL = YOLO(str(_MODEL_PATH))
    return _MODEL


def infer_barlines_from_measures(measure_boxes: List[Tuple[int, int, int, int]]) -> List[Tuple[int, int, int, int]]:
    """
    Converts measure bounding boxes into barline bounding boxes.
    A measure (x1, y1, x2, y2) implies a left barline and a right barline,
    using the measure's own vertical span.
    """
    barlines = []
    for mx1, my1, mx2, my2 in measure_boxes:
        barlines.append((mx1 - BARLINE_WIDTH // 2, my1, mx1 + BARLINE_WIDTH // 2, my2))
        barlines.append((mx2 - BARLINE_WIDTH // 2, my1, mx2 + BARLINE_WIDTH // 2, my2))
    return barlines


def run_omr_dln_batch(
    images: List[Path],
    output_dir: Path,
    pre_computed_sr_dir: Path | None = None,
    conf: float = 0.25,
    in_memory_images: Dict[str, Any] | None = None,
) -> None:
    """
    Runs OMR-DLN measure detection and infers barlines for a batch of images.
    """
    model = _get_model()
    output_dir.mkdir(parents=True, exist_ok=True)

    for img_path in images:
        stem = img_path.stem
        logger.info(f"OMR-DLN processing {stem}")

        page_output_dir = output_dir / stem
        page_output_dir.mkdir(parents=True, exist_ok=True)

        original_img_bgr = load_image(img_path, in_memory_images=in_memory_images)
        if original_img_bgr is None:
            logger.error(f"Could not load image {img_path}. Skipping.")
            continue

        inference_input = original_img_bgr
        sr_scale = 1

        if pre_computed_sr_dir:
            # Check potential paths for SR image
            sr_img_path = None
            p1 = pre_computed_sr_dir / stem / img_path.name
            p2 = pre_computed_sr_dir / stem / f"{stem}.png"
            p3 = pre_computed_sr_dir / f"{stem}.png"
            
            for p in [p1, p2, p3]:
                if p.exists():
                    sr_img_path = p
                    break
            
            if sr_img_path:
                logger.debug(f"Using pre-computed SR: {sr_img_path}")
                sr_img_bgr = cv2.imread(str(sr_img_path))
                if sr_img_bgr is not None:
                    original_h, original_w = original_img_bgr.shape[:2]
                    up_h, up_w = sr_img_bgr.shape[:2]
                    inferred_scale = round(up_w / original_w) if original_w else 1
                    if inferred_scale >= 2:
                        sr_scale = inferred_scale
                        inference_input = sr_img_bgr
            else:
                logger.warning(f"Pre-computed SR requested but not found for {stem}.")

        results = model.predict(inference_input, conf=conf, save=False, verbose=False)
        result = results[0]

        measure_boxes = []
        if result.boxes is not None:
            for box in result.boxes:  # type: ignore[attr-defined,union-attr]
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                measure_boxes.append((int(x1), int(y1), int(x2), int(y2)))

        pred_barlines_inference = infer_barlines_from_measures(measure_boxes)

        pred_barlines_1x = []
        for x1, y1, x2, y2 in pred_barlines_inference:
            pred_barlines_1x.append(
                (
                    int(round(x1 / sr_scale)),
                    int(round(y1 / sr_scale)),
                    int(round(x2 / sr_scale)),
                    int(round(y2 / sr_scale)),
                )
            )

        # Save predictions
        predictions_path = page_output_dir / "predictions.json"
        with open(predictions_path, "w") as f:
            json.dump(pred_barlines_1x, f)
