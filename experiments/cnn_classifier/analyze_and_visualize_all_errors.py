import collections
import csv
import json
import re
import sys
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms
from tqdm import tqdm

# Add project root to path
sys.path.append(".")

# --- CONFIGURATION ---
WORK_DIR = Path("logs/cnn_barline_classification/training_resnet18_sr_experiment")
DATASET_ROOT = Path("/mnt/d/datasets/cnn_classifier_v1")
TEST_SPLIT_DIR = DATASET_ROOT / "splits" / "test"
METADATA_FILE = DATASET_ROOT / "metadata" / "samples.csv"
MODEL_PATH = WORK_DIR / "cnn_classifier_best.pth"
OUTPUT_DIR = WORK_DIR / "visualizations_classified"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
BATCH_SIZE = 256
IOU_THRESHOLD = 0.5
NEAR_HIT_THRESHOLD_PX = 50

# Local Pages Config (for path resolution)
DEFAULT_PAGES = [
    {
        "name": "page_001",
        "image": "logs/homr_eval/20251229T_gt_rebuild_eval/page_001/page_001.png",
        "gt": "logs/phase6_detector_miss/gt_rebuild/page_001_boxes_sorted.json",
        "preds": "logs/phase5b_confirmed_union_eval/page_001_hybrid_preds.json",
    },
    {
        "name": "page_3",
        "image": "data/evaluation/images/page_3_x4.png",
        "gt": "data/evaluation/annotations/page_003/boxes_sorted_v20260111_x4.json",
        "preds": "data/evaluation/annotations/page_003/expanded_candidates_nopeak_x4.json",
    },
    {
        "name": "page_004",
        "image": "logs/homr_eval/20251229T_gt_rebuild_eval/page_004/page_004.png",
        "gt": "logs/phase6_detector_miss/gt_rebuild/page_004_boxes_sorted.json",
        "preds": "logs/phase5b_confirmed_union_eval/page_004_hybrid_preds.json",
    },
    {
        "name": "page_10",
        "image": "data/training/images/page_10.png",
        "gt": "data/training/annotations/page_010/boxes_sorted_v20260111.json",
        "preds": "data/training/annotations/page_010/expanded_candidates_nopeak.json",
    },
    {
        "name": "page_15",
        "image": "data/training/images/page_15.png",
        "gt": "data/training/annotations/page_015/boxes_sorted_v20260111.json",
        "preds": "data/training/annotations/page_015/expanded_candidates_nopeak.json",
    },
]


# --- UTILS ---
def barline_iou(box1, box2):
    x1_1, y1_1, x2_1, y2_1 = box1
    x1_2, y1_2, x2_2, y2_2 = box2
    inter_x1 = max(x1_1, x1_2)
    inter_y1 = max(y1_1, y1_2)
    inter_x2 = min(x2_1, x2_2)
    inter_y2 = min(y2_1, y2_2)
    if inter_x2 < inter_x1 or inter_y2 < inter_y1:
        return 0.0
    inter_area = (inter_x2 - inter_x1 + 1) * (inter_y2 - inter_y1 + 1)
    area1 = (x2_1 - x1_1 + 1) * (y2_1 - y1_1 + 1)
    area2 = (x2_2 - x1_2 + 1) * (y2_2 - y1_2 + 1)
    return inter_area / float(area1 + area2 - inter_area)


def box_center(box):
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def box_dist(box1, box2):
    c1 = box_center(box1)
    c2 = box_center(box2)
    return np.sqrt((c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2)


class TestDataset(Dataset):
    def __init__(self, root_dir, transform=None):
        self.tp_paths = sorted(list((root_dir / "tp").glob("*.png")))
        self.fp_paths = sorted(list((root_dir / "fp").glob("*.png")))
        self.all_paths = self.tp_paths + self.fp_paths
        self.labels = [1] * len(self.tp_paths) + [0] * len(self.fp_paths)
        self.transform = transform
        self.filenames = [p.name for p in self.all_paths]

    def __len__(self):
        return len(self.all_paths)

    def __getitem__(self, idx):
        path = self.all_paths[idx]
        img = Image.open(path).convert("RGB")
        if self.transform:
            img = self.transform(img)
        return img, torch.tensor(self.labels[idx], dtype=torch.float32), self.filenames[idx]


def get_model():
    model = models.resnet18(weights=None)
    in_features = model.fc.in_features
    model.fc = nn.Linear(in_features, 1)
    return model


def get_transform():
    return transforms.Compose(
        [
            transforms.Resize((256, 128)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ]
    )


def load_metadata():
    print("Loading metadata...")
    meta = {}
    with open(METADATA_FILE, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            meta[row["sample_id"]] = row
    return meta


def load_gt_and_preds(gt_path, preds_path):
    with open(gt_path, "r") as f:
        gt_data = json.load(f)
    if isinstance(gt_data, dict):
        if "predictions" in gt_data:
            gt_data = gt_data["predictions"]

    gt_boxes = []
    # robust parsing
    if gt_data and isinstance(gt_data[0], dict):
        if "barline_location" in gt_data[0]:
            gt_boxes = [e["barline_location"] for e in gt_data]
        elif "bbox" in gt_data[0]:
            gt_boxes = [e["bbox"] for e in gt_data]
    else:
        gt_boxes = gt_data  # list of lists

    candidates = []
    if preds_path.exists():
        with open(preds_path, "r") as f:
            data = json.load(f)
            if isinstance(data, list):
                candidates = data
            elif isinstance(data, dict):
                candidates = [item["bbox"] for item in data.get("scores", [])]
    return gt_boxes, candidates


def parse_original_index_from_path(original_path_str):
    name = Path(original_path_str).stem
    if "_tp_" in name:
        parts = name.split("_tp_")
        return int(parts[-1]), "tp"
    elif "_fp_" in name:
        parts = name.split("_fp_")
        return int(parts[-1]), "fp"
    raise ValueError(f"Cannot parse index from {name}")


def get_fp_candidates(candidates, gt_boxes, scale=1.0):
    fp_candidates = []
    for raw_cand in candidates:
        cand = [x * scale for x in raw_cand]
        is_match = False
        for gt_box in gt_boxes:
            if barline_iou(gt_box, cand) > IOU_THRESHOLD:
                is_match = True
                break
        if not is_match:
            fp_candidates.append(cand)
    return fp_candidates


def analyze_page(group, source, error_list, meta):
    # 1. Resolve Paths
    image_path = None
    gt_path = None
    preds_path = None

    if source == "local":
        config_map = {p["name"]: p for p in DEFAULT_PAGES}
        if group in config_map:
            cfg = config_map[group]
            image_path = Path(cfg["image"])
            gt_path = Path(cfg["gt"])
            preds_path = Path(cfg["preds"])
        else:
            print(f"Skipping unknown local group: {group}")
            return None

    elif source == "eval2":
        # Dynamic Eval2 Parsing
        match = re.search(r"(.+)_(page_\d+)", group)
        if not match:
            print(f"Could not parse eval2 group: {group}")
            return None
        score = match.group(1)
        page_name = match.group(2)

        image_path = Path(f"data/evaluation2/images/{score}/{page_name}.png")
        gt_dir = Path(f"data/evaluation2/annotations/{score}/{page_name}")
        gt_path = gt_dir / "boxes_sorted.json"

        # Fallback for versioned GTs
        if not gt_path.exists():
            jsons = list(gt_dir.glob("boxes_sorted*.json"))
            if jsons:
                gt_path = sorted(jsons)[-1]

        preds_path = Path(
            f"logs/hybrid_generalization/eval2_{score}_{page_name}/expanded_candidates_nopeak.json"
        )

    if not image_path or not image_path.exists():
        print(f"Missing Image: {image_path}")
        return None
    if not gt_path or not gt_path.exists():
        print(f"Missing GT: {gt_path}")
        return None

    # 2. Load Data
    gt_boxes, all_candidates = load_gt_and_preds(gt_path, preds_path)
    fp_candidates = get_fp_candidates(all_candidates, gt_boxes)

    # 3. Analyze Errors
    stats = {
        "fp_near_hit": 0,
        "fp_ghost": 0,
        "fn_recoverable": 0,
        "fn_hard": 0,
        "total_fp": 0,
        "total_fn": 0,
    }

    img = cv2.imread(str(image_path))
    overlay = img.copy()

    # Draw GTs (Gray)
    for gt in gt_boxes:
        x1, y1, x2, y2 = map(int, gt)
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (200, 200, 200), 1)

    # Analyze FPs
    fps = [e for e in error_list if e["label"] == 0 and e["pred"] == 1]
    stats["total_fp"] = len(fps)

    for err in fps:
        orig_path = meta[err["filename"]]["path"]
        try:
            idx, _ = parse_original_index_from_path(orig_path)
            if idx >= len(fp_candidates):
                continue
            box = fp_candidates[idx]

            # Check Dist to GT
            min_dist = float("inf")
            for gt in gt_boxes:
                min_dist = min(min_dist, box_dist(box, gt))

            x1, y1, x2, y2 = map(int, box)

            if min_dist < NEAR_HIT_THRESHOLD_PX:
                stats["fp_near_hit"] += 1
                color = (0, 255, 0)  # Green (Near Hit)
            else:
                stats["fp_ghost"] += 1
                color = (0, 165, 255)  # Orange (Ghost)

            cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)

        except Exception as e:
            print(f"FP Err: {e}")

    # Analyze FNs
    fns = [e for e in error_list if e["label"] == 1 and e["pred"] == 0]
    stats["total_fn"] = len(fns)

    # Get Positive FP Boxes for FN revocery check
    # (Any box the model Predicted=1, even if it's an FP candidate)
    full_page_results_indices = []  # We need to know which candidates were predicted positive in the FULL SET
    # But here 'error_list' only has ERRORS.
    # To correctly judge "Recoverable", we strictly need ALL positive predictions (including Hits).
    # However, approximations: A Hard Miss usually means NO candidates.
    # If there is an FP nearby that was predicted positive, it means we have a candidate.
    # For now, let's just mark FNs as Blue. The quantitative classification of "Recoverable"
    # is harder without the full prediction set (TPs + True Negatives).
    # I will stick to basic FN visualization.

    for err in fns:
        orig_path = meta[err["filename"]]["path"]
        try:
            idx, _ = parse_original_index_from_path(orig_path)
            if idx >= len(gt_boxes):
                continue
            box = gt_boxes[idx]

            x1, y1, x2, y2 = map(int, box)
            cv2.rectangle(overlay, (x1, y1), (x2, y2), (255, 0, 0), 2)  # Blue
            stats["fn_hard"] += 1  # Default assumption without full context
        except Exception as e:
            print(f"FN Err: {e}")

    # Save Visualization
    safe_name = group.replace("/", "_")
    cv2.imwrite(str(OUTPUT_DIR / f"{safe_name}_errors_classified.jpg"), overlay)

    return stats


def main():
    # 1. Load Data
    meta = load_metadata()
    model = get_model().to(DEVICE)
    model.load_state_dict(torch.load(MODEL_PATH, map_location=DEVICE))
    model.eval()

    dataset = TestDataset(TEST_SPLIT_DIR, transform=get_transform())
    loader = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=False, num_workers=4)

    # 2. Inference
    print("Running inference...")
    errors = []
    with torch.no_grad():
        for inputs, labels, filenames in tqdm(loader):
            inputs = inputs.to(DEVICE)
            outputs = model(inputs)
            preds = (torch.sigmoid(outputs) > 0.5).float().cpu()

            for i in range(len(preds)):
                if preds[i].item() != labels[i].item():
                    errors.append(
                        {
                            "filename": filenames[i],
                            "label": int(labels[i].item()),
                            "pred": int(preds[i].item()),
                        }
                    )

    print(f"Total Errors: {len(errors)}")

    # 3. Group by Page
    page_errors = collections.defaultdict(list)
    for err in errors:
        fname = err["filename"]
        if fname not in meta:
            continue
        info = meta[fname]
        if info["source"] == "deepscores":
            continue

        key = (info["group"], info["source"])
        page_errors[key].append(err)

    # 4. Analyze All Pages
    print("\n--- Comparative Error Analysis ---")
    print(f"{'Page':<40} | {'FP (Total)':<10} | {'Ghost':<8} | {'Near Hit':<8} | {'FN':<5}")
    print("-" * 85)

    final_stats = {}

    for (group, source), err_list in page_errors.items():
        stats = analyze_page(group, source, err_list, meta)
        if stats:
            print(
                f"{group:<40} | {stats['total_fp']:<10} | {stats['fp_ghost']:<8} | {stats['fp_near_hit']:<8} | {stats['total_fn']:<5}"
            )
            final_stats[group] = stats

    print("-" * 85)
    print(f"Visualizations saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
