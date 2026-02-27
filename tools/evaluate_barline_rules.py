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
    measure_match_tp: Optional[int] = None
    measure_match_fp: Optional[int] = None
    measure_match_fn: Optional[int] = None
    measure_match_recall: Optional[float] = None
    measure_match_precision: Optional[float] = None
    measure_boundary_mae: Optional[float] = None
    measure_nlc_rate: Optional[float] = None


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


def _measure_iou_2d(a: Box, b: Box) -> float:
    inter = _intersection_area(a, b)
    union = _box_area(a) + _box_area(b) - inter
    return inter / union if union > 0 else 0.0


def _x_iou(a: Box, b: Box) -> float:
    ax1, ax2 = a[0], a[2]
    bx1, bx2 = b[0], b[2]
    inter = max(0, min(ax2, bx2) - max(ax1, bx1))
    union = max(ax2, bx2) - min(ax1, bx1)
    if union <= 0:
        return 0.0
    return inter / union


def _extract_measures(page) -> List[Dict[str, object]]:
    measures: List[Dict[str, object]] = []
    for s_idx, system in enumerate(page.systems):
        for m in system.measures:
            bbox = (m.bbox.x1, m.bbox.y1, m.bbox.x2, m.bbox.y2)
            measures.append({"number": int(m.number), "bbox": bbox, "system": s_idx})
    return measures


def _measure_local_kpis(
    gt_measures: Sequence[Dict[str, object]],
    pred_measures: Sequence[Dict[str, object]],
    *,
    x_iou_threshold: float = 0.85,
    min_vertical_overlap: float = 0.5,
    nlc_iou_threshold: float = 0.5,
) -> Dict[str, Optional[float]]:
    # 1) 1D-X IoU based greedy matching
    pairs: List[Tuple[Tuple[float, float], int, int]] = []
    for p_idx, pm in enumerate(pred_measures):
        pb = pm["bbox"]
        for g_idx, gm in enumerate(gt_measures):
            gb = gm["bbox"]
            x_iou = _x_iou(pb, gb)
            vov = barline_vertical_overlap(pb, gb)
            if x_iou >= x_iou_threshold and vov >= min_vertical_overlap:
                pairs.append(((x_iou, vov), p_idx, g_idx))
    pairs.sort(reverse=True)

    used_p = set()
    used_g = set()
    matched: List[Tuple[int, int]] = []
    for _, p_idx, g_idx in pairs:
        if p_idx in used_p or g_idx in used_g:
            continue
        used_p.add(p_idx)
        used_g.add(g_idx)
        matched.append((p_idx, g_idx))

    tp = len(matched)
    fp = len(pred_measures) - tp
    fn = len(gt_measures) - tp
    recall = tp / len(gt_measures) if gt_measures else 0.0
    precision = tp / len(pred_measures) if pred_measures else 0.0

    # 2) boundary X MAE on matched pairs
    boundary_errs: List[float] = []
    for p_idx, g_idx in matched:
        pb = pred_measures[p_idx]["bbox"]
        gb = gt_measures[g_idx]["bbox"]
        boundary_errs.append(abs(pb[0] - gb[0]))
        boundary_errs.append(abs(pb[2] - gb[2]))
    boundary_mae = sum(boundary_errs) / len(boundary_errs) if boundary_errs else None

    # 3) Number-location consistency (same measure number, 2D IoU)
    pred_by_num: Dict[int, List[Box]] = defaultdict(list)
    gt_by_num: Dict[int, List[Box]] = defaultdict(list)
    for pm in pred_measures:
        pred_by_num[int(pm["number"])].append(pm["bbox"])
    for gm in gt_measures:
        gt_by_num[int(gm["number"])].append(gm["bbox"])

    nlc_total = 0
    nlc_hit = 0
    for num, gt_list in gt_by_num.items():
        pred_list = pred_by_num.get(num, [])
        for gb in gt_list:
            nlc_total += 1
            best_iou = 0.0
            for pb in pred_list:
                iou = _measure_iou_2d(pb, gb)
                if iou > best_iou:
                    best_iou = iou
            if best_iou >= nlc_iou_threshold:
                nlc_hit += 1
    nlc_rate = nlc_hit / nlc_total if nlc_total > 0 else None

    return {
        "measure_match_tp": tp,
        "measure_match_fp": fp,
        "measure_match_fn": fn,
        "measure_match_recall": recall,
        "measure_match_precision": precision,
        "measure_boundary_mae": boundary_mae,
        "measure_nlc_rate": nlc_rate,
    }


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
            local_measure_kpis: Dict[str, Optional[float]] = {
                "measure_match_tp": None,
                "measure_match_fp": None,
                "measure_match_fn": None,
                "measure_match_recall": None,
                "measure_match_precision": None,
                "measure_boundary_mae": None,
                "measure_nlc_rate": None,
            }
            if args.numbering_eval and pipeline is not None and staff_mask is not None:
                image_path = images_root / score_name / f"{page_name}.png"
                if image_path.exists():
                    img = cv2.imread(str(image_path))
                    if img is not None:
                        h, w = img.shape[:2]
                        pred_page = pipeline.process_page(
                            barline_boxes=[list(b) for b in accepted],
                            staff_mask_path=staff_mask,
                            image_size=(w, h),
                            page_number=1,
                            image=img,
                        )
                        gt_page = pipeline.process_page(
                            barline_boxes=[list(b) for b in gt_boxes],
                            staff_mask_path=staff_mask,
                            image_size=(w, h),
                            page_number=1,
                            image=img,
                        )
                        pred_score = Score()
                        pred_score.pages.append(pred_page)
                        pipeline.numberer.number_score(pred_score, start_number=1)

                        gt_score = Score()
                        gt_score.pages.append(gt_page)
                        pipeline.numberer.number_score(gt_score, start_number=1)

                        pred_measures = _extract_measures(pred_page)
                        gt_measures = _extract_measures(gt_page)
                        measure_pred_proxy = len(pred_measures)
                        measure_gt_proxy = len(gt_measures)
                        measure_abs_delta = abs(measure_pred_proxy - measure_gt_proxy)
                        local_measure_kpis = _measure_local_kpis(gt_measures, pred_measures)

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
                    measure_match_tp=(
                        int(local_measure_kpis["measure_match_tp"])
                        if local_measure_kpis["measure_match_tp"] is not None
                        else None
                    ),
                    measure_match_fp=(
                        int(local_measure_kpis["measure_match_fp"])
                        if local_measure_kpis["measure_match_fp"] is not None
                        else None
                    ),
                    measure_match_fn=(
                        int(local_measure_kpis["measure_match_fn"])
                        if local_measure_kpis["measure_match_fn"] is not None
                        else None
                    ),
                    measure_match_recall=local_measure_kpis["measure_match_recall"],
                    measure_match_precision=local_measure_kpis["measure_match_precision"],
                    measure_boundary_mae=local_measure_kpis["measure_boundary_mae"],
                    measure_nlc_rate=local_measure_kpis["measure_nlc_rate"],
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
            "measure_match_tp": 0,
            "measure_match_fp": 0,
            "measure_match_fn": 0,
            "measure_boundary_mae_sum": 0.0,
            "measure_boundary_mae_pages": 0,
            "measure_nlc_sum": 0.0,
            "measure_nlc_pages": 0,
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
        if r.measure_match_tp is not None:
            a["measure_match_tp"] += r.measure_match_tp
        if r.measure_match_fp is not None:
            a["measure_match_fp"] += r.measure_match_fp
        if r.measure_match_fn is not None:
            a["measure_match_fn"] += r.measure_match_fn
        if r.measure_boundary_mae is not None:
            a["measure_boundary_mae_sum"] += r.measure_boundary_mae
            a["measure_boundary_mae_pages"] += 1
        if r.measure_nlc_rate is not None:
            a["measure_nlc_sum"] += r.measure_nlc_rate
            a["measure_nlc_pages"] += 1

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
            "measure_match_recall": (
                a["measure_match_tp"] / (a["measure_match_tp"] + a["measure_match_fn"])
                if (a["measure_match_tp"] + a["measure_match_fn"]) > 0
                else ""
            ),
            "measure_match_precision": (
                a["measure_match_tp"] / (a["measure_match_tp"] + a["measure_match_fp"])
                if (a["measure_match_tp"] + a["measure_match_fp"]) > 0
                else ""
            ),
            "measure_boundary_mae_mean": (
                a["measure_boundary_mae_sum"] / a["measure_boundary_mae_pages"]
                if a["measure_boundary_mae_pages"]
                else ""
            ),
            "measure_nlc_rate_mean": (
                a["measure_nlc_sum"] / a["measure_nlc_pages"] if a["measure_nlc_pages"] else ""
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
