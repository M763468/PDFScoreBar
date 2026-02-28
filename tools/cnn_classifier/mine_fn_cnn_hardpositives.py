import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import yaml
from tqdm import tqdm

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT))

from src.common.barline_evaluation import barline_iou, greedy_barline_match
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
class HardPositiveRow:
    score: str
    page: str
    gt_index: int
    gt_x1: int
    gt_y1: int
    gt_x2: int
    gt_y2: int
    cand_x1: int
    cand_y1: int
    cand_x2: int
    cand_y2: int
    cand_score: float
    iou: float
    image_path: str
    crop_path: str


def _best_recoverable_candidate(
    gt_box: Box, candidates: Sequence[Dict], iou_threshold: float
) -> Optional[Tuple[Box, float, float]]:
    best: Optional[Tuple[Box, float, float]] = None
    for c in candidates:
        bbox = tuple(int(v) for v in c["bbox"][:4])
        score = float(c.get("score", 0.0))
        iou = float(barline_iou(bbox, gt_box))
        if iou < iou_threshold:
            continue
        if best is None or iou > best[2] or (iou == best[2] and score > best[1]):
            best = (bbox, score, iou)
    return best


def main():
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--config", type=Path, help="YAML/JSON config path")
    pre_args, _ = pre_parser.parse_known_args()

    parser = argparse.ArgumentParser(parents=[pre_parser])
    parser.add_argument("--scored-root")
    parser.add_argument("--gt-root")
    parser.add_argument("--images-root")
    parser.add_argument("--output-root")
    parser.add_argument("--threshold", type=float, default=0.1)
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    parser.add_argument("--scored-glob", default="*_scored.json")
    parser.add_argument("--max-per-page", type=int, default=0)

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
    crops_dir = output_root / "hard_positives"
    crops_dir.mkdir(parents=True, exist_ok=True)

    scored_files = sorted(scored_root.rglob(args.scored_glob))
    rows: List[HardPositiveRow] = []
    page_stats: List[Dict[str, object]] = []

    print(f"Mining FN_cnn hard positives from {len(scored_files)} scored files...")

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

        with json_path.open("r") as f:
            candidates = json.load(f)
        gt_boxes = _load_gt_boxes(gt_path)
        accepted = [
            tuple(int(v) for v in c["bbox"][:4])
            for c in candidates
            if float(c["score"]) > args.threshold
        ]
        match_result = greedy_barline_match(accepted, gt_boxes)

        img = cv2.imread(str(image_path))
        if img is None:
            continue

        recovered_this_page = 0
        fn_total = len(match_result.false_negative_indices)
        fn_cnn = 0
        fn_det = 0

        for fn_idx in match_result.false_negative_indices:
            gt_box = gt_boxes[fn_idx]
            best = _best_recoverable_candidate(gt_box, candidates, args.iou_threshold)
            if best is None:
                fn_det += 1
                continue
            fn_cnn += 1
            if args.max_per_page > 0 and recovered_this_page >= args.max_per_page:
                continue

            bbox, cand_score, iou = best
            x1, y1, x2, y2 = bbox
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)
            cw, ch = crop_size_from_bbox(bbox)
            crop = center_crop(img, cx, cy, cw, ch)

            crop_name = (
                f"hcfn_{score_name}__{page_name}__gt{fn_idx:03d}__bx{x1}_by{y1}_ex{x2}_ey{y2}.png"
            )
            crop_path = crops_dir / crop_name
            cv2.imwrite(str(crop_path), crop)

            rows.append(
                HardPositiveRow(
                    score=score_name,
                    page=page_name,
                    gt_index=fn_idx,
                    gt_x1=gt_box[0],
                    gt_y1=gt_box[1],
                    gt_x2=gt_box[2],
                    gt_y2=gt_box[3],
                    cand_x1=x1,
                    cand_y1=y1,
                    cand_x2=x2,
                    cand_y2=y2,
                    cand_score=cand_score,
                    iou=iou,
                    image_path=str(image_path),
                    crop_path=str(crop_path),
                )
            )
            recovered_this_page += 1

        page_stats.append(
            {
                "score": score_name,
                "page": page_name,
                "fn_total": fn_total,
                "fn_cnn": fn_cnn,
                "fn_det": fn_det,
                "mined_hard_positives": recovered_this_page,
            }
        )

    if rows:
        detail_csv = output_root / "hard_positives.csv"
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
    total_fn = sum(int(r["fn_total"]) for r in page_stats)
    total_fn_cnn = sum(int(r["fn_cnn"]) for r in page_stats)
    total_fn_det = sum(int(r["fn_det"]) for r in page_stats)
    mined = len(rows)
    with summary_json.open("w") as f:
        json.dump(
            {
                "scored_root": str(scored_root),
                "threshold": args.threshold,
                "iou_threshold": args.iou_threshold,
                "files_scanned": len(scored_files),
                "total_fn": total_fn,
                "total_fn_cnn": total_fn_cnn,
                "total_fn_det": total_fn_det,
                "mined_hard_positives": mined,
            },
            f,
            indent=2,
        )

    print(f"Done. total_fn={total_fn}, fn_cnn={total_fn_cnn}, fn_det={total_fn_det}, mined={mined}")


if __name__ == "__main__":
    main()
