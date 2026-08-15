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

    def collect_one_bar_evidence(self, ocr_result: List) -> List[Dict]:
        """Return OCR evidence for printed one-bar rest markers.

        MMR overrides represent multi-measure rests only. A strong printed
        "1" should not become skip=0; it is used as veto evidence instead.

        Raw "1" OCR boxes that are part of a merged multi-digit candidate
        are excluded so true 10-19 MMR counts do not become veto evidence.
        """
        if not ocr_result:
            return []

        def _bounds(item: List) -> Tuple[float, float, float, float]:
            points = item[0]
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            return min(xs), min(ys), max(xs), max(ys)

        def _contains(
            outer: Tuple[float, float, float, float],
            inner: Tuple[float, float, float, float],
        ) -> bool:
            ox1, oy1, ox2, oy2 = outer
            ix1, iy1, ix2, iy2 = inner
            return ox1 <= ix1 and oy1 <= iy1 and ix2 <= ox2 and iy2 <= oy2

        def _has_multidigit_candidate(item: List) -> bool:
            _box_points, text, _confidence = item
            clean_text = re.sub(r"^[EP](\d)", r"\1", text)
            clean_text = re.sub(r"[.,;]", "", clean_text)
            blacklisted = self._has_blacklisted_text(text)
            for n_str in self._extract_numeric_candidates(clean_text, blacklisted):
                try:
                    if int(n_str) >= 2:
                        return True
                except (TypeError, ValueError):
                    pass
            return False

        candidate_items = self._candidate_items(ocr_result)
        merged_multidigit_bounds = [
            _bounds(item)
            for item, source in candidate_items
            if source == "merged" and _has_multidigit_candidate(item)
        ]

        evidence = []
        for item, source in candidate_items:
            _box_points, text, confidence = item
            if source == "raw" and any(
                _contains(bounds, _bounds(item)) for bounds in merged_multidigit_bounds
            ):
                continue

            clean_text = re.sub(r"^[EP](\d)", r"\1", text)
            clean_text = re.sub(r"[.,;]", "", clean_text)
            blacklisted = self._has_blacklisted_text(text)
            nums_found = self._extract_numeric_candidates(clean_text, blacklisted)
            for n_str in nums_found:
                try:
                    val = int(n_str)
                    conf = float(confidence)
                except (TypeError, ValueError):
                    continue
                if val == 1:
                    evidence.append({"text": text, "confidence": conf, "source": source})
        return evidence

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

    ONE_BAR_VETO_PROB_MAX = 0.60
    ONE_BAR_VETO_SCORE_MAX = 0.0
    ONE_BAR_VETO_MIN_EVIDENCE = 2
    ONE_BAR_VETO_MIN_CONFIDENCE = 0.80
    UNMASKED_FALLBACK_MIN_SCORE = 0.0

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
        self.support_stats = {"phase_a_ocr_fallback": 0, "alternate_veto_suppression": 0}
        # Runtime-only progress state.  This is deliberately separate from
        # the MMR decision data so callers can record a useful failure report.
        self.current_page_id: Optional[str] = None
        self.last_completed_page_id: Optional[str] = None

    def _count_high_confidence_one_bar_evidence(self, ocr_result: List) -> int:
        collector = getattr(self.ocr, "collect_one_bar_evidence", None)
        if collector is None:
            return 0

        count = 0
        for evidence in collector(ocr_result):
            try:
                confidence = float(evidence["confidence"])
            except (KeyError, TypeError, ValueError):
                continue
            if confidence >= self.ONE_BAR_VETO_MIN_CONFIDENCE:
                count += 1
        return count

    def _should_veto_one_bar_rest(
        self,
        found_num: Optional[int],
        prob: float,
        final_score: float,
        one_bar_evidence_count: int,
    ) -> bool:
        return bool(
            found_num
            and self.threshold < prob < self.ONE_BAR_VETO_PROB_MAX
            and final_score < self.ONE_BAR_VETO_SCORE_MAX
            and one_bar_evidence_count >= self.ONE_BAR_VETO_MIN_EVIDENCE
        )

    def process_pages(
        self,
        pages_data: List[Dict],
        image_paths: List[Path],
        debug_root: Optional[Path] = None,
        support_data: Optional[List[Optional[Dict]]] = None,
    ) -> List[Dict[str, List[Dict]]]:
        """
        Process multiple pages and return measure overrides for each.
        Returns a list of dictionaries, one per page, containing 'measure_overrides'.
        """
        results = []
        if support_data is not None and len(support_data) != len(pages_data):
            raise ValueError("support_data must have one entry for each MMR page")
        for page_index, (page_data, img_path) in enumerate(zip(pages_data, image_paths)):
            page_num = page_data.get("pages", [{}])[0].get("page_number", page_index + 1)
            page_id = f"page_{int(page_num):03d}"
            self.current_page_id = page_id
            print(f"MMR page start: {page_id}", flush=True)
            image = cv2.imread(str(img_path))
            if image is None:
                logger.error(f"Could not read image: {img_path}")
                results.append({"measure_overrides": []})
                self.last_completed_page_id = page_id
                print(f"MMR page complete: {page_id}", flush=True)
                continue

            h_img, w_img = image.shape[:2]
            overrides = []
            debug_img = None
            if debug_root:
                debug_img = image.copy()

            support = support_data[page_index] if support_data is not None else None
            if support is not None:
                overrides = self._process_page_with_support(
                    page_data=page_data,
                    support=support,
                    image=image,
                    page_num=page_num,
                    image_width=w_img,
                    image_height=h_img,
                    debug_img=debug_img,
                )
                if debug_img is not None and debug_root:
                    debug_path = debug_root / f"page_{page_num:03d}_mmr_debug.png"
                    cv2.imwrite(str(debug_path), debug_img)
                results.append({"measure_overrides": overrides})
                self.last_completed_page_id = page_id
                print(f"MMR page complete: {page_id}", flush=True)
                continue

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
                            found_num, final_score, final_debug, one_bar_evidence_count = (
                                self._detect_number_with_evidence(
                                    image, system, x1, y1, x2, y2, prob, w_img, h_img
                                )
                            )

                            is_valid = False
                            status_label = ""
                            one_bar_vetoed = False
                            if found_num:
                                one_bar_vetoed = self._should_veto_one_bar_rest(
                                    found_num,
                                    prob,
                                    final_score,
                                    one_bar_evidence_count,
                                )
                                if one_bar_vetoed:
                                    status_label = "one_bar_veto"
                                elif prob > self.threshold:
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
                            elif one_bar_vetoed:
                                logger.info(
                                    "  [VETO] P%s S%s M%s: Prob=%.2f -> OCR=%s "
                                    "(score=%.1f, one_bar_evidence=%s)",
                                    page_num,
                                    sys_idx,
                                    measure["number"],
                                    prob,
                                    found_num,
                                    final_score,
                                    one_bar_evidence_count,
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
            self.last_completed_page_id = page_id
            print(f"MMR page complete: {page_id}", flush=True)

        return results

    def _valid_status(
        self,
        found_num: Optional[int],
        prob: float,
        final_score: float,
        one_bar_evidence_count: int,
    ) -> tuple[bool, str, bool]:
        if not found_num:
            return False, "", False
        vetoed = self._should_veto_one_bar_rest(
            found_num, prob, final_score, one_bar_evidence_count
        )
        if vetoed:
            return False, "one_bar_veto", True
        if prob > self.threshold:
            return True, "found", False
        if final_score > 60:
            return True, "rescue", False
        return False, "", False

    @staticmethod
    def _support_view(support: Dict, name: str) -> Dict:
        try:
            view = support["views"][name]
            if not isinstance(view, dict):
                raise TypeError
            return view
        except (KeyError, TypeError) as error:
            raise ValueError(f"Invalid MMR support sidecar: missing {name} view") from error

    def _process_page_with_support(
        self,
        *,
        page_data: Dict,
        support: Dict,
        image: np.ndarray,
        page_num: int,
        image_width: int,
        image_height: int,
        debug_img: Optional[np.ndarray],
    ) -> List[Dict]:
        """Apply current-x4 geometry without mutating Phase-A logical indices."""

        primary_page = self._support_view(support, "primary")
        alternate_page = self._support_view(support, "implicit_start_alternate")
        fallback_page = self._support_view(support, "fallback")
        primary_systems = primary_page.get("pages", [{}])[0].get("systems", [])
        alternate_systems = alternate_page.get("pages", [{}])[0].get("systems", [])
        fallback_systems = fallback_page.get("pages", [{}])[0].get("systems", [])
        original_systems = page_data.get("pages", [{}])[0].get("systems", [])
        if not (
            len(primary_systems)
            == len(alternate_systems)
            == len(fallback_systems)
            == len(original_systems)
        ):
            raise ValueError("MMR support topology differs from Phase-A numbering")

        overrides: List[Dict] = []
        for sys_idx, original_system in enumerate(original_systems):
            primary_system = primary_systems[sys_idx]
            alternate_system = alternate_systems[sys_idx]
            fallback_system = fallback_systems[sys_idx]
            original_measures = original_system.get("measures", [])
            if not (
                len(primary_system.get("measures", []))
                == len(alternate_system.get("measures", []))
                == len(fallback_system.get("measures", []))
                == len(original_measures)
            ):
                raise ValueError("MMR support measure layout differs from Phase-A numbering")
            for m_idx, original_measure in enumerate(original_measures):
                primary_measure = primary_system["measures"][m_idx]
                x1, y1, x2, y2 = primary_measure["bbox"]
                margin = 20
                cx1, cy1 = int(max(0, x1 - margin)), int(max(0, y1 - margin))
                cx2, cy2 = int(min(image_width, x2 + margin)), int(min(image_height, y2 + margin))
                prob = self.classifier.predict(image[cy1:cy2, cx1:cx2])
                if prob <= self.rescue_threshold:
                    continue

                found_num, final_score, _debug, evidence = self._detect_number_with_evidence(
                    image, primary_system, x1, y1, x2, y2, prob, image_width, image_height
                )
                is_valid, status_label, vetoed = self._valid_status(
                    found_num, prob, final_score, evidence
                )

                alternate_measure = alternate_system["measures"][m_idx]
                if is_valid and alternate_measure["bbox"][0] != primary_measure["bbox"][0]:
                    ax1, ay1, ax2, ay2 = alternate_measure["bbox"]
                    alt_num, alt_score, _alt_debug, alt_evidence = (
                        self._detect_number_with_evidence(
                            image,
                            alternate_system,
                            ax1,
                            ay1,
                            ax2,
                            ay2,
                            prob,
                            image_width,
                            image_height,
                        )
                    )
                    if self._should_veto_one_bar_rest(alt_num, prob, alt_score, alt_evidence):
                        is_valid, status_label, vetoed = False, "one_bar_veto", True
                        self.support_stats["alternate_veto_suppression"] += 1

                # A Phase-A retry is OCR-only: it reuses the primary CNN probability.
                if found_num is None and prob > self.threshold:
                    self.support_stats["phase_a_ocr_fallback"] += 1
                    fallback_measure = fallback_system["measures"][m_idx]
                    fx1, fy1, fx2, fy2 = fallback_measure["bbox"]
                    found_num, final_score, _fallback_debug, evidence = (
                        self._detect_number_with_evidence(
                            image,
                            fallback_system,
                            fx1,
                            fy1,
                            fx2,
                            fy2,
                            prob,
                            image_width,
                            image_height,
                        )
                    )
                    is_valid, status_label, vetoed = self._valid_status(
                        found_num, prob, final_score, evidence
                    )

                if is_valid:
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
                            debug_img, x1, y1, x2, y2, status_label, f"R{found_num}", f"P{prob:.2f}"
                        )
                elif vetoed:
                    logger.info(
                        "  [VETO] P%s S%s M%s: Prob=%.2f",
                        page_num,
                        sys_idx,
                        original_measure["number"],
                        prob,
                    )
        return overrides

    def _detect_number(self, image, system, x1, y1, x2, y2, prob, w_img, h_img):
        found_number, best_score, best_debug, _one_bar_evidence_count = (
            self._detect_number_with_evidence(image, system, x1, y1, x2, y2, prob, w_img, h_img)
        )
        return found_number, best_score, best_debug

    def _detect_number_with_evidence(self, image, system, x1, y1, x2, y2, prob, w_img, h_img):
        variants = [("standard", 0)]
        if prob > self.threshold:
            variants = [("standard", 0), ("no_dilate", 0), ("heavy_dilate", 0)]
            if self.ocr.enable_rotation_tta:
                variants.extend(
                    [("standard", -2), ("standard", 2), ("heavy_dilate", -2), ("heavy_dilate", 2)]
                )

        variant_results = []
        one_bar_evidences = {}

        for mode, angle in variants:
            stave_results = []
            for stave in system.get("staves", []):
                s_bbox = stave["bbox"]
                margin_y = 80
                ox1, ox2 = int(max(0, x1 - 30)), int(min(w_img, x2 + 30))
                oy1, oy2 = int(max(0, s_bbox[1] - margin_y)), int(min(h_img, s_bbox[3] + 80))
                stave_crop = image[oy1:oy2, ox1:ox2]
                if stave_crop is None or stave_crop.size == 0:
                    continue

                stave_crop = self.ocr.mask_hbar_candidates(
                    stave_crop, margin_y, s_bbox[3] - s_bbox[1]
                )
                if stave_crop is None or stave_crop.size == 0:
                    continue

                proc_img = self.ocr.preprocess_variant(stave_crop, mode=mode, angle=angle)
                if proc_img is None:
                    continue

                ocr_res, _ = self.ocr.ocr_engine(proc_img)
                variant_key = (mode, angle)
                one_bar_evidences[variant_key] = one_bar_evidences.get(
                    variant_key, 0
                ) + self._count_high_confidence_one_bar_evidence(ocr_res)
                num, score, dbg = self.ocr.select_best_candidate(
                    ocr_res, proc_img.shape[1], proc_img.shape[0]
                )
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
            fallback_configs = [
                {
                    "name": "unmasked_fallback_standard",
                    "margin_y": 80,
                    "dx1": -30,
                    "dx2": 30,
                    "min_prob": self.rescue_threshold,
                },
                {
                    "name": "left_wide_unmasked_fallback_standard",
                    "margin_y": 120,
                    "dx1": -180,
                    "dx2": 60,
                    "min_prob": self.threshold,
                },
            ]

            for cfg in fallback_configs:
                if variant_results:
                    break
                if prob <= cfg["min_prob"]:
                    continue

                fallback_results = []
                name = cfg["name"]
                margin_y = cfg["margin_y"]
                dx1 = cfg["dx1"]
                dx2 = cfg["dx2"]

                for stave in system.get("staves", []):
                    s_bbox = stave["bbox"]
                    ox1 = int(max(0, x1 + dx1))
                    ox2 = int(min(w_img, x2 + dx2))
                    oy1 = int(max(0, s_bbox[1] - margin_y))
                    oy2 = int(min(h_img, s_bbox[3] + margin_y))
                    stave_crop = image[oy1:oy2, ox1:ox2]
                    if stave_crop is None or stave_crop.size == 0:
                        continue

                    proc_img = self.ocr.preprocess_variant(stave_crop, mode="standard", angle=0)
                    if proc_img is None:
                        continue

                    ocr_res, _ = self.ocr.ocr_engine(proc_img)
                    variant_key = (name, 0)
                    one_bar_evidences[variant_key] = one_bar_evidences.get(
                        variant_key, 0
                    ) + self._count_high_confidence_one_bar_evidence(ocr_res)

                    num, score, dbg = self.ocr.select_best_candidate(
                        ocr_res, proc_img.shape[1], proc_img.shape[0]
                    )
                    if num is not None and score > self.UNMASKED_FALLBACK_MIN_SCORE:
                        fallback_results.append((num, score, dbg))

                if fallback_results:
                    counts = Counter([r[0] for r in fallback_results])
                    current_num = counts.most_common(1)[0][0]
                    if not (current_num > 20 and (x2 - x1) < 100):
                        _, best_score, best_dbg = max(
                            [r for r in fallback_results if r[0] == current_num],
                            key=lambda x: x[1],
                        )
                        if best_dbg:
                            variant_debug = f"{best_dbg},variant={name}:0"
                        else:
                            variant_debug = f"variant={name}:0"
                        variant_results.append((current_num, best_score, variant_debug))

        one_bar_evidence_count = max(one_bar_evidences.values(), default=0)
        if not variant_results:
            return None, 0, "", one_bar_evidence_count

        found_number, best_score, best_debug = max(variant_results, key=lambda x: x[1])
        return found_number, best_score, best_debug, one_bar_evidence_count

    def _draw_debug(self, img, x1, y1, x2, y2, status, text, details):
        colors = {"found": (0, 255, 0), "rescue": (0, 165, 255), "skip": (0, 255, 255)}
        color = colors.get(status, (0, 0, 255))
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        label = f"{text} ({details})" if details else text
        cv2.putText(img, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)


def run_mmr_batch(
    pages_data: List[Dict],
    image_paths: List[Path],
    model_path: Path,
    device: torch.device,
    debug_root: Optional[Path] = None,
    rapidocr_instance: Optional[RapidOCR] = None,
    threshold: float = 0.5,
    rescue_threshold: float = 0.1,
    enable_rotation_tta: bool = False,
    support_data: Optional[List[Optional[Dict]]] = None,
) -> List[Dict[str, List[Dict]]]:
    ocr_engine = None
    if rapidocr_instance is not None:
        ocr_engine = MMROCREngine(
            enable_rotation_tta=enable_rotation_tta, ocr_engine=rapidocr_instance
        )
    processor = MMRProcessor(
        model_path,
        device,
        ocr_engine=ocr_engine,
        threshold=threshold,
        rescue_threshold=rescue_threshold,
        enable_rotation_tta=enable_rotation_tta,
    )
    return processor.process_pages(pages_data, image_paths, debug_root, support_data)
