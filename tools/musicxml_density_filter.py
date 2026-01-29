#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from src.common.barline_evaluation import barline_iou, greedy_barline_match

Box = Tuple[int, int, int, int]


@dataclass
class MeasureInfo:
    number: str
    beats: Optional[int]
    beat_type: Optional[int]
    divisions: Optional[int]
    expected_duration: Optional[float]
    note_count: int
    rest_count: int
    duration_sum: int


def parse_musicxml(xml_path: Path) -> List[MeasureInfo]:
    root = ET.parse(xml_path).getroot()
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    parts = root.findall(f"{ns}part")
    if not parts:
        return []

    measures = []
    current_divisions = None
    current_beats = None
    current_beat_type = None

    for measure in parts[0].findall(f"{ns}measure"):
        number = measure.attrib.get("number", "")
        for attrs in measure.findall(f"{ns}attributes"):
            divisions = attrs.find(f"{ns}divisions")
            if divisions is not None and divisions.text:
                current_divisions = int(divisions.text)
            time = attrs.find(f"{ns}time")
            if time is not None:
                beats = time.find(f"{ns}beats")
                beat_type = time.find(f"{ns}beat-type")
                if beats is not None and beats.text:
                    current_beats = int(beats.text)
                if beat_type is not None and beat_type.text:
                    current_beat_type = int(beat_type.text)

        note_count = 0
        rest_count = 0
        duration_sum = 0
        for note in measure.findall(f"{ns}note"):
            # skip grace notes
            if note.find(f"{ns}grace") is not None:
                continue
            is_rest = note.find(f"{ns}rest") is not None
            duration = note.find(f"{ns}duration")
            if duration is not None and duration.text:
                duration_sum += int(duration.text)
            if is_rest:
                rest_count += 1
            else:
                note_count += 1

        expected_duration = None
        if current_divisions and current_beats and current_beat_type:
            expected_duration = current_beats * current_divisions * (4.0 / current_beat_type)

        measures.append(
            MeasureInfo(
                number=number,
                beats=current_beats,
                beat_type=current_beat_type,
                divisions=current_divisions,
                expected_duration=expected_duration,
                note_count=note_count,
                rest_count=rest_count,
                duration_sum=duration_sum,
            )
        )
    return measures


def load_json(path: Path):
    return json.loads(path.read_text())


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def compute_core_mask(mask: np.ndarray, core_scale: float) -> np.ndarray:
    dist = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    dist_max = dist.max() if dist.size else 0.0
    core = dist >= (dist_max * core_scale) if dist_max > 0 else np.zeros_like(mask, dtype=bool)
    return core.astype(np.uint8) * 255


def remove_by_core(
    boxes: List[Box],
    core: np.ndarray,
    rx: int,
    ry: int,
) -> List[Box]:
    kept = []
    for box in boxes:
        x1, y1, x2, y2 = box
        xc = int(round((x1 + x2) / 2))
        windows = [
            (xc - rx, y1 - ry, xc + rx, y1 + ry),
            (xc - rx, y2 - ry, xc + rx, y2 + ry),
        ]
        hit = False
        for wx1, wy1, wx2, wy2 in windows:
            wx1c = max(0, wx1)
            wy1c = max(0, wy1)
            wx2c = min(core.shape[1] - 1, wx2)
            wy2c = min(core.shape[0] - 1, wy2)
            if wx1c >= wx2c or wy1c >= wy2c:
                continue
            if core[wy1c : wy2c + 1, wx1c : wx2c + 1].any():
                hit = True
                break
        if not hit:
            kept.append(box)
    return kept


def assign_staff(
    box: Box,
    staff_comps: List[Dict[str, int]],
) -> Optional[Dict[str, int]]:
    x1, y1, x2, y2 = box
    best = None
    best_overlap = 0
    for comp in staff_comps:
        cx1 = comp["x"]
        cy1 = comp["y"]
        cx2 = comp["x"] + comp["w"]
        cy2 = comp["y"] + comp["h"]
        if cx2 < x1 or x2 < cx1 or cy2 < y1 or y2 < cy1:
            continue
        ix1, iy1 = max(x1, cx1), max(y1, cy1)
        ix2, iy2 = min(x2, cx2), min(y2, cy2)
        overlap = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        if overlap > best_overlap:
            best_overlap = overlap
            best = comp
    return best


def load_detections(path: Path) -> List[Dict[str, object]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return data.get("predictions", [])


def barline_score(box: Box, barline_mask: np.ndarray) -> float:
    x1, y1, x2, y2 = box
    crop = barline_mask[y1 : y2 + 1, x1 : x2 + 1]
    return float((crop > 0).sum()) / max(1, crop.size)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-tag", default=None)
    parser.add_argument("--output-root", type=Path, default=Path("logs/musicxml_density_filter"))
    parser.add_argument(
        "--baseline-root",
        type=Path,
        default=Path("logs/gt_rebuild_hybrid_eval/repro_var88_from_logs_reuse_rows_probe_eps"),
    )
    parser.add_argument(
        "--homr-root", type=Path, default=Path("logs/homr_eval/20251229T_gt_rebuild_eval")
    )
    parser.add_argument("--ratio", type=float, default=0.30)
    parser.add_argument("--min-notes", type=int, default=8)
    parser.add_argument("--notehead-density-max", type=float, default=0.02)
    parser.add_argument("--use-detections-align", action="store_true")
    parser.add_argument("--core-scale", type=float, default=0.50)
    parser.add_argument("--rx-scale", type=float, default=0.06)
    parser.add_argument("--ry-scale", type=float, default=0.60)
    args = parser.parse_args()

    pages = {
        "page_001": {
            "image": Path("data/evaluation2/images/Va_Prokofiev_Symphony1/page_001.png"),
            "xml": args.homr_root / "page_001" / "page_001.musicxml",
            "gt": Path(
                "data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_001/boxes_sorted_v20251229.json"
            ),
        },
        "page_004": {
            "image": Path("data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png"),
            "xml": args.homr_root / "page_004" / "page_004.musicxml",
            "gt": Path(
                "data/evaluation2/annotations/Va_Prokofiev_Symphony1/page_004/boxes_sorted_v20251229.json"
            ),
        },
        "page_10": {
            "image": Path("data/training/images/page_10.png"),
            "xml": args.homr_root / "page_10" / "page_10.musicxml",
            "gt": Path("data/training/annotations/page_010/boxes_sorted_v20251229.json"),
        },
        "page_15": {
            "image": Path("data/training/images/page_15.png"),
            "xml": args.homr_root / "page_15" / "page_15.musicxml",
            "gt": Path("data/training/annotations/page_015/boxes_sorted_v20251229.json"),
        },
    }

    run_id = args.run_tag or datetime.now().strftime("%Y%m%dT%H%M%S") + "_var88_repro"
    out_root = args.output_root / run_id
    ensure_dir(out_root)

    summary: Dict[str, Dict[str, int]] = {}

    for page, info in pages.items():
        page_dir = args.baseline_root / "per_page" / page
        pred_boxes = load_json(page_dir / "geom_kept.json")
        tp_boxes = load_json(page_dir / "tp_boxes.json")
        fp_boxes = load_json(page_dir / "fp_boxes.json")
        gt_entries = load_json(info["gt"])
        gt_boxes = [e["barline_location"] for e in gt_entries]

        measures = parse_musicxml(info["xml"])

        img = cv2.imread(str(info["image"]), cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError(f"Failed to read image: {info['image']}")

        # masks
        clef = cv2.imread(
            str(args.homr_root / page / f"{page}_debug_7_clefs_keys.png"), cv2.IMREAD_GRAYSCALE
        )
        staff = cv2.imread(
            str(args.homr_root / page / f"{page}_debug_15_staffs.png"), cv2.IMREAD_GRAYSCALE
        )
        barline = cv2.imread(
            str(args.homr_root / page / f"{page}_debug_11_bar_lines.png"), cv2.IMREAD_GRAYSCALE
        )
        notehead = cv2.imread(
            str(args.homr_root / page / f"{page}_debug_6_notehead.png"), cv2.IMREAD_GRAYSCALE
        )
        if clef is None or staff is None or barline is None or notehead is None:
            raise RuntimeError(f"Failed to read masks for {page}")

        if clef.shape[:2] != img.shape[:2]:
            clef = cv2.resize(clef, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
        if staff.shape[:2] != img.shape[:2]:
            staff = cv2.resize(staff, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
        if barline.shape[:2] != img.shape[:2]:
            barline = cv2.resize(
                barline, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST
            )
        if notehead.shape[:2] != img.shape[:2]:
            notehead = cv2.resize(
                notehead, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST
            )

        _, clef_bin = cv2.threshold(clef, 0, 255, cv2.THRESH_BINARY)
        _, staff_bin = cv2.threshold(staff, 0, 255, cv2.THRESH_BINARY)
        _, barline_bin = cv2.threshold(barline, 0, 255, cv2.THRESH_BINARY)
        _, notehead_bin = cv2.threshold(notehead, 0, 255, cv2.THRESH_BINARY)

        heights = [b[3] - b[1] for b in pred_boxes]
        median_height = int(np.median(heights)) if heights else 0
        rx = int(round(median_height * args.rx_scale))
        ry = int(round(median_height * args.ry_scale))

        core = compute_core_mask(clef_bin, args.core_scale)
        kept_core = remove_by_core(pred_boxes, core, rx, ry)

        # staff components for grouping
        num, labels, stats, _ = cv2.connectedComponentsWithStats(staff_bin, connectivity=8)
        staff_comps = []
        for i in range(1, num):
            x, y, w, h, area = stats[i]
            staff_comps.append({"x": x, "y": y, "w": w, "h": h, "id": i})

        detections = load_detections(args.homr_root / page / f"{page}_detections.json")
        detection_groups: Dict[int, List[Box]] = {}
        if args.use_detections_align and detections:
            for det in detections:
                box = tuple(det["orig_bbox"])
                comp = assign_staff(box, staff_comps)
                if not comp:
                    continue
                detection_groups.setdefault(comp["id"], []).append(box)
            for comp_id in list(detection_groups.keys()):
                detection_groups[comp_id] = sorted(
                    detection_groups[comp_id],
                    key=lambda b: (b[0] + b[2]) / 2.0,
                )

        # group candidates by staff
        staff_groups: Dict[int, List[Box]] = {}
        for box in kept_core:
            comp = assign_staff(box, staff_comps)
            if not comp:
                continue
            staff_groups.setdefault(comp["id"], []).append(box)

        removed = []
        kept = []
        pair_rows = []

        for group_id, boxes in staff_groups.items():
            if len(boxes) < 2:
                kept.extend(boxes)
                continue

            boxes_sorted = sorted(boxes, key=lambda b: (b[0] + b[2]) / 2.0)
            xs = [(b[0] + b[2]) / 2.0 for b in boxes_sorted]
            spacings = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
            if not spacings:
                kept.extend(boxes_sorted)
                continue

            median_spacing = float(np.median(spacings))
            det_pairs = 0
            if args.use_detections_align and group_id in detection_groups:
                det_pairs = max(0, len(detection_groups[group_id]) - 1)
            max_pairs = min(len(spacings), len(measures), det_pairs or len(measures))

            for i in range(len(spacings)):
                left = boxes_sorted[i]
                right = boxes_sorted[i + 1]
                spacing = spacings[i]
                ratio = spacing / median_spacing if median_spacing else 0.0

                measure = measures[i] if i < max_pairs else None
                note_count = measure.note_count if measure else None
                rest_count = measure.rest_count if measure else None

                # notehead density in gap (staff range)
                comp = next((c for c in staff_comps if c["id"] == group_id), None)
                if comp is None:
                    kept.append(right)
                    continue
                sx1 = int(min(xs[i], xs[i + 1]))
                sx2 = int(max(xs[i], xs[i + 1]))
                sy1 = comp["y"]
                sy2 = comp["y"] + comp["h"]
                note_crop = notehead_bin[sy1:sy2, sx1:sx2]
                note_density = float((note_crop > 0).sum()) / max(1, note_crop.size)

                pair_rows.append(
                    {
                        "staff_id": group_id,
                        "pair_index": i,
                        "spacing": spacing,
                        "median_spacing": median_spacing,
                        "ratio": ratio,
                        "note_density": note_density,
                        "measure_number": measure.number if measure else None,
                        "measure_notes": note_count,
                        "measure_rests": rest_count,
                        "expected_duration": measure.expected_duration if measure else None,
                    }
                )

                should_remove = (
                    measure is not None
                    and note_count is not None
                    and note_count >= args.min_notes
                    and ratio < args.ratio
                    and note_density < args.notehead_density_max
                )
                if should_remove:
                    left_score = barline_score(left, barline_bin)
                    right_score = barline_score(right, barline_bin)
                    target = left if left_score <= right_score else right
                    removed.append(target)
                else:
                    kept.append(left)

            kept.append(boxes_sorted[-1])

        kept_final = [box for box in kept if box not in removed]

        match = greedy_barline_match(kept_final, gt_boxes, iou_threshold=0.5)
        tp = len(match.matches)
        fp = len(match.false_positive_indices)
        fn = len(match.false_negative_indices)

        removed_tp = []
        removed_fp = []
        for box in removed:
            if any(barline_iou(box, tpbox) >= 0.5 for tpbox in tp_boxes):
                removed_tp.append(box)
            elif any(barline_iou(box, fpbox) >= 0.5 for fpbox in fp_boxes):
                removed_fp.append(box)

        removed_fp_flags = []
        for fpbox in fp_boxes:
            removed_fp_flags.append(any(barline_iou(fpbox, r) >= 0.5 for r in removed_fp))

        out_dir = out_root / page
        ensure_dir(out_dir)

        # baseline FP visuals
        for idx, (box, is_removed) in enumerate(zip(fp_boxes, removed_fp_flags)):
            x1, y1, x2, y2 = box
            margin = 60
            sx1 = max(0, x1 - margin)
            sy1 = max(0, y1 - margin)
            sx2 = min(img.shape[1] - 1, x2 + margin)
            sy2 = min(img.shape[0] - 1, y2 + margin)
            crop = img[sy1 : sy2 + 1, sx1 : sx2 + 1].copy()
            color = (255, 0, 255) if is_removed else (0, 0, 255)
            cv2.rectangle(crop, (x1 - sx1, y1 - sy1), (x2 - sx1, y2 - sy1), color, 2)
            label = "REMOVED_FP" if is_removed else "BASE_FP"
            cv2.putText(crop, label, (5, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
            out_name = f"fp_{idx:02d}_{label}_x{x1}_y{y1}_x{x2}_y{y2}.png"
            cv2.imwrite(str(out_dir / out_name), crop)

        # new FN visuals
        for idx, box in enumerate(removed_tp):
            x1, y1, x2, y2 = box
            margin = 60
            sx1 = max(0, x1 - margin)
            sy1 = max(0, y1 - margin)
            sx2 = min(img.shape[1] - 1, x2 + margin)
            sy2 = min(img.shape[0] - 1, y2 + margin)
            crop = img[sy1 : sy2 + 1, sx1 : sx2 + 1].copy()
            cv2.rectangle(crop, (x1 - sx1, y1 - sy1), (x2 - sx1, y2 - sy1), (0, 0, 255), 2)
            cv2.putText(
                crop, "NEW_FN", (5, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA
            )
            out_name = f"fn_{idx:02d}_NEW_FN_x{x1}_y{y1}_x{x2}_y{y2}.png"
            cv2.imwrite(str(out_dir / out_name), crop)

        summary[page] = {
            "TP": tp,
            "FP": fp,
            "FN": fn,
            "removed_fp_count": len(removed_fp),
            "new_fn_count": len(removed_tp),
            "pair_count": len(pair_rows),
        }

        (out_dir / "pair_stats.json").write_text(json.dumps(pair_rows, indent=2), encoding="utf-8")

    (out_root / "summary.json").write_text(
        json.dumps(
            {
                "config": {
                    "ratio": args.ratio,
                    "min_notes": args.min_notes,
                    "notehead_density_max": args.notehead_density_max,
                    "core_scale": args.core_scale,
                    "rx_scale": args.rx_scale,
                    "ry_scale": args.ry_scale,
                    "use_detections_align": args.use_detections_align,
                },
                "summary": summary,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(out_root)


if __name__ == "__main__":
    main()
