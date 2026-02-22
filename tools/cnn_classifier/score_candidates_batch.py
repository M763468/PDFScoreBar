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

    # Prepare batch
    batch_tensors = []

    for box in candidates:
        if len(box) != 4:
            continue
        x1, y1, x2, y2 = box
        cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
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
        ):
            count += 1

    print(f"Completed {count} pages.")


if __name__ == "__main__":
    main()
