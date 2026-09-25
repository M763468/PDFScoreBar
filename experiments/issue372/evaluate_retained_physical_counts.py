#!/usr/bin/env python3
"""Compare physical measure topology from retained detections and evaluation2 GT.

The GT's printed measure-number fields are intentionally ignored. Both inputs
use the same retained staff mask, image, and production system builder, so this
isolates the effect of barline geometry on the count downstream of detection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2

from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.pipeline.steps.barlines import normalize_barlines


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def host_path(value: str, repo: Path) -> Path:
    return repo / value.removeprefix("/workspace/") if value.startswith("/workspace/") else Path(value)


def topology(pipeline: MeasureNumberingPipeline, boxes, mask: Path, image, page_number: int):
    page = pipeline.process_page(
        boxes, mask, (image.shape[1], image.shape[0]), page_number=page_number, image=image
    )
    rows = []
    for raw_index, system in enumerate(page.systems):
        pipeline.numberer.number_system(system, 1)
        if system.measures:
            rows.append({
                "raw_index": raw_index,
                "staff_y": [round(sum((s.bbox.y1, s.bbox.y2)) / 2) for s in system.staves],
                "count": len(system.measures),
                "intervals": [[m.bbox.x1, m.bbox.x2] for m in system.measures],
            })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--image-root", type=Path, required=True)
    parser.add_argument("--gt-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--score")
    parser.add_argument("--page")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    source = load(args.report)
    pipeline = MeasureNumberingPipeline()
    rows = []
    for summary in source["score_summaries"]:
        score = summary["score"]
        if args.score and args.score != score:
            continue
        manifest = load(host_path(summary["pipeline_run"], args.repo) / "manifest.json")
        for page_index, item in enumerate(manifest["pages"]):
            page_id = item["page_id"]
            if args.page and args.page != page_id:
                continue
            image_path = args.image_root / score / f"{page_id}.png"
            image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
            if image is None:
                raise FileNotFoundError(image_path)
            mask_path = host_path(item["staff_mask"], args.repo)
            pred_path = host_path(summary["page_results"][page_id]["final_detector"], args.repo)
            gt_path = args.gt_root / score / page_id / "boxes_sorted.json"
            pred_boxes = normalize_barlines(load(pred_path))
            gt_boxes = [row["barline_location"] for row in load(gt_path)]
            predicted = topology(pipeline, pred_boxes, mask_path, image, page_index + 1)
            reference = topology(pipeline, gt_boxes, mask_path, image, page_index + 1)
            same_system_counts = [row["count"] for row in predicted] == [
                row["count"] for row in reference
            ]
            boundary_shifts = []
            if same_system_counts:
                for pred_system, gt_system in zip(predicted, reference):
                    for pred_interval, gt_interval in zip(
                        pred_system["intervals"], gt_system["intervals"]
                    ):
                        boundary_shifts.extend(
                            abs(pred_x - gt_x)
                            for pred_x, gt_x in zip(pred_interval, gt_interval)
                        )
            rows.append({
                "score": score, "page": page_id,
                "predicted": predicted, "gt_geometry": reference,
                "predicted_total": sum(row["count"] for row in predicted),
                "gt_geometry_total": sum(row["count"] for row in reference),
                "same_system_counts": same_system_counts,
                "boundary_max_shift_px": max(boundary_shifts) if boundary_shifts else None,
                "boundary_count": len(boundary_shifts),
                "image_sha256": digest(image_path),
                "mask_sha256": digest(mask_path),
                "pred_sha256": digest(pred_path),
                "gt_sha256": digest(gt_path),
            })
            print(score, page_id, rows[-1]["predicted_total"], rows[-1]["gt_geometry_total"], flush=True)
    result = {
        "schema_version": "issue372.physical_count_comparison.v1",
        "analysis_script_sha256": digest(Path(__file__)),
        "numbering_source_sha256": digest(
            Path(__file__).resolve().parents[2] / "src/measure_numbering/numbering.py"
        ),
        "builder_source_sha256": digest(
            Path(__file__).resolve().parents[2] / "src/measure_numbering/builder.py"
        ),
        "producer_report": str(args.report),
        "producer_report_sha256": digest(args.report),
        "source_commit": source.get("source_commit"),
        "page_count": len(rows),
        "total_predicted": sum(row["predicted_total"] for row in rows),
        "total_gt_geometry": sum(row["gt_geometry_total"] for row in rows),
        "different_page_count": sum(row["predicted_total"] != row["gt_geometry_total"] for row in rows),
        "different_system_count_pages": sum(not row["same_system_counts"] for row in rows),
        "boundary_max_shift_px": max(
            (row["boundary_max_shift_px"] for row in rows
             if row["boundary_max_shift_px"] is not None), default=None
        ),
        "boundary_count": sum(row["boundary_count"] for row in rows),
        "pages": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
