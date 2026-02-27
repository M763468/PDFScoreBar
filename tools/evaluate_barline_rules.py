import argparse
import csv
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import yaml
from tqdm import tqdm

# Add repo root to sys path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))

from src.common.barline_evaluation import (
    barline_iou,
    barline_vertical_overlap,
    greedy_barline_match,
)
from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.measure_numbering.types import Score

Box = Tuple[int, int, int, int]


@dataclass
class RuleResult:
    rule: str
    score: str
    page: str
    tp: int
    fp: int
    fn_total: int
    fn_cnn: int
    fn_det: int
    gt_count: int
    pred_count: int
    measure_count_pred: Optional[int] = None
    measure_count_gt: Optional[int] = None
    measure_abs_delta: Optional[int] = None


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


def find_gt_file(gt_root: Path, subdir: str, page_name: str) -> Optional[Path]:
    base_dir = gt_root / subdir / page_name
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


def parse_scored_context(json_path: Path, scored_root: Path) -> Optional[Tuple[str, str]]:
    """Parse score/page context from scored JSON path."""
    try:
        rel_parts = json_path.relative_to(scored_root).parts
    except ValueError:
        rel_parts = ()

    if len(rel_parts) >= 3 and rel_parts[-1].endswith("_scored.json"):
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


def load_gt_boxes(gt_path: Path) -> List[Box]:
    with gt_path.open("r") as f:
        gt_data = json.load(f)
    gt_boxes: List[Box] = []
    for item in gt_data:
        if isinstance(item, list):
            gt_boxes.append(tuple(int(v) for v in item[:4]))
        elif isinstance(item, dict):
            if "box" in item:
                gt_boxes.append(tuple(int(v) for v in item["box"]))
            elif "barline_location" in item:
                gt_boxes.append(tuple(int(v) for v in item["barline_location"]))
    return gt_boxes


def _intersection_area(a: Box, b: Box) -> int:
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    w = max(0, x2 - x1)
    h = max(0, y2 - y1)
    return w * h


def _box_area(a: Box) -> int:
    return max(1, a[2] - a[0]) * max(1, a[3] - a[1])


def barline_ioa(pred: Box, gt: Box) -> float:
    inter = _intersection_area(pred, gt)
    return inter / _box_area(gt)


def center_distance_x(a: Box, b: Box) -> float:
    ac = (a[0] + a[2]) / 2.0
    bc = (b[0] + b[2]) / 2.0
    return abs(ac - bc)


def _metrics(pred: Box, gt: Box) -> Dict[str, float]:
    iou = barline_iou(pred, gt)
    ioa = barline_ioa(pred, gt)
    vov = barline_vertical_overlap(pred, gt)
    xdist = center_distance_x(pred, gt)
    return {"iou": iou, "ioa": ioa, "vov": vov, "xdist": xdist}


def _rule_specs(args) -> Dict[str, Dict[str, float]]:
    return {
        "baseline_iou": {
            "iou_min": args.rule_baseline_iou_min,
        },
        "relaxed_geom": {
            "iou_min": args.rule_relaxed_iou_min,
            "vov_min": args.rule_relaxed_vov_min,
            "xdist_max": args.rule_relaxed_xdist_max,
        },
        "coverage_ioa": {
            "ioa_min": args.rule_coverage_ioa_min,
            "vov_min": args.rule_coverage_vov_min,
        },
        "center_anchor": {
            "vov_min": args.rule_center_vov_min,
            "xdist_max": args.rule_center_xdist_max,
        },
    }


def _rule_accept(rule_name: str, m: Dict[str, float], rule_cfg: Dict[str, float]) -> bool:
    if rule_name == "baseline_iou":
        return m["iou"] >= rule_cfg["iou_min"]
    if rule_name == "relaxed_geom":
        return (m["iou"] >= rule_cfg["iou_min"]) or (
            m["vov"] >= rule_cfg["vov_min"] and m["xdist"] <= rule_cfg["xdist_max"]
        )
    if rule_name == "coverage_ioa":
        return m["ioa"] >= rule_cfg["ioa_min"] and m["vov"] >= rule_cfg["vov_min"]
    if rule_name == "center_anchor":
        return m["vov"] >= rule_cfg["vov_min"] and m["xdist"] <= rule_cfg["xdist_max"]
    raise ValueError(f"Unknown rule: {rule_name}")


def _rule_rank(rule_name: str, m: Dict[str, float]) -> Tuple[float, float, float, float]:
    if rule_name == "baseline_iou":
        return (m["iou"], m["ioa"], m["vov"], -m["xdist"])
    if rule_name == "relaxed_geom":
        return (max(m["iou"], 0.3), m["vov"], m["ioa"], -m["xdist"])
    if rule_name == "coverage_ioa":
        return (m["ioa"], m["vov"], m["iou"], -m["xdist"])
    if rule_name == "center_anchor":
        return (m["vov"], -m["xdist"], m["ioa"], m["iou"])
    raise ValueError(f"Unknown rule: {rule_name}")


def greedy_match_by_rule(
    predictions: Sequence[Box],
    ground_truth: Sequence[Box],
    *,
    rule_name: str,
    rule_cfg: Dict[str, float],
) -> Tuple[List[Tuple[int, int]], List[int], List[int], Dict[Tuple[int, int], Dict[str, float]]]:
    metrics_by_pair: Dict[Tuple[int, int], Dict[str, float]] = {}
    if rule_name == "baseline_iou":
        for p_idx, pred in enumerate(predictions):
            for g_idx, gt in enumerate(ground_truth):
                metrics_by_pair[(p_idx, g_idx)] = _metrics(pred, gt)
        baseline = greedy_barline_match(
            predictions,
            ground_truth,
            iou_threshold=rule_cfg["iou_min"],
        )
        matches = [(m.pred_index, m.gt_index) for m in baseline.matches]
        return (
            matches,
            baseline.false_positive_indices,
            baseline.false_negative_indices,
            metrics_by_pair,
        )

    pairs: List[Tuple[Tuple[float, float, float, float], int, int]] = []
    for p_idx, pred in enumerate(predictions):
        for g_idx, gt in enumerate(ground_truth):
            m = _metrics(pred, gt)
            metrics_by_pair[(p_idx, g_idx)] = m
            if _rule_accept(rule_name, m, rule_cfg):
                pairs.append((_rule_rank(rule_name, m), p_idx, g_idx))

    pairs.sort(reverse=True)
    used_pred = set()
    used_gt = set()
    matches: List[Tuple[int, int]] = []
    for _, p_idx, g_idx in pairs:
        if p_idx in used_pred or g_idx in used_gt:
            continue
        used_pred.add(p_idx)
        used_gt.add(g_idx)
        matches.append((p_idx, g_idx))

    fp = sorted(i for i in range(len(predictions)) if i not in used_pred)
    fn = sorted(i for i in range(len(ground_truth)) if i not in used_gt)
    return matches, fp, fn, metrics_by_pair


def load_fn_det_classification(
    path: Optional[Path],
) -> Dict[Tuple[str, str, int, int, int, int], str]:
    if not path:
        return {}
    out: Dict[Tuple[str, str, int, int, int, int], str] = {}
    with path.open("r", newline="") as f:
        for row in csv.DictReader(f):
            key = (
                row["score"],
                row["page"],
                int(row["gt_x1"]),
                int(row["gt_y1"]),
                int(row["gt_x2"]),
                int(row["gt_y2"]),
            )
            out[key] = row["type"]
    return out


def _find_staff_mask_for_eval2_page(
    bench_root: Path, score_name: str, page_name: str
) -> Optional[Path]:
    pattern = f"eval2_{score_name}_{page_name}_*"
    runs = sorted(bench_root.glob(pattern), reverse=True)
    page_id = page_name
    for run in runs:
        mask = run / "baseline" / page_id / page_id / f"{page_id}_proxy_debug_3_staff.png"
        if mask.exists():
            return mask
    return None


def _measure_count_for_boxes(
    pipeline: MeasureNumberingPipeline,
    boxes: Sequence[Box],
    staff_mask: Path,
    image_path: Path,
) -> Optional[int]:
    img = cv2.imread(str(image_path))
    if img is None:
        return None
    h, w = img.shape[:2]
    page = pipeline.process_page(
        barline_boxes=[list(b) for b in boxes],
        staff_mask_path=staff_mask,
        image_size=(w, h),
        page_number=1,
        image=img,
    )
    score = Score()
    score.pages.append(page)
    pipeline.numberer.number_score(score, start_number=1)
    return sum(len(system.measures) for system in page.systems)


def main():
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--config", type=Path, help="YAML/JSON config path")
    pre_args, _ = pre_parser.parse_known_args()

    parser = argparse.ArgumentParser(parents=[pre_parser])
    parser.add_argument("--scored-root")
    parser.add_argument("--gt-root")
    parser.add_argument("--output-dir")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--scored-glob", default="*_scored.json")
    parser.add_argument("--limit-pages", type=int, default=0)

    # Optional: classification join (#46 FN_det 15)
    parser.add_argument("--fn-det-classification-csv", type=Path, default=None)

    # Optional: numbering proxy KPI
    parser.add_argument("--numbering-eval", action="store_true")
    parser.add_argument("--images-root", default="data/evaluation2/images")
    parser.add_argument("--bench-root", default="logs/hybrid_pipeline_bench")

    # Rule params
    parser.add_argument("--rule-baseline-iou-min", type=float, default=0.5)
    parser.add_argument("--rule-relaxed-iou-min", type=float, default=0.3)
    parser.add_argument("--rule-relaxed-vov-min", type=float, default=0.7)
    parser.add_argument("--rule-relaxed-xdist-max", type=float, default=5.0)
    parser.add_argument("--rule-coverage-ioa-min", type=float, default=0.8)
    parser.add_argument("--rule-coverage-vov-min", type=float, default=0.7)
    parser.add_argument("--rule-center-vov-min", type=float, default=0.5)
    parser.add_argument("--rule-center-xdist-max", type=float, default=12.0)

    if pre_args.config:
        cfg = load_config_file(pre_args.config)
        parser.set_defaults(**{k.replace("-", "_"): v for k, v in cfg.items() if k != "config"})

    args = parser.parse_args()
    missing = [k for k in ("scored_root", "gt_root", "output_dir") if not getattr(args, k)]
    if missing:
        parser.error(
            "Missing required arguments (provide via CLI or --config): "
            + ", ".join(f"--{k.replace('_', '-')}" for k in missing)
        )

    scored_root = Path(args.scored_root)
    gt_root = Path(args.gt_root)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    fn_map = load_fn_det_classification(args.fn_det_classification_csv)
    rule_specs = _rule_specs(args)

    scored_files = sorted(scored_root.rglob(args.scored_glob))
    if args.limit_pages and args.limit_pages > 0:
        scored_files = scored_files[: args.limit_pages]

    print(f"Processing {len(scored_files)} scored files for rule comparison...")

    pipeline = MeasureNumberingPipeline() if args.numbering_eval else None
    images_root = Path(args.images_root)
    bench_root = Path(args.bench_root)

    page_results: List[RuleResult] = []
    fn_case_rows: List[Dict[str, object]] = []

    for json_path in tqdm(scored_files):
        parsed = parse_scored_context(json_path, scored_root)
        if not parsed:
            continue
        score_name, page_name = parsed
        gt_path = find_gt_file(gt_root, score_name, page_name)
        if not gt_path:
            continue

        with json_path.open("r") as f:
            candidates = json.load(f)
        gt_boxes = load_gt_boxes(gt_path)

        accepted = [
            tuple(int(v) for v in c["bbox"]) for c in candidates if c["score"] > args.threshold
        ]
        all_boxes = [tuple(int(v) for v in c["bbox"]) for c in candidates]

        measure_gt_proxy = None
        staff_mask = None
        if args.numbering_eval and pipeline is not None:
            staff_mask = _find_staff_mask_for_eval2_page(bench_root, score_name, page_name)
            image_path = images_root / score_name / f"{page_name}.png"
            if staff_mask is not None and image_path.exists():
                measure_gt_proxy = _measure_count_for_boxes(
                    pipeline, gt_boxes, staff_mask, image_path
                )

        for rule_name, rule_cfg in rule_specs.items():
            matches, fps, fns, metrics_by_pair = greedy_match_by_rule(
                accepted,
                gt_boxes,
                rule_name=rule_name,
                rule_cfg=rule_cfg,
            )
            fn_cnn = 0
            fn_det = 0
            for gt_idx in fns:
                gt_box = gt_boxes[gt_idx]
                found = False
                for cand in all_boxes:
                    m = _metrics(cand, gt_box)
                    if _rule_accept(rule_name, m, rule_cfg):
                        found = True
                        break
                if found:
                    fn_cnn += 1
                else:
                    fn_det += 1

            measure_pred_proxy = None
            measure_abs_delta = None
            if args.numbering_eval and pipeline is not None and staff_mask is not None:
                image_path = images_root / score_name / f"{page_name}.png"
                if image_path.exists():
                    measure_pred_proxy = _measure_count_for_boxes(
                        pipeline,
                        accepted,
                        staff_mask,
                        image_path,
                    )
                    if measure_gt_proxy is not None and measure_pred_proxy is not None:
                        measure_abs_delta = abs(measure_pred_proxy - measure_gt_proxy)

            page_results.append(
                RuleResult(
                    rule=rule_name,
                    score=score_name,
                    page=page_name,
                    tp=len(matches),
                    fp=len(fps),
                    fn_total=len(fns),
                    fn_cnn=fn_cnn,
                    fn_det=fn_det,
                    gt_count=len(gt_boxes),
                    pred_count=len(accepted),
                    measure_count_pred=measure_pred_proxy,
                    measure_count_gt=measure_gt_proxy,
                    measure_abs_delta=measure_abs_delta,
                )
            )

            # Per-case status for #46 FN_det=15 keys
            if fn_map:
                matched_gt = {g for _, g in matches}
                for gt_idx, gt_box in enumerate(gt_boxes):
                    key = (
                        score_name,
                        page_name,
                        gt_box[0],
                        gt_box[1],
                        gt_box[2],
                        gt_box[3],
                    )
                    if key not in fn_map:
                        continue

                    if gt_idx in matched_gt:
                        status = "TP"
                    else:
                        found = False
                        for cand in all_boxes:
                            m = _metrics(cand, gt_box)
                            if _rule_accept(rule_name, m, rule_cfg):
                                found = True
                                break
                        status = "FN_cnn" if found else "FN_det"

                    best_iou = 0.0
                    best_ioa = 0.0
                    best_vov = 0.0
                    best_xdist = float("inf")
                    for p_idx, pred in enumerate(accepted):
                        m = metrics_by_pair.get((p_idx, gt_idx))
                        if m is None:
                            m = _metrics(pred, gt_box)
                        if m["iou"] > best_iou:
                            best_iou = m["iou"]
                        if m["ioa"] > best_ioa:
                            best_ioa = m["ioa"]
                        if m["vov"] > best_vov:
                            best_vov = m["vov"]
                        if m["xdist"] < best_xdist:
                            best_xdist = m["xdist"]

                    fn_case_rows.append(
                        {
                            "rule": rule_name,
                            "score": score_name,
                            "page": page_name,
                            "gt_x1": gt_box[0],
                            "gt_y1": gt_box[1],
                            "gt_x2": gt_box[2],
                            "gt_y2": gt_box[3],
                            "category": fn_map[key],
                            "status": status,
                            "best_iou_vs_accepted": best_iou,
                            "best_ioa_vs_accepted": best_ioa,
                            "best_vertical_overlap_vs_accepted": best_vov,
                            "best_xdist_vs_accepted": best_xdist
                            if best_xdist != float("inf")
                            else "",
                        }
                    )

    if not page_results:
        raise RuntimeError("No evaluation result generated.")

    # Write per-page detail
    detail_csv = output_dir / "rule_eval_per_page.csv"
    with detail_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(RuleResult.__dataclass_fields__.keys()))
        writer.writeheader()
        for r in page_results:
            writer.writerow(r.__dict__)

    # Aggregate by rule
    agg = defaultdict(
        lambda: {
            "tp": 0,
            "fp": 0,
            "fn_total": 0,
            "fn_cnn": 0,
            "fn_det": 0,
            "gt": 0,
            "pages": 0,
            "measure_abs_delta_sum": 0,
            "measure_pages": 0,
        }
    )
    for r in page_results:
        a = agg[r.rule]
        a["tp"] += r.tp
        a["fp"] += r.fp
        a["fn_total"] += r.fn_total
        a["fn_cnn"] += r.fn_cnn
        a["fn_det"] += r.fn_det
        a["gt"] += r.gt_count
        a["pages"] += 1
        if r.measure_abs_delta is not None:
            a["measure_abs_delta_sum"] += r.measure_abs_delta
            a["measure_pages"] += 1

    summary_rows: List[Dict[str, object]] = []
    for rule, a in sorted(agg.items()):
        tp = a["tp"]
        fp = a["fp"]
        gt = a["gt"]
        recall = tp / gt if gt else 0.0
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        row = {
            "rule": rule,
            "pages": a["pages"],
            "tp": tp,
            "fp": fp,
            "fn_total": a["fn_total"],
            "fn_cnn": a["fn_cnn"],
            "fn_det": a["fn_det"],
            "recall": recall,
            "precision": prec,
            "measure_abs_delta_sum": a["measure_abs_delta_sum"],
            "measure_pages": a["measure_pages"],
            "measure_abs_delta_mean": (
                a["measure_abs_delta_sum"] / a["measure_pages"] if a["measure_pages"] else ""
            ),
        }
        summary_rows.append(row)

    summary_csv = output_dir / "rule_eval_summary.csv"
    with summary_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(summary_rows)

    # Detect inversion cases: better FN_total but worse measure_abs_delta than baseline
    inversion_rows: List[Dict[str, object]] = []
    baseline_by_page: Dict[Tuple[str, str], RuleResult] = {}
    for r in page_results:
        if r.rule == "baseline_iou":
            baseline_by_page[(r.score, r.page)] = r
    for r in page_results:
        if r.rule == "baseline_iou":
            continue
        b = baseline_by_page.get((r.score, r.page))
        if b is None:
            continue
        if (
            r.fn_total < b.fn_total
            and r.measure_abs_delta is not None
            and b.measure_abs_delta is not None
            and r.measure_abs_delta > b.measure_abs_delta
        ):
            inversion_rows.append(
                {
                    "rule": r.rule,
                    "score": r.score,
                    "page": r.page,
                    "baseline_fn_total": b.fn_total,
                    "rule_fn_total": r.fn_total,
                    "baseline_measure_abs_delta": b.measure_abs_delta,
                    "rule_measure_abs_delta": r.measure_abs_delta,
                }
            )

    inversion_csv = output_dir / "rule_eval_kpi_inversion_cases.csv"
    with inversion_csv.open("w", newline="") as f:
        fieldnames = [
            "rule",
            "score",
            "page",
            "baseline_fn_total",
            "rule_fn_total",
            "baseline_measure_abs_delta",
            "rule_measure_abs_delta",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(inversion_rows)

    fn_case_csv = None
    if fn_case_rows:
        fn_case_csv = output_dir / "rule_eval_fn_det15_cases.csv"
        with fn_case_csv.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(fn_case_rows[0].keys()))
            writer.writeheader()
            writer.writerows(fn_case_rows)

        # Category aggregate
        by_rule_cat = defaultdict(lambda: {"TP": 0, "FN_cnn": 0, "FN_det": 0, "count": 0})
        for row in fn_case_rows:
            key = (row["rule"], row["category"])
            by_rule_cat[key]["count"] += 1
            by_rule_cat[key][row["status"]] += 1

        cat_rows = []
        for (rule, cat), v in sorted(by_rule_cat.items()):
            cat_rows.append(
                {
                    "rule": rule,
                    "category": cat,
                    "count": v["count"],
                    "tp": v["TP"],
                    "fn_cnn": v["FN_cnn"],
                    "fn_det": v["FN_det"],
                }
            )
        cat_csv = output_dir / "rule_eval_fn_det15_by_category.csv"
        with cat_csv.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(cat_rows[0].keys()))
            writer.writeheader()
            writer.writerows(cat_rows)

    # Save metadata
    metadata = {
        "scored_root": str(scored_root),
        "gt_root": str(gt_root),
        "threshold": args.threshold,
        "scored_glob": args.scored_glob,
        "numbering_eval": args.numbering_eval,
        "images_root": str(images_root),
        "bench_root": str(bench_root),
        "rule_specs": rule_specs,
        "outputs": {
            "detail_csv": str(detail_csv),
            "summary_csv": str(summary_csv),
            "kpi_inversion_csv": str(inversion_csv),
            "fn_case_csv": str(fn_case_csv) if fn_case_csv else None,
        },
    }
    with (output_dir / "rule_eval_metadata.json").open("w") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    print("\n=== Rule Comparison Summary ===")
    for row in summary_rows:
        print(
            f"{row['rule']:<14} TP={row['tp']:<4} FP={row['fp']:<4} FN={row['fn_total']:<4} "
            f"FN_cnn={row['fn_cnn']:<4} FN_det={row['fn_det']:<4} "
            f"Recall={row['recall']:.3f} Prec={row['precision']:.3f} "
            f"MeasureAbsDeltaSum={row['measure_abs_delta_sum']}"
        )
    print(f"\nWrote: {summary_csv}")


if __name__ == "__main__":
    main()
