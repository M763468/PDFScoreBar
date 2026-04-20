#!/usr/bin/env python3
from __future__ import annotations

import gc
import logging
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

try:
    import torch
except ImportError:
    pass

from homr.main import ProcessingConfig, download_weights
from homr.music_xml_generator import XmlGeneratorArguments, generate_xml
from src.common.thin_barline_finder import ThinBarlineConfig, detect_thin_vertical_runs

REPO_ROOT = Path(__file__).resolve().parents[2]
if __name__ != "__main__":
    REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"
_HOMR_CANDIDATES = (REPO_ROOT / "homr", REPO_ROOT / "external" / "homr")
HOMR_REPO = next((p for p in _HOMR_CANDIDATES if (p / "homr").exists()), _HOMR_CANDIDATES[1])
JST = ZoneInfo("Asia/Tokyo")

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

logger = logging.getLogger("homr_evaluator")

from src.homr_eval_scripts.core.heuristics import (
    compute_transform_info,
    detect_staffs_with_barlines,
    filter_detections_by_notehead_proximity,
    recover_end_barlines,
)
from src.homr_eval_scripts.core.metrics import (
    BarlinePrediction,
)
from src.homr_eval_scripts.core.utils import STEM_CONTEXT_HEURISTICS, map_pred_to_orig


class HomrPredictor:
    """Persistent Homr Predictor for batch processing."""

    def __init__(
        self,
        config: ProcessingConfig,
        tuning: Dict[str, float],
        enable_cache: bool = True,
        use_gpu_inference: bool = False,
    ) -> None:
        self.config = config
        self.tuning = tuning
        self.enable_cache = enable_cache
        self.use_gpu_inference = use_gpu_inference

        # Ensure Segnet cache is enabled for persistence
        if self.enable_cache:
            try:
                from homr_eval_scripts.segnet_cache import enable_segnet_cache

                if enable_segnet_cache():
                    logger.info("HomrPredictor: Segnet cache enabled.")
            except ImportError:
                # Local import fallback if running in-process from elsewhere
                try:
                    from .segnet_cache import enable_segnet_cache

                    if enable_segnet_cache():
                        logger.info("HomrPredictor: Segnet cache enabled (local).")
                except Exception as exc:
                    logger.warning(f"HomrPredictor: Failed to enable Segnet cache: {exc}")
            except Exception as exc:
                logger.warning(f"HomrPredictor: Failed to enable Segnet cache: {exc}")

        # Ensure weights are available
        download_weights(self.use_gpu_inference)

        # Note: use_gpu_inference is handled internally by SegNet/Transformer
        # when running in-process via ONNX runtime settings.

        # Initialize transformer config for parse_staffs
        from homr.transformer.configs import default_config

        _ = default_config  # Ensure it is importable

    def predict(
        self,
        image_path: Path,
        xml_args: XmlGeneratorArguments,
        sr_scale: int = 1,
        timeout_s: float = 0.0,
        image_run_dir: Optional[Path] = None,
    ) -> Tuple[
        List[BarlinePrediction],
        Optional[Path],
        Tuple[int, int],
        float,
        np.ndarray,
        np.ndarray,
        List[BarlinePrediction],
        List[BarlinePrediction],
    ]:
        """Runs the core homr staff and symbol detection pipeline for a single image with proxying and post-processing."""
        stem = image_path.stem

        # 1. Proxy logic
        inference_image_path = image_path
        proxy_scale_x = 1.0
        proxy_scale_y = 1.0

        img_check = cv2.imread(str(image_path))
        if img_check is None:
            raise FileNotFoundError(f"Image not found: {image_path}")

        sr_h, sr_w = img_check.shape[:2]
        pixels = sr_h * sr_w
        target_pixels = 3.5 * 1000 * 1000  # Target ~3.5MP for Homr Inference

        temp_proxy_path: Optional[Path] = None
        if pixels > target_pixels * 1.5:
            proxy_scale = (pixels / target_pixels) ** 0.5
            proxy_w = int(sr_w / proxy_scale)
            proxy_h = int(sr_h / proxy_scale)

            proxy_scale_x = sr_w / proxy_w
            proxy_scale_y = sr_h / proxy_h

            logger.info(
                f"HomrPredictor: Creating Proxy: {sr_w}x{sr_h} -> {proxy_w}x{proxy_h} (Scale: {proxy_scale:.2f})"
            )
            proxy_img = cv2.resize(img_check, (proxy_w, proxy_h))

            if image_run_dir:
                inference_image_path = image_run_dir / f"{stem}_proxy.png"
                cv2.imwrite(str(inference_image_path), proxy_img)
            else:
                fd, proxy_path_str = tempfile.mkstemp(suffix=".png", prefix="homr_proxy_")
                os.close(fd)
                temp_proxy_path = Path(proxy_path_str)
                inference_image_path = temp_proxy_path
                cv2.imwrite(str(inference_image_path), proxy_img)

        # 2. Run core inference
        predictions, xml_path, seg_shape, runtime_s, notehead_mask, staff_mask = run_homr_on_image(
            inference_image_path,
            self.config,
            xml_args,
            timeout_s,
            self.tuning,
            self.use_gpu_inference,
        )

        # 3. Map predictions back to the input image coordinates
        transform = compute_transform_info(inference_image_path, seg_shape)
        mapped_predictions: List[BarlinePrediction] = []
        for pred in predictions:
            # Map Seg -> Inference image (Proxy or Original)
            orig_bbox_proxy = map_pred_to_orig(pred.pred_bbox, transform)

            # Map Inference image -> Input image
            x1, y1, x2, y2 = orig_bbox_proxy
            if proxy_scale_x != 1.0 or proxy_scale_y != 1.0:
                x1 = int(round(x1 * proxy_scale_x))
                y1 = int(round(y1 * proxy_scale_y))
                x2 = int(round(x2 * proxy_scale_x))
                y2 = int(round(y2 * proxy_scale_y))

            mapped_predictions.append(
                BarlinePrediction(
                    pred_bbox=pred.pred_bbox,
                    orig_bbox=(x1, y1, x2, y2),
                    system_index=pred.system_index,
                    staff_index=pred.staff_index,
                )
            )

        # 4. Resize masks to input image size
        # FIX: content is 0/1. Scale to 0/255 for correct bitwise operations and resize interpolation
        notehead_mask_255 = (notehead_mask * 255).astype(np.uint8)
        staff_mask_255 = (staff_mask * 255).astype(np.uint8)

        notehead_mask_resized = cv2.resize(
            notehead_mask_255,
            dsize=(sr_w, sr_h),
            interpolation=cv2.INTER_NEAREST,
        )
        staff_mask_resized = cv2.resize(
            staff_mask_255,
            dsize=(sr_w, sr_h),
            interpolation=cv2.INTER_NEAREST,
        )

        # 5. Thin Barline Detection
        tb_config = ThinBarlineConfig()
        if sr_scale > 1:
            # Scale thin barline parameters
            # Note: max_height needs to be large enough to cover multi-staff barlines in SR space.
            # In 600dpi, full-staff is ~140px. In 1200dpi (SRx2), it is ~280px.
            # We set a generous limit (800 * sr_scale) to avoid rejections.
            tb_config = ThinBarlineConfig(
                min_height=int(sr_scale * 8),
                max_height=int(sr_scale * 800),
                max_width=int(sr_scale * 30),  # Scale width too
                pixel_threshold=235,
                max_intensity_std=120.0,
                max_intensity_std_relaxed=150.0,
                y_merge_tolerance=tb_config.y_merge_tolerance * sr_scale,
                y_center_tolerance=tb_config.y_center_tolerance * sr_scale,
                x_center_tolerance=tb_config.x_center_tolerance * sr_scale,
                adjacent_relaxed_span=tb_config.adjacent_relaxed_span * sr_scale,
                vertical_gap_fill=tb_config.vertical_gap_fill * sr_scale,
                left_margin_limit=tb_config.left_margin_limit * sr_scale,
                cluster_x_tolerance=tb_config.cluster_x_tolerance * sr_scale,
                cluster_reject_span=tb_config.cluster_reject_span * sr_scale,
                dark_pixel_threshold=tb_config.dark_pixel_threshold,
            )
        else:
            # 600dpi (Standard) optimizations
            tb_config = ThinBarlineConfig(
                min_height=18,
                max_height=800,  # Allow multi-staff
                max_width=30,
                pixel_threshold=235,
                max_intensity_std=120.0,
                max_intensity_std_relaxed=150.0,
            )

        extra_barlines = detect_thin_vertical_runs(
            image_path,
            [p.orig_bbox for p in mapped_predictions],
            config=tb_config,
        )

        def _centre(box: Tuple[int, int, int, int]) -> Tuple[float, float]:
            x1, y1, x2, y2 = box
            return (x1 + x2) / 2.0, (y1 + y2) / 2.0

        def _vertical_overlap_fraction(
            box_a: Tuple[int, int, int, int], box_b: Tuple[int, int, int, int]
        ) -> float:
            top = max(box_a[1], box_b[1])
            bottom = min(box_a[3], box_b[3])
            if bottom <= top:
                return 0.0
            overlap = bottom - top
            height_a = max(box_a[3] - box_a[1], 1)
            height_b = max(box_b[3] - box_b[1], 1)
            return overlap / float(max(height_a, height_b))

        for box in extra_barlines:
            cx_extra, cy_extra = _centre(box)
            box_height = max(box[3] - box[1], 1)
            replaced = False
            for idx, pred in enumerate(mapped_predictions):
                existing_box = pred.orig_bbox
                cx_existing, cy_existing = _centre(existing_box)
                if abs(cx_existing - cx_extra) > 2 * sr_scale:
                    continue

                existing_height = max(existing_box[3] - existing_box[1], 1)
                centre_gap = abs(cy_existing - cy_extra)
                vertical_overlap = _vertical_overlap_fraction(existing_box, box)

                if vertical_overlap >= 0.6:
                    if box_height > existing_height:
                        mapped_predictions[idx] = BarlinePrediction(
                            pred_bbox=box,
                            orig_bbox=box,
                            system_index=-2,
                            staff_index=-1,
                        )
                    replaced = True
                    break

                max_height = max(box_height, existing_height)
                if centre_gap <= max_height:
                    if box_height >= existing_height:
                        mapped_predictions[idx] = BarlinePrediction(
                            pred_bbox=box,
                            orig_bbox=box,
                            system_index=-2,
                            staff_index=-1,
                        )
                    replaced = True
                    break

            if not replaced:
                mapped_predictions.append(
                    BarlinePrediction(
                        pred_bbox=box,
                        orig_bbox=box,
                        system_index=-2,
                        staff_index=-1,
                    )
                )

        # 6. Heuristic Rejection
        rejected_by_heuristic: List[BarlinePrediction] = []
        if self.tuning.get("stem_context_heuristics_enabled", True):
            h_config = STEM_CONTEXT_HEURISTICS.copy()
            if sr_scale > 1:
                h_config["notehead_proximity_threshold_px"] *= sr_scale
                h_config["min_overlap_px"] *= sr_scale * sr_scale
                h_config["max_height_px"] *= sr_scale
                h_config["max_width_px"] *= sr_scale
                h_config["cluster_gap_threshold_px"] *= sr_scale

            mapped_predictions, rejected_by_heuristic = filter_detections_by_notehead_proximity(
                mapped_predictions,
                notehead_mask_resized,
                h_config["notehead_proximity_threshold_px"],
                h_config["min_overlap_px"],
                h_config["max_height_px"],
                h_config["max_width_px"],
                staff_mask_resized,
                h_config["min_staff_crossings"],
                h_config["staff_crossing_enabled"],
            )

        # 7. End Barline Recovery
        added_end: List[BarlinePrediction] = []
        if self.tuning.get("enable_end_barline_recovery", False):
            # recover_end_barlines needs image_path
            added_end = recover_end_barlines(
                image_path, mapped_predictions, staff_mask_resized, sr_scale
            )
            if added_end:
                mapped_predictions.extend(added_end)

        # Cleanup
        if temp_proxy_path and temp_proxy_path.exists():
            try:
                os.remove(str(temp_proxy_path))
            except OSError as e:
                logger.warning(f"Failed to remove temporary proxy file {temp_proxy_path}: {e}")

        return (
            mapped_predictions,
            xml_path,
            seg_shape,
            runtime_s,
            notehead_mask_resized,
            staff_mask_resized,
            rejected_by_heuristic,
            added_end,
        )

    def cleanup(self) -> None:
        """Release VRAM and other resources."""
        try:
            # Clear any persistent Segnet sessions
            try:
                from homr_eval_scripts.segnet_cache import clear_segnet_cache

                clear_segnet_cache()
            except Exception:
                pass

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
                logger.info("HomrPredictor: Released VRAM.")

            gc.collect()
        except Exception as e:
            logger.warning(f"Exception during HomrPredictor cleanup: {e}")


def run_homr_on_image(
    image_path: Path,
    config: ProcessingConfig,
    xml_args: XmlGeneratorArguments,
    timeout_s: float,
    tuning: Dict[str, float],
    use_gpu_inference: bool,
) -> Tuple[List[BarlinePrediction], Optional[Path], Tuple[int, int], float, np.ndarray, np.ndarray]:
    start = time.perf_counter()
    try:
        (
            multi_staffs,
            preprocessed_image,
            debug,
            title_future,
            bar_line_boxes,
            notehead_mask,
            staff_mask,
        ) = detect_staffs_with_barlines(str(image_path), config, tuning, use_gpu_inference)
    except RuntimeError as e:
        msg = str(e)
        if "No staffs found" in msg or "No noteheads found" in msg:
            logger.warning(
                f"Detection failed for {image_path.name}: {msg}. Returning empty results."
            )
            img = cv2.imread(str(image_path))
            if img is None:
                # Fallback if image cannot be read
                h, w = 0, 0
            else:
                h, w = img.shape[:2]
            runtime_s = time.perf_counter() - start
            empty_mask = np.zeros((h, w), dtype=np.uint8)
            return [], None, (h, w), runtime_s, empty_mask, empty_mask
        raise

    predictions: List[BarlinePrediction] = []
    for barline_box in bar_line_boxes:
        bbox = barline_box.to_bounding_box()
        x1, y1, x2, y2 = map(int, bbox.box)
        predictions.append(
            BarlinePrediction(
                pred_bbox=(x1, y1, x2, y2),
                orig_bbox=(0, 0, 0, 0),
                system_index=getattr(barline_box, "debug_id", -1),
                staff_index=-1,
            )
        )

    xml_path: Optional[Path] = None
    seg_shape = (debug.original_image.shape[0], debug.original_image.shape[1])

    try:
        from homr.main import parse_staffs

        try:
            from homr.transformer.configs import default_config

            default_config.use_gpu_inference = use_gpu_inference
            result_staffs = parse_staffs(
                debug, multi_staffs, preprocessed_image, default_config, selected_staff=-1
            )
        except (TypeError, ImportError):
            # Fallback for legacy version that doesn't take config or where config is missing
            result_staffs = parse_staffs(debug, multi_staffs, preprocessed_image, selected_staff=-1)
        try:
            title = title_future.result(timeout_s)
        except Exception:  # pylint: disable=broad-except
            title = ""
        xml = generate_xml(xml_args, result_staffs, title)
        xml_path = Path(str(image_path.with_suffix(".musicxml")))
        xml.write(xml_path)
        teaser_file = Path(str(image_path.with_name(image_path.stem + "_teaser.png")))
        debug.write_teaser(str(teaser_file), multi_staffs)
    finally:
        debug.clean_debug_files_from_previous_runs()

    runtime_s = time.perf_counter() - start
    return predictions, xml_path, seg_shape, runtime_s, notehead_mask, staff_mask
