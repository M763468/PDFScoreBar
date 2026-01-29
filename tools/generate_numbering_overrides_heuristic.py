import argparse
import json
import re
import sys
from pathlib import Path

import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def preprocess_image(img):
    """
    Apply preprocessing for OCR:
    - Grayscale
    - Otsu Thresholding
    - Inversion (to ensure Black text on White BG)
    - Denoising (Opening)
    - Padding
    """
    if img is None:
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    binary_white_bg = cv2.bitwise_not(binary)

    # Add dilation to thicken text
    kernel = np.ones((2, 2), np.uint8)
    dilated = cv2.dilate(binary_white_bg, kernel, iterations=1)

    padded = cv2.copyMakeBorder(dilated, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    return padded


def detect_hbar(roi_img):
    """
    Detect if the ROI contains a rectangular horizontal bar (H-bar) characteristic of multi-measure rests.
    Returns: (bool found, rect tuple (x,y,w,h))
    """
    if roi_img is None or roi_img.size == 0:
        return False, None

    gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    h, w = binary.shape
    if w < 20 or h < 10:
        return False, None

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best_rect = None

    # Staff center definitions
    v_center_min = h * 0.25
    v_center_max = h * 0.75

    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)

        cw / float(ch)
        cw / float(w)
        # print(f"    [DEBUG H-BAR CANDIDATE] AR={aspect:.2f}, WR={width_ratio:.2f} (w={cw}, h={ch})")

        # 1. Aspect Ratio Check (Horizontal Bar)
        aspect_ratio = cw / float(ch)
        if aspect_ratio < 2.5:  # Increased from 2.0 to filter blocky whole rests
            continue

        # 2. Area Check (Ignore speckles)
        if cw < w * 0.15:
            continue

        # 3. Vertical Centering Check
        cy = y + ch / 2
        if not (v_center_min <= cy <= v_center_max):
            continue

        best_rect = (x, y, cw, ch)
        break  # Found one

    return (best_rect is not None), best_rect


def extract_number_from_text(text):
    """
    Extract a valid multi-measure rest number from text.
    """
    if not text:
        return None

    # 1. Blacklist check
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
        "con",
        "senza",
    ]
    for word in blacklist:
        if word.lower() in text.lower():
            return None

    # 2. Extract all digit sequences
    numbers = re.findall(r"\d+", text)
    if not numbers:
        return None

    # 3. Pick best number
    valid_nums = []
    for n_str in numbers:
        try:
            val = int(n_str)
            if val >= 2:
                valid_nums.append(val)
        except Exception:
            pass

    if not valid_nums:
        return None

    # Return the largest valid number found
    return max(valid_nums)


def check_musical_elements(roi_img, roi_staff_mask, roi_notehead_mask, hbar_rect, text_boxes):
    """
    Check if the measure contains musical elements (notes, stems) that contradict a multi-measure rest.

    Returns: (bool has_elements, str reason, dict debug_masks)
    debug_masks contains 'noteheads', 'stems', 'exclusion' binary images for visualization.
    """
    debug_masks = {}
    if roi_img is None:
        return False, "No Image", {}

    h, w = roi_img.shape[:2]
    exclusion_mask = np.zeros((h, w), dtype=np.uint8)

    if hbar_rect:
        x, y, w_rect, h_rect = hbar_rect
        margin = 3
        cv2.rectangle(
            exclusion_mask,
            (max(0, x - margin), max(0, y - margin)),
            (min(w, x + w_rect + margin), min(h, y + h_rect + margin)),
            255,
            -1,
        )

    if text_boxes:
        for box in text_boxes:
            pts = np.array(box, dtype=np.int32)
            temp_mask = np.zeros((h, w), dtype=np.uint8)
            cv2.fillPoly(temp_mask, [pts], 255)
            # Increase dilation to ensure full number coverage (especially for thick fonts)
            kernel = np.ones((15, 15), np.uint8)
            temp_dilated = cv2.dilate(temp_mask, kernel, iterations=1)
            exclusion_mask = cv2.bitwise_or(exclusion_mask, temp_dilated)

    debug_masks["exclusion"] = exclusion_mask

    # --- Check 1: Notehead Mask ---
    notehead_pixels = 0
    if roi_notehead_mask is not None:
        if roi_notehead_mask.shape != (h, w):
            roi_notehead_mask = cv2.resize(roi_notehead_mask, (w, h))

        _, bin_notehead = cv2.threshold(roi_notehead_mask, 127, 255, cv2.THRESH_BINARY)

        # Denoise Notehead Mask (Remove small speckles)
        kernel_noise = np.ones((3, 3), np.uint8)
        bin_notehead = cv2.morphologyEx(bin_notehead, cv2.MORPH_OPEN, kernel_noise)

        valid_noteheads = cv2.bitwise_and(bin_notehead, cv2.bitwise_not(exclusion_mask))
        debug_masks["noteheads"] = valid_noteheads

        notehead_pixels = cv2.countNonZero(valid_noteheads)

    # --- Check 2: Vertical Stems ---
    gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    kernel_staff = np.ones((3, 3), np.uint8)
    if roi_staff_mask is not None:
        if roi_staff_mask.shape != (h, w):
            roi_staff_mask = cv2.resize(roi_staff_mask, (w, h))
        staff_dilated = cv2.dilate(roi_staff_mask, kernel_staff, iterations=1)
        ink_no_staff = cv2.bitwise_and(binary, cv2.bitwise_not(staff_dilated))
    else:
        ink_no_staff = binary.copy()

    ink_clean = cv2.bitwise_and(ink_no_staff, cv2.bitwise_not(exclusion_mask))

    margin_x = int(w * 0.1)
    cv2.rectangle(ink_clean, (0, 0), (margin_x, h), 0, -1)
    cv2.rectangle(ink_clean, (w - margin_x, 0), (w, h), 0, -1)

    k_height = max(10, int(h * 0.3))
    vert_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, k_height))
    detected_stems = cv2.morphologyEx(ink_clean, cv2.MORPH_OPEN, vert_kernel, iterations=1)

    debug_masks["stems"] = detected_stems
    stem_pixels = cv2.countNonZero(detected_stems)

    if notehead_pixels > 50:
        return True, f"Noteheads found: {notehead_pixels}px", debug_masks

    if stem_pixels > 20:
        return True, f"Stems found: {stem_pixels}px", debug_masks

    return False, "Clean", debug_masks


def draw_debug_info(debug_img, x1, y1, x2, y2, status, text="", details=""):
    """
    Draw rectangle and text on debug image.
    Status: 'found' (Green), 'rejected' (Red), 'skip' (Yellow)
    """
    if debug_img is None:
        return

    color = (0, 0, 255)  # Red default
    if status == "found":
        color = (0, 255, 0)  # Green
    elif status == "skip":
        color = (0, 255, 255)  # Yellow

    cv2.rectangle(debug_img, (x1, y1), (x2, y2), color, 2)

    label = f"{text}"
    if details:
        label += f" ({details})"

    cv2.putText(debug_img, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)


def visualize_masks(debug_img, roi_rect, masks):
    """
    Overlay mask visualizations on the debug image.
    roi_rect: (x, y, w, h) absolute coordinates
    masks: dict from check_musical_elements
    """
    if debug_img is None or not masks:
        return

    x, y, w, h = roi_rect

    # Slice of debug image
    # Note: Ensure bounds
    roi_slice = debug_img[y : y + h, x : x + w]
    if roi_slice.shape[:2] != (h, w):
        return  # Safety check

    # 1. Exclusion (Gray)
    if "exclusion" in masks:
        mask = masks["exclusion"]
        # Blend gray
        # Need 3-channel mask
        colored_mask = np.zeros_like(roi_slice)
        colored_mask[mask == 255] = [128, 128, 128]
        # Additive blend
        # roi_slice = cv2.addWeighted(roi_slice, 0.7, colored_mask, 0.3, 0)
        # Simple pixel replacement for visibility or overlay
        # Let's just draw outlines or weak fill
        roi_slice[mask == 255] = roi_slice[mask == 255] * 0.5 + np.array([128, 128, 128]) * 0.5

    # 2. Noteheads (Blue)
    if "noteheads" in masks:
        mask = masks["noteheads"]
        # Set Blue channel to 255, others reduced
        # roi_slice[mask == 255] = [255, 0, 0] # Solid Blue
        # Or blend
        roi_slice[mask == 255] = roi_slice[mask == 255] * 0.3 + np.array([255, 0, 0]) * 0.7

    # 3. Stems (Magenta)
    if "stems" in masks:
        mask = masks["stems"]
        # Magenta: B=255, G=0, R=255
        roi_slice[mask == 255] = roi_slice[mask == 255] * 0.3 + np.array([255, 0, 255]) * 0.7

    debug_img[y : y + h, x : x + w] = roi_slice


def main():
    parser = argparse.ArgumentParser(
        description="Generate numbering overrides from multi-measure rest OCR."
    )
    parser.add_argument("--numbering-json", type=Path, required=True, help="Path to numbering JSON")
    parser.add_argument(
        "--notehead-mask", type=Path, required=True, help="Path to notehead mask PNG"
    )
    parser.add_argument(
        "--staff-mask",
        type=Path,
        required=False,
        help="Path to staff mask PNG (Optional but recommended)",
    )
    parser.add_argument("--image", type=Path, required=True, help="Path to original image")
    parser.add_argument(
        "--output-overrides", type=Path, required=True, help="Path to save overrides JSON"
    )
    parser.add_argument(
        "--debug-image", type=Path, default=None, help="Path to save debug overlay image"
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=150,
        help="Max pixels of notehead to consider 'empty' (Legacy)",
    )
    parser.add_argument(
        "--vertical-margin-check",
        type=int,
        default=10,
        help="Vertical margin for Density/H-Bar check",
    )
    parser.add_argument(
        "--vertical-margin-ocr", type=int, default=80, help="Vertical margin for OCR"
    )
    parser.add_argument("--erode-iter", type=int, default=1, help="Iterations of erosion")

    args = parser.parse_args()

    # Initialize OCR
    ocr_engine = RapidOCR()

    # Load data
    with open(args.numbering_json, "r") as f:
        data = json.load(f)

    mask = cv2.imread(str(args.notehead_mask), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        print(f"Error: Could not read mask: {args.notehead_mask}")
        sys.exit(1)

    staff_mask = None
    if args.staff_mask:
        staff_mask = cv2.imread(str(args.staff_mask), cv2.IMREAD_GRAYSCALE)
        if staff_mask is not None:
            _, staff_mask = cv2.threshold(staff_mask, 127, 255, cv2.THRESH_BINARY)

    image = cv2.imread(str(args.image))
    if image is None:
        print(f"Error: Could not read image: {args.image}")
        sys.exit(1)

    debug_img = None
    if args.debug_image:
        debug_img = image.copy()

    h_img, w_img = image.shape[:2]
    h_mask, w_mask = mask.shape[:2]
    scale_x = w_mask / w_img
    scale_y = h_mask / h_img

    # Mask Preprocessing
    _, bin_mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
    if args.erode_iter > 0:
        kernel = np.ones((3, 3), np.uint8)
        cv2.erode(bin_mask, kernel, iterations=args.erode_iter)
    else:
        pass

    overrides = []

    print("Scanning measures for multi-measure rests...")

    for page in data["pages"]:
        page_num = page["page_number"]
        for sys_idx, system in enumerate(page["systems"]):
            for m_idx, measure in enumerate(system["measures"]):
                m_num = measure["number"]
                bbox = measure["bbox"]

                x1, y1, x2, y2 = bbox

                # 2. H-Bar Check (Strict Margin)
                roi_x1 = max(0, x1 - 10)
                roi_x2 = min(w_img, x2 + 10)

                roi_y1_check = max(0, y1 - args.vertical_margin_check)
                roi_y2_check = min(h_img, y2 + args.vertical_margin_check)

                roi_img_check = image[roi_y1_check:roi_y2_check, roi_x1:roi_x2]

                if roi_img_check.size == 0:
                    continue

                # Refined H-Bar Check
                is_hbar, hbar_rect = detect_hbar(roi_img_check)
                if not is_hbar:
                    # draw_debug_info(debug_img, x1, y1, x2, y2, 'skip', details="No H-Bar")
                    continue
                else:
                    hx, hy, hw, hh = hbar_rect
                    print(
                        f"  [INFO] P{page_num} S{sys_idx} M{m_num}: H-Bar Found: w={hw}, h={hh}, AR={hw / hh:.2f}"
                    )

                # 3. OCR (Relaxed Margin)
                roi_y1_ocr = max(0, y1 - args.vertical_margin_ocr)
                roi_y2_ocr = min(h_img, y2 + args.vertical_margin_check)

                roi_img_ocr = image[roi_y1_ocr:roi_y2_ocr, roi_x1:roi_x2]

                # Preprocess and OCR
                proc_img = preprocess_image(roi_img_ocr)
                try:
                    ocr_result, _ = ocr_engine(proc_img)
                    if ocr_result:
                        # Spatial Filtering & Text Aggregation
                        roi_w = proc_img.shape[1]
                        center_x = roi_w / 2
                        valid_texts = []
                        valid_boxes_relative_to_ocr_roi = []

                        for res in ocr_result:
                            box = res[0]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                            text = res[1]
                            score = res[2]

                            # Calculate text center relative to ROI
                            xs = [p[0] for p in box]
                            ys = [p[1] for p in box]
                            text_center_x = sum(xs) / len(xs)

                            # Calculate absolute coordinates for debug drawing
                            abs_x1 = roi_x1 + int(min(xs))
                            abs_y1 = roi_y1_ocr + int(min(ys))
                            abs_x2 = roi_x1 + int(max(xs))
                            abs_y2 = roi_y1_ocr + int(max(ys))

                            # 0. Score Filter
                            if score < 0.6:
                                print(f"    [REJECT] '{text}': Low Score ({score:.2f})")
                                draw_debug_info(
                                    debug_img,
                                    abs_x1,
                                    abs_y1,
                                    abs_x2,
                                    abs_y2,
                                    "rejected",
                                    text,
                                    f"Score:{score:.2f}",
                                )
                                continue

                            # Spatial Filter:
                            is_left_edge = text_center_x < (roi_w * 0.15)
                            is_right_edge = text_center_x > (roi_w * 0.85)
                            dist = abs(text_center_x - center_x)
                            is_centered = dist < (roi_w * 0.15)

                            if is_left_edge or is_right_edge:
                                print(
                                    f"    [REJECT] '{text}': Edge (x={text_center_x:.1f}, w={roi_w})"
                                )
                                draw_debug_info(
                                    debug_img,
                                    abs_x1,
                                    abs_y1,
                                    abs_x2,
                                    abs_y2,
                                    "rejected",
                                    text,
                                    "Edge",
                                )
                                continue

                            if not is_centered:
                                print(
                                    f"    [REJECT] '{text}': Not Centered (dist={dist:.1f}, limit={roi_w * 0.15:.1f})"
                                )
                                draw_debug_info(
                                    debug_img,
                                    abs_x1,
                                    abs_y1,
                                    abs_x2,
                                    abs_y2,
                                    "rejected",
                                    text,
                                    "Not Centered",
                                )
                                continue

                            # Passed filters
                            valid_texts.append(text)
                            valid_boxes_relative_to_ocr_roi.append(box)

                        if valid_texts:
                            full_text = " ".join(valid_texts)
                            number = extract_number_from_text(full_text)

                            if number:
                                # 4. MUSICAL ELEMENTS CHECK (New Strategy)

                                roi_staff_mask_full = None
                                if staff_mask is not None:
                                    # Scale coordinates to mask space
                                    sy1 = int(max(0, roi_y1_ocr) * scale_y)
                                    sy2 = int(min(h_img, roi_y2_ocr) * scale_y)
                                    sx1 = int(max(0, roi_x1) * scale_x)
                                    sx2 = int(min(w_img, roi_x2) * scale_x)

                                    # Clamp to mask dimensions
                                    sy2 = min(staff_mask.shape[0], sy2)
                                    sx2 = min(staff_mask.shape[1], sx2)

                                    if sy2 > sy1 and sx2 > sx1:
                                        roi_staff_mask_full = staff_mask[sy1:sy2, sx1:sx2]

                                roi_notehead_mask_full = None
                                if mask is not None:
                                    # Scale coordinates to mask space
                                    sy1 = int(max(0, roi_y1_ocr) * scale_y)
                                    sy2 = int(min(h_img, roi_y2_ocr) * scale_y)
                                    sx1 = int(max(0, roi_x1) * scale_x)
                                    sx2 = int(min(w_img, roi_x2) * scale_x)

                                    # Clamp to mask dimensions
                                    sy2 = min(mask.shape[0], sy2)
                                    sx2 = min(mask.shape[1], sx2)

                                    if sy2 > sy1 and sx2 > sx1:
                                        roi_notehead_mask_full = mask[sy1:sy2, sx1:sx2]

                                offset_y = roi_y1_check - roi_y1_ocr
                                hx, hy, hw, hh = hbar_rect
                                adjusted_hbar = (hx, hy + offset_y, hw, hh)

                                has_elements, reason, debug_masks = check_musical_elements(
                                    roi_img_ocr,
                                    roi_staff_mask_full,
                                    roi_notehead_mask_full,
                                    adjusted_hbar,
                                    valid_boxes_relative_to_ocr_roi,
                                )

                                # Visualize
                                if debug_img is not None:
                                    # Use original OCR ROI dimensions, not processed image dims
                                    roi_h_ocr, roi_w_ocr = roi_img_ocr.shape[:2]
                                    roi_rect_abs = (roi_x1, roi_y1_ocr, roi_w_ocr, roi_h_ocr)
                                    visualize_masks(debug_img, roi_rect_abs, debug_masks)

                                if has_elements:
                                    print(
                                        f"  [REJECT] P{page_num} S{sys_idx} M{m_num}: Text='{full_text}' -> Musical Elements Found: {reason}"
                                    )
                                    draw_debug_info(
                                        debug_img, x1, y1, x2, y2, "rejected", f"{number}", reason
                                    )
                                else:
                                    print(
                                        f"  [FOUND] P{page_num} S{sys_idx} M{m_num}: Text='{full_text}' -> Count={number}"
                                    )

                                    overrides.append(
                                        {
                                            "page": page_num - 1,
                                            "system": sys_idx,
                                            "measure": m_idx,
                                            "skip": number - 1,
                                            "comment": f"Auto-detected multi-measure rest: {number}",
                                        }
                                    )
                                    draw_debug_info(
                                        debug_img, x1, y1, x2, y2, "found", f"Rest: {number}"
                                    )
                            else:
                                print(
                                    f"  [SKIP]  P{page_num} S{sys_idx} M{m_num}: Text='{full_text}' (Not a number)"
                                )
                                draw_debug_info(
                                    debug_img, x1, y1, x2, y2, "skip", f"NaN: {full_text}"
                                )

                except Exception as e:
                    print(f"  [ERROR] P{page_num} S{sys_idx} M{m_num}: {e}")
                    import traceback

                    traceback.print_exc()

    # Output JSON
    output_data = {"measure_overrides": overrides}
    with open(args.output_overrides, "w") as f:
        json.dump(output_data, f, indent=2)
    print(f"Saved {len(overrides)} overrides to {args.output_overrides}")

    # Output Image
    if args.debug_image and debug_img is not None:
        cv2.imwrite(str(args.debug_image), debug_img)
        print(f"Saved debug image to {args.debug_image}")


if __name__ == "__main__":
    main()
