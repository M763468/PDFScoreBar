#!/usr/bin/env python3
"""Audit evaluation2 barline GT for exact/near-duplicate and multi-line cases.

Issue #274 investigation helper.

This is an audit-only tool.  It never modifies `data/evaluation2/annotations`.
It scans the authoritative `boxes_sorted.json`, compares it with `raw_boxes.json`
and `boxes_provisional.json`, classifies suspicious bbox pairs conservatively, and
writes:

- a machine-readable JSON report;
- a CSV review list;
- optional image crops for suspicious pairs;
- a config for the existing `tools/gt_relabel_gui` that saves reviewed copies under
  the audit output root instead of overwriting the authoritative GT.

The classification intentionally separates:

1. bbox duplication / overlap;
2. declared musical multi-line events (`double_barline`, `end_barline`, `repeat`);
3. close ordinary `barline` pairs that require human review.

It does not automatically delete or relabel any GT record.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ANNOTATIONS = Path("data/evaluation2/annotations")
DEFAULT_IMAGES = Path("data/evaluation2/images")
DEFAULT_OUTPUT = Path(
    "logs/issue274_homr_unification_analysis/evaluation2_gt_near_duplicate_audit_01"
)

# Existing GUI Auto Dedup contract, tools/gt_relabel_gui/app_gt.js.
GUI_DEDUP_X_CENTER_TOL = 3.0
GUI_DEDUP_Y_OVERLAP_MIN = 0.70

# Current MeasureNumberer uses bbox.x1 distance < 15 px inside one system.
# This is only recorded as downstream context; it is not used to call a GT pair valid.
NUMBERER_X1_DEDUP_TOL = 15.0

DECLARED_MULTI_TYPES = {"double_barline", "end_barline", "repeat"}

# Audit-only review thresholds.  High-overlap means likely same physical ink region,
# but the tool still requires human review before correction.
HIGH_Y_OVERLAP = 0.70
SAME_INK_X_OVERLAP = 0.25
CLOSE_X_CENTER_REVIEW = 15.0
PARTIAL_Y_OVERLAP_MIN = 0.15

FOCUSED = {
    ("Shostakovich-Sym5-Va", "page_013"): {
        (1679, 1168, 1683, 1270),
        (1679, 1202, 1683, 1296),
    },
    ("Shostakovich-Sym5-Va", "page_015"): {
        (2294, 2244, 2298, 2344),
        (2296, 2246, 2305, 2344),
    },
    ("Sibelius-Violin_Concerto-Viola", "page_004"): {
        (1514, 4015, 1518, 4195),
        (1514, 4092, 1518, 4196),
        (1923, 4092, 1927, 4196),
        (1924, 4015, 1928, 4195),
    },
}


@dataclass(frozen=True)
class Record:
    index: int
    bbox: tuple[int, int, int, int]
    barline_type: str
    measure_number: int | None


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def normalize_bbox(value: Sequence[Any]) -> tuple[int, int, int, int]:
    if len(value) < 4:
        raise ValueError(f"Invalid bbox: {value!r}")
    x1, y1, x2, y2 = (int(round(float(v))) for v in value[:4])
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    return x1, y1, x2, y2


def parse_records(path: Path) -> list[Record]:
    if not path.is_file():
        return []
    payload = load_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"Expected list: {path}")
    records: list[Record] = []
    for index, item in enumerate(payload):
        if isinstance(item, (list, tuple)):
            bbox = normalize_bbox(item)
            records.append(Record(index, bbox, "barline", None))
            continue
        if not isinstance(item, dict):
            continue
        value = item.get("barline_location") or item.get("bbox") or item.get("box")
        if not isinstance(value, (list, tuple)) or len(value) < 4:
            continue
        measure_number = item.get("measure_number")
        records.append(
            Record(
                index=index,
                bbox=normalize_bbox(value),
                barline_type=str(item.get("barline_type") or item.get("type") or "barline"),
                measure_number=(
                    int(measure_number) if isinstance(measure_number, (int, float)) else None
                ),
            )
        )
    return records


def multiset(records: Iterable[Record]) -> Counter[tuple[tuple[int, int, int, int], str]]:
    return Counter((record.bbox, record.barline_type) for record in records)


def interval_overlap(a1: int, a2: int, b1: int, b2: int) -> int:
    return max(0, min(a2, b2) - max(a1, b1))


def interval_gap(a1: int, a2: int, b1: int, b2: int) -> int:
    if a2 < b1:
        return b1 - a2
    if b2 < a1:
        return a1 - b2
    return 0


def pair_metrics(a: Record, b: Record) -> dict[str, Any]:
    ax1, ay1, ax2, ay2 = a.bbox
    bx1, by1, bx2, by2 = b.bbox
    aw = max(1, ax2 - ax1)
    bw = max(1, bx2 - bx1)
    ah = max(1, ay2 - ay1)
    bh = max(1, by2 - by1)
    x_overlap = interval_overlap(ax1, ax2, bx1, bx2)
    y_overlap = interval_overlap(ay1, ay2, by1, by2)
    x_union = max(ax2, bx2) - min(ax1, bx1)
    y_union = max(ay2, by2) - min(ay1, by1)
    acx = (ax1 + ax2) / 2.0
    bcx = (bx1 + bx2) / 2.0
    return {
        "exact_bbox": a.bbox == b.bbox,
        "x_center_delta": abs(acx - bcx),
        "x1_delta": abs(ax1 - bx1),
        "x_gap": interval_gap(ax1, ax2, bx1, bx2),
        "x_overlap_px": x_overlap,
        "x_overlap_over_min_width": x_overlap / min(aw, bw),
        "x_iou_1d": x_overlap / max(1, x_union),
        "y_overlap_px": y_overlap,
        "y_overlap_over_min_height": y_overlap / min(ah, bh),
        "y_iou_1d": y_overlap / max(1, y_union),
    }


def classify_pair(
    a: Record, b: Record, metrics: dict[str, Any]
) -> tuple[str | None, str | None, list[str]]:
    types = {a.barline_type, b.barline_type}
    both_plain = a.barline_type == "barline" and b.barline_type == "barline"
    declared_multi = bool(types & DECLARED_MULTI_TYPES)
    exact = bool(metrics["exact_bbox"])
    x_overlap = float(metrics["x_overlap_over_min_width"])
    y_overlap = float(metrics["y_overlap_over_min_height"])
    x_center_delta = float(metrics["x_center_delta"])

    gui_dedup = x_center_delta <= GUI_DEDUP_X_CENTER_TOL and y_overlap >= GUI_DEDUP_Y_OVERLAP_MIN
    reasons: list[str] = []

    if exact:
        reasons.append("identical bbox appears more than once")
        return "P0", "exact_duplicate", reasons

    if both_plain and x_overlap >= SAME_INK_X_OVERLAP and y_overlap >= HIGH_Y_OVERLAP:
        reasons.append("ordinary barline bboxes overlap in both x and y")
        reasons.append("GT policy says one bbox per physical vertical line")
        if gui_dedup:
            reasons.append("pair also matches existing GT GUI Auto Dedup rule")
        return "P1", "ordinary_same_ink_high_overlap", reasons

    if both_plain and x_center_delta <= CLOSE_X_CENTER_REVIEW and y_overlap >= HIGH_Y_OVERLAP:
        reasons.append("ordinary barlines are very close in x with strong vertical overlap")
        reasons.append("could be duplicate annotation or an unlabeled multi-line event")
        return "P2", "ordinary_close_parallel_high_overlap", reasons

    if both_plain and x_overlap >= SAME_INK_X_OVERLAP and y_overlap >= PARTIAL_Y_OVERLAP_MIN:
        reasons.append("ordinary barline bboxes share x ink region and overlap vertically")
        reasons.append("manual review needed for split-staff/divisi versus duplicate annotation")
        return "P2", "ordinary_same_x_partial_overlap", reasons

    if declared_multi and x_center_delta <= CLOSE_X_CENTER_REVIEW and y_overlap >= HIGH_Y_OVERLAP:
        reasons.append("declared multi-line bar event; close boxes are expected in principle")
        reasons.append("verify that boxes actually cover distinct physical vertical lines")
        return "P3", "declared_multiline_event_pair", reasons

    return None, None, []


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def in_provisional(record: Record, provisional: set[tuple[int, int, int, int]]) -> bool:
    return record.bbox in provisional


def render_pair_crop(
    *,
    image_path: Path,
    a: Record,
    b: Record,
    output: Path,
    label: str,
    padding: int,
) -> bool:
    try:
        import cv2
    except ImportError:
        return False
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        return False
    height, width = image.shape[:2]
    xs = [a.bbox[0], a.bbox[2], b.bbox[0], b.bbox[2]]
    ys = [a.bbox[1], a.bbox[3], b.bbox[1], b.bbox[3]]
    x1 = max(0, min(xs) - padding)
    y1 = max(0, min(ys) - padding)
    x2 = min(width, max(xs) + padding)
    y2 = min(height, max(ys) + padding)
    crop = image[y1:y2, x1:x2].copy()
    if crop.size == 0:
        return False

    def shifted(box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        return box[0] - x1, box[1] - y1, box[2] - x1, box[3] - y1

    for box, color, text in (
        (shifted(a.bbox), (0, 255, 0), f"A#{a.index} {a.barline_type}"),
        (shifted(b.bbox), (0, 0, 255), f"B#{b.index} {b.barline_type}"),
    ):
        bx1, by1, bx2, by2 = box
        cv2.rectangle(crop, (bx1, by1), (bx2, by2), color, 2)
        cv2.putText(
            crop,
            text,
            (max(0, bx1), max(14, by1 - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA,
        )
    cv2.putText(
        crop,
        label,
        (8, 18),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (255, 0, 255),
        1,
        cv2.LINE_AA,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    return bool(cv2.imwrite(str(output), crop))


def page_entries(annotation_root: Path) -> list[tuple[str, str, Path]]:
    entries: list[tuple[str, str, Path]] = []
    for sorted_path in sorted(annotation_root.glob("*/page_*/boxes_sorted.json")):
        page_dir = sorted_path.parent
        score = page_dir.parent.name
        page = page_dir.name
        entries.append((score, page, page_dir))
    return entries


def focused_pair_flag(score: str, page: str, a: Record, b: Record) -> bool:
    focused = FOCUSED.get((score, page), set())
    return a.bbox in focused and b.bbox in focused


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--images", type=Path, default=DEFAULT_IMAGES)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--no-render", action="store_true")
    parser.add_argument("--crop-padding", type=int, default=100)
    args = parser.parse_args()

    annotation_root = (
        (ROOT / args.annotations).resolve()
        if not args.annotations.is_absolute()
        else args.annotations.resolve()
    )
    image_root = (
        (ROOT / args.images).resolve() if not args.images.is_absolute() else args.images.resolve()
    )
    output_root = (
        (ROOT / args.output_root).resolve()
        if not args.output_root.is_absolute()
        else args.output_root.resolve()
    )
    output_root.mkdir(parents=True, exist_ok=True)

    page_reports: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    class_counts: Counter[str] = Counter()
    priority_counts: Counter[str] = Counter()
    label_counts: Counter[str] = Counter()
    raw_sorted_mismatch_pages: list[str] = []
    review_pages: dict[tuple[str, str], dict[str, Any]] = {}

    entries = page_entries(annotation_root)
    pair_id = 0
    for score, page, page_dir in entries:
        sorted_path = page_dir / "boxes_sorted.json"
        raw_path = page_dir / "raw_boxes.json"
        provisional_path = page_dir / "boxes_provisional.json"
        image_path = image_root / score / f"{page}.png"

        sorted_records = parse_records(sorted_path)
        raw_records = parse_records(raw_path)
        provisional_records = parse_records(provisional_path)
        provisional_boxes = {record.bbox for record in provisional_records}
        label_counts.update(record.barline_type for record in sorted_records)

        raw_sorted_equal = bool(raw_records) and multiset(raw_records) == multiset(sorted_records)
        if not raw_sorted_equal:
            raw_sorted_mismatch_pages.append(f"{score}/{page}")

        page_pairs: list[dict[str, Any]] = []
        for i, a in enumerate(sorted_records):
            for b in sorted_records[i + 1 :]:
                metrics = pair_metrics(a, b)
                priority, classification, reasons = classify_pair(a, b, metrics)
                if classification is None:
                    continue
                pair_id += 1
                class_counts[classification] += 1
                priority_counts[priority or "none"] += 1
                crop_rel = None
                if priority in {"P0", "P1", "P2"} and not args.no_render:
                    crop_path = (
                        output_root
                        / "crops"
                        / score
                        / page
                        / f"pair_{pair_id:04d}_{classification}.png"
                    )
                    if render_pair_crop(
                        image_path=image_path,
                        a=a,
                        b=b,
                        output=crop_path,
                        label=f"{priority} {classification}",
                        padding=args.crop_padding,
                    ):
                        crop_rel = rel(crop_path)

                row = {
                    "pair_id": pair_id,
                    "priority": priority,
                    "classification": classification,
                    "score": score,
                    "page": page,
                    "a": {
                        "index": a.index,
                        "bbox": list(a.bbox),
                        "barline_type": a.barline_type,
                        "measure_number": a.measure_number,
                        "present_in_provisional_seed": in_provisional(a, provisional_boxes),
                    },
                    "b": {
                        "index": b.index,
                        "bbox": list(b.bbox),
                        "barline_type": b.barline_type,
                        "measure_number": b.measure_number,
                        "present_in_provisional_seed": in_provisional(b, provisional_boxes),
                    },
                    "metrics": metrics,
                    "matches_existing_gui_auto_dedup": (
                        float(metrics["x_center_delta"]) <= GUI_DEDUP_X_CENTER_TOL
                        and float(metrics["y_overlap_over_min_height"]) >= GUI_DEDUP_Y_OVERLAP_MIN
                    ),
                    "within_measure_numberer_x1_dedup_threshold": (
                        float(metrics["x1_delta"]) < NUMBERER_X1_DEDUP_TOL
                    ),
                    "focused_issue274_pair": focused_pair_flag(score, page, a, b),
                    "reasons": reasons,
                    "crop": crop_rel,
                    "review_decision": None,
                }
                page_pairs.append(row)
                review_rows.append(row)
                if priority in {"P0", "P1", "P2"}:
                    review_pages[(score, page)] = {
                        "score": score,
                        "page": page,
                        "page_dir": page_dir,
                        "image": image_path,
                    }

        page_reports.append(
            {
                "score": score,
                "page": page,
                "sorted_path": rel(sorted_path),
                "raw_path": rel(raw_path),
                "provisional_path": rel(provisional_path),
                "image": rel(image_path),
                "sorted_count": len(sorted_records),
                "raw_count": len(raw_records),
                "provisional_count": len(provisional_records),
                "raw_sorted_multiset_equal": raw_sorted_equal,
                "review_pair_count": len(page_pairs),
                "pairs": page_pairs,
            }
        )

    # Compact CSV for manual triage.
    csv_path = output_root / "issue274_evaluation2_gt_near_duplicate_review.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "pair_id",
                "priority",
                "classification",
                "score",
                "page",
                "a_bbox",
                "a_type",
                "b_bbox",
                "b_type",
                "x_center_delta",
                "x_overlap_over_min_width",
                "y_overlap_over_min_height",
                "a_in_provisional",
                "b_in_provisional",
                "gui_auto_dedup",
                "numberer_x1_dedup",
                "focused_issue274_pair",
                "crop",
            ],
        )
        writer.writeheader()
        for row in review_rows:
            writer.writerow(
                {
                    "pair_id": row["pair_id"],
                    "priority": row["priority"],
                    "classification": row["classification"],
                    "score": row["score"],
                    "page": row["page"],
                    "a_bbox": row["a"]["bbox"],
                    "a_type": row["a"]["barline_type"],
                    "b_bbox": row["b"]["bbox"],
                    "b_type": row["b"]["barline_type"],
                    "x_center_delta": row["metrics"]["x_center_delta"],
                    "x_overlap_over_min_width": row["metrics"]["x_overlap_over_min_width"],
                    "y_overlap_over_min_height": row["metrics"]["y_overlap_over_min_height"],
                    "a_in_provisional": row["a"]["present_in_provisional_seed"],
                    "b_in_provisional": row["b"]["present_in_provisional_seed"],
                    "gui_auto_dedup": row["matches_existing_gui_auto_dedup"],
                    "numberer_x1_dedup": row["within_measure_numberer_x1_dedup_threshold"],
                    "focused_issue274_pair": row["focused_issue274_pair"],
                    "crop": row["crop"],
                }
            )

    # Existing browser GT editor config.  Save to a review copy, never authoritative GT.
    gui_pages: list[dict[str, Any]] = []
    for score, page in sorted(review_pages):
        review_raw = output_root / "gui_review" / score / page / "raw_boxes.json"
        review_sorted = output_root / "gui_review" / score / page / "boxes_sorted.json"
        page_dir = annotation_root / score / page
        gui_pages.append(
            {
                "name": f"{score}/{page}",
                "image": rel(image_root / score / f"{page}.png"),
                "editable": rel(page_dir / "raw_boxes.json"),
                "output_raw": rel(review_raw),
                "output_sorted": rel(review_sorted),
                "y_threshold": 50,
                "references": [
                    {
                        "label": "provisional_seed",
                        "path": rel(page_dir / "boxes_provisional.json"),
                        "color": "#808080",
                    }
                ],
            }
        )
    gui_config_path = output_root / "evaluation2_gt_near_duplicate_review_config.json"
    write_json(gui_config_path, {"pages": gui_pages})

    focused_rows = [row for row in review_rows if row["focused_issue274_pair"]]
    report = {
        "schema_version": "issue274.evaluation2_gt_near_duplicate_audit.v1",
        "status": "completed",
        "scope": {
            "page_count": len(entries),
            "sorted_gt_count": sum(page["sorted_count"] for page in page_reports),
            "authoritative_gt_modified": False,
            "image_rendering_enabled": not args.no_render,
        },
        "policy_sources": {
            "gt_policy": "docs/GT_PREPARATION_POLICY.md: one bbox per physical vertical line; multi-line events use independent bboxes with semantic type labels",
            "gui_auto_dedup": {
                "source": "tools/gt_relabel_gui/app_gt.js",
                "x_center_tolerance_px": GUI_DEDUP_X_CENTER_TOL,
                "vertical_overlap_over_shorter_box": GUI_DEDUP_Y_OVERLAP_MIN,
            },
            "measure_numberer": {
                "source": "src/measure_numbering/numbering.py",
                "x1_dedup_threshold_px": NUMBERER_X1_DEDUP_TOL,
                "note": "downstream context only; applied within reconstructed systems and not a GT validity rule",
            },
        },
        "audit_classification": {
            "P0_exact_duplicate": "identical bbox repeated; requires review/correction",
            "P1_ordinary_same_ink_high_overlap": "plain barline boxes overlap substantially in both x and y; strongest policy-conflict candidate",
            "P2_ordinary_close_or_partial_overlap": "could be duplicate, staff split, or unlabeled multi-line event; manual review required",
            "P3_declared_multiline_event_pair": "semantic multi-line labels make close physical lines plausible; informational verification",
        },
        "summary": {
            "classification_counts": dict(class_counts),
            "priority_counts": dict(priority_counts),
            "label_counts": dict(label_counts),
            "review_page_count_p0_p2": len(review_pages),
            "raw_sorted_mismatch_page_count": len(raw_sorted_mismatch_pages),
            "raw_sorted_mismatch_pages": raw_sorted_mismatch_pages,
            "focused_issue274_flagged_pair_count": len(focused_rows),
        },
        "focused_issue274_pairs": focused_rows,
        "review_outputs": {
            "csv": rel(csv_path),
            "gui_config": rel(gui_config_path),
            "gui_review_outputs_root": rel(output_root / "gui_review"),
            "crops_root": rel(output_root / "crops"),
        },
        "gui_command": (
            "python3 tools/gt_relabel_gui/server.py --mode gt --root . "
            f"--config {rel(gui_config_path)} --host 127.0.0.1 --port 8010"
        ),
        "pages": page_reports,
        "decision_guardrails": [
            "Do not remove or relabel a GT pair from geometry alone.",
            "A declared double/end/repeat event must cover distinct physical vertical lines according to GT policy.",
            "Ordinary barline boxes that overlap in both x and y are review candidates, not automatically legitimate divisi labels.",
            "Keep GT correction separate from Issue 274 detector/HOMR architecture changes until the audit is reviewed.",
        ],
    }
    report_path = output_root / "issue274_evaluation2_gt_near_duplicate_audit.json"
    write_json(report_path, report)
    print(
        json.dumps(
            {
                "status": "completed",
                "output": str(report_path),
                "review_csv": str(csv_path),
                "gui_config": str(gui_config_path),
                "summary": report["summary"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
