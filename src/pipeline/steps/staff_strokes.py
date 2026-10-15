"""Normalize maintained dense CNN inputs without changing probe scan seeds."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from statistics import median

import cv2

from src.common.barline_strokes import StaffRegion, normalize_staff_stroke
from src.measure_numbering.pipeline import StaffExtractor
from src.pipeline.core import build_probe_run_id
from src.pipeline.steps.hybrid_consensus import apply_hybrid_consensus_filter, load_json_boxes


def prepare_staff_stroke_candidates(
    *, inventory: Path, hybrid_root: Path, probe_root: Path
) -> dict[str, float]:
    """Use declared fresh producer outputs; missing support fails explicitly.

    Raw generation, heuristic filtering and rescue have already completed. Their
    row-stat seeds stay unchanged; only CNN candidate geometry is replaced.
    """
    units = {}
    for record in json.loads(inventory.read_text())["records"]:
        image_path = Path(record["image"])
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(image_path)
        height, width = image.shape[:2]
        mask = Path(record["staff_mask"])
        regions = [
            StaffRegion((s.bbox.x1, s.bbox.y1, s.bbox.x2, s.bbox.y2), s.unit_size)
            for s in StaffExtractor().extract(mask, (width, height))
        ]
        run_id = build_probe_run_id(image_path, score_name=record["score"])
        target = probe_root / run_id / "pipeline2_no_peak_candidates.json"
        source_bytes = target.read_bytes()
        original_candidates = json.loads(source_bytes)
        if not regions:
            # Blank/non-staff pages are filtered downstream. Preserve their
            # detector output and do not invent a unit for duplicate handling.
            target.with_name("pipeline2_no_peak_staff_strokes.json").write_text(
                json.dumps(
                    {
                        "schema_version": "pipeline.staff_strokes.v1",
                        "status": "no_staff_geometry",
                        "source_candidates_sha256": hashlib.sha256(source_bytes).hexdigest(),
                        "source_count": len(original_candidates),
                    },
                    indent=2,
                )
                + "\n"
            )
            continue
        units[str(image_path)] = float(median(s.unit_size for s in regions))
        # Match the producer's filesystem identity, including composite stems;
        # inventory score/page labels can differ from the actual parent/stem.
        support_path = (
            hybrid_root
            / "current_support"
            / image_path.parent.name
            / image_path.stem
            / "result.json"
        )
        support = json.loads(support_path.read_text())
        if support.get("status") != "completed" or not support.get("current_homr_executed"):
            raise ValueError(f"Current-x4 support is not verified complete: {support_path}")
        if Path(support["image"]).resolve() != image_path.resolve():
            raise ValueError(f"Stroke support image identity mismatch: {support_path}")
        baseline = Path(record["run_dir"]) / f"{image_path.stem}_detections.json"
        sr = Path(support["current_sr_detection"])
        omr = Path(support["current_omr"])
        changes = []
        candidates = set()
        for raw in original_candidates:
            box = tuple(raw)
            pieces = normalize_staff_stroke(box, regions)
            candidates.update(piece for _, piece in pieces)
            if pieces != [(-1, box)]:
                changes.append({"parent": box, "staff_pieces": pieces})
        seed_pieces = []
        for box in load_json_boxes(baseline):
            pieces = normalize_staff_stroke(box, regions)
            if pieces != [(-1, box)]:
                seed_pieces.extend(piece for _, piece in pieces)
        agreed = apply_hybrid_consensus_filter(
            baseline_boxes=seed_pieces,
            sr_boxes=load_json_boxes(sr),
            omr_boxes=load_json_boxes(omr),
        )
        candidates.update(tuple(box) for box in agreed)
        audit = {
            "schema_version": "pipeline.staff_strokes.v1",
            "coordinate_space": "source_page",
            "source_candidates_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "source_count": len(original_candidates),
            "normalized_count": len(candidates),
            "unit_size": units[str(image_path)],
            "changes": changes,
            "agreed_seeds": agreed,
            "input_sha256": {
                str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (image_path, mask, baseline, sr, omr, support_path)
            },
        }
        target.with_name("pipeline2_no_peak_staff_strokes.json").write_text(
            json.dumps(audit, indent=2) + "\n"
        )
        target.write_text(json.dumps(sorted(candidates), indent=2) + "\n")
    return units
