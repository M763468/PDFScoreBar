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


def crop_size_from_bbox(box, scale=3.0, aspect_ratio=0.5, min_h=48, max_h=256, min_w=16, max_w=128):
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


def _estimate_unit_size_from_bbox_height(box):
    # Heuristic: single-staff barline bbox height is roughly ~4 * unit_size.
    # Keeps split thresholds scale-aware without requiring explicit metadata.
    x1, y1, x2, y2 = box
    h = max(1.0, abs(y2 - y1))
    return max(1.0, h / 4.0)


def _extract_x_profile_peaks(
    gray_crop, smooth_window=5, prominence_ratio=0.15, min_peak_distance=3
):
    if gray_crop.size == 0:
        return []
    if len(gray_crop.shape) == 3:
        gray_crop = cv2.cvtColor(gray_crop, cv2.COLOR_BGR2GRAY)
    # Ink is dark => invert then sum over Y to get X profile
    profile = (255.0 - gray_crop.astype(np.float32)).sum(axis=0)
    if profile.size < 3:
        return []
    if smooth_window > 1:
        k = int(max(1, smooth_window))
        if k % 2 == 0:
            k += 1
        kernel = np.ones(k, dtype=np.float32) / k
        profile = np.convolve(profile, kernel, mode="same")
    pmax = float(profile.max()) if profile.size else 0.0
    if pmax <= 0:
        return []
    threshold = pmax * float(prominence_ratio)
    # Local maxima
    idxs = []
    for i in range(1, len(profile) - 1):
        if (
            profile[i] >= threshold
            and profile[i] >= profile[i - 1]
            and profile[i] >= profile[i + 1]
        ):
            idxs.append(i)
    if not idxs:
        return []
    # NMS on peaks by profile height
    idxs = sorted(idxs, key=lambda i: float(profile[i]), reverse=True)
    kept = []
    min_dist = int(max(1, min_peak_distance))
    for i in idxs:
        if all(abs(i - j) >= min_dist for j in kept):
            kept.append(i)
    kept.sort()
    return kept


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

    unit_size = _estimate_unit_size_from_bbox_height(box)
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


def maybe_split_wide_candidates(
    img,
    candidates,
    *,
    enabled=False,
    recenter_single_peak=False,
    emit_merged_two_peak_box=False,
    merged_two_peak_pad_unit_ratio=0.4,
    min_split_width_unit_ratio=1.0,
    split_box_width_unit_ratio=0.8,
    min_peak_distance_unit_ratio=0.4,
    peak_prominence_ratio=0.15,
):
    if not enabled:
        return [tuple(int(v) for v in c) for c in candidates], {
            "split_applied": 0,
            "split_examined": 0,
        }

    out = []
    split_applied = 0
    split_examined = 0
    img_h, img_w = img.shape[:2]

    for raw in candidates:
        if len(raw) != 4:
            continue
        box = tuple(int(v) for v in raw)
        x1, y1, x2, y2 = box
        bx1, bx2 = sorted((max(0, x1), min(img_w - 1, x2)))
        by1, by2 = sorted((max(0, y1), min(img_h - 1, y2)))
        if bx2 <= bx1 or by2 <= by1:
            out.append(box)
            continue

        unit_size = _estimate_unit_size_from_bbox_height(box)
        min_split_width = max(2, int(round(unit_size * float(min_split_width_unit_ratio))))
        width = abs(x2 - x1)
        if width < min_split_width:
            out.append(box)
            continue

        split_examined += 1
        crop = img[by1:by2, bx1:bx2]
        min_peak_distance = max(1, int(round(unit_size * float(min_peak_distance_unit_ratio))))
        peaks = _extract_x_profile_peaks(
            crop,
            prominence_ratio=peak_prominence_ratio,
            min_peak_distance=min_peak_distance,
        )
        # Split only clean 2-peak cases to avoid destabilizing single/repeat cases.
        if len(peaks) != 2:
            if recenter_single_peak and len(peaks) == 1:
                px = peaks[0]
                cx = bx1 + int(px)
                new_w = max(2, int(round(unit_size * float(split_box_width_unit_ratio))))
                nx1 = max(0, int(round(cx - new_w / 2)))
                nx2 = min(img_w - 1, int(round(cx + new_w / 2)))
                out.append((nx1, by1, nx2, by2))
            else:
                out.append(box)
            continue

        # len(peaks) == 2
        new_w = max(2, int(round(unit_size * float(split_box_width_unit_ratio))))
        split_boxes = []
        for px in peaks:
            cx = bx1 + int(px)
            nx1 = max(0, int(round(cx - new_w / 2)))
            nx2 = min(img_w - 1, int(round(cx + new_w / 2)))
            split_boxes.append((nx1, by1, nx2, by2))

        # Only accept if boxes are distinct and ordered.
        if len(split_boxes) == 2 and split_boxes[0] != split_boxes[1]:
            out.extend(split_boxes)
            if emit_merged_two_peak_box:
                pad = max(1, int(round(unit_size * float(merged_two_peak_pad_unit_ratio))))
                peak_xs = [bx1 + int(px) for px in peaks]
                mx1 = max(0, min(peak_xs) - pad)
                mx2 = min(img_w - 1, max(peak_xs) + pad)
                out.append((mx1, by1, mx2, by2))
            split_applied += 1
        else:
            out.append(box)

    # Deduplicate after split
    out = sorted(set(out))
    return out, {"split_applied": split_applied, "split_examined": split_examined}


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

    if not candidates:
        return True  # Processed (empty)

    img = cv2.imread(str(image_path))
    if img is None:
        print(f"Failed to load image: {image_path}")
        return False

    candidates, split_stats = maybe_split_wide_candidates(
        img,
        candidates,
        enabled=split_wide_candidates,
        recenter_single_peak=recenter_wide_single_peak,
        emit_merged_two_peak_box=emit_merged_two_peak_box,
        merged_two_peak_pad_unit_ratio=merged_two_peak_pad_unit_ratio,
        min_split_width_unit_ratio=split_min_width_unit_ratio,
        split_box_width_unit_ratio=split_box_width_unit_ratio,
        min_peak_distance_unit_ratio=split_peak_distance_unit_ratio,
        peak_prominence_ratio=split_peak_prominence_ratio,
    )
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

    scored_results = []
    filtered_boxes = []

    for i, box in enumerate(candidates):
        score = float(scores[i])
        scored_results.append({"bbox": box, "score": score})
        if score > threshold:
            filtered_boxes.append(box)

    # Save
    with open(log_dir / scored_filename, "w") as f:
        json.dump(scored_results, f, indent=2)

    with open(log_dir / filtered_filename, "w") as f:
        json.dump(filtered_boxes, f, indent=2)

    return True


def main():
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument(
        "--config",
        type=Path,
        help="Path to YAML/JSON config file. CLI args override config values.",
    )
    pre_args, _ = pre_parser.parse_known_args()

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

    if pre_args.config:
        config_values = load_config_file(pre_args.config)
        parser.set_defaults(
            **{k.replace("-", "_"): v for k, v in config_values.items() if k not in {"config"}}
        )

    args = parser.parse_args()

    # Verify model path. Usually in experiments/cnn_classifier/checkpoints/
    # Or current best might be elsewhere. User used `cnn_classifier_best.pth` conceptually.
    # Looking at `train.py` might reveal where it saves.
    # Taking a guess at `experiments/cnn_classifier/checkpoints/best_model.pth` or similar.

    if not os.path.exists(args.model):
        # Fallback search
        candidates = list(Path("experiments/cnn_classifier").rglob("best_model.pth"))
        if candidates:
            args.model = str(candidates[0])
            print(f"Resolved model to {args.model}")
        else:
            print("Model not found!")
            return

    model = get_model(args.model)
    gpu_norm = GPUNormalize(MEAN, STD).to(DEVICE)

    log_root = Path(args.logs)
    images_root = Path(args.images_root)
    # Support both flat layout (<run_dir>/pipeline2_no_peak_candidates.json)
    # and nested eval2 layout (<score>/<page>/pipeline2_no_peak_candidates.json).
    candidate_dirs = []
    for d in sorted([d for d in log_root.iterdir() if d.is_dir()]):
        if (d / "pipeline2_no_peak_candidates.json").exists():
            candidate_dirs.append(d)
            continue
        nested = sorted(
            [
                p
                for p in d.iterdir()
                if p.is_dir() and (p / "pipeline2_no_peak_candidates.json").exists()
            ]
        )
        candidate_dirs.extend(nested)

    print(f"Processing {len(candidate_dirs)} directories...")

    count = 0
    for d in tqdm(candidate_dirs):
        if process_dir(
            d,
            log_root,
            images_root,
            model,
            gpu_norm,
            threshold=args.threshold,
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
        ):
            count += 1

    print(f"Completed {count} pages.")


if __name__ == "__main__":
    main()
