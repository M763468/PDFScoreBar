import argparse
import json
import logging
import sys
from pathlib import Path

import cv2

project_root = Path(__file__).resolve().parents[2]
sys.path.append(str(project_root))

from src.measure_numbering.connector_aware_builder import ConnectorAwareSystemBuilder
from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.measure_numbering.types import Score
from tools.add_measure_numbers import normalize_barlines, render_overlay, score_to_dict

logger = logging.getLogger(__name__)


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(
        description="Issue #197 connector-aware measure numbering helper."
    )
    parser.add_argument("--barlines", type=Path, required=True)
    parser.add_argument("--staff-mask", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--symbol-mask", type=Path)
    parser.add_argument("--brace-dot-mask", type=Path)
    parser.add_argument("--connector-evidence-json", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-overlay", type=Path)
    parser.add_argument("--start-number", type=int, default=1)
    parser.add_argument("--page-number", type=int, default=1)
    args = parser.parse_args()

    with open(args.barlines) as f:
        barline_boxes = normalize_barlines(json.load(f))

    image = cv2.imread(str(args.image))
    if image is None:
        raise FileNotFoundError(f"Image not found: {args.image}")
    h, w = image.shape[:2]

    connector_mask_paths = {}
    if args.symbol_mask is not None:
        connector_mask_paths["symbols"] = args.symbol_mask
    if args.brace_dot_mask is not None:
        connector_mask_paths["brace_dot"] = args.brace_dot_mask

    pipeline = MeasureNumberingPipeline()
    pipeline.builder = ConnectorAwareSystemBuilder()
    page = pipeline.process_page(
        barline_boxes,
        args.staff_mask,
        (w, h),
        page_number=args.page_number,
        image=image,
        connector_mask_paths=connector_mask_paths or None,
        connector_evidence_output_path=args.connector_evidence_json,
    )

    score = Score()
    score.pages.append(page)
    pipeline.numberer.number_score(score, start_number=args.start_number)

    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output_json, "w") as f:
            json.dump(score_to_dict(score), f, indent=2)
    if args.output_overlay is not None:
        args.output_overlay.parent.mkdir(parents=True, exist_ok=True)
        render_overlay(score, args.image, args.output_overlay)


if __name__ == "__main__":
    main()
