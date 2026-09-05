#!/usr/bin/env python3
"""Run an immutable upstream HOMR source commit as a detector-material candidate.

This Issue #294 experiment intentionally stops before staff grouping, PDF input,
title OCR, Transformer parsing, and MusicXML generation. The Stage-E baseline is
consumed downstream for barline/staff/clef material; current-x4 HOMR remains the
connector-semantic source. Only detector-path modules and the SegNet weight are
materialized for this run.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import inspect
import json
import platform
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TARGET_PIXELS = 3.5 * 1000 * 1000
MODEL_RELEASE_BASE = "https://github.com/liebharc/homr/releases/download/onnx_checkpoints/"
DETECTOR_ONLY_MODULES = (
    "homr",
    "homr.autocrop",
    "homr.bar_line_detection",
    "homr.bounding_boxes",
    "homr.color_adjust",
    "homr.constants",
    "homr.debug",
    "homr.download_utils",
    "homr.model",
    "homr.noise_filtering",
    "homr.note_detection",
    "homr.resize",
    "homr.segmentation.config",
    "homr.segmentation.inference_segnet",
    "homr.staff_detection",
)
EXCLUDED_OPTIONAL_MODULES = (
    "homr.main",
    "homr.pdf_utils",
    "homr.title_detection",
    "homr.transformer.configs",
    "homr.music_xml_generator",
)
STEM_CONTEXT_HEURISTICS = {
    "notehead_proximity_threshold_px": 5,
    "min_overlap_px": 5,
    "max_height_px": 24,
    "max_width_px": 4,
    "staff_crossing_enabled": False,
    "min_staff_crossings": 3,
}


@dataclass
class BarlinePrediction:
    pred_bbox: tuple[int, int, int, int]
    orig_bbox: tuple[int, int, int, int]
    system_index: int
    staff_index: int


@dataclass
class TransformInfo:
    original_shape: tuple[int, int]
    crop_box: tuple[int, int, int, int]
    resize_shape: tuple[int, int]
    seg_shape: tuple[int, int]
    resize_scale: tuple[float, float]
    seg_scale: tuple[float, float]

    @property
    def total_scale(self) -> tuple[float, float]:
        return (
            self.resize_scale[0] * self.seg_scale[0],
            self.resize_scale[1] * self.seg_scale[1],
        )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_dir(path: Path) -> Path:
    marker = path / ".git"
    if marker.is_dir():
        return marker
    if marker.is_file():
        text = marker.read_text(encoding="utf-8").strip()
        prefix = "gitdir:"
        if not text.lower().startswith(prefix):
            raise RuntimeError(f"Unsupported .git file: {marker}")
        target = text[len(prefix) :].strip()
        resolved = Path(target)
        if not resolved.is_absolute():
            resolved = (path / resolved).resolve()
        if not resolved.is_dir():
            raise FileNotFoundError(resolved)
        return resolved
    raise FileNotFoundError(marker)


def _checkout_head(path: Path) -> str:
    """Resolve checkout HEAD without requiring a git executable in the runtime image."""

    git_dir = _git_dir(path)
    head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    if not head.startswith("ref: "):
        return head

    ref = head.removeprefix("ref: ").strip()
    loose_ref = git_dir / ref
    if loose_ref.is_file():
        return loose_ref.read_text(encoding="utf-8").strip()

    packed_refs = git_dir / "packed-refs"
    if packed_refs.is_file():
        for line in packed_refs.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith(("#", "^")):
                continue
            commit, separator, candidate_ref = line.partition(" ")
            if separator and candidate_ref == ref:
                return commit
    raise RuntimeError(f"Unable to resolve Git HEAD ref {ref!r} under {git_dir}")


def _shape(path: Path) -> list[int] | None:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return None
    return [int(image.shape[1]), int(image.shape[0])]


def _excluded_imports() -> list[str]:
    return [module for module in EXCLUDED_OPTIONAL_MODULES if module in sys.modules]


def _assert_excluded_modules_absent(stage: str) -> None:
    imported = _excluded_imports()
    if imported:
        raise RuntimeError(
            f"Excluded full-application HOMR modules imported during {stage}: {imported}"
        )


def _ensure_segnet_model(segnet_config: Any, *, use_gpu: bool) -> Path:
    from homr import download_utils

    path = Path(segnet_config.segnet_path_onnx_fp16 if use_gpu else segnet_config.segnet_path_onnx)
    if path.is_file():
        return path
    base_name = path.name.split(".")[0]
    zip_path = path.parent / f"{base_name}.zip"
    try:
        download_utils.download_file(MODEL_RELEASE_BASE + zip_path.name, str(zip_path))
        download_utils.unzip_file(str(zip_path), str(path.parent))
    finally:
        if zip_path.exists():
            zip_path.unlink()
    if not path.is_file():
        raise FileNotFoundError(f"SegNet download did not materialize {path}")
    return path


def _verify_source(homr_source: Path, expected_commit: str) -> tuple[str, Path]:
    source = homr_source.resolve()
    if not (source / "homr").is_dir():
        raise FileNotFoundError(source / "homr")
    actual_commit = _checkout_head(source)
    if actual_commit != expected_commit:
        raise RuntimeError(
            f"HOMR checkout mismatch: expected={expected_commit} actual={actual_commit}"
        )
    homr = importlib.import_module("homr")
    imported_homr = Path(str(homr.__file__)).resolve()
    if source not in imported_homr.parents:
        raise RuntimeError(f"Expected HOMR import from {source}, got {imported_homr}")
    return actual_commit, imported_homr


def preflight(homr_source: Path, expected_commit: str) -> dict[str, Any]:
    """Import exactly the detector-only dependency closure before expensive matrix work."""

    actual_commit, imported_homr = _verify_source(homr_source, expected_commit)
    imported: dict[str, str | None] = {}
    for module_name in DETECTOR_ONLY_MODULES:
        module = importlib.import_module(module_name)
        raw_file = getattr(module, "__file__", None)
        imported[module_name] = str(Path(raw_file).resolve()) if raw_file else None

    from homr.segmentation.inference_segnet import extract

    extract_parameters = inspect.signature(extract).parameters
    required_extract_parameters = {
        "original_image",
        "img_path_str",
        "use_cache",
        "use_gpu_inference",
    }
    missing = sorted(required_extract_parameters - set(extract_parameters))
    if missing:
        raise RuntimeError(f"Unsupported HOMR SegNet extract signature; missing={missing}")

    import onnxruntime as ort

    providers = list(ort.get_available_providers())
    _assert_excluded_modules_absent("detector preflight")
    return {
        "status": "completed",
        "scope": "detector_only_import_preflight",
        "homr_source": str(homr_source.resolve()),
        "homr_commit": actual_commit,
        "homr_module": str(imported_homr),
        "commit_verification": "read_git_metadata_without_git_executable",
        "imported_modules": imported,
        "excluded_optional_modules": list(EXCLUDED_OPTIONAL_MODULES),
        "optional_modules_imported": _excluded_imports(),
        "runtime": {
            "python": sys.executable,
            "python_version": platform.python_version(),
            "numpy_version": np.__version__,
            "opencv_version": cv2.__version__,
            "onnxruntime_version": ort.__version__,
            "providers": providers,
        },
        "segnet_extract_parameters": list(extract_parameters),
        "detector_runtime_classification": (
            "upstream_source_detector_material_on_existing_pipeline_runtime; "
            "not yet an upstream-supported full maintained-runtime gate"
        ),
    }


def _make_proxy(image: Path, image_run_dir: Path) -> tuple[Path, float, float, np.ndarray]:
    original = cv2.imread(str(image))
    if original is None:
        raise FileNotFoundError(image)
    height, width = original.shape[:2]
    pixels = height * width
    if pixels <= TARGET_PIXELS * 1.5:
        return image, 1.0, 1.0, original
    scale = (pixels / TARGET_PIXELS) ** 0.5
    proxy_width = int(width / scale)
    proxy_height = int(height / scale)
    proxy = cv2.resize(original, (proxy_width, proxy_height))
    proxy_path = image_run_dir / f"{image.stem}_proxy.png"
    if not cv2.imwrite(str(proxy_path), proxy):
        raise RuntimeError(f"Failed to write proxy: {proxy_path}")
    return proxy_path, width / proxy_width, height / proxy_height, original


def _load_predictions(image: Path, *, use_gpu: bool) -> tuple[Any, Any]:
    """Mirror HOMR detector preprocessing without importing homr.main."""

    from homr import color_adjust
    from homr.autocrop import autocrop
    from homr.debug import Debug
    from homr.model import InputPredictions
    from homr.noise_filtering import filter_predictions
    from homr.resize import resize_image
    from homr.segmentation.inference_segnet import extract
    from homr.staff_detection import make_lines_stronger

    original = cv2.imread(str(image))
    if original is None:
        raise FileNotFoundError(image)
    original = autocrop(original)
    original = resize_image(original)
    preprocessed = color_adjust.apply_clahe(original)
    result = extract(
        preprocessed,
        str(image),
        use_cache=False,
        use_gpu_inference=use_gpu,
        step_size=320,
    )
    original_image = cv2.resize(original, (result.staff.shape[1], result.staff.shape[0]))
    preprocessed_image = cv2.resize(
        preprocessed,
        (result.staff.shape[1], result.staff.shape[0]),
    )
    predictions = InputPredictions(
        original=original_image,
        preprocessed=preprocessed_image,
        notehead=result.notehead.astype(np.uint8),
        symbols=result.symbols.astype(np.uint8),
        staff=result.staff.astype(np.uint8),
        clefs_keys=result.clefs_keys.astype(np.uint8),
        stems_rest=result.stems_rests.astype(np.uint8),
    )
    debug = Debug(predictions.original, str(image), False)
    predictions = filter_predictions(predictions, debug)
    predictions.staff = make_lines_stronger(predictions.staff, (1, 2))
    return predictions, debug


def _predict_symbols(debug: Any, predictions: Any) -> Any:
    """Mirror HOMR predict_symbols without importing the full application module."""

    from homr.bar_line_detection import prepare_bar_line_image
    from homr.bounding_boxes import create_bounding_ellipses, create_rotated_bounding_boxes

    noteheads = create_bounding_ellipses(predictions.notehead, min_size=(4, 4))
    staff_fragments = create_rotated_bounding_boxes(
        predictions.staff,
        skip_merging=True,
        min_size=(5, 1),
        max_size=(10000, 100),
    )
    clefs_keys = create_rotated_bounding_boxes(
        predictions.clefs_keys,
        min_size=(20, 40),
        max_size=(1000, 1000),
    )
    stems_rest = create_rotated_bounding_boxes(predictions.stems_rest)
    bar_line_img = prepare_bar_line_image(predictions.stems_rest)
    debug.write_threshold_image("bar_line_img", bar_line_img)
    bar_lines = create_rotated_bounding_boxes(
        bar_line_img,
        skip_merging=True,
        min_size=(1, 5),
    )
    return SimpleNamespace(
        noteheads=noteheads,
        staff_fragments=staff_fragments,
        clefs_keys=clefs_keys,
        stems_rest=stems_rest,
        bar_lines=bar_lines,
    )


def _detect_material(inference_image: Path, *, use_gpu: bool) -> tuple[Any, ...]:
    from homr import constants
    from homr.note_detection import combine_noteheads_with_stems
    from homr.staff_detection import break_wide_fragments

    predictions, debug = _load_predictions(inference_image, use_gpu=use_gpu)
    symbols = _predict_symbols(debug, predictions)
    symbols.staff_fragments = break_wide_fragments(symbols.staff_fragments)
    noteheads_with_stems = combine_noteheads_with_stems(symbols.noteheads, symbols.stems_rest)
    if not noteheads_with_stems:
        raise RuntimeError("No noteheads found")

    average_note_head_height = float(
        np.median([notehead.notehead.size[1] for notehead in noteheads_with_stems])
    )
    all_noteheads = [notehead.notehead for notehead in noteheads_with_stems]
    all_stems = [note.stem for note in noteheads_with_stems if note.stem is not None]
    bar_lines_or_rests = [
        line
        for line in symbols.bar_lines
        if not line.is_overlapping_with_any(all_noteheads)
        and not line.is_overlapping_with_any(all_stems)
    ]
    min_height = constants.bar_line_min_height(average_note_head_height)
    max_width = constants.bar_line_max_width(average_note_head_height)
    bar_line_boxes = [
        line
        for line in bar_lines_or_rests
        if line.size[1] >= min_height and line.size[0] <= max_width
    ]
    return bar_line_boxes, predictions.notehead, predictions.staff, predictions.clefs_keys


def _autocrop_bounds(image: np.ndarray) -> tuple[tuple[int, int, int, int], bool]:
    """Pure copy of the evaluator coordinate helper, without heuristics imports."""

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    hist = cv2.calcHist([image], [0], None, [256], [0, 256])
    dominant = int(
        max(
            enumerate(hist),
            key=lambda item: float(item[1].item() if hasattr(item[1], "item") else item[1]),
        )[0]
    )
    thresh = cv2.threshold(gray, max(dominant - 30, 0), 255, cv2.THRESH_BINARY)[1]
    morph = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    morph = cv2.morphologyEx(morph, cv2.MORPH_ERODE, np.ones((9, 9), np.uint8))
    contours_tuple = cv2.findContours(morph, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = contours_tuple[0] if len(contours_tuple) == 2 else contours_tuple[1]
    area_thresh = 0.0
    big_contour = None
    for contour in contours:
        area = cv2.contourArea(contour)
        if area > area_thresh:
            area_thresh = area
            big_contour = contour

    height, width = image.shape[:2]
    if big_contour is None:
        return (0, 0, width, height), False
    x, y, crop_width, crop_height = cv2.boundingRect(big_contour)
    is_full_page_view = x < width * 0.25 or y < height * 0.25
    if is_full_page_view:
        return (0, 0, width, height), False
    return (x, y, crop_width, crop_height), True


def _compute_transform_info(image_path: Path, seg_shape: tuple[int, int]) -> TransformInfo:
    from homr.resize import calc_target_image_size

    original = cv2.imread(str(image_path))
    if original is None:
        raise RuntimeError(f"Failed to load image for transform computation: {image_path}")
    crop_box, cropped = _autocrop_bounds(original)
    crop_x, crop_y, crop_width, crop_height = crop_box
    if not cropped:
        crop_x = crop_y = 0
        crop_width = original.shape[1]
        crop_height = original.shape[0]

    target_width, target_height = calc_target_image_size(crop_width, crop_height)
    resize_scale_x = target_width / crop_width
    resize_scale_y = target_height / crop_height
    seg_height, seg_width = seg_shape
    seg_scale_x = seg_width / target_width
    seg_scale_y = seg_height / target_height
    return TransformInfo(
        original_shape=(original.shape[1], original.shape[0]),
        crop_box=(crop_x, crop_y, crop_width, crop_height),
        resize_shape=(target_width, target_height),
        seg_shape=(seg_width, seg_height),
        resize_scale=(resize_scale_x, resize_scale_y),
        seg_scale=(seg_scale_x, seg_scale_y),
    )


def _map_pred_to_orig(
    box: tuple[int, int, int, int], transform: TransformInfo
) -> tuple[int, int, int, int]:
    crop_x, crop_y, *_ = transform.crop_box
    scale_x, scale_y = transform.total_scale
    inv_scale_x = 1.0 / scale_x if scale_x != 0 else 0.0
    inv_scale_y = 1.0 / scale_y if scale_y != 0 else 0.0
    orig_width, orig_height = transform.original_shape
    x1, y1, x2, y2 = box
    mapped = (
        int(round(x1 * inv_scale_x + crop_x)),
        int(round(y1 * inv_scale_y + crop_y)),
        int(round(x2 * inv_scale_x + crop_x)),
        int(round(y2 * inv_scale_y + crop_y)),
    )
    x1c = max(0, min(orig_width - 1, mapped[0]))
    y1c = max(0, min(orig_height - 1, mapped[1]))
    x2c = max(0, min(orig_width - 1, mapped[2]))
    y2c = max(0, min(orig_height - 1, mapped[3]))
    return (x1c, y1c, max(x1c, x2c), max(y1c, y2c))


def _map_predictions(
    bar_line_boxes: list[Any],
    inference_image: Path,
    seg_shape: tuple[int, int],
    proxy_scale_x: float,
    proxy_scale_y: float,
) -> list[BarlinePrediction]:
    transform = _compute_transform_info(inference_image, seg_shape)
    mapped: list[BarlinePrediction] = []
    for barline_box in bar_line_boxes:
        raw = barline_box.to_bounding_box().box
        pred_bbox = tuple(int(value) for value in raw)
        x1, y1, x2, y2 = _map_pred_to_orig(pred_bbox, transform)
        if proxy_scale_x != 1.0 or proxy_scale_y != 1.0:
            x1 = int(round(x1 * proxy_scale_x))
            y1 = int(round(y1 * proxy_scale_y))
            x2 = int(round(x2 * proxy_scale_x))
            y2 = int(round(y2 * proxy_scale_y))
        mapped.append(
            BarlinePrediction(
                pred_bbox=pred_bbox,
                orig_bbox=(x1, y1, x2, y2),
                system_index=-1,
                staff_index=-1,
            )
        )
    return mapped


def _filter_notehead_proximity(
    detections: list[BarlinePrediction], notehead_mask: np.ndarray
) -> list[BarlinePrediction]:
    """Mirror the currently enabled safe stem filter without importing heuristics.py."""

    cfg = STEM_CONTEXT_HEURISTICS
    if cfg["staff_crossing_enabled"]:
        raise RuntimeError("Issue #294 detector adapter assumes staff-crossing filter is disabled")

    kept: list[BarlinePrediction] = []
    mask_height, mask_width = notehead_mask.shape
    proximity = int(cfg["notehead_proximity_threshold_px"])
    min_overlap = int(cfg["min_overlap_px"])
    max_height = int(cfg["max_height_px"])
    max_width = int(cfg["max_width_px"])

    for pred in detections:
        x1, y1, x2, y2 = pred.orig_bbox
        width = x2 - x1
        height = y2 - y1
        is_small_candidate = (height < max_height) and (width < max_width)
        search_x1 = max(0, x1 - proximity)
        search_x2 = min(mask_width, x2 + proximity)
        y1c = max(0, min(mask_height, y1))
        y2c = max(0, min(mask_height, y2))
        if y1c >= y2c or search_x1 >= search_x2:
            kept.append(pred)
            continue
        search_window = notehead_mask[y1c:y2c, search_x1:search_x2]
        if not np.any(search_window):
            kept.append(pred)
            continue
        box_x1 = max(0, min(mask_width, x1))
        box_x2 = max(0, min(mask_width, x2))
        overlap_area = (
            0 if box_x1 >= box_x2 else int(np.count_nonzero(notehead_mask[y1c:y2c, box_x1:box_x2]))
        )
        if is_small_candidate and overlap_area >= min_overlap:
            continue
        kept.append(pred)
    return kept


def _postprocess(
    image: Path,
    original: np.ndarray,
    predictions: list[BarlinePrediction],
    notehead_mask: np.ndarray,
) -> list[BarlinePrediction]:
    """Mirror the production HomrPredictor thin-barline merge and safe stem filter."""

    from src.common.thin_barline_finder import ThinBarlineConfig, detect_thin_vertical_runs

    thin_config = ThinBarlineConfig(
        min_height=18,
        max_height=800,
        max_width=30,
        pixel_threshold=235,
        max_intensity_std=120.0,
        max_intensity_std_relaxed=150.0,
    )
    gray = cv2.cvtColor(original, cv2.COLOR_BGR2GRAY)
    extras = detect_thin_vertical_runs(
        image,
        [prediction.orig_bbox for prediction in predictions],
        config=thin_config,
        grayscale_image=gray,
    )

    def centre(box: tuple[int, int, int, int]) -> tuple[float, float]:
        return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)

    def vertical_overlap_fraction(
        box_a: tuple[int, int, int, int], box_b: tuple[int, int, int, int]
    ) -> float:
        top = max(box_a[1], box_b[1])
        bottom = min(box_a[3], box_b[3])
        if bottom <= top:
            return 0.0
        overlap = bottom - top
        height_a = max(box_a[3] - box_a[1], 1)
        height_b = max(box_b[3] - box_b[1], 1)
        return overlap / float(max(height_a, height_b))

    for box_raw in extras:
        box = tuple(int(value) for value in box_raw)
        cx_extra, cy_extra = centre(box)
        extra_height = max(box[3] - box[1], 1)
        replaced = False
        for index, prediction in enumerate(predictions):
            existing = prediction.orig_bbox
            cx_existing, cy_existing = centre(existing)
            if abs(cx_existing - cx_extra) > 2:
                continue

            existing_height = max(existing[3] - existing[1], 1)
            centre_gap = abs(cy_existing - cy_extra)
            vertical_overlap = vertical_overlap_fraction(existing, box)

            if vertical_overlap >= 0.6:
                if extra_height > existing_height:
                    predictions[index] = BarlinePrediction(
                        pred_bbox=box,
                        orig_bbox=box,
                        system_index=-2,
                        staff_index=-1,
                    )
                replaced = True
                break

            max_height = max(extra_height, existing_height)
            if centre_gap <= max_height:
                if extra_height >= existing_height:
                    predictions[index] = BarlinePrediction(
                        pred_bbox=box,
                        orig_bbox=box,
                        system_index=-2,
                        staff_index=-1,
                    )
                replaced = True
                break

        if not replaced:
            predictions.append(
                BarlinePrediction(
                    pred_bbox=box,
                    orig_bbox=box,
                    system_index=-2,
                    staff_index=-1,
                )
            )
    return _filter_notehead_proximity(predictions, notehead_mask)


def _save_homr_results(
    image_path: Path,
    image_run_dir: Path,
    predictions: list[BarlinePrediction],
    notehead_mask: np.ndarray,
    staff_mask: np.ndarray,
) -> Path:
    image_run_dir.mkdir(parents=True, exist_ok=True)
    stem = image_path.stem
    notehead_path = image_run_dir / f"{stem}_notehead_mask.png"
    staff_path = image_run_dir / f"{stem}_staff_mask.png"
    if not cv2.imwrite(str(notehead_path), notehead_mask):
        raise RuntimeError(f"Failed to write notehead mask: {notehead_path}")
    if not cv2.imwrite(str(staff_path), staff_mask):
        raise RuntimeError(f"Failed to write staff mask: {staff_path}")
    detections_path = image_run_dir / f"{stem}_detections.json"
    detections_path.write_text(
        json.dumps(
            {
                "image": str(image_path),
                "predictions": [
                    {
                        "pred_bbox": pred.pred_bbox,
                        "orig_bbox": pred.orig_bbox,
                        "system_index": pred.system_index,
                        "staff_index": pred.staff_index,
                    }
                    for pred in predictions
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return detections_path


def run(
    image: Path,
    homr_source: Path,
    expected_commit: str,
    output_root: Path,
    result_path: Path,
) -> dict[str, Any]:
    started = time.perf_counter()
    image = image.resolve()
    output_root = output_root.resolve()
    result_path = result_path.resolve()
    if not image.is_file():
        raise FileNotFoundError(image)
    if output_root.exists():
        raise FileExistsError(output_root)
    if result_path.exists():
        raise FileExistsError(result_path)

    preflight_payload = preflight(homr_source, expected_commit)
    actual_commit = str(preflight_payload["homr_commit"])
    imported_homr = Path(str(preflight_payload["homr_module"]))

    import onnxruntime as ort

    from homr.segmentation import config as segnet_config

    providers = list(ort.get_available_providers())
    use_gpu = any(
        provider in providers
        for provider in (
            "CUDAExecutionProvider",
            "ROCMExecutionProvider",
            "CoreMLExecutionProvider",
        )
    )
    sessions: list[dict[str, Any]] = []
    original_session = ort.InferenceSession

    def recorded_session(path_or_bytes: Any, *args: Any, **kwargs: Any) -> Any:
        session = original_session(path_or_bytes, *args, **kwargs)
        sessions.append(
            {
                "model": str(path_or_bytes),
                "requested_providers": repr(kwargs.get("providers")),
                "active_providers": list(session.get_providers()),
            }
        )
        return session

    ort.InferenceSession = recorded_session
    stem = image.stem
    image_run_dir = output_root / "batch" / stem
    image_run_dir.mkdir(parents=True, exist_ok=False)
    try:
        segnet = _ensure_segnet_model(segnet_config, use_gpu=use_gpu)
        inference_image, proxy_x, proxy_y, original = _make_proxy(image, image_run_dir)
        detector_started = time.perf_counter()
        bar_line_boxes, notehead_mask, staff_mask, clef_mask = _detect_material(
            inference_image, use_gpu=use_gpu
        )
        detector_core_sec = time.perf_counter() - detector_started

        seg_shape = tuple(int(value) for value in staff_mask.shape[:2])
        mapped = _map_predictions(bar_line_boxes, inference_image, seg_shape, proxy_x, proxy_y)
        height, width = original.shape[:2]
        notehead_resized = cv2.resize(
            (notehead_mask * 255).astype(np.uint8),
            (width, height),
            interpolation=cv2.INTER_NEAREST,
        )
        staff_resized = cv2.resize(
            (staff_mask * 255).astype(np.uint8),
            (width, height),
            interpolation=cv2.INTER_NEAREST,
        )
        clef_resized = cv2.resize(
            (clef_mask * 255).astype(np.uint8),
            (width, height),
            interpolation=cv2.INTER_NEAREST,
        )
        mapped = _postprocess(image, original, mapped, notehead_resized)
        detection = _save_homr_results(
            image, image_run_dir, mapped, notehead_resized, staff_resized
        )
        clef_path = image_run_dir / f"{stem}_clef_mask.png"
        if not cv2.imwrite(str(clef_path), clef_resized):
            raise RuntimeError(f"Failed to write clef mask: {clef_path}")
        _assert_excluded_modules_absent("detector inference and postprocessing")
    finally:
        ort.InferenceSession = original_session

    payload = {
        "schema_version": "issue294.upstream_detector_material.v6",
        "status": "completed",
        "scope": "segnet_barline_staff_clef_material_only_pre_transformer",
        "historical_detector_artifact_runtime_input": False,
        "image": str(image),
        "homr": {
            "source": str(homr_source.resolve()),
            "commit": actual_commit,
            "commit_verification": "read_git_metadata_without_git_executable",
            "module": str(imported_homr),
        },
        "preflight": preflight_payload,
        "postrun_optional_modules_imported": _excluded_imports(),
        "runtime": {
            "python": sys.executable,
            "python_version": platform.python_version(),
            "numpy_version": np.__version__,
            "opencv_version": cv2.__version__,
            "onnxruntime_version": ort.__version__,
            "providers": providers,
            "gpu_requested": use_gpu,
            "compatibility_mode": (
                "upstream_source_detector_material_on_existing_pipeline_runtime; "
                "not yet an upstream-supported full maintained-runtime gate"
            ),
        },
        "models": {
            "segnet": {"path": str(segnet), "sha256": sha256(segnet), "executed": True},
            "transformer_encoder": {
                "path": None,
                "executed": False,
                "imported": False,
                "downloaded_by_this_worker": False,
            },
            "transformer_decoder": {
                "path": None,
                "executed": False,
                "imported": False,
                "downloaded_by_this_worker": False,
            },
        },
        "onnx_sessions": sessions,
        "timings_sec": {
            "detector_core": detector_core_sec,
            "worker_total": time.perf_counter() - started,
            "timing_comparable_to_full_A_or_B": False,
        },
        "artifacts": {
            "detections": str(detection),
            "staff_mask": str(image_run_dir / f"{stem}_staff_mask.png"),
            "notehead_mask": str(image_run_dir / f"{stem}_notehead_mask.png"),
            "clef_mask": str(clef_path),
            "proxy": str(inference_image) if inference_image != image else None,
        },
        "coordinate_checks": {
            "original_shape_wh": [int(original.shape[1]), int(original.shape[0])],
            "staff_mask_shape_wh": _shape(image_run_dir / f"{stem}_staff_mask.png"),
            "notehead_mask_shape_wh": _shape(image_run_dir / f"{stem}_notehead_mask.png"),
            "clef_mask_shape_wh": _shape(clef_path),
        },
    }
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--homr-source", type=Path, required=True)
    parser.add_argument("--homr-commit", required=True)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--image", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--result", type=Path)
    args = parser.parse_args()
    try:
        if args.preflight_only:
            payload = preflight(args.homr_source, args.homr_commit)
            print(json.dumps(payload, ensure_ascii=False))
            return 0
        if args.image is None or args.output_root is None or args.result is None:
            parser.error(
                "--image, --output-root, and --result are required unless --preflight-only"
            )
        payload = run(
            args.image,
            args.homr_source,
            args.homr_commit,
            args.output_root,
            args.result,
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
            {
                "status": "completed",
                "result": str(args.result.resolve()),
                "scope": payload["scope"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
