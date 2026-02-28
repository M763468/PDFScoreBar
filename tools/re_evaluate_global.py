import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import yaml
from tqdm import tqdm

# Add repo root to sys path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))

from src.common.barline_evaluation import barline_iou, greedy_barline_match


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


def find_gt_file(gt_root, subdir, page_name):
    base_dir = Path(gt_root) / subdir / page_name
    if not base_dir.exists():
        return None
    candidates = list(base_dir.glob("boxes_sorted*.json"))
    if candidates:
        candidates.sort(reverse=True)
        return candidates[0]
    f = base_dir / "boxes_sorted.json"
    if f.exists():
        return f
    return None


def parse_scored_context(json_path: Path, scored_root: Path):
    """Parse score/page context from scored JSON path.

    Supported layouts:
    - nested: <scored_root>/<score>/<page>/<*_scored.json>
    - legacy flat filename/dir patterns containing *_<score>_page_XXX
    """
    try:
        rel_parts = json_path.relative_to(scored_root).parts
    except ValueError:
        rel_parts = ()

    if len(rel_parts) >= 3 and rel_parts[-1].endswith(".json") and "_scored" in rel_parts[-1]:
        score_name = rel_parts[-3]
        page_name = rel_parts[-2]
        if page_name.startswith("page_"):
            return score_name, page_name

    for candidate_name in (json_path.stem.replace("_scored", ""), json_path.parent.name):
        parts = candidate_name.split("_")
        if "page" not in parts:
            continue
        page_idx = parts.index("page")
        score_start = 1 if parts and parts[0] == "eval2" else 0
        if page_idx <= score_start:
            continue
        score_name = "_".join(parts[score_start:page_idx])
        page_name = "_".join(parts[page_idx:])
        if score_name and page_name.startswith("page_"):
            return score_name, page_name
    return None


def main():
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument(
        "--config",
        type=Path,
        help="Path to YAML/JSON config file. CLI args override config values.",
    )
    pre_args, _ = pre_parser.parse_known_args()

    parser = argparse.ArgumentParser(parents=[pre_parser])
    parser.add_argument("--scored-root")
    parser.add_argument("--gt-root")
    parser.add_argument("--output-csv")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument(
        "--eval-rule",
        choices=["baseline_iou", "center_anchor"],
        default="baseline_iou",
        help="Rule name for greedy matching.",
    )
    parser.add_argument("--vov-threshold", type=float, default=0.5)
    parser.add_argument("--xdist-threshold", type=float, default=12.0)
    parser.add_argument(
        "--scored-glob",
        default="*_scored.json",
        help="Glob pattern (recursive) to find scored JSON files under --scored-root.",
    )

    if pre_args.config:
        config_values = load_config_file(pre_args.config)
        parser.set_defaults(
            **{k.replace("-", "_"): v for k, v in config_values.items() if k not in {"config"}}
        )

    args = parser.parse_args()
    missing = [name for name in ("scored_root", "gt_root", "output_csv") if not getattr(args, name)]
    if missing:
        parser.error(
            "Missing required arguments (provide via CLI or --config): "
            + ", ".join(f"--{name.replace('_', '-')}" for name in missing)
        )

    scored_root = Path(args.scored_root)
    scored_files = list(scored_root.rglob(args.scored_glob))
    stats = []

    print(f"Processing {len(scored_files)} scored files with greedy_barline_match...")

    for json_path in tqdm(scored_files):
        parsed = parse_scored_context(json_path, scored_root)
        if not parsed:
            print(f"Skipping (unparseable scored path): {json_path}")
            continue
        subdir, page_name = parsed

        with open(json_path, "r") as f:
            candidates = json.load(f)

        gt_path = find_gt_file(args.gt_root, subdir, page_name)
        if not gt_path:
            print(f"GT not found for {subdir}/{page_name} in {args.gt_root}")
            continue

        with open(gt_path, "r") as f:
            gt_data = json.load(f)

        gt_boxes = []
        for item in gt_data:
            if isinstance(item, list):
                gt_boxes.append(tuple(item[:4]))
            elif isinstance(item, dict):
                if "box" in item:
                    gt_boxes.append(tuple(item["box"]))
                elif "barline_location" in item:
                    gt_boxes.append(tuple(item["barline_location"]))

        accepted_candidates = [tuple(c["bbox"]) for c in candidates if c["score"] > args.threshold]

        # USE GREEDY MATCH
        match_result = greedy_barline_match(
            accepted_candidates,
            gt_boxes,
            rule_name=args.eval_rule,
            iou_threshold=0.5,  # Standard IoU if using baseline_iou
            vov_threshold=args.vov_threshold,
            xdist_threshold=args.xdist_threshold,
        )

        tp = len(match_result.matches)
        fp = len(match_result.false_positive_indices)
        fn_total = len(match_result.false_negative_indices)

        # Detector vs CNN breakdown for FNs
        # (A GT is a Detector Miss if NO candidate in the entire set (even < threshold) hits it)
        all_candidate_boxes = [tuple(c["bbox"]) for c in candidates]
        fn_cnn = 0
        fn_det = 0
        from src.common.barline_evaluation import barline_vertical_overlap, center_distance_x

        for fn_idx in match_result.false_negative_indices:
            found_by_detector = False
            gt_box = gt_boxes[fn_idx]
            for cand in all_candidate_boxes:
                # Use same rule for detector check
                accepted = False
                if args.eval_rule == "baseline_iou":
                    if barline_iou(cand, gt_box) > 0.5:
                        accepted = True
                elif args.eval_rule == "center_anchor":
                    vov = barline_vertical_overlap(cand, gt_box)
                    xdist = center_distance_x(cand, gt_box)
                    if vov >= args.vov_threshold and xdist <= args.xdist_threshold:
                        accepted = True

                if accepted:
                    found_by_detector = True
                    break

            if found_by_detector:
                fn_cnn += 1
            else:
                fn_det += 1

        stats.append(
            {
                "score": subdir,
                "page": page_name,
                "tp": tp,
                "fp": fp,
                "fn_total": fn_total,
                "fn_cnn": fn_cnn,
                "fn_det": fn_det,
                "gt_count": len(gt_boxes),
            }
        )

    # Output Aggregate Summary
    agg = defaultdict(
        lambda: {"tp": 0, "fp": 0, "fn": 0, "fn_cnn": 0, "fn_det": 0, "gt": 0, "pages": 0}
    )
    for s in stats:
        b = agg[s["score"]]
        b["tp"] += s["tp"]
        b["fp"] += s["fp"]
        b["fn"] += s["fn_total"]
        b["fn_cnn"] += s["fn_cnn"]
        b["fn_det"] += s["fn_det"]
        b["gt"] += s["gt_count"]
        b["pages"] += 1

    print("\n=== Professional Evaluation Summary (Greedy Match) ===")
    print(
        f"{'Score':<35} | {'Pages':<5} | {'TP':<5} | {'FP':<5} | {'FN(T)':<5} | {'FN(C)':<5} | {'FN(D)':<5} | {'Recall':<6} | {'Prec':<6}"
    )
    print("-" * 110)

    total_tp, total_fp, total_fn, total_cnn, total_det, total_gt = 0, 0, 0, 0, 0, 0
    for score, data in sorted(agg.items()):
        tp, fp, fn, gt = data["tp"], data["fp"], data["fn"], data["gt"]
        total_tp += tp
        total_fp += fp
        total_fn += fn
        total_cnn += data["fn_cnn"]
        total_det += data["fn_det"]
        total_gt += gt
        recall = tp / gt if gt > 0 else 0
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0
        print(
            f"{score:<35} | {data['pages']:<5} | {tp:<5} | {fp:<5} | {fn:<5} | {data['fn_cnn']:<5} | {data['fn_det']:<5} | {recall:.1%} | {prec:.1%}"
        )

    g_recall = total_tp / total_gt if total_gt > 0 else 0
    g_prec = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
    print("-" * 110)
    print(
        f"{'GLOBAL TOTAL':<35} | {'-':<5} | {total_tp:<5} | {total_fp:<5} | {total_fn:<5} | {total_cnn:<5} | {total_det:<5} | {g_recall:.1%} | {g_prec:.1%}"
    )

    # Save CSV
    if not stats:
        print("No stats collected!")
        return

    with open(args.output_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=stats[0].keys())
        writer.writeheader()
        writer.writerows(stats)


if __name__ == "__main__":
    main()
