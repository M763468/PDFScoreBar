import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import yaml
from tqdm import tqdm

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

from src.common.barline_evaluation import barline_iou
from tools.cnn_classifier.score_candidates_batch import center_crop, crop_size_from_bbox
from tools.re_evaluate_global import find_gt_file, parse_scored_context

Box = Tuple[int, int, int, int]


def load_config_file(config_path: Path) -> Dict:
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


def _load_gt_boxes(gt_path: Path) -> List[Box]:
    with gt_path.open("r") as f:
        gt_data = json.load(f)
    gt_boxes: List[Box] = []
    for item in gt_data:
        if isinstance(item, list):
            gt_boxes.append(tuple(int(v) for v in item[:4]))
        elif isinstance(item, dict):
            if "box" in item:
                gt_boxes.append(tuple(int(v) for v in item["box"][:4]))
            elif "barline_location" in item:
                gt_boxes.append(tuple(int(v) for v in item["barline_location"][:4]))
    return gt_boxes


@dataclass
class HardNegativeRow:
    score: str
    page: str
    cand_x1: int
    cand_y1: int
    cand_x2: int
    cand_y2: int
    cand_score: float
    max_iou_with_gt: float
    image_path: str
    crop_path: str


def main():
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--config", type=Path, help="YAML/JSON config path")
    pre_args, _ = pre_parser.parse_known_args()

    parser = argparse.ArgumentParser(parents=[pre_parser])
    parser.add_argument("--scored-root")
    parser.add_argument("--gt-root")
    parser.add_argument("--images-root")
    parser.add_argument("--output-root")
    parser.add_argument("--scored-glob", default="*_scored.json")
    parser.add_argument("--min-score", type=float, default=0.08)
    parser.add_argument("--max-score", type=float, default=0.20)
    parser.add_argument("--max-iou", type=float, default=0.10)
    parser.add_argument("--max-per-page", type=int, default=3)

    if pre_args.config:
        cfg = load_config_file(pre_args.config)
        parser.set_defaults(**{k.replace("-", "_"): v for k, v in cfg.items() if k != "config"})

    args = parser.parse_args()
    missing = [
        k
        for k in ("scored_root", "gt_root", "images_root", "output_root")
        if not getattr(args, k, None)
    ]
    if missing:
        parser.error(
            "Missing required arguments (provide via CLI or --config): "
            + ", ".join(f"--{k.replace('_', '-')}" for k in missing)
        )

    scored_root = Path(args.scored_root)
    gt_root = Path(args.gt_root)
    images_root = Path(args.images_root)
    output_root = Path(args.output_root)
    crops_dir = output_root / "hard_negatives"
    crops_dir.mkdir(parents=True, exist_ok=True)

    scored_files = sorted(scored_root.rglob(args.scored_glob))
    rows: List[HardNegativeRow] = []
    page_stats: List[Dict[str, object]] = []

    print(f"Mining hard negatives from {len(scored_files)} scored files...")

    for json_path in tqdm(scored_files):
        parsed = parse_scored_context(json_path, scored_root)
        if not parsed:
            continue
        score_name, page_name = parsed
        gt_path = find_gt_file(gt_root, score_name, page_name)
        if not gt_path:
            continue
        image_path = images_root / score_name / f"{page_name}.png"
        if not image_path.exists():
            continue

        gt_boxes = _load_gt_boxes(gt_path)
        with json_path.open("r") as f:
            candidates = json.load(f)

        img = cv2.imread(str(image_path))
        if img is None:
            continue

        selected: List[Tuple[float, Box, float]] = []
        for c in candidates:
            bbox = tuple(int(v) for v in c["bbox"][:4])
            score = float(c.get("score", 0.0))
            if score < args.min_score or score > args.max_score:
                continue
            max_iou = 0.0
            for gt in gt_boxes:
                max_iou = max(max_iou, float(barline_iou(bbox, gt)))
            if max_iou > args.max_iou:
                continue
            selected.append((score, bbox, max_iou))

        selected.sort(key=lambda x: x[0], reverse=True)
        selected = selected[: max(0, int(args.max_per_page))]

        for idx, (cand_score, bbox, max_iou) in enumerate(selected):
            x1, y1, x2, y2 = bbox
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)
            cw, ch = crop_size_from_bbox(bbox)
            crop = center_crop(img, cx, cy, cw, ch)
            crop_name = (
                f"hneg_{score_name}__{page_name}__{idx:02d}"
                f"__bx{x1}_by{y1}_ex{x2}_ey{y2}_s{cand_score:.4f}.png"
            )
            crop_path = crops_dir / crop_name
            cv2.imwrite(str(crop_path), crop)
            rows.append(
                HardNegativeRow(
                    score=score_name,
                    page=page_name,
                    cand_x1=x1,
                    cand_y1=y1,
                    cand_x2=x2,
                    cand_y2=y2,
                    cand_score=cand_score,
                    max_iou_with_gt=max_iou,
                    image_path=str(image_path),
                    crop_path=str(crop_path),
                )
            )

        page_stats.append(
            {
                "score": score_name,
                "page": page_name,
                "selected_hard_negatives": len(selected),
            }
        )

    if rows:
        detail_csv = output_root / "hard_negatives.csv"
        with detail_csv.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].__dict__.keys()))
            writer.writeheader()
            for r in rows:
                writer.writerow(r.__dict__)

    if page_stats:
        summary_csv = output_root / "mining_page_summary.csv"
        with summary_csv.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(page_stats[0].keys()))
            writer.writeheader()
            writer.writerows(page_stats)

    summary_json = output_root / "summary.json"
    with summary_json.open("w") as f:
        json.dump(
            {
                "scored_root": str(scored_root),
                "scored_glob": args.scored_glob,
                "min_score": args.min_score,
                "max_score": args.max_score,
                "max_iou": args.max_iou,
                "max_per_page": args.max_per_page,
                "files_scanned": len(scored_files),
                "mined_hard_negatives": len(rows),
            },
            f,
            indent=2,
        )

    print(f"Done. mined_hard_negatives={len(rows)}")


if __name__ == "__main__":
    main()
