#!/usr/bin/env python3
"""Trace Issue36 v12 candidates across the historical producer boundary.

The tool reads saved JSON and image metadata only. It does not run candidate
generation, filtering, CNN scoring, or any inference pipeline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Sequence

from src.common.barline_evaluation import (
    barline_vertical_overlap,
    center_distance_x,
    is_barline_match,
)

Box = tuple[int, int, int, int]
CANDIDATE_FILENAME = "pipeline2_no_peak_candidates.json"
MATCHING_KWARGS = {
    "rule_name": "center_anchor",
    "vov_threshold": 0.5,
    "xdist_threshold": 12.0,
}


class InventoryRecordNotFoundError(ValueError):
    """Raised when an inventory has no record for a requested score/page."""


class InventoryRecordAmbiguousError(ValueError):
    """Raised when an inventory has multiple records for a requested score/page."""


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_box(value: Sequence[Any]) -> Box:
    if len(value) < 4:
        raise ValueError(f"Invalid bbox: {value!r}")
    return tuple(int(round(float(item))) for item in value[:4])  # type: ignore[return-value]


def _resolve_path(value: str | Path, main_repo_root: Path) -> Path:
    path = Path(value)
    if path.is_absolute() and path.parts[:2] == ("/", "workspace"):
        return main_repo_root.joinpath(*path.parts[2:])
    return path if path.is_absolute() else main_repo_root / path


def _load_boxes(path: Path) -> list[Box]:
    payload = _load_json(path)
    records = payload.get("predictions", payload) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        return []
    boxes: list[Box] = []
    for item in records:
        if isinstance(item, (list, tuple)):
            boxes.append(_normalize_box(item))
        elif isinstance(item, dict):
            bbox = item.get("bbox", item.get("orig_bbox", item.get("pred_bbox")))
            if isinstance(bbox, (list, tuple)):
                boxes.append(_normalize_box(bbox))
    return boxes


def _find_inventory_record(inventory_path: Path, score: str, page: str) -> dict[str, Any]:
    payload = _load_json(inventory_path)
    records = payload.get("records", payload) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError(f"Inventory records must be a list: {inventory_path}")
    matches = [
        record
        for record in records
        if isinstance(record, dict)
        and str(record.get("score")) == score
        and str(record.get("page")) == page
    ]
    if not matches:
        raise InventoryRecordNotFoundError(f"No inventory record for {score}/{page}")
    if len(matches) > 1:
        raise InventoryRecordAmbiguousError(
            f"Ambiguous inventory records for {score}/{page}: {len(matches)}"
        )
    return matches[0]


def _sha256(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _image_dimensions(path: Path | None) -> list[int] | None:
    if path is None or not path.is_file():
        return None
    try:
        import cv2
    except ImportError:  # pragma: no cover - optional in lightweight environments
        return None
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        return None
    height, width = image.shape[:2]
    return [int(width), int(height)]


def _record_metadata(record: dict[str, Any], main_repo_root: Path) -> dict[str, Any]:
    def resolve(key: str) -> Path | None:
        value = record.get(key)
        return _resolve_path(value, main_repo_root) if value else None

    image_path = resolve("image")
    hybrid_path = resolve("hybrid_predictions")
    staff_mask_path = resolve("staff_mask")
    return {
        "score": record.get("score"),
        "page": record.get("page"),
        "image_path": str(image_path) if image_path else None,
        "image_sha256": _sha256(image_path),
        "image_dimensions": _image_dimensions(image_path),
        "hybrid_predictions_path": str(hybrid_path) if hybrid_path else None,
        "hybrid_predictions_sha256": _sha256(hybrid_path),
        "staff_mask_path": str(staff_mask_path) if staff_mask_path else None,
        "staff_mask_sha256": _sha256(staff_mask_path),
    }


def _height(box: Box) -> int:
    return abs(box[3] - box[1])


def _l1_distance(left: Box, right: Box) -> int:
    return sum(abs(left[index] - right[index]) for index in range(4))


def _matches(candidate: Box, reference: Box) -> bool:
    return is_barline_match(candidate, reference, **MATCHING_KWARGS)


def _closest(boxes: Iterable[Box], reference: Box) -> dict[str, Any] | None:
    candidates = list(boxes)
    if not candidates:
        return None
    closest = min(
        candidates,
        key=lambda box: (
            center_distance_x(box, reference),
            -barline_vertical_overlap(box, reference),
            _l1_distance(box, reference),
            box,
        ),
    )
    reference_height = _height(reference)
    closest_height = _height(closest)
    return {
        "bbox": list(closest),
        "bbox_delta": [closest[index] - reference[index] for index in range(4)],
        "xdist": center_distance_x(closest, reference),
        "vertical_overlap": barline_vertical_overlap(closest, reference),
        "height": closest_height,
        "height_ratio": closest_height / reference_height if reference_height else None,
    }


def _stage(path: Path, boxes: Iterable[Box], full_span: Box, short: Box) -> dict[str, Any]:
    box_list = list(boxes)
    return {
        "path": str(path),
        "candidate_count": len(box_list),
        "exact_full_span_present": full_span in box_list,
        "exact_short_present": short in box_list,
        "full_span_matching_candidates": [
            list(box) for box in box_list if _matches(box, full_span)
        ],
        "short_matching_candidates": [list(box) for box in box_list if _matches(box, short)],
        "closest_to_full_span": _closest(box_list, full_span),
        "closest_to_short": _closest(box_list, short),
    }


def _candidate_path(root: Path, score: str, page: str) -> Path:
    direct_paths = (
        root / score / page / CANDIDATE_FILENAME,
        root / f"eval2_{score}_{page}" / CANDIDATE_FILENAME,
    )
    direct_matches = [path for path in direct_paths if path.is_file()]
    if len(direct_matches) == 1:
        return direct_matches[0]
    if len(direct_matches) > 1:
        raise RuntimeError(
            f"Ambiguous direct candidate paths for {score}/{page}: "
            + ", ".join(map(str, direct_matches))
        )
    matches = sorted(
        {
            path
            for path in root.rglob(CANDIDATE_FILENAME)
            if path.is_file() and score in str(path) and page in str(path)
        }
    )
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise RuntimeError(
            f"Ambiguous candidate paths for {score}/{page}: " + ", ".join(map(str, matches))
        )
    raise FileNotFoundError(f"Missing candidates for {score}/{page} below {root}")


def resolve_summary_inputs(
    generation_summary_path: Path, filter_summary_path: Path, main_repo_root: Path
) -> dict[str, Path]:
    generation = _load_json(generation_summary_path)
    filter_summary = _load_json(filter_summary_path)
    required = {
        "inventory": generation.get("inventory"),
        "raw_root": generation.get("output_root"),
        "filter_inventory": filter_summary.get("inventory"),
        "filter_raw_root": filter_summary.get("candidates_root"),
        "filtered_root": filter_summary.get("output_root"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError("Summary missing required fields: " + ", ".join(missing))
    resolved = {name: _resolve_path(value, main_repo_root) for name, value in required.items()}
    if resolved["inventory"] != resolved["filter_inventory"]:
        raise ValueError("Generation and filter summaries reference different inventories")
    if resolved["raw_root"] != resolved["filter_raw_root"]:
        raise ValueError("Generation and filter summaries reference different raw roots")
    return {
        "inventory": resolved["inventory"],
        "raw_root": resolved["raw_root"],
        "filtered_root": resolved["filtered_root"],
    }


def _classify(stages: dict[str, dict[str, Any]]) -> str:
    existing = stages["producer_existing_boxes"]
    raw = stages["v12_raw_candidates"]
    filtered = stages["v12_filtered_candidates"]
    if existing["exact_full_span_present"]:
        return "full_span_carried_from_existing_input"
    if raw["exact_full_span_present"]:
        return "full_span_generated_by_issue36_probe"
    if filtered["exact_full_span_present"]:
        return "full_span_first_seen_in_filter_output"
    return "unresolved"


def _bbox_provenance(stages: dict[str, dict[str, Any]], bbox_name: str) -> str:
    key = f"exact_{bbox_name}_present"
    if stages["producer_existing_boxes"][key]:
        return "existing_input"
    if stages["v12_raw_candidates"][key]:
        return "probe_generated_or_other_raw_input"
    if stages["v12_filtered_candidates"][key]:
        return "first_seen_in_filter_output"
    return "not_present"


def _parse_target(raw: str) -> dict[str, Any]:
    parts = raw.split("|")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("target must be score|page|full_span_bbox|short_bbox")
    return {
        "score": parts[0],
        "page": parts[1],
        "full_span": _normalize_box(parts[2].split(",")),
        "short": _normalize_box(parts[3].split(",")),
    }


def build_report(
    *,
    main_repo_root: Path,
    generation_summary_path: Path,
    filter_summary_path: Path,
    historical_final_root: Path,
    v12_scoring_root: Path,
    current_mixed_inventory_path: Path,
    current_stage_e_root: Path,
    targets: list[dict[str, Any]],
) -> dict[str, Any]:
    summary_inputs = resolve_summary_inputs(
        generation_summary_path, filter_summary_path, main_repo_root
    )
    target_reports = []
    for target in targets:
        score = str(target["score"])
        page = str(target["page"])
        full_span = _normalize_box(target["full_span"])
        short = _normalize_box(target["short"])
        try:
            historical_record = _find_inventory_record(summary_inputs["inventory"], score, page)
        except InventoryRecordNotFoundError as error:
            target_reports.append(
                {
                    "score": score,
                    "page": page,
                    "full_span": list(full_span),
                    "short": list(short),
                    "classification": "historical_producer_input_missing",
                    "error": str(error),
                }
            )
            continue
        except InventoryRecordAmbiguousError as error:
            target_reports.append(
                {
                    "score": score,
                    "page": page,
                    "full_span": list(full_span),
                    "short": list(short),
                    "classification": "historical_inventory_ambiguous",
                    "error": str(error),
                }
            )
            continue

        current_record = _find_inventory_record(current_mixed_inventory_path, score, page)
        historical_metadata = _record_metadata(historical_record, main_repo_root)
        current_metadata = _record_metadata(current_record, main_repo_root)
        existing_path = Path(historical_metadata["hybrid_predictions_path"])
        current_hybrid_path = Path(current_metadata["hybrid_predictions_path"])
        paths = {
            "producer_existing_boxes": existing_path,
            "v12_raw_candidates": _candidate_path(summary_inputs["raw_root"], score, page),
            "v12_filtered_candidates": _candidate_path(
                summary_inputs["filtered_root"], score, page
            ),
            "v12_scoring_input": _candidate_path(v12_scoring_root, score, page),
            "historical_final_candidates": _candidate_path(historical_final_root, score, page),
            "current_mixed_hybrid": current_hybrid_path,
            "current_raw_dense": _candidate_path(
                current_stage_e_root
                / "dense_candidate_reconstruction"
                / "probe_candidates_from_inventory",
                score,
                page,
            ),
        }
        stages = {
            name: _stage(path, _load_boxes(path), full_span, short) for name, path in paths.items()
        }
        target_reports.append(
            {
                "score": score,
                "page": page,
                "full_span": list(full_span),
                "short": list(short),
                "producer_inventory_record": {
                    "inventory_path": str(summary_inputs["inventory"]),
                    "inventory_sha256": _sha256(summary_inputs["inventory"]),
                    **historical_metadata,
                },
                "current_mixed_inventory_record": {
                    "inventory_path": str(current_mixed_inventory_path),
                    "inventory_sha256": _sha256(current_mixed_inventory_path),
                    **current_metadata,
                },
                "input_comparison": {
                    "image_sha256_equal": (
                        historical_metadata["image_sha256"] == current_metadata["image_sha256"]
                    ),
                    "image_dimensions_equal": (
                        historical_metadata["image_dimensions"]
                        == current_metadata["image_dimensions"]
                    ),
                    "hybrid_predictions_sha256_equal": (
                        historical_metadata["hybrid_predictions_sha256"]
                        == current_metadata["hybrid_predictions_sha256"]
                    ),
                    "staff_mask_sha256_equal": (
                        historical_metadata["staff_mask_sha256"]
                        == current_metadata["staff_mask_sha256"]
                    ),
                },
                "stages": stages,
                "bbox_provenance": {
                    "full_span": _bbox_provenance(stages, "full_span"),
                    "short": _bbox_provenance(stages, "short"),
                },
                "classification": _classify(stages),
            }
        )
    return {
        "schema_version": "issue245.issue36_v12_producer_boundary.v1",
        "inputs": {
            "main_repo_root": str(main_repo_root),
            "generation_summary": str(generation_summary_path),
            "filter_summary": str(filter_summary_path),
            "historical_final_root": str(historical_final_root),
            "v12_scoring_root": str(v12_scoring_root),
            "current_mixed_inventory": str(current_mixed_inventory_path),
            "current_stage_e_root": str(current_stage_e_root),
            **{name: str(path) for name, path in summary_inputs.items()},
        },
        "matching_contract": {
            "rule": "center_anchor",
            "vov_threshold": 0.5,
            "xdist_threshold": 12.0,
        },
        "targets": target_reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main-repo-root", type=Path, required=True)
    parser.add_argument("--generation-summary", type=Path, required=True)
    parser.add_argument("--filter-summary", type=Path, required=True)
    parser.add_argument("--historical-final-root", type=Path, required=True)
    parser.add_argument("--v12-scoring-root", type=Path, required=True)
    parser.add_argument("--current-mixed-inventory", type=Path, required=True)
    parser.add_argument("--current-stage-e-root", type=Path, required=True)
    parser.add_argument("--target", type=_parse_target, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = build_report(
        main_repo_root=args.main_repo_root,
        generation_summary_path=args.generation_summary,
        filter_summary_path=args.filter_summary,
        historical_final_root=args.historical_final_root,
        v12_scoring_root=args.v12_scoring_root,
        current_mixed_inventory_path=args.current_mixed_inventory,
        current_stage_e_root=args.current_stage_e_root,
        targets=args.target,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    for target in report["targets"]:
        print(f"{target['score']}/{target['page']} {target['classification']}")
    print(f"Wrote: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
