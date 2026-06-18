import argparse
import json
import logging
import sys
from pathlib import Path

import cv2

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.measure_numbering.types import Score

logger = logging.getLogger(__name__)


def render_overlay(score: Score, image_path: Path, output_path: Path):
    img = cv2.imread(image_path)
    if img is None:
        logger.error(f"Error: Could not read image for overlay: {image_path}")
        return

    overlay = img.copy()
    overlay_temp = overlay.copy()
    for page in score.pages:
        for sys_obj in page.systems:
            for staff in sys_obj.staves:
                cv2.rectangle(
                    overlay_temp,
                    (int(staff.bbox.x1), int(staff.bbox.y1)),
                    (int(staff.bbox.x2), int(staff.bbox.y2)),
                    (255, 0, 0),
                    -1,
                )
    cv2.addWeighted(overlay_temp, 0.15, overlay, 0.85, 0, overlay)

    for page in score.pages:
        for sys_obj in page.systems:
            top_staff = min(sys_obj.staves, key=lambda s: s.bbox.y1)
            text_y = top_staff.bbox.y1 - 10
            for measure in sys_obj.measures:
                center_x = int((measure.bbox.x1 + measure.bbox.x2) / 2)
                text = str(measure.number)
                font_scale = 1.2
                thickness = 2
                (text_w, _text_h), _ = cv2.getTextSize(
                    text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness
                )
                cv2.putText(
                    overlay,
                    text,
                    (center_x - text_w // 2, text_y),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    font_scale,
                    (0, 150, 0),
                    thickness,
                    cv2.LINE_AA,
                )
                cv2.line(
                    overlay,
                    (int(measure.bbox.x1), int(text_y)),
                    (int(measure.bbox.x1), int(text_y + 10)),
                    (0, 255, 0),
                    1,
                )
                cv2.line(
                    overlay,
                    (int(measure.bbox.x2), int(text_y)),
                    (int(measure.bbox.x2), int(text_y + 10)),
                    (0, 255, 0),
                    1,
                )

            for staff in sys_obj.staves:
                for bar in staff.barlines:
                    color = (0, 0, 255)
                    if getattr(bar, "is_ghost", False):
                        color = (255, 0, 255)
                    cv2.rectangle(
                        overlay,
                        (int(bar.bbox.x1), int(bar.bbox.y1)),
                        (int(bar.bbox.x2), int(bar.bbox.y2)),
                        color,
                        2,
                    )

    cv2.imwrite(str(output_path), overlay)
    logger.info(f"Overlay saved to: {output_path}")


def score_to_dict(score: Score) -> dict:
    data = {"pages": []}
    for p in score.pages:
        page_data = {
            "page_number": p.page_number,
            "width": p.width,
            "height": p.height,
            "systems": [],
        }
        for s in p.systems:
            sys_data = {
                "staves": [
                    {"bbox": [st.bbox.x1, st.bbox.y1, st.bbox.x2, st.bbox.y2]} for st in s.staves
                ],
                "measures": [],
            }
            for m in s.measures:
                m_data = {
                    "number": m.number,
                    "bbox": [m.bbox.x1, m.bbox.y1, m.bbox.x2, m.bbox.y2],
                }
                sys_data["measures"].append(m_data)
            page_data["systems"].append(sys_data)
        data["pages"].append(page_data)
    return data


def normalize_barlines(raw_data):
    if not raw_data:
        return []

    normalized = []
    for item in raw_data:
        if isinstance(item, list) and len(item) == 4:
            normalized.append(item)
        elif isinstance(item, dict):
            if "barline_location" in item:
                normalized.append(item["barline_location"])
            elif all(k in item for k in ["x1", "y1", "x2", "y2"]):
                normalized.append([item["x1"], item["y1"], item["x2"], item["y2"]])
    return normalized


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Add measure numbers to detected barlines.")
    parser.add_argument("--barlines", type=Path, required=True)
    parser.add_argument("--staff-mask", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-overlay", type=Path)
    parser.add_argument("--start-number", type=int, default=1)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--page-number", type=int, default=1)
    parser.add_argument("--force-single-system", action="store_true")
    parser.add_argument("--symbol-mask", type=Path)
    parser.add_argument("--brace-dot-mask", type=Path)
    parser.add_argument("--connector-evidence-json", type=Path)
    args = parser.parse_args()

    with open(args.barlines) as f:
        barline_boxes = normalize_barlines(json.load(f))

    overrides = None
    if args.config:
        with open(args.config) as f:
            overrides = json.load(f).get("measure_overrides")

    img_ref = cv2.imread(str(args.image))
    if img_ref is None:
        logger.error(f"Error: Could not read reference image: {args.image}")
        sys.exit(1)
    h, w = img_ref.shape[:2]

    pipeline = MeasureNumberingPipeline()
    connector_mask_paths = {}
    if args.symbol_mask is not None:
        connector_mask_paths["symbols"] = args.symbol_mask
    if args.brace_dot_mask is not None:
        connector_mask_paths["brace_dot"] = args.brace_dot_mask

    score = Score()
    page = pipeline.process_page(
        barline_boxes,
        args.staff_mask,
        (w, h),
        args.page_number,
        assume_one_staff_per_system=args.force_single_system,
        image=img_ref,
        connector_mask_paths=connector_mask_paths or None,
        connector_evidence_output_path=args.connector_evidence_json,
    )
    score.pages.append(page)
    pipeline.numberer.number_score(score, start_number=args.start_number, overrides=overrides)

    if args.output_json:
        with open(args.output_json, "w") as f:
            json.dump(score_to_dict(score), f, indent=2)
        logger.info(f"Result JSON saved to: {args.output_json}")

    if args.output_overlay:
        render_overlay(score, args.image, args.output_overlay)


if __name__ == "__main__":
    main()
