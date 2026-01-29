"""
Analyze known failure cases for multi-measure rest detection.

This script collects density/H-bar/OCR signals for specified measures,
exports diagnostic crops, and writes a structured report.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Target:
    work: str
    page: int
    measure: int


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )


def parse_targets(targets_path: Optional[Path], target_args: List[str]) -> List[Target]:
    if targets_path:
        with targets_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        return [Target(item["work"], int(item["page"]), int(item["measure"])) for item in raw]

    targets: List[Target] = []
    for item in target_args:
        try:
            work, page_str, measure_str = item.split(":")
            targets.append(Target(work, int(page_str), int(measure_str)))
        except ValueError as exc:
            raise ValueError(
                f"Invalid --target format: {item} (expected work:page:measure)"
            ) from exc
    return targets


def scan_pages(numbering_root: Path) -> List[Target]:
    pages: List[Target] = []
    for path in numbering_root.glob("*/*/numbering_final.json"):
        work = path.parent.parent.name
        page_str = path.parent.name
        if page_str.startswith("page_"):
            try:
                page_num = int(page_str.split("_")[-1])
            except ValueError:
                continue
            pages.append(Target(work, page_num, -1))
    for path in numbering_root.glob("*/*/numbering_base.json"):
        work = path.parent.parent.name
        page_str = path.parent.name
        if page_str.startswith("page_"):
            try:
                page_num = int(page_str.split("_")[-1])
            except ValueError:
                continue
            pages.append(Target(work, page_num, -1))
    # Deduplicate by work/page
    seen: set[Tuple[str, int]] = set()
    unique_pages: List[Target] = []
    for item in pages:
        key = (item.work, item.page)
        if key in seen:
            continue
        seen.add(key)
        unique_pages.append(item)
    return unique_pages


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def preprocess_image(img: np.ndarray) -> Optional[np.ndarray]:
    """Apply OCR-friendly preprocessing (mirrors debug_ocr_candidates.py)."""
    if img is None or img.size == 0:
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    binary_white_bg = cv2.bitwise_not(binary)

    kernel = np.ones((2, 2), np.uint8)
    dilated = cv2.dilate(binary_white_bg, kernel, iterations=1)
    padded = cv2.copyMakeBorder(dilated, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    return padded


def detect_hbar(roi_img: np.ndarray) -> Tuple[bool, int]:
    """Detect horizontal bar presence (H-bar) and return pixel count."""
    if roi_img is None or roi_img.size == 0:
        return False, 0

    gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    h, w = binary.shape
    if w < 20:
        return False, 0

    k_width = max(15, int(w * 0.3))
    horiz_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k_width, 1))
    detected_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horiz_kernel, iterations=1)
    count = int(cv2.countNonZero(detected_lines))
    return count > 20, count


def extract_number_from_text(text: str) -> Optional[int]:
    if not text:
        return None

    blacklist = [
        "Viol",
        "Vc",
        "Cb",
        "Fl",
        "Ob",
        "Cl",
        "Fag",
        "Cor",
        "Tr",
        "Timp",
        "Pizz",
        "Arco",
        "Div",
        "Legni",
        "Solo",
        "Tutti",
    ]
    for word in blacklist:
        if word.lower() in text.lower():
            return None

    numbers = re.findall(r"\d+", text)
    if not numbers:
        return None

    valid_nums: List[int] = []
    for n_str in numbers:
        try:
            val = int(n_str)
            if val >= 2:
                valid_nums.append(val)
        except ValueError:
            continue

    if not valid_nums:
        return None

    return max(valid_nums)


def build_paths(
    numbering_root: Path,
    image_root: Path,
    mask_root: Path,
    target: Target,
) -> Tuple[Path, Path, Path]:
    page_str = f"page_{target.page:03d}"
    numbering_json = numbering_root / target.work / page_str / "numbering_final.json"
    image_path = image_root / target.work / f"{page_str}.png"
    notehead_mask = (
        mask_root
        / f"eval2_{target.work}_{page_str}"
        / "baseline"
        / page_str
        / page_str
        / f"{page_str}_debug_6_notehead.png"
    )
    return numbering_json, image_path, notehead_mask


def iter_measures(data: Dict) -> Iterable[Dict]:
    for page in data.get("pages", []):
        for system in page.get("systems", []):
            for measure in system.get("measures", []):
                yield measure


def analyze_measure(
    measure: Dict,
    image: np.ndarray,
    mask: np.ndarray,
    scale_x: float,
    scale_y: float,
    vertical_margin_check: int,
    vertical_margin_ocr: int,
    horizontal_margin: int,
    erode_iter: int,
    center_offset_ratio: float,
    ocr_engine: RapidOCR,
) -> Dict:
    x1, y1, x2, y2 = measure["bbox"]

    # Mask density (strict ROI)
    margin_y_check_scaled = int(vertical_margin_check * scale_y)
    mx1 = max(0, int(x1 * scale_x))
    my1 = max(0, int(y1 * scale_y) - margin_y_check_scaled)
    mx2 = min(mask.shape[1], int(x2 * scale_x))
    my2 = min(mask.shape[0], int(y2 * scale_y) + margin_y_check_scaled)
    roi_mask = mask[my1:my2, mx1:mx2]
    pixel_count = int(cv2.countNonZero(roi_mask))

    # H-bar ROI (strict)
    roi_x1 = max(0, x1 - horizontal_margin)
    roi_x2 = min(image.shape[1], x2 + horizontal_margin)
    roi_y1_check = max(0, y1 - vertical_margin_check)
    roi_y2_check = min(image.shape[0], y2 + vertical_margin_check)
    roi_img_check = image[roi_y1_check:roi_y2_check, roi_x1:roi_x2]
    has_hbar, hbar_pixels = detect_hbar(roi_img_check)

    # OCR ROI (relaxed)
    roi_y1_ocr = max(0, y1 - vertical_margin_ocr)
    roi_y2_ocr_limit = y1 + int((y2 - y1) * 0.7) + 30
    roi_y2_ocr = min(image.shape[0], roi_y2_ocr_limit)
    roi_img_ocr = image[roi_y1_ocr:roi_y2_ocr, roi_x1:roi_x2]

    ocr_result = None
    extracted_number = None
    valid_texts: List[str] = []
    rejected_texts: List[str] = []
    ocr_items: List[Dict] = []

    if roi_img_ocr.size > 0:
        proc_img = preprocess_image(roi_img_ocr)
        if proc_img is not None:
            try:
                ocr_result, _ = ocr_engine(proc_img)
            except Exception as exc:
                LOGGER.warning("OCR failed: %s", exc)
                ocr_result = None

    if ocr_result:
        roi_w = proc_img.shape[1] if proc_img is not None else roi_img_ocr.shape[1]
        center_x = roi_w / 2

        for res in ocr_result:
            box = res[0]
            text = res[1]
            score = float(res[2])

            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            text_center_x = sum(xs) / len(xs)
            text_center_y = sum(ys) / len(ys)
            dist = abs(text_center_x - center_x)
            offset_ratio = dist / roi_w if roi_w else 1.0
            is_centered = offset_ratio < center_offset_ratio

            if is_centered:
                valid_texts.append(text)
            else:
                rejected_texts.append(text)

            ocr_items.append(
                {
                    "text": text,
                    "score": score,
                    "center_offset_ratio": round(offset_ratio, 4),
                    "center_y": round(text_center_y, 1),
                    "is_centered": is_centered,
                }
            )

        full_valid_text = " ".join(valid_texts)
        extracted_number = extract_number_from_text(full_valid_text)

    return {
        "pixel_count": pixel_count,
        "has_hbar": has_hbar,
        "hbar_pixels": hbar_pixels,
        "valid_texts": valid_texts,
        "rejected_texts": rejected_texts,
        "ocr_items": ocr_items,
        "extracted_number": extracted_number,
        "roi_check": (roi_x1, roi_y1_check, roi_x2, roi_y2_check),
        "roi_ocr": (roi_x1, roi_y1_ocr, roi_x2, roi_y2_ocr),
        "mask_bbox": (mx1, my1, mx2, my2),
    }


def draw_context_overlay(
    image: np.ndarray,
    bbox: Tuple[int, int, int, int],
    roi_check: Tuple[int, int, int, int],
    roi_ocr: Tuple[int, int, int, int],
) -> np.ndarray:
    x1, y1, x2, y2 = [int(v) for v in bbox]
    rc = [int(v) for v in roi_check]
    ro = [int(v) for v in roi_ocr]
    cv2.rectangle(image, (x1, y1), (x2, y2), (255, 0, 0), 2)
    cv2.rectangle(image, (rc[0], rc[1]), (rc[2], rc[3]), (255, 255, 0), 1)
    cv2.rectangle(image, (ro[0], ro[1]), (ro[2], ro[3]), (0, 0, 255), 2)
    return image


def draw_label_box(
    image: np.ndarray,
    bbox: Tuple[int, int, int, int],
    lines: List[str],
    font_scale: float = 0.6,
    text_color: Tuple[int, int, int] = (0, 0, 0),
    bg_color: Tuple[int, int, int] = (255, 255, 255),
    padding: int = 4,
) -> None:
    if not lines:
        return

    h_img, w_img = image.shape[:2]
    line_heights: List[int] = []
    line_widths: List[int] = []
    for line in lines:
        (tw, th), _ = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
        line_widths.append(tw)
        line_heights.append(th)

    box_w = max(line_widths) + padding * 2
    box_h = sum(line_heights) + padding * (len(lines) + 1)

    x1, y1, x2, y2 = bbox
    x = max(0, min(x1, w_img - box_w))
    y = y1 - box_h - 6
    if y < 0:
        y = y2 + 6
    if y + box_h > h_img:
        y = max(0, h_img - box_h)

    cv2.rectangle(image, (x, y), (x + box_w, y + box_h), bg_color, -1)

    cursor_y = y + padding + line_heights[0]
    for idx, line in enumerate(lines):
        cv2.putText(
            image,
            line,
            (x + padding, cursor_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            text_color,
            1,
        )
        if idx + 1 < len(line_heights):
            cursor_y += line_heights[idx + 1] + padding


def draw_label_corner(
    image: np.ndarray,
    lines: List[str],
    font_scale: float = 0.6,
    text_color: Tuple[int, int, int] = (0, 0, 0),
    bg_color: Tuple[int, int, int] = (255, 255, 255),
    padding: int = 4,
) -> None:
    if not lines:
        return

    h_img, w_img = image.shape[:2]
    line_heights: List[int] = []
    line_widths: List[int] = []
    for line in lines:
        (tw, th), _ = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
        line_widths.append(tw)
        line_heights.append(th)

    box_w = min(w_img, max(line_widths) + padding * 2)
    box_h = min(h_img, sum(line_heights) + padding * (len(lines) + 1))
    x, y = 4, 4

    cv2.rectangle(image, (x, y), (x + box_w, y + box_h), bg_color, -1)
    cursor_y = y + padding + line_heights[0]
    for idx, line in enumerate(lines):
        cv2.putText(
            image,
            line,
            (x + padding, cursor_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            text_color,
            1,
        )
        if idx + 1 < len(line_heights):
            cursor_y += line_heights[idx + 1] + padding


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Analyze and visualize known failure cases.")
    parser.add_argument("--targets", type=Path, help="JSON list: [{work,page,measure}, ...]")
    parser.add_argument("--target", action="append", default=[], help="Format: work:page:measure")
    parser.add_argument(
        "--all-pages", action="store_true", help="Process all pages found under numbering-root."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("logs/experiments/failure_analysis"),
    )
    parser.add_argument(
        "--numbering-root",
        type=Path,
        default=Path("logs/experiments/batch_verification_20260107_v5"),
    )
    parser.add_argument(
        "--image-root",
        type=Path,
        default=Path("data/evaluation2/images"),
    )
    parser.add_argument(
        "--mask-root",
        type=Path,
        default=Path("logs/hybrid_generalization"),
    )
    parser.add_argument("--vertical-margin-check", type=int, default=10)
    parser.add_argument("--vertical-margin-ocr", type=int, default=80)
    parser.add_argument("--horizontal-margin", type=int, default=10)
    parser.add_argument("--erode-iter", type=int, default=1)
    parser.add_argument("--center-offset-ratio", type=float, default=0.10)
    parser.add_argument("--density-threshold", type=int, default=150)
    parser.add_argument(
        "--overlay-all",
        action="store_true",
        help="Draw overlays for all measures (not only ROI candidates).",
    )
    parser.add_argument(
        "--number-roi",
        action="store_true",
        help="Add ROI index labels for easier reference.",
    )
    parser.add_argument(
        "--nearby", type=int, default=2, help="Also export neighbors within this range."
    )
    args = parser.parse_args()

    if not args.targets and not args.target and not args.all_pages:
        parser.error("Provide --targets or --target.")

    targets = (
        parse_targets(args.targets, args.target)
        if not args.all_pages
        else scan_pages(args.numbering_root)
    )
    ensure_dir(args.output_dir)

    ocr_engine = RapidOCR()

    report_rows: List[Dict] = []
    missing_rows: List[Dict] = []
    page_overlays: Dict[Tuple[str, str], np.ndarray] = {}

    pages: List[Target] = []
    seen_pages: set[Tuple[str, int]] = set()
    for target in targets:
        key = (target.work, target.page)
        if key in seen_pages:
            continue
        seen_pages.add(key)
        pages.append(target)

    for target in pages:
        page_str = f"page_{target.page:03d}"
        numbering_json, image_path, mask_path = build_paths(
            args.numbering_root, args.image_root, args.mask_root, target
        )
        if not numbering_json.exists():
            fallback = numbering_json.with_name("numbering_base.json")
            if fallback.exists():
                numbering_json = fallback

        if not numbering_json.exists():
            LOGGER.warning("Missing numbering JSON: %s", numbering_json)
            missing_rows.append(
                {
                    "work": target.work,
                    "page": target.page,
                    "measure": target.measure,
                    "reason": "missing_numbering_json",
                }
            )
            continue
        if not image_path.exists():
            LOGGER.warning("Missing image: %s", image_path)
            missing_rows.append(
                {
                    "work": target.work,
                    "page": target.page,
                    "measure": target.measure,
                    "reason": "missing_image",
                }
            )
            continue
        if not mask_path.exists():
            LOGGER.warning("Missing mask: %s", mask_path)
            missing_rows.append(
                {
                    "work": target.work,
                    "page": target.page,
                    "measure": target.measure,
                    "reason": "missing_mask",
                }
            )
            continue

        with numbering_json.open("r", encoding="utf-8") as f:
            data = json.load(f)

        image = cv2.imread(str(image_path))
        mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
        if image is None or mask is None:
            LOGGER.warning("Failed to load image/mask for %s %s", target.work, page_str)
            continue

        _, bin_mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
        if args.erode_iter > 0:
            kernel = np.ones((3, 3), np.uint8)
            proc_mask = cv2.erode(bin_mask, kernel, iterations=args.erode_iter)
        else:
            proc_mask = bin_mask

        h_img, w_img = image.shape[:2]
        h_mask, w_mask = proc_mask.shape[:2]
        scale_x = w_mask / w_img
        scale_y = h_mask / h_img

        page_key = (target.work, page_str)
        page_out_dir = args.output_dir / target.work / page_str
        ensure_dir(page_out_dir)
        if page_key not in page_overlays:
            page_overlays[page_key] = image.copy()

        found_any = False
        roi_index = 0
        for measure in iter_measures(data):
            m_num = measure.get("number")
            if m_num is None:
                continue

            found_any = True
            bbox = tuple(measure["bbox"])
            result = analyze_measure(
                measure=measure,
                image=image,
                mask=proc_mask,
                scale_x=scale_x,
                scale_y=scale_y,
                vertical_margin_check=args.vertical_margin_check,
                vertical_margin_ocr=args.vertical_margin_ocr,
                horizontal_margin=args.horizontal_margin,
                erode_iter=args.erode_iter,
                center_offset_ratio=args.center_offset_ratio,
                ocr_engine=ocr_engine,
            )

            ocr_texts = (
                [item["text"] for item in result["ocr_items"]] if result["ocr_items"] else []
            )
            ocr_text_label = " / ".join(ocr_texts) if ocr_texts else "-"
            rest_label = (
                str(result["extracted_number"]) if result["extracted_number"] is not None else "-"
            )
            roi_index += 1
            label_lines = []
            if args.number_roi:
                label_lines.append(f"ROI: {roi_index}")
            label_lines.extend([f"OCR: {ocr_text_label}", f"Rest: {rest_label}"])

            is_candidate = result["pixel_count"] <= args.density_threshold and result["has_hbar"]
            if args.overlay_all or is_candidate:
                context = page_overlays[page_key]
                draw_context_overlay(
                    image=context,
                    bbox=bbox,
                    roi_check=result["roi_check"],
                    roi_ocr=result["roi_ocr"],
                )
                draw_label_box(context, bbox, label_lines)

            x1, y1, x2, y2 = bbox
            pad = 200
            cx1 = max(0, x1 - pad)
            cy1 = max(0, y1 - pad)
            cx2 = min(image.shape[1], x2 + pad)
            cy2 = min(image.shape[0], y2 + pad)
            if is_candidate:
                context_crop = page_overlays[page_key][cy1:cy2, cx1:cx2].copy()

            roi_check = result["roi_check"]
            roi_ocr = result["roi_ocr"]
            roi_img_check = image[roi_check[1] : roi_check[3], roi_check[0] : roi_check[2]]
            roi_img_ocr = image[roi_ocr[1] : roi_ocr[3], roi_ocr[0] : roi_ocr[2]]

            mask_bbox = result["mask_bbox"]
            mask_crop = proc_mask[mask_bbox[1] : mask_bbox[3], mask_bbox[0] : mask_bbox[2]]

            prefix = f"{target.work}_{page_str}_M{m_num}"
            draw_label_corner(roi_img_check, label_lines)
            draw_label_corner(roi_img_ocr, label_lines)
            if is_candidate:
                cv2.imwrite(str(page_out_dir / f"{prefix}_context.png"), context_crop)
                cv2.imwrite(str(page_out_dir / f"{prefix}_hbar_roi.png"), roi_img_check)
                cv2.imwrite(str(page_out_dir / f"{prefix}_ocr_roi.png"), roi_img_ocr)
                cv2.imwrite(str(page_out_dir / f"{prefix}_mask.png"), mask_crop)

            report_rows.append(
                {
                    "work": target.work,
                    "page": target.page,
                    "target_measure": target.measure,
                    "matched_measure": m_num,
                    "pixel_count": result["pixel_count"],
                    "has_hbar": result["has_hbar"],
                    "hbar_pixels": result["hbar_pixels"],
                    "valid_texts": " | ".join(result["valid_texts"]),
                    "rejected_texts": " | ".join(result["rejected_texts"]),
                    "ocr_texts": " | ".join(ocr_texts),
                    "extracted_number": result["extracted_number"],
                    "ocr_items": result["ocr_items"],
                    "bbox": bbox,
                    "roi_check": result["roi_check"],
                    "roi_ocr": result["roi_ocr"],
                    "is_candidate": is_candidate,
                }
            )

        if not found_any:
            missing_rows.append(
                {
                    "work": target.work,
                    "page": target.page,
                    "measure": target.measure,
                    "reason": "no_measures_found",
                }
            )

    report_json = args.output_dir / "analysis_report.json"
    report_csv = args.output_dir / "analysis_report.csv"
    missing_json = args.output_dir / "analysis_missing.json"
    overlay_dir = args.output_dir / "page_overlays"
    ensure_dir(overlay_dir)

    for (work, page_str), overlay in page_overlays.items():
        out_path = overlay_dir / f"{work}_{page_str}_roi_overlay.png"
        cv2.imwrite(str(out_path), overlay)

    with report_json.open("w", encoding="utf-8") as f:
        json.dump(report_rows, f, ensure_ascii=True, indent=2)

    if report_rows:
        with report_csv.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "work",
                    "page",
                    "target_measure",
                    "matched_measure",
                    "pixel_count",
                    "has_hbar",
                    "hbar_pixels",
                    "ocr_texts",
                    "valid_texts",
                    "rejected_texts",
                    "extracted_number",
                    "bbox",
                    "roi_check",
                    "roi_ocr",
                    "is_candidate",
                ],
            )
            writer.writeheader()
            for row in report_rows:
                writer.writerow({k: row.get(k) for k in writer.fieldnames})

    with missing_json.open("w", encoding="utf-8") as f:
        json.dump(missing_rows, f, ensure_ascii=True, indent=2)

    LOGGER.info("Report written to %s", report_json)
    if missing_rows:
        LOGGER.info("Missing items written to %s", missing_json)


if __name__ == "__main__":
    main()
