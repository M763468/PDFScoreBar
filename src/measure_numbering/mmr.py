import logging
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from rapidocr_onnxruntime import RapidOCR
from torchvision import models, transforms

logger = logging.getLogger(__name__)

# --- Preprocessing for Model ---
# Must match training transforms (val)
MODEL_TRANSFORM = transforms.Compose(
    [
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ]
)


class MMRClassifier:
    """Handles CNN inference for Multi-Measure Rest (MMR) detection."""

    def __init__(self, model_path: Path, device: torch.device, model: Optional[nn.Module] = None):
        self.device = device
        self.transform = MODEL_TRANSFORM
        if model is not None:
            self.model = model
        else:
            self.model = self._load_model(model_path)

    def _load_model(self, model_path: Path) -> nn.Module:
        model = models.resnet18(weights=None)
        model.fc = nn.Linear(model.fc.in_features, 1)

        try:
            state_dict = torch.load(model_path, map_location=self.device, weights_only=True)
            # Handle torch.compile prefix (e.g. from Issue #44 models)
            if any(k.startswith("_orig_mod.") for k in state_dict.keys()):
                state_dict = {k.replace("_orig_mod.", ""): v for k, v in state_dict.items()}
            model.load_state_dict(state_dict)
        except Exception as e:
            logger.error(f"Error loading MMR model from {model_path}: {e}")
            raise

        model = model.to(self.device)
        model.eval()
        return model

    def predict(self, cv2_img: np.ndarray) -> float:
        """Returns probability of being a Rest (Label 1)."""
        if cv2_img is None or cv2_img.size == 0:
            return 0.0

        img_rgb = cv2.cvtColor(cv2_img, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(img_rgb)

        input_tensor = self.transform(pil_img).unsqueeze(0).to(self.device)

        with torch.no_grad():
            output = self.model(input_tensor)
            prob = torch.sigmoid(output).item()

        return prob


class MMROCREngine:
    """Handles RapidOCR and post-processing for MMR number detection."""

    def __init__(self, enable_rotation_tta: bool = False, ocr_engine: Optional[RapidOCR] = None):
        if ocr_engine is not None:
            self.ocr_engine = ocr_engine
        else:
            self.ocr_engine = RapidOCR()
        self.enable_rotation_tta = enable_rotation_tta
        self.blacklist = [
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
            "Allegro",
            "Adagio",
            "Andante",
            "Lento",
            "Presto",
            "Moderato",
        ]

    def mask_hbar_candidates(
        self, img: np.ndarray, staff_top_rel: float, staff_height: float
    ) -> np.ndarray:
        if img is None:
            return img

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        v_erode_kernel = np.ones((4, 1), np.uint8)
        thick_objects = cv2.erode(binary, v_erode_kernel, iterations=1)
        thick_objects = cv2.dilate(thick_objects, v_erode_kernel, iterations=1)

        contours, _ = cv2.findContours(thick_objects, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        masked_img = img.copy()
        staff_center = staff_top_rel + staff_height / 2.0

        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            cy = y + h / 2.0
            dist_center = abs(cy - staff_center)

            if w > 40 and h > 4 and dist_center < 40:
                pad = 5
                cv2.rectangle(
                    masked_img,
                    (max(0, x - pad), max(0, y - pad)),
                    (min(img.shape[1], x + w + pad), min(img.shape[0], y + h + pad)),
                    (255, 255, 255),
                    -1,
                )
        return masked_img

    def rotate_image(self, image: np.ndarray, angle: float) -> np.ndarray:
        if angle == 0:
            return image
        (h, w) = image.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        return cv2.warpAffine(
            image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
        )

    def preprocess_variant(
        self, img: np.ndarray, mode: str = "standard", angle: float = 0
    ) -> Optional[np.ndarray]:
        if img is None:
            return None
        if angle != 0:
            img = self.rotate_image(img, angle)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        binary_white_bg = cv2.bitwise_not(binary)

        if mode == "no_dilate":
            final = binary_white_bg
        elif mode == "heavy_dilate":
            kernel = np.ones((3, 3), np.uint8)
            final = cv2.dilate(binary_white_bg, kernel, iterations=1)
        else:
            kernel = np.ones((2, 2), np.uint8)
            final = cv2.dilate(binary_white_bg, kernel, iterations=1)

        return cv2.copyMakeBorder(final, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)

    def merge_ocr_results(self, ocr_result: List) -> List:
        if not ocr_result or len(ocr_result) < 2:
            return ocr_result

        ocr_result.sort(key=lambda x: min([p[0] for p in x[0]]))
        merged = []
        current_box = ocr_result[0]

        for next_box in ocr_result[1:]:
            c_pts, c_txt, c_conf = current_box
            c_xs = [p[0] for p in c_pts]
            c_ys = [p[1] for p in c_pts]
            c_x2, c_y1, c_y2 = max(c_xs), min(c_ys), max(c_ys)
            c_h = c_y2 - c_y1

            n_pts, n_txt, n_conf = next_box
            n_xs = [p[0] for p in n_pts]
            n_ys = [p[1] for p in n_pts]
            n_x1, n_y1, n_y2 = min(n_xs), min(n_ys), max(n_ys)
            n_h = n_y2 - n_y1

            c_cy = (c_y1 + c_y2) / 2
            n_cy = (n_y1 + n_y2) / 2
            min_h = min(c_h, n_h)

            vertical_diff = abs(c_cy - n_cy)
            vertical_aligned_loose = vertical_diff < (min_h * 0.5)
            vertical_aligned_strict = vertical_diff < (min_h * 0.2)

            gap = n_x1 - c_x2
            digit_pat = r"^[\dIl|!i\]\[]$"
            is_potential_split = bool(
                re.match(digit_pat, c_txt.strip()) and re.match(digit_pat, n_txt.strip())
            )

            gap_threshold = min_h * 0.3
            if is_potential_split:
                if vertical_aligned_strict:
                    gap_threshold = min_h * 1.5
                elif vertical_aligned_loose:
                    gap_threshold = min_h * 0.8

            horizontal_close = gap < gap_threshold
            height_diff = abs(c_h - n_h) / max(c_h, n_h)
            height_similar = height_diff < (0.4 if is_potential_split else 0.25)
            is_digit_pattern = bool(re.match(r"^\d+$", c_txt + n_txt))

            if vertical_aligned_loose and horizontal_close and height_similar and is_digit_pattern:
                mx1, my1 = min(c_xs + n_xs), min(c_ys + n_ys)
                mx2, my2 = max(c_xs + n_xs), max(c_ys + n_ys)
                new_pts = [[mx1, my1], [mx2, my1], [mx2, my2], [mx1, my2]]
                current_box = [new_pts, c_txt + n_txt, (c_conf + n_conf) / 2]
            else:
                merged.append(current_box)
                current_box = next_box

        merged.append(current_box)
        return merged

    def _has_blacklisted_text(self, text: str) -> bool:
        return any(b.lower() in text.lower() for b in self.blacklist)

    def _candidate_items(self, ocr_result: List) -> List[Tuple[List, str]]:
        """Return raw and merged OCR items so merges do not erase valid single digits."""
        raw_items = [(item, "raw") for item in ocr_result]
        merged_results = self.merge_ocr_results(list(ocr_result))
        merged_items = [(item, "merged") for item in merged_results if item not in ocr_result]
        return raw_items + merged_items

    def _extract_numeric_candidates(self, text: str, blacklisted: bool) -> List[str]:
        if blacklisted:
            return re.findall(r"(?<![A-Za-z])\d+(?![A-Za-z])", text)
        return re.findall(r"\d+", text)

    def select_best_candidate(
        self, ocr_result: List, img_width: int, img_height: int
    ) -> Tuple[Optional[int], float, str]:
        if not ocr_result:
            return None, 0, ""

        candidates = []
        center_x = img_width / 2.0

        for item, source in self._candidate_items(ocr_result):
            box_points, text, _ = item
            clean_text = re.sub(r"^[EP](\d)", r"\1", text)
            clean_text = re.sub(r"[.,;]", "", clean_text)
            blacklisted = self._has_blacklisted_text(text)
            nums_found = self._extract_numeric_candidates(clean_text, blacklisted)
            if not nums_found:
                continue

            xs, ys = [p[0] for p in box_points], [p[1] for p in box_points]
            x_min, x_max, y_min, y_max = min(xs), max(xs), min(ys), max(ys)
            box_h = y_max - y_min
            box_center_x, box_center_y = (x_min + x_max) / 2.0, (y_min + y_max) / 2.0

            dist_x_norm = abs(box_center_x - center_x) / img_width
            dist_y_norm = abs(box_center_y - (img_height / 2.0)) / img_height
            h_ratio = box_h / img_height

            for n_str in nums_found:
                try:
                    val = int(n_str)
                    if val < 2:
                        continue
                    score = 100 - dist_x_norm * 200 - dist_y_norm * 100
                    if 0.4 <= h_ratio <= 0.95:
                        score += 20
                    elif h_ratio < 0.3:
                        score -= 30
                    if "=" in text:
                        parts = text.split("=")
                        if len(parts) > 1 and n_str in parts[1]:
                            score -= 80
                    if val > 100:
                        score -= 50
                    if val > 20 and img_width < 100:
                        score -= 200

                    debug_flags = [
                        f"dx={dist_x_norm:.2f}",
                        f"dy={dist_y_norm:.2f}",
                        f"h={h_ratio:.2f}",
                        source,
                    ]
                    if blacklisted:
                        debug_flags.append("blacklist_digit")

                    candidates.append(
                        {
                            "val": val,
                            "score": score,
                            "debug": ",".join(debug_flags),
                        }
                    )
                except ValueError:
                    pass
        if not candidates:
            return None, 0, ""
        candidates.sort(key=lambda x: x["score"], reverse=True)
        best = candidates[0]
        return best["val"], best["score"], best["debug"]


class MMRProcessor:
    """Integrated processor for batch MMR detection."""

    def __init__(
        self,
        model_path: Path,
        device: torch.device,
        enable_rotation_tta: bool = False,
        threshold: float = 0.5,
        rescue_threshold: float = 0.1,
        classifier: Optional[MMRClassifier] = None,
        ocr_engine: Optional[MMROCREngine] = None,
    ):
        if classifier is not None:
            self.classifier = classifier
        else:
            self.classifier = MMRClassifier(model_path, device)

        if ocr_engine is not None:
            self.ocr = ocr_engine
        else:
            self.ocr = MMROCREngine(enable_rotation_tta=enable_rotation_tta)

        self.threshold = threshold
        self.rescue_threshold = rescue_threshold

    def process_pages(
        self,
        pages_data: List[Dict],
        image_paths: List[Path],
        debug_root: Optional[Path] = None,
    ) -> List[Dict[str, List[Dict]]]:
        """
        Process multiple pages and return measure overrides for each.
        Returns a list of dictionaries, one per page, containing 'measure_overrides'.
        """
        results = []
        for page_data, img_path in zip(pages_data, image_paths):
            image = cv2.imread(str(img_path))
            if image is None:
                logger.error(f"Could not read image: {img_path}")
                results.append({"measure_overrides": []})
                continue

            h_img, w_img = image.shape[:2]
            overrides = []
            page_num = page_data.get("pages", [{}])[0].get("page_number", 1)

            debug_img = None
            if debug_root:
                debug_img = image.copy()

            for page_entry in page_data.get("pages", []):
                for sys_idx, system in enumerate(page_entry.get("systems", [])):
                    for m_idx, measure in enumerate(system.get("measures", [])):
                        x1, y1, x2, y2 = measure["bbox"]
                        margin = 20
                        cx1, cy1 = int(max(0, x1 - margin)), int(max(0, y1 - margin))
                        cx2, cy2 = int(min(w_img, x2 + margin)), int(min(h_img, y2 + margin))
                        crop = image[cy1:cy2, cx1:cx2]

                        prob = self.classifier.predict(crop)
                        if prob > self.rescue_threshold:
                            found_num, final_score, final_debug = self._detect_number(
                                image, system, x1, y1, x2, y2, prob, w_img, h_img
                            )

                            is_valid = False
                            status_label = ""
                            if found_num:
                                if prob > self.threshold:
                                    is_valid, status_label = True, "found"
                                elif final_score > 60:
                                    is_valid, status_label = True, "rescue"

                            if is_valid:
                                logger.info(
                                    f"  [{status_label.upper()}] P{page_num} S{sys_idx} M{measure['number']}: Prob={prob:.2f} -> OCR={found_num}"
                                )
                                overrides.append(
                                    {
                                        "page": page_num - 1,
                                        "system": sys_idx,
                                        "measure": m_idx,
                                        "skip": found_num - 1,
                                        "comment": f"CNN({prob:.2f})+OCR({final_score:.1f}): {found_num}",
                                    }
                                )
                                if debug_img is not None:
                                    self._draw_debug(
                                        debug_img,
                                        x1,
                                        y1,
                                        x2,
                                        y2,
                                        status_label,
                                        f"R{found_num}",
                                        f"P{prob:.2f}",
                                    )
                            elif prob > self.threshold:
                                if debug_img is not None:
                                    self._draw_debug(
                                        debug_img, x1, y1, x2, y2, "skip", "CNN-only", f"{prob:.2f}"
                                    )

            if debug_img is not None and debug_root:
                debug_path = debug_root / f"page_{page_num:03d}_mmr_debug.png"
                cv2.imwrite(str(debug_path), debug_img)

            results.append({"measure_overrides": overrides})

        return results

    def _detect_number(self, image, system, x1, y1, x2, y2, prob, w_img, h_img):
        variants = [("standard", 0)]
        if prob > self.threshold:
            variants = [("standard", 0), ("no_dilate", 0), ("heavy_dilate", 0)]
            if self.ocr.enable_rotation_tta:
                variants.extend(
                    [("standard", -2), ("standard", 2), ("heavy_dilate", -2), ("heavy_dilate", 2)]
                )

        variant_results = []

        for mode, angle in variants:
            stave_results = []
            for stave in system.get("staves", []):
                s_bbox = stave["bbox"]
                margin_y = 80
                ox1, ox2 = int(max(0, x1 - 30)), int(min(w_img, x2 + 30))
                oy1, oy2 = int(max(0, s_bbox[1] - margin_y)), int(min(h_img, s_bbox[3] + 80))
                stave_crop = image[oy1:oy2, ox1:ox2]
                stave_crop = self.ocr.mask_hbar_candidates(
                    stave_crop, margin_y, s_bbox[3] - s_bbox[1]
                )

                proc_img = self.ocr.preprocess_variant(stave_crop, mode=mode, angle=angle)
                if proc_img is None:
                    continue

                ocr_res, _ = self.ocr.ocr_engine(proc_img)
                num, score, dbg = self.ocr.select_best_candidate(ocr_res, ox2 - ox1, oy2 - oy1)
                stave_results.append((num, score, dbg))

            valid_results = [r for r in stave_results if r[0] is not None]
            if valid_results:
                counts = Counter([r[0] for r in valid_results])
                current_num = counts.most_common(1)[0][0]

                if not (current_num > 20 and (x2 - x1) < 100):
                    _, best_score, best_dbg = max(
                        [r for r in valid_results if r[0] == current_num], key=lambda x: x[1]
                    )
                    if best_dbg:
                        variant_debug = f"{best_dbg},variant={mode}:{angle}"
                    else:
                        variant_debug = f"variant={mode}:{angle}"
                    variant_results.append((current_num, best_score, variant_debug))

        if not variant_results:
            return None, 0, ""

        found_number, best_score, best_debug = max(variant_results, key=lambda x: x[1])
        return found_number, best_score, best_debug

    def _draw_debug(self, img, x1, y1, x2, y2, status, text, details):
        colors = {"found": (0, 255, 0), "rescue": (0, 165, 255), "skip": (0, 255, 255)}
        color = colors.get(status, (0, 0, 255))
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        label = f"{text} ({details})" if details else text
        cv2.putText(img, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
