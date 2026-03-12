import argparse
import json
import os
from pathlib import Path

import cv2
import numpy as np
import torch
import yaml
from PIL import Image
from torchvision import models, transforms
from tqdm import tqdm

from src.pipeline.probe_detector.bands import build_row_stats, staff_bands_from_mask
from src.pipeline.steps.filters import filter_by_staff_overlap
from src.pipeline.utils.wide_split_utils import (
    estimate_unit_size_from_box_height,
)
from src.pipeline.utils.wide_split_utils import (
    split_wide_candidates as split_wide_candidates_util,
)

# --- Config ---
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
IMG_SIZE = (256, 128)  # H, W
MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]


def load_config_file(config_path: Path):
    with config_path.open("r") as f:
        if config_path.suffix.lower() in {".yaml", ".yml"}:
            data = yaml.safe_load(f)
        else:
            data = json.load(f)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a mapping/dict: {config_path}")
    return data


class GPUNormalize(torch.nn.Module):
    def __init__(self, mean, std):
        super().__init__()
        self.register_buffer("mean", torch.tensor(mean).view(1, 3, 1, 1))
        self.register_buffer("std", torch.tensor(std).view(1, 3, 1, 1))

    def forward(self, x):
        return (x - self.mean) / self.std


def get_model(model_path, model_name="resnet18"):
    if model_name == "resnet18":
        model = models.resnet18(weights=None)
        in_features = model.fc.in_features
        model.fc = torch.nn.Linear(in_features, 1)
    else:
        raise ValueError(f"Unknown model: {model_name}")

    state_dict = torch.load(model_path, map_location=DEVICE)
    # Handle checkpoints saved from torch.compile(model), which prefixes keys with "_orig_mod."
    if any(k.startswith("_orig_mod.") for k in state_dict.keys()):
        state_dict = {
            (k[len("_orig_mod.") :] if k.startswith("_orig_mod.") else k): v
            for k, v in state_dict.items()
        }
    model.load_state_dict(state_dict)
    model.to(DEVICE)
    model.eval()
    return model


def crop_size_from_bbox(
    box, scale=3.0, aspect_ratio=0.5, min_h=48, max_h=1024, min_w=16, max_w=512
):
    x1, y1, x2, y2 = box
    bbox_h = max(1.0, abs(y2 - y1))
    crop_h = int(round(bbox_h * scale))
    crop_h = max(min_h, min(max_h, crop_h))
    crop_w = int(round(crop_h * aspect_ratio))
    crop_w = max(min_w, min(max_w, crop_w))
    return crop_w, crop_h


def center_crop(img, cx, cy, crop_w, crop_h):
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
    img,
    box,
    *,
    min_aspect_ratio=3.0,
    apply_if_width_ge_unit_ratio=0.0,
    apply_if_width_le_unit_ratio=1.0,
    mask_ratio=0.85,
    max_shift_unit_ratio=0.35,
):
    """Estimate a better crop X-center from the bbox-local ink profile.

    Intended for narrow, tall vertical candidates where the barline can sit near a bbox edge.
    Returns an absolute X center or None (no adjustment).
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
    if h / max(1, w) < float(min_aspect_ratio):
        return None

    unit_size = estimate_unit_size_from_box_height(box)
    min_apply_w = max(1, int(round(unit_size * float(apply_if_width_ge_unit_ratio))))
    max_apply_w = max(2, int(round(unit_size * float(apply_if_width_le_unit_ratio))))
    if w < min_apply_w or w > max_apply_w:
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

    active = np.where(profile >= pmax * float(mask_ratio))[0]
    if active.size == 0:
        return None

    local_center = float(active.mean())
    base_local_center = (w - 1) / 2.0
    shift = local_center - base_local_center
    max_shift = max(1.0, unit_size * float(max_shift_unit_ratio))
    shift = float(np.clip(shift, -max_shift, max_shift))
    if abs(shift) < 0.5:
        return None
    return int(round((x1 + x2) / 2.0 + shift))


def parse_eval2_context(log_dir: Path, log_root: Path):
    """Parse score/page context from either nested or legacy flat log layouts.

    Supported layouts:
    - nested: <log_root>/<score>/<page>
    - flat:   <log_root>/eval2_<score>_<page>
    """
    try:
        rel_parts = log_dir.relative_to(log_root).parts
    except ValueError:
        rel_parts = ()

    if len(rel_parts) == 2:
        score_name, page_name = rel_parts
        if page_name.startswith("page_"):
            return score_name, page_name

    parts = log_dir.name.split("_")
    if "page" not in parts:
        return None
    page_idx = parts.index("page")
    score_start = 1 if parts and parts[0] == "eval2" else 0
    if page_idx <= score_start:
        return None
    score_name = "_".join(parts[score_start:page_idx])
    page_name = "_".join(parts[page_idx:])
    if not score_name or not page_name.startswith("page_"):
        return None
    return score_name, page_name


def resolve_image_path(score_name: str, page_name: str, images_root: Path):
    image_path = images_root / score_name / f"{page_name}.png"
    return image_path if image_path.exists() else None


def process_dir(
    log_dir,
    log_root,
    images_root,
    model,
    gpu_norm,
    threshold=0.5,
    candidate_filename="pipeline2_no_peak_candidates.json",
    scored_filename="pipeline2_no_peak_scored.json",
    filtered_filename="pipeline2_no_peak_filtered_cnn.json",
    overwrite=False,
    split_wide_candidates=False,
    split_min_width_unit_ratio=1.0,
    split_box_width_unit_ratio=0.8,
    split_peak_distance_unit_ratio=0.4,
    split_peak_prominence_ratio=0.15,
    recenter_wide_single_peak=False,
    emit_merged_two_peak_box=False,
    merged_two_peak_pad_unit_ratio=0.4,
    crop_recenter_on_bbox_ink=False,
    crop_recenter_min_aspect_ratio=3.0,
    crop_recenter_apply_if_width_ge_unit_ratio=0.0,
    crop_recenter_apply_if_width_le_unit_ratio=1.0,
    crop_recenter_mask_ratio=0.85,
    crop_recenter_max_shift_unit_ratio=0.35,
    staff_mask_map: dict[str, Path] | None = None,
    bands_from: Path | None = None,
    staff_vov_threshold: float = 0.5,
):
    scored_json_path = log_dir / scored_filename
    if scored_json_path.exists() and not overwrite:
        return True  # Already processed

    candidates_path = log_dir / candidate_filename
    if not candidates_path.exists():
        print(f"Candidates file missing: {candidates_path}")
        return False

    parsed = parse_eval2_context(log_dir, log_root)
    if not parsed:
        print(f"Skipping {log_dir}: could not parse score/page context")
        return False
    score_name, page_num = parsed
    image_path = resolve_image_path(score_name, page_num, images_root)
    if image_path is None:
        print(
            f"Error: Image not found for {score_name}/{page_num} under {images_root} "
            f"(from {log_dir})"
        )
        return False

    with open(candidates_path, "r") as f:
        candidates = json.load(f)

    print(f"DEBUG: Processing {len(candidates)} candidates for {image_path}")

    if not candidates:
        # Persist empty outputs so downstream evaluation does not skip this page.
        with open(log_dir / scored_filename, "w") as f:
            json.dump([], f, indent=2)
        with open(log_dir / filtered_filename, "w") as f:
            json.dump([], f, indent=2)
        return True

    img = cv2.imread(str(image_path))
    if img is None:
        print(f"Failed to load image: {image_path}")
        return False

    # --- Resolve Staff Bands ---
    staff_bands = []
    if staff_mask_map and page_num in staff_mask_map:
        mask = cv2.imread(str(staff_mask_map[page_num]), cv2.IMREAD_GRAYSCALE)
        if mask is not None:
            staff_bands = staff_bands_from_mask(mask)

    if split_wide_candidates:
        candidates, split_stats = split_wide_candidates_util(
            boxes=candidates,
            img=img,
            min_split_width_unit_ratio=split_min_width_unit_ratio,
            split_box_width_unit_ratio=split_box_width_unit_ratio,
            split_peak_distance_unit_ratio=split_peak_distance_unit_ratio,
            peak_prominence_ratio=split_peak_prominence_ratio,
            require_exactly_two_peaks=True,
            recenter_single_peak=recenter_wide_single_peak,
            emit_merged_two_peak_box=emit_merged_two_peak_box,
            merged_two_peak_pad_unit_ratio=merged_two_peak_pad_unit_ratio,
            keep_original_when_not_split=True,
        )
    else:
        candidates = [tuple(int(v) for v in c) for c in candidates]
        split_stats = {"split_applied": 0, "split_examined": 0}
    if split_wide_candidates and split_stats["split_applied"] > 0:
        print(
            f"Split wide candidates for {score_name}/{page_num}: "
            f"{split_stats['split_applied']} / {split_stats['split_examined']}"
        )

    # Prepare batch
    batch_tensors = []

    for box in candidates:
        if len(box) != 4:
            continue
        x1, y1, x2, y2 = box
        cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
        if crop_recenter_on_bbox_ink:
            cx_adjusted = _compute_bbox_ink_center_x(
                img,
                box,
                min_aspect_ratio=crop_recenter_min_aspect_ratio,
                apply_if_width_ge_unit_ratio=crop_recenter_apply_if_width_ge_unit_ratio,
                apply_if_width_le_unit_ratio=crop_recenter_apply_if_width_le_unit_ratio,
                mask_ratio=crop_recenter_mask_ratio,
                max_shift_unit_ratio=crop_recenter_max_shift_unit_ratio,
            )
            if cx_adjusted is not None:
                cx = cx_adjusted
        cw, ch = crop_size_from_bbox(box)
        crop = center_crop(img, cx, cy, cw, ch)

        if len(batch_tensors) == 0:
            print(f"DEBUG: First crop cx={cx}, cy={cy}, cw={cw}, ch={ch} for img {img.shape}")
            cv2.imwrite(f"artifacts/debug_crop_{cx}_{cy}.png", crop)

        crop_pil = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        # PIL resize expects (Width, Height). IMG_SIZE is (Height, Width).
        # So we pass (IMG_SIZE[1], IMG_SIZE[0])
        tensor = transforms.ToTensor()(crop_pil.resize((IMG_SIZE[1], IMG_SIZE[0]), Image.BILINEAR))
        batch_tensors.append(tensor)

    if not batch_tensors:
        # Save empty results to allow evaluation to proceed
        with open(log_dir / scored_filename, "w") as f:
            json.dump([], f, indent=2)
        with open(log_dir / filtered_filename, "w") as f:
            json.dump([], f, indent=2)
        return True

    # Prepare batch and run inference in smaller chunks
    scores_list = []
    batch_size = 64

    for i in range(0, len(batch_tensors), batch_size):
        chunk = batch_tensors[i : i + batch_size]
        batch_t = torch.stack(chunk).to(DEVICE)
        batch_t = gpu_norm(batch_t)

        with torch.no_grad():
            logits = model(batch_t)
            chunk_scores = torch.sigmoid(logits).cpu().numpy().flatten()
            scores_list.append(chunk_scores)

    scores = np.concatenate(scores_list)
    print(
        f"DEBUG: Score stats for {log_dir.name}: max={scores.max():.4f}, min={scores.min():.4f}, mean={scores.mean():.4f}, count={len(scores)}"
    )

    scored_results = []
    candidate_objects_for_filter = []

    for i, box in enumerate(candidates):
        score = float(scores[i])
        item = {"bbox": box, "score": score}
        scored_results.append(item)
        if score > threshold:
            candidate_objects_for_filter.append(item)

    # --- Apply Geometric Filtering ---
    if (staff_mask_map or bands_from) and scored_results:
        staff_bands = []
        if staff_mask_map and page_num in staff_mask_map:
            mask = cv2.imread(str(staff_mask_map[page_num]), cv2.IMREAD_GRAYSCALE)
            if mask is not None:
                staff_bands = staff_bands_from_mask(mask)

        if not staff_bands and bands_from:
            # Resolve row stats if mask was not used
            from src.pipeline.steps.probe_scan import _load_bands_for_image

            existing_boxes = _load_bands_for_image(
                bands_from=bands_from,
                current_score_name=score_name,
                stem=page_num,
            )
            if existing_boxes:
                staff_bands_stats = build_row_stats(
                    existing_boxes, cluster_max_dist=None, min_row_count=1
                )
                staff_bands = [(int(r["top"]), int(r["bottom"])) for r in staff_bands_stats]

        if staff_bands:
            # Suppress candidates that fail the geometric filter
            to_geo_filter = [item for item in scored_results if item["score"] >= threshold]
            if to_geo_filter:
                kept_items = filter_by_staff_overlap(
                    to_geo_filter, staff_bands, vov_threshold=staff_vov_threshold
                )
                kept_indices = {id(item) for item in kept_items}
                for item in to_geo_filter:
                    if id(item) not in kept_indices:
                        item["score"] = 0.0

    filtered_boxes = [item["bbox"] for item in scored_results if item["score"] >= threshold]

    # Save
    with open(log_dir / scored_filename, "w") as f:
        json.dump(scored_results, f, indent=2)

    with open(log_dir / filtered_filename, "w") as f:
        json.dump(filtered_boxes, f, indent=2)

    return True


def _build_parser(pre_parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(parents=[pre_parser])
    parser.add_argument("--logs", default="logs/hybrid_generalization")
    parser.add_argument(
        "--model", default="experiments/cnn_classifier/checkpoints/best_model.pth"
    )  # Adjust path if needed
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--images-root", default="data/evaluation2/images")
    parser.add_argument("--candidate-filename", default="pipeline2_no_peak_candidates.json")
    parser.add_argument("--scored-filename", default="pipeline2_no_peak_scored.json")
    parser.add_argument("--filtered-filename", default="pipeline2_no_peak_filtered_cnn.json")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Recompute scored/filtered outputs even if files already exist.",
    )
    parser.add_argument(
        "--split-wide-candidates",
        action="store_true",
        help="Try splitting wide double/end-bar-like candidates into two thin boxes before scoring.",
    )
    parser.add_argument("--split-min-width-unit-ratio", type=float, default=1.0)
    parser.add_argument("--split-box-width-unit-ratio", type=float, default=0.8)
    parser.add_argument("--split-peak-distance-unit-ratio", type=float, default=0.4)
    parser.add_argument("--split-peak-prominence-ratio", type=float, default=0.15)
    parser.add_argument(
        "--recenter-wide-single-peak",
        action="store_true",
        help="For wide candidates with a single strong ink peak, recenter and narrow bbox before scoring.",
    )
    parser.add_argument(
        "--emit-merged-two-peak-box",
        action="store_true",
        help="When splitting a wide two-peak candidate, also emit a normalized merged bbox.",
    )
    parser.add_argument("--merged-two-peak-pad-unit-ratio", type=float, default=0.4)
    parser.add_argument(
        "--crop-recenter-on-bbox-ink",
        action="store_true",
        help="Recenter crop X using bbox-local ink profile for narrow/tall candidates.",
    )
    parser.add_argument("--crop-recenter-min-aspect-ratio", type=float, default=3.0)
    parser.add_argument("--crop-recenter-apply-if-width-ge-unit-ratio", type=float, default=0.0)
    parser.add_argument("--crop-recenter-apply-if-width-le-unit-ratio", type=float, default=1.0)
    parser.add_argument("--crop-recenter-mask-ratio", type=float, default=0.85)
    parser.add_argument("--crop-recenter-max-shift-unit-ratio", type=float, default=0.35)
    parser.add_argument("--staff-mask-dir", default=None, help="Directory containing staff masks.")
    parser.add_argument("--bands-from", default=None, help="Source for staff bands (json or dir).")
    parser.add_argument("--staff-vov-threshold", type=float, default=0.5)
    return parser


def _resolve_model_path(model_path: str | os.PathLike[str]) -> str | None:
    model_path = str(model_path)
    if not os.path.exists(model_path):
        # Fallback search
        candidates = list(Path("experiments/cnn_classifier").rglob("best_model.pth"))
        if candidates:
            model_path = str(candidates[0])
            print(f"Resolved model to {model_path}")
            return model_path
        print("Model not found!")
        return None
    return model_path


def _find_candidate_dirs(log_root: Path, candidate_filename: str) -> list[Path]:
    # Support both flat layout (<run_dir>/pipeline2_no_peak_candidates.json)
    # and nested eval2 layout (<score>/<page>/pipeline2_no_peak_candidates.json).
    candidate_dirs = []
    for d in sorted([d for d in log_root.iterdir() if d.is_dir()]):
        if (d / candidate_filename).exists():
            candidate_dirs.append(d)
            continue
        nested = sorted(
            [p for p in d.iterdir() if p.is_dir() and (p / candidate_filename).exists()]
        )
        candidate_dirs.extend(nested)
    return candidate_dirs


def run_scoring_batch(
    *,
    logs: str | os.PathLike[str],
    model: str | os.PathLike[str],
    threshold: float = 0.5,
    images_root: str | os.PathLike[str] = "data/evaluation2/images",
    candidate_filename: str = "pipeline2_no_peak_candidates.json",
    scored_filename: str = "pipeline2_no_peak_scored.json",
    filtered_filename: str = "pipeline2_no_peak_filtered_cnn.json",
    overwrite: bool = False,
    split_wide_candidates: bool = False,
    split_min_width_unit_ratio: float = 1.0,
    split_box_width_unit_ratio: float = 0.8,
    split_peak_distance_unit_ratio: float = 0.4,
    split_peak_prominence_ratio: float = 0.15,
    recenter_wide_single_peak: bool = False,
    emit_merged_two_peak_box: bool = False,
    merged_two_peak_pad_unit_ratio: float = 0.4,
    crop_recenter_on_bbox_ink: bool = False,
    crop_recenter_min_aspect_ratio: float = 3.0,
    crop_recenter_apply_if_width_ge_unit_ratio: float = 0.0,
    crop_recenter_apply_if_width_le_unit_ratio: float = 1.0,
    crop_recenter_mask_ratio: float = 0.85,
    crop_recenter_max_shift_unit_ratio: float = 0.35,
    staff_mask_dir: str | os.PathLike[str] | None = None,
    bands_from: str | os.PathLike[str] | None = None,
    staff_vov_threshold: float = 0.5,
) -> int:
    model_path = _resolve_model_path(model)
    if model_path is None:
        return 0

    loaded_model = get_model(model_path)
    gpu_norm = GPUNormalize(MEAN, STD).to(DEVICE)
    log_root = Path(logs)
    images_root = Path(images_root)
    candidate_dirs = _find_candidate_dirs(log_root, candidate_filename)
    print(f"Processing {len(candidate_dirs)} directories...")

    # For staff mask resolution
    staff_mask_map = {}
    if staff_mask_dir:
        staff_mask_dir = Path(staff_mask_dir)
        for path in staff_mask_dir.rglob("*_debug_3_staff.png"):
            stem_key = path.name.replace("_proxy_debug_3_staff.png", "").replace(
                "_debug_3_staff.png", ""
            )
            staff_mask_map[stem_key] = path

    count = 0
    for d in tqdm(candidate_dirs):
        if process_dir(
            d,
            log_root,
            images_root,
            loaded_model,
            gpu_norm,
            threshold=threshold,
            candidate_filename=candidate_filename,
            scored_filename=scored_filename,
            filtered_filename=filtered_filename,
            overwrite=overwrite,
            split_wide_candidates=split_wide_candidates,
            split_min_width_unit_ratio=split_min_width_unit_ratio,
            split_box_width_unit_ratio=split_box_width_unit_ratio,
            split_peak_distance_unit_ratio=split_peak_distance_unit_ratio,
            split_peak_prominence_ratio=split_peak_prominence_ratio,
            recenter_wide_single_peak=recenter_wide_single_peak,
            emit_merged_two_peak_box=emit_merged_two_peak_box,
            merged_two_peak_pad_unit_ratio=merged_two_peak_pad_unit_ratio,
            crop_recenter_on_bbox_ink=crop_recenter_on_bbox_ink,
            crop_recenter_min_aspect_ratio=crop_recenter_min_aspect_ratio,
            crop_recenter_apply_if_width_ge_unit_ratio=crop_recenter_apply_if_width_ge_unit_ratio,
            crop_recenter_apply_if_width_le_unit_ratio=crop_recenter_apply_if_width_le_unit_ratio,
            crop_recenter_mask_ratio=crop_recenter_mask_ratio,
            crop_recenter_max_shift_unit_ratio=crop_recenter_max_shift_unit_ratio,
            staff_mask_map=staff_mask_map,
            bands_from=Path(bands_from) if bands_from else None,
            staff_vov_threshold=staff_vov_threshold,
        ):
            count += 1

    print(f"Completed {count} pages.")
    return count


def main():
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument(
        "--config",
        type=Path,
        help="Path to YAML/JSON config file. CLI args override config values.",
    )
    pre_args, _ = pre_parser.parse_known_args()
    parser = _build_parser(pre_parser)
    if pre_args.config:
        config_values = load_config_file(pre_args.config)
        parser.set_defaults(
            **{k.replace("-", "_"): v for k, v in config_values.items() if k not in {"config"}}
        )

    args = parser.parse_args()
    run_scoring_batch(
        logs=args.logs,
        model=args.model,
        threshold=args.threshold,
        images_root=args.images_root,
        candidate_filename=args.candidate_filename,
        scored_filename=args.scored_filename,
        filtered_filename=args.filtered_filename,
        overwrite=args.overwrite,
        split_wide_candidates=args.split_wide_candidates,
        split_min_width_unit_ratio=args.split_min_width_unit_ratio,
        split_box_width_unit_ratio=args.split_box_width_unit_ratio,
        split_peak_distance_unit_ratio=args.split_peak_distance_unit_ratio,
        split_peak_prominence_ratio=args.split_peak_prominence_ratio,
        recenter_wide_single_peak=args.recenter_wide_single_peak,
        emit_merged_two_peak_box=args.emit_merged_two_peak_box,
        merged_two_peak_pad_unit_ratio=args.merged_two_peak_pad_unit_ratio,
        crop_recenter_on_bbox_ink=args.crop_recenter_on_bbox_ink,
        crop_recenter_min_aspect_ratio=args.crop_recenter_min_aspect_ratio,
        crop_recenter_apply_if_width_ge_unit_ratio=args.crop_recenter_apply_if_width_ge_unit_ratio,
        crop_recenter_apply_if_width_le_unit_ratio=args.crop_recenter_apply_if_width_le_unit_ratio,
        crop_recenter_mask_ratio=args.crop_recenter_mask_ratio,
        crop_recenter_max_shift_unit_ratio=args.crop_recenter_max_shift_unit_ratio,
    )


if __name__ == "__main__":
    main()
