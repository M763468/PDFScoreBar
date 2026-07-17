#!/usr/bin/env python3
"""Trace saved Issue #245 historical candidates back to the v12 seed artifact.

This tool reads saved JSON only.  It does not run candidate generation, CNN
scoring, or any inference pipeline.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable, Sequence

from src.common.barline_evaluation import (
    barline_vertical_overlap,
    center_distance_x,
    is_barline_match,
)
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue120.eval_full68_from_intermediates import PageRecord, find_page_file

Box = tuple[int, int, int, int]
CANDIDATE_FILENAME = "pipeline2_no_peak_candidates.json"
SCORED_FILENAME = "pipeline2_no_peak_scored.json"
MATCHING_KWARGS = {
    "rule_name": "center_anchor",
    "vov_threshold": 0.5,
    "xdist_threshold": 12.0,
}


def _normalize_box(value: Sequence[Any]) -> Box:
    if len(value) < 4:
        raise ValueError(f"Invalid bbox: {value!r}")
    return tuple(int(round(float(item))) for item in value[:4])  # type: ignore[return-value]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_path(value: str | Path, main_repo_root: Path) -> Path:
    path = Path(value)
    if path.is_absolute() and path.parts[:2] == ("/", "workspace"):
        return main_repo_root.joinpath(*path.parts[2:])
    return path if path.is_absolute() else main_repo_root / path


def _find_record(records: Iterable[dict[str, Any]], score: str, page: str) -> dict[str, Any]:
    matches = [
        record
        for record in records
        if str(record.get("score")) == score and str(record.get("page")) == page
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one record for {score}/{page}, got {len(matches)}")
    return matches[0]


def _find_historical_baseline(run_dir: Path, page: str) -> Path:
    candidates = sorted((run_dir / "baseline").rglob(f"{page}_detections.json"))
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise FileNotFoundError(
            f"No historical baseline detection JSON below {run_dir / 'baseline'}"
        )
    raise RuntimeError(
        "Ambiguous historical baseline detection JSON: " + ", ".join(map(str, candidates))
    )


def _run_subdir(score: str, page: str) -> str:
    return f"eval2_{score}_{page}"


def _historical_seed_candidates(root: Path, score: str, page: str) -> tuple[Path, ...]:
    """Return the bc23deb `_load_bands_for_image` candidate order."""
    run_subdir = _run_subdir(score, page)
    return (
        root / score / page / CANDIDATE_FILENAME,
        root / score / page / SCORED_FILENAME,
        root / run_subdir / SCORED_FILENAME,
        root / f"{page}.json",
        root / "hybrid_results" / f"{page}_hybrid.json",
        root / f"{run_subdir}_scored.json",
    )


def resolve_historical_seed_path(root: Path, score: str, page: str) -> Path:
    """Resolve exactly as bc23deb first did, with guarded fallback discovery.

    The ordered direct paths preserve the historical runner's semantics.  A
    recursive fallback is only for saved layouts not represented by that code;
    it refuses to pick among multiple candidates.
    """
    direct_paths = _historical_seed_candidates(root, score, page)
    for path in direct_paths:
        if path.is_file():
            return path

    recursive_matches = sorted(
        {
            path
            for filename in (CANDIDATE_FILENAME, SCORED_FILENAME)
            for path in root.rglob(filename)
            if score in str(path) and page in str(path)
        }
    )
    if len(recursive_matches) == 1:
        return recursive_matches[0]
    if len(recursive_matches) > 1:
        raise RuntimeError(
            f"Ambiguous historical v12 seed for {score}/{page}: "
            + ", ".join(map(str, recursive_matches))
        )
    raise FileNotFoundError(
        f"Missing historical v12 seed for {score}/{page}. Tried: "
        + ", ".join(map(str, direct_paths))
    )


def _resolve_candidate_path(root: Path, score: str, page: str, filename: str) -> Path:
    direct_paths = (
        root / score / page / filename,
        root / _run_subdir(score, page) / filename,
        root / score / _run_subdir(score, page) / filename,
    )
    direct_matches = [path for path in direct_paths if path.is_file()]
    if len(direct_matches) == 1:
        return direct_matches[0]
    if len(direct_matches) > 1:
        raise RuntimeError(
            f"Ambiguous direct {filename} for {score}/{page}: "
            + ", ".join(map(str, direct_matches))
        )
    recursive_matches = sorted(
        {
            path
            for path in root.rglob(filename)
            if score in str(path) and page in str(path) and path.is_file()
        }
    )
    if len(recursive_matches) == 1:
        return recursive_matches[0]
    if len(recursive_matches) > 1:
        raise RuntimeError(
            f"Ambiguous {filename} for {score}/{page}: " + ", ".join(map(str, recursive_matches))
        )
    raise FileNotFoundError(f"Missing {filename} for {score}/{page} below {root}")


def _resolve_final_candidate_path(root: Path, score: str, page: str) -> Path:
    path = find_page_file(root, PageRecord(score=score, page=page), CANDIDATE_FILENAME)
    if path is not None and path.is_file():
        return path
    matches = sorted(
        {
            candidate
            for candidate in root.rglob(CANDIDATE_FILENAME)
            if "dense_candidate_reconstruction" not in candidate.parts
            and score in str(candidate)
            and page in str(candidate)
        }
    )
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise RuntimeError(
            f"Ambiguous final candidates for {score}/{page}: " + ", ".join(map(str, matches))
        )
    raise FileNotFoundError(f"Missing final candidates for {score}/{page} below {root}")


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


def _stage_summary(path: Path, boxes: Iterable[Box], full_span: Box, short: Box) -> dict[str, Any]:
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


def _parse_target(raw: str) -> dict[str, Any]:
    parts = raw.split("|")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("target must be score|page|full_span_bbox|short_bbox")
    try:
        return {
            "score": parts[0],
            "page": parts[1],
            "full_span": _normalize_box(parts[2].split(",")),
            "short": _normalize_box(parts[3].split(",")),
        }
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _load_boxes(path: Path) -> list[Box]:
    production_boxes = [_normalize_box(box) for box in load_json_boxes(path)]
    if production_boxes:
        return production_boxes

    payload = _load_json(path)
    records = payload.get("predictions", payload) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        return []
    boxes = []
    for record in records:
        if isinstance(record, (list, tuple)):
            boxes.append(_normalize_box(record))
        elif isinstance(record, dict):
            bbox = record.get("bbox", record.get("orig_bbox", record.get("pred_bbox")))
            if isinstance(bbox, (list, tuple)):
                boxes.append(_normalize_box(bbox))
    return boxes


def _classify(*, seed_error: Exception | None, stages: dict[str, dict[str, Any]]) -> str:
    if isinstance(seed_error, FileNotFoundError):
        return "v12_seed_missing"
    if isinstance(seed_error, RuntimeError):
        return "historical_artifact_ambiguous"
    seed = stages.get("historical_v12_seed")
    historical_final = stages["historical_final_candidates"]
    if seed is None:
        return "unresolved"
    if seed["exact_full_span_present"]:
        return "full_span_present_in_v12_seed"
    if historical_final["exact_full_span_present"]:
        return "full_span_generated_after_v12_seed"
    return "unresolved"


def build_report(
    *,
    main_repo_root: Path,
    mixed_route_root: Path,
    stage_e_root: Path,
    historical_root: Path,
    v12_root: Path,
    targets: list[dict[str, Any]],
) -> dict[str, Any]:
    mixed_report_path = mixed_route_root / "accuracy_first_mixed_route_report.json"
    mixed_report = _load_json(mixed_report_path)
    page_records = mixed_report.get("pages", [])
    historical_info = mixed_report.get("historical_inventory", {})
    if not isinstance(page_records, list) or not isinstance(historical_info, dict):
        raise ValueError("Invalid mixed route report")
    inventory_path = _resolve_path(historical_info["path"], main_repo_root)
    historical_records = _load_json(inventory_path).get("records", [])
    if not isinstance(historical_records, list):
        raise ValueError("Historical inventory records must be a list")

    target_reports = []
    for target in targets:
        score = str(target["score"])
        page = str(target["page"])
        full_span = _normalize_box(target["full_span"])
        short = _normalize_box(target["short"])
        page_record = _find_record(page_records, score, page)
        historical_record = _find_record(historical_records, score, page)
        paths = {
            "historical_baseline": _find_historical_baseline(
                _resolve_path(historical_record["run_dir"], main_repo_root), page
            ),
            "historical_hybrid": _resolve_path(
                historical_record["hybrid_predictions"], main_repo_root
            ),
            "historical_final_candidates": _resolve_candidate_path(
                historical_root, score, page, CANDIDATE_FILENAME
            ),
            "historical_final_scored": _resolve_candidate_path(
                historical_root, score, page, SCORED_FILENAME
            ),
            "current_mixed_hybrid": _resolve_path(page_record["mixed_hybrid"], main_repo_root),
            "current_raw_dense": _resolve_candidate_path(
                stage_e_root / "dense_candidate_reconstruction" / "probe_candidates_from_inventory",
                score,
                page,
                CANDIDATE_FILENAME,
            ),
            "current_filtered_dense": _resolve_candidate_path(
                stage_e_root / "dense_candidate_reconstruction" / "probe_candidates_filtered",
                score,
                page,
                CANDIDATE_FILENAME,
            ),
            "current_probe_rescue": _resolve_candidate_path(
                stage_e_root / "dense_candidate_reconstruction" / "probe_rescue_candidates",
                score,
                page,
                CANDIDATE_FILENAME,
            ),
            "current_final_candidates": _resolve_final_candidate_path(stage_e_root, score, page),
        }
        stages = {
            name: _stage_summary(path, _load_boxes(path), full_span, short)
            for name, path in paths.items()
        }
        seed_error: Exception | None = None
        try:
            seed_path = resolve_historical_seed_path(v12_root, score, page)
            stages["historical_v12_seed"] = _stage_summary(
                seed_path, _load_boxes(seed_path), full_span, short
            )
        except (FileNotFoundError, RuntimeError) as error:
            seed_error = error

        target_reports.append(
            {
                "score": score,
                "page": page,
                "full_span": list(full_span),
                "short": list(short),
                "historical_seed_resolution": {
                    "path": str(seed_path) if seed_error is None else None,
                    "candidate_order": [
                        str(path) for path in _historical_seed_candidates(v12_root, score, page)
                    ],
                    "error": str(seed_error) if seed_error else None,
                },
                "stages": stages,
                "classification": _classify(seed_error=seed_error, stages=stages),
            }
        )

    return {
        "schema_version": "issue245.historical_candidate_seed_trace.v1",
        "inputs": {
            "main_repo_root": str(main_repo_root),
            "mixed_route_root": str(mixed_route_root),
            "mixed_route_report": str(mixed_report_path),
            "historical_root": str(historical_root),
            "v12_root": str(v12_root),
            "stage_e_root": str(stage_e_root),
            "historical_inventory": str(inventory_path),
        },
        "matching_contract": {
            "rule": "center_anchor",
            "vov_threshold": 0.5,
            "xdist_threshold": 12.0,
        },
        "historical_seed_resolution_contract": {
            "implementation": "bc23deb src/pipeline/probe_scan.py:_load_bands_for_image",
            "ordered_candidates": "score/page candidates, score/page scored, run-id scored, page JSON, hybrid JSON, run-id scored JSON",
            "fallback": "recursive candidate/scored search only when all historical direct paths are absent; ambiguous matches raise RuntimeError",
        },
        "targets": target_reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main-repo-root", type=Path, required=True)
    parser.add_argument("--mixed-route-root", type=Path, required=True)
    parser.add_argument("--stage-e-root", type=Path, required=True)
    parser.add_argument("--historical-root", type=Path, required=True)
    parser.add_argument("--v12-root", type=Path, required=True)
    parser.add_argument("--target", type=_parse_target, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = build_report(
        main_repo_root=args.main_repo_root,
        mixed_route_root=args.mixed_route_root,
        stage_e_root=args.stage_e_root,
        historical_root=args.historical_root,
        v12_root=args.v12_root,
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
