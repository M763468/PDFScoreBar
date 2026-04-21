"""In-process CNN scoring for probe candidates."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import cv2
import numpy as np
import torch
from PIL import Image
from torchvision import models, transforms
from tqdm import tqdm

from src.common.barline_evaluation import barline_iou, barline_vertical_overlap
from src.pipeline.core.run_ids import build_probe_run_id
from src.pipeline.probe_detector.bands import build_row_stats, staff_bands_from_mask
from src.pipeline.steps.filters import filter_by_staff_overlap
from src.pipeline.steps.probe_scan import _build_staff_mask_map, _load_bands_for_image

logger = logging.getLogger(__name__)

IMG_SIZE = (256, 128)  # H, W
MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]


class GPUNormalize(torch.nn.Module):
    def __init__(self, mean: Sequence[float], std: Sequence[float]) -> None:
        super().__init__()
        self.register_buffer("mean", torch.tensor(mean).view(1, 3, 1, 1))
        self.register_buffer("std", torch.tensor(std).view(1, 3, 1, 1))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return (x - self.mean) / self.std


def _resolve_model_path(model_path: Path) -> Path:
    if model_path.exists():
        return model_path
    candidates = list(Path("experiments/cnn_classifier").rglob("best_model.pth"))
    if candidates:
        return candidates[0]
    raise FileNotFoundError(f"Model not found: {model_path}")


def _load_model(model_path: Path, device: torch.device) -> torch.nn.Module:
    model = models.resnet18(weights=None)
    in_features = model.fc.in_features
    model.fc = torch.nn.Linear(in_features, 1)
    state_dict = torch.load(model_path, map_location=device)

    # Handle torch.compile prefix
    if any(k.startswith("_orig_mod.") for k in state_dict.keys()):
        state_dict = {k.replace("_orig_mod.", ""): v for k, v in state_dict.items()}

    model.load_state_dict(state_dict)
    model.to(device)
    model.eval()
    return model


def _crop_size_from_bbox(
    box: Sequence[float],
    scale: float = 3.0,
    aspect_ratio: float = 0.5,
    min_h: int = 48,
    max_h: int = 256,
    min_w: int = 16,
    max_w: int = 128,
) -> Tuple[int, int]:
    x1, y1, x2, y2 = box
    bbox_h = max(1.0, abs(y2 - y1))
    crop_h = int(round(bbox_h * scale))
    crop_h = max(min_h, min(max_h, crop_h))
    crop_w = int(round(crop_h * aspect_ratio))
    crop_w = max(min_w, min(max_w, crop_w))
    return crop_w, crop_h


def _center_crop(img: np.ndarray, cx: int, cy: int, crop_w: int, crop_h: int) -> np.ndarray:
    w_half = crop_w // 2
    h_half = crop_h // 2
    cy1 = max(0, cy - h_half)
    cy2 = min(img.shape[0], cy + h_half)
    cx1 = max(0, cx - w_half)
    cx2 = min(img.shape[1], cx + w_half)
    crop = img[cy1:cy2, cx1:cx2]
    if crop.shape[0] < crop_h or crop.shape[1] < crop_w:
        pad_y1 = h_half - (cy - cy1)
        pad_y2 = h_half - (cy2 - cy)
        pad_x1 = w_half - (cx - cx1)
        pad_x2 = w_half - (cx2 - cx)
        crop = cv2.copyMakeBorder(
            crop, pad_y1, pad_y2, pad_x1, pad_x2, cv2.BORDER_CONSTANT, value=[255, 255, 255]
        )
    return crop


def _compute_bbox_ink_center_x(
    img: np.ndarray,
    box: Sequence[float],
    *,
    min_aspect_ratio: float = 3.0,
    apply_if_width_le_unit_ratio: float = 1.0,
    mask_ratio: float = 0.85,
    max_shift_unit_ratio: float = 0.35,
) -> int | None:
    """Estimate a better crop X-center from the bbox-local ink profile.

    Intended for narrow, tall vertical candidates where the barline can sit near a bbox edge.
    """
    if img is None or len(box) != 4:
        return None
    x1, y1, x2, y2 = [int(v) for v in box]
    img_h, img_w = img.shape[:2]
    bx1 = max(0, min(img_w - 1, min(x1, x2)))
    bx2 = max(0, min(img_w, max(x1, x2)))
    by1 = max(0, min(img_h - 1, min(y1, y2)))
    by2 = max(0, min(img_h, max(y1, y2)))
    if bx2 <= bx1 or by2 <= by1:
        return None

    w = bx2 - bx1
    h = by2 - by1
    if w <= 0 or h <= 0:
        return None
    if h / max(1, w) < min_aspect_ratio:
        return None

    # Estimate unit_size (staff spacing) from box height
    unit_size = max(1.0, h / 4.0)
    if w > unit_size * apply_if_width_le_unit_ratio:
        return None

    crop = img[by1:by2, bx1:bx2]
    if crop.size == 0:
        return None
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
    profile = (255.0 - gray.astype(np.float32)).sum(axis=0)
    if profile.size == 0:
        return None
    pmax = float(profile.max())
    if pmax <= 0:
        return None

    active = np.where(profile >= pmax * mask_ratio)[0]
    if active.size == 0:
        return None

    local_center = float(active.mean())
    base_local_center = (w - 1) / 2.0
    shift = local_center - base_local_center
    max_shift = max(1.0, unit_size * max_shift_unit_ratio)
    shift = float(np.clip(shift, -max_shift, max_shift))
    if abs(shift) < 0.5:
        return None
    return int(round((x1 + x2) / 2.0 + shift))


def apply_nms(
    scored_results: List[Dict[str, Any]], iou_threshold: float = 0.5, x_dist_unit_ratio: float = 1.0
) -> List[Dict[str, Any]]:
    """Apply greedy suppression to scored results.

    Uses a combination of IoU and horizontal distance (scale-aware) to handle thin vertical lines.
    """
    if not scored_results:
        return []

    # Sort by score descending
    sorted_items = sorted(scored_results, key=lambda x: x["score"], reverse=True)
    kept: List[Dict[str, Any]] = []

    while sorted_items:
        best = sorted_items.pop(0)
        kept.append(best)
        remaining = []
        b_x = (best["bbox"][0] + best["bbox"][2]) / 2.0
        # derive scale from the 'best' box height
        b_h = max(1.0, float(abs(best["bbox"][3] - best["bbox"][1])))
        unit_size = max(1.0, b_h / 4.0)
        x_dist_threshold = unit_size * x_dist_unit_ratio
        for item in sorted_items:
            suppressed = False
            # 1. IoU check
            iou = barline_iou(best["bbox"], item["bbox"])
            if iou >= iou_threshold:
                suppressed = True

            # 2. X-distance check (if vertical overlap is high)
            if not suppressed:
                i_x = (item["bbox"][0] + item["bbox"][2]) / 2.0
                dist = abs(b_x - i_x)
                vov = barline_vertical_overlap(best["bbox"], item["bbox"])

                if dist < x_dist_threshold and vov >= 0.5:
                    suppressed = True

            if suppressed:
                item["score"] = 0.0
                continue
            remaining.append(item)
        sorted_items = remaining

    return kept


def _score_directory(
    *,
    run_dir: Path,
    image_path: Path,
    model: torch.nn.Module,
    gpu_norm: GPUNormalize,
    threshold: float,
    device: torch.device,
    batch_size: int,
    staff_mask_path: Optional[Path] = None,
    bands_from: Optional[Path] = None,
    current_score_name: Optional[str] = None,
    staff_vov_threshold: float = 0.5,
    crop_recenter_on_bbox_ink: bool = False,
    crop_recenter_max_shift_unit_ratio: float = 0.35,
    input_image_scale: float = 1.0,
) -> bool:
    candidates_path = run_dir / "pipeline2_no_peak_candidates.json"
    if not candidates_path.exists():
        logger.warning("Candidates path missing: %s", candidates_path)
        return False

    try:
        candidates = json.loads(candidates_path.read_text())
    except json.JSONDecodeError:
        logger.warning("Invalid JSON in candidates file: %s", candidates_path)
        return False
    if not isinstance(candidates, list):
        logger.warning("Invalid candidates payload: %s", candidates_path)
        return False

    if not candidates:
        (run_dir / "pipeline2_no_peak_scored.json").write_text(json.dumps([], indent=2))
        (run_dir / "pipeline2_no_peak_filtered_cnn.json").write_text(json.dumps([], indent=2))
        return True

    img = cv2.imread(str(image_path))
    if img is None:
        logger.warning("Failed to load image: %s", image_path)
        return False

    # --- Handle SR Downscaling for CNN ---
    # If using an SR image, downscale it back to original resolution (e.g. 300DPI equivalent)
    # using INTER_AREA to avoid aliasing and match training features.
    if input_image_scale > 1.0:
        h, w = img.shape[:2]
        new_h = int(round(h / input_image_scale))
        new_w = int(round(w / input_image_scale))
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        # Rescale candidates back to downscaled image coordinate space
        candidates = [[v / input_image_scale for v in box] for box in candidates]

    # --- Resolve Staff Bands ---
    staff_bands = []
    if staff_mask_path and staff_mask_path.exists():
        mask = cv2.imread(str(staff_mask_path), cv2.IMREAD_GRAYSCALE)
        if mask is not None:
            staff_bands = staff_bands_from_mask(mask)

    resize_filter = Image.Resampling.BILINEAR if hasattr(Image, "Resampling") else Image.BILINEAR
    to_tensor = transforms.ToTensor()
    batch_tensors: List[torch.Tensor] = []
    valid_boxes: List[List[float]] = []

    for box in candidates:
        if not isinstance(box, list) or len(box) != 4:
            continue
        x1, y1, x2, y2 = box
        cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)

        if crop_recenter_on_bbox_ink:
            cx_adjusted = _compute_bbox_ink_center_x(
                img, box, max_shift_unit_ratio=crop_recenter_max_shift_unit_ratio
            )
            if cx_adjusted is not None:
                cx = cx_adjusted

        cw, ch = _crop_size_from_bbox(box)
        crop = _center_crop(img, cx, cy, cw, ch)
        crop_pil = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        tensor = to_tensor(crop_pil.resize((IMG_SIZE[1], IMG_SIZE[0]), resize_filter))
        batch_tensors.append(tensor)
        valid_boxes.append(box)

    if not batch_tensors:
        (run_dir / "pipeline2_no_peak_scored.json").write_text(json.dumps([], indent=2))
        (run_dir / "pipeline2_no_peak_filtered_cnn.json").write_text(json.dumps([], indent=2))
        return True

    score_chunks: List[np.ndarray] = []
    for i in range(0, len(batch_tensors), batch_size):
        chunk = batch_tensors[i : i + batch_size]
        batch_t = torch.stack(chunk).to(device)
        batch_t = gpu_norm(batch_t)
        with torch.no_grad():
            logits = model(batch_t)
            score_chunks.append(torch.sigmoid(logits).cpu().numpy().flatten())
    scores = np.concatenate(score_chunks)

    scored_results = []
    candidate_objects_for_filter = []
    for idx, box in enumerate(valid_boxes):
        score = float(scores[idx])
        item = {"bbox": box, "score": score}
        scored_results.append(item)
        if score >= threshold:
            candidate_objects_for_filter.append(item)

    # --- Apply Geometric Filtering ---
    if (staff_mask_path or bands_from) and candidate_objects_for_filter:
        staff_bands = []
        if staff_mask_path and staff_mask_path.exists():
            mask = cv2.imread(str(staff_mask_path), cv2.IMREAD_GRAYSCALE)
            if mask is not None:
                staff_bands = staff_bands_from_mask(mask)

        if not staff_bands and bands_from:
            existing_boxes = _load_bands_for_image(
                bands_from=bands_from,
                current_score_name=current_score_name or "",
                stem=image_path.stem,
            )
            if existing_boxes:
                staff_bands_stats = build_row_stats(
                    existing_boxes, cluster_max_dist=None, min_row_count=1
                )
                staff_bands = [(int(r["top"]), int(r["bottom"])) for r in staff_bands_stats]

        if staff_bands:
            # Suppress items that fail staff VOV
            kept_items = filter_by_staff_overlap(
                candidate_objects_for_filter, staff_bands, vov_threshold=staff_vov_threshold
            )
            kept_indices = {id(item) for item in kept_items}
            for item in candidate_objects_for_filter:
                if id(item) not in kept_indices:
                    item["score"] = 0.0

    apply_nms(candidate_objects_for_filter)

    filtered_boxes = [
        item["bbox"] for item in candidate_objects_for_filter if item["score"] >= threshold
    ]

    (run_dir / "pipeline2_no_peak_scored.json").write_text(json.dumps(scored_results, indent=2))
    (run_dir / "pipeline2_no_peak_filtered_cnn.json").write_text(
        json.dumps(filtered_boxes, indent=2)
    )
    return True


def run_cnn_scoring_batch(
    *,
    probe_output_root: Path,
    images: Iterable[Path],
    model_path: Path,
    threshold: float,
    score_name: Optional[str] = None,
    batch_size: int = 64,
    staff_mask_dir: Optional[Path] = None,
    bands_from: Optional[Path] = None,
    staff_vov_threshold: float = 0.5,
    crop_recenter_on_bbox_ink: bool = False,
    crop_recenter_max_shift_unit_ratio: float = 0.35,
    input_image_scale: float = 1.0,
    candidate_rescale_factor: Optional[float] = None,
) -> int:
    """Run CNN scoring for all probe output dirs with one model load."""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    resolved_model_path = _resolve_model_path(model_path)
    model = _load_model(resolved_model_path, device)
    gpu_norm = GPUNormalize(MEAN, STD).to(device)

    staff_mask_map = _build_staff_mask_map(staff_mask_dir)

    processed = 0
    for img_path in tqdm(images, desc="CNN Scoring", unit="page"):
        run_id = build_probe_run_id(img_path, score_name=score_name)
        run_dir = probe_output_root / run_id
        if _score_directory(
            run_dir=run_dir,
            image_path=img_path,
            model=model,
            gpu_norm=gpu_norm,
            threshold=threshold,
            device=device,
            batch_size=batch_size,
            staff_mask_path=staff_mask_map.get(img_path.stem),
            bands_from=bands_from,
            current_score_name=score_name,
            staff_vov_threshold=staff_vov_threshold,
            crop_recenter_on_bbox_ink=crop_recenter_on_bbox_ink,
            crop_recenter_max_shift_unit_ratio=crop_recenter_max_shift_unit_ratio,
            input_image_scale=input_image_scale,
        ):
            processed += 1
    return processed
