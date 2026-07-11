#!/usr/bin/env python3
"""Compare historical Stage E and Issue #244 production-default route artifacts.

This is a temporary Issue #244 diagnostic helper. It reuses completed local
artifacts and identifies the earliest detector layer where the current route
stops matching the retained Stage E route.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

CANONICAL_INVENTORY = Path("logs/issue36_prep/20260208_bench_inventory.json")
CANONICAL_EXCLUDE = Path("logs/issue36_prep/excluded_pages_for_gt_prep.json")
HISTORICAL_ROOT = Path("logs/issue120_e2e_recovery/stage_e_full_pipeline")
CURRENT_RUN = Path("logs/issue244_full_regression/runs/production_default_full68")
CURRENT_ROUTE = CURRENT_RUN / "intermediate" / "dense_detector_route"
CURRENT_INVENTORY = CURRENT_ROUTE / "current_run_inventory.json"
REPORT = Path("logs/issue244_full_regression/full68_route_artifact_comparison.json")
CANDIDATES_FILE = "pipeline2_no_peak_candidates.json"
SCORED_FILE = "pipeline2_no_peak_scored.json"
SCORE_THRESHOLD = 0.1


def load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else Path.cwd() / path


def sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_records() -> list[dict[str, Any]]:
    inventory = load_json(CANONICAL_INVENTORY)
    exclude_payload = load_json(CANONICAL_EXCLUDE)
    excluded = {
        (item["score"], item["page"])
        for item in exclude_payload.get("excluded_pages", [])
        if isinstance(item, dict) and "score" in item and "page" in item
    }
    records = [
        record
        for record in inventory.get("records", [])
        if (record.get("score"), record.get("page")) not in excluded
    ]
    if len(records) != 68:
        raise RuntimeError(f"Expected 68 canonical records, got {len(records)}")
    return records


def current_records_by_canonical_key(
    canonical: list[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    composite_to_key = {
        f"{record['score']}_{record['page']}": (record["score"], record["page"])
        for record in canonical
    }
    current_payload = load_json(CURRENT_INVENTORY)
    mapped: dict[tuple[str, str], dict[str, Any]] = {}
    unknown: list[str] = []
    for record in current_payload.get("records", []):
        image = resolve_path(str(record["image"]))
        key = composite_to_key.get(image.stem)
        if key is None:
            unknown.append(image.stem)
            continue
        if key in mapped:
            raise RuntimeError(f"Duplicate current inventory record for {key}")
        mapped[key] = record
    if unknown:
        raise RuntimeError(f"Unknown current image stems: {unknown}")
    if len(mapped) != len(canonical):
        missing = sorted(set(composite_to_key.values()) - set(mapped))
        raise RuntimeError(f"Current inventory is missing canonical pages: {missing}")
    return mapped


def find_artifact(root: Path, score: str, page: str, filename: str) -> Path:
    candidates = [
        root / score / page / filename,
        root / f"eval2_{score}_{page}" / filename,
        root / score / f"eval2_{score}_{page}" / filename,
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def normalize_box(value: Any) -> tuple[int, int, int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        return None
    try:
        return tuple(int(round(float(item))) for item in value[:4])  # type: ignore[return-value]
    except (TypeError, ValueError):
        return None


def boxes_from_payload(payload: Any, *, scored: bool = False) -> list[tuple[int, int, int, int]]:
    if not isinstance(payload, list):
        return []
    boxes: list[tuple[int, int, int, int]] = []
    for item in payload:
        if isinstance(item, dict):
            if scored and float(item.get("score", 0.0)) < SCORE_THRESHOLD:
                continue
            box = normalize_box(item.get("bbox") or item.get("box") or item.get("barline_location"))
        else:
            box = normalize_box(item)
        if box is not None:
            boxes.append(box)
    return boxes


def vertical_overlap_ratio(
    left: tuple[int, int, int, int], right: tuple[int, int, int, int]
) -> float:
    overlap = max(0, min(left[3], right[3]) - max(left[1], right[1]))
    denominator = max(1, min(left[3] - left[1], right[3] - right[1]))
    return overlap / denominator


def tolerant_match_count(
    historical: list[tuple[int, int, int, int]],
    current: list[tuple[int, int, int, int]],
) -> int:
    candidates: list[tuple[float, int, int]] = []
    for historical_index, historical_box in enumerate(historical):
        historical_x = (historical_box[0] + historical_box[2]) / 2.0
        for current_index, current_box in enumerate(current):
            current_x = (current_box[0] + current_box[2]) / 2.0
            x_distance = abs(historical_x - current_x)
            if x_distance <= 12.0 and vertical_overlap_ratio(historical_box, current_box) >= 0.5:
                candidates.append((x_distance, historical_index, current_index))
    matched_historical: set[int] = set()
    matched_current: set[int] = set()
    for _, historical_index, current_index in sorted(candidates):
        if historical_index in matched_historical or current_index in matched_current:
            continue
        matched_historical.add(historical_index)
        matched_current.add(current_index)
    return len(matched_historical)


def compare_json_files(historical: Path, current: Path) -> dict[str, Any]:
    historical_sha = sha256(historical)
    current_sha = sha256(current)
    return {
        "historical": str(historical),
        "current": str(current),
        "historical_exists": historical.exists(),
        "current_exists": current.exists(),
        "historical_sha256": historical_sha,
        "current_sha256": current_sha,
        "exact_equal": historical_sha is not None and historical_sha == current_sha,
    }


def compare_box_files(historical: Path, current: Path, *, scored: bool = False) -> dict[str, Any]:
    result = compare_json_files(historical, current)
    if not historical.exists() or not current.exists():
        result.update(
            {
                "historical_count": None,
                "current_count": None,
                "tolerant_matches": None,
                "historical_only": None,
                "current_only": None,
            }
        )
        return result
    historical_boxes = boxes_from_payload(load_json(historical), scored=scored)
    current_boxes = boxes_from_payload(load_json(current), scored=scored)
    matched = tolerant_match_count(historical_boxes, current_boxes)
    result.update(
        {
            "historical_count": len(historical_boxes),
            "current_count": len(current_boxes),
            "count_delta": len(current_boxes) - len(historical_boxes),
            "tolerant_matches": matched,
            "historical_only": len(historical_boxes) - matched,
            "current_only": len(current_boxes) - matched,
        }
    )
    return result


def artifact_paths(
    canonical: dict[str, Any], current: dict[str, Any]
) -> dict[str, tuple[Path, Path]]:
    score = str(canonical["score"])
    page = str(canonical["page"])
    current_score = str(current["score"])
    current_page = str(current["page"])

    historical_dense = HISTORICAL_ROOT / "dense_candidate_reconstruction"
    current_dense = CURRENT_ROUTE / "dense_candidate_reconstruction"
    return {
        "input_image": (
            resolve_path(str(canonical["image"])),
            resolve_path(str(current["image"])),
        ),
        "hybrid_predictions": (
            resolve_path(str(canonical["hybrid_predictions"])),
            resolve_path(str(current["hybrid_predictions"])),
        ),
        "staff_mask": (
            resolve_path(str(canonical["staff_mask"])),
            resolve_path(str(current["staff_mask"])),
        ),
        "clef_mask": (
            resolve_path(str(canonical.get("clef_mask", "__missing__"))),
            resolve_path(str(current.get("clef_mask", "__missing__"))),
        ),
        "filtered_candidates": (
            find_artifact(
                historical_dense / "probe_candidates_filtered",
                score,
                page,
                CANDIDATES_FILE,
            ),
            find_artifact(
                current_dense / "probe_candidates_filtered",
                current_score,
                current_page,
                CANDIDATES_FILE,
            ),
        ),
        "probe_rescue_candidates": (
            find_artifact(
                historical_dense / "probe_rescue_candidates",
                score,
                page,
                CANDIDATES_FILE,
            ),
            find_artifact(
                current_dense / "probe_rescue_candidates",
                current_score,
                current_page,
                CANDIDATES_FILE,
            ),
        ),
        "scored_output": (
            find_artifact(
                HISTORICAL_ROOT / "intermediate" / "probe_scan",
                score,
                page,
                SCORED_FILE,
            ),
            find_artifact(
                CURRENT_RUN / "intermediate" / "probe_scan",
                current_score,
                current_page,
                SCORED_FILE,
            ),
        ),
    }


def first_divergent_layer(layers: dict[str, dict[str, Any]]) -> str | None:
    order = (
        "input_image",
        "hybrid_predictions",
        "staff_mask",
        "clef_mask",
        "filtered_candidates",
        "probe_rescue_candidates",
        "scored_output",
    )
    for layer in order:
        result = layers[layer]
        if not result.get("exact_equal", False):
            return layer
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=REPORT)
    args = parser.parse_args()

    canonical = canonical_records()
    current_by_key = current_records_by_canonical_key(canonical)

    pages: dict[str, Any] = {}
    equal_pages_by_layer: dict[str, int] = {}
    first_divergence_counts: dict[str, int] = {}
    aggregate_box_counts: dict[str, dict[str, int]] = {}

    for index, canonical_record in enumerate(canonical, start=1):
        key = (str(canonical_record["score"]), str(canonical_record["page"]))
        current_record = current_by_key[key]
        paths = artifact_paths(canonical_record, current_record)
        layers: dict[str, dict[str, Any]] = {}
        for layer, (historical_path, current_path) in paths.items():
            if layer in {"filtered_candidates", "probe_rescue_candidates"}:
                comparison = compare_box_files(historical_path, current_path)
            elif layer == "scored_output":
                comparison = compare_box_files(historical_path, current_path, scored=True)
            else:
                comparison = compare_json_files(historical_path, current_path)
            layers[layer] = comparison
            if comparison.get("exact_equal"):
                equal_pages_by_layer[layer] = equal_pages_by_layer.get(layer, 0) + 1
            if comparison.get("historical_count") is not None:
                aggregate = aggregate_box_counts.setdefault(
                    layer, {"historical": 0, "current": 0, "tolerant_matches": 0}
                )
                aggregate["historical"] += int(comparison["historical_count"])
                aggregate["current"] += int(comparison["current_count"])
                aggregate["tolerant_matches"] += int(comparison["tolerant_matches"])

        first_divergence = first_divergent_layer(layers)
        first_divergence_key = first_divergence or "none"
        first_divergence_counts[first_divergence_key] = (
            first_divergence_counts.get(first_divergence_key, 0) + 1
        )
        pages[f"page_{index:03d}"] = {
            "canonical_score": key[0],
            "canonical_page": key[1],
            "current_score": current_record["score"],
            "current_page": current_record["page"],
            "first_divergent_layer": first_divergence,
            "layers": layers,
        }

    report = {
        "schema": "issue244.full68_route_artifact_comparison.v1",
        "page_count": len(pages),
        "roots": {
            "historical": str(HISTORICAL_ROOT),
            "current_run": str(CURRENT_RUN),
            "canonical_inventory": str(CANONICAL_INVENTORY),
            "current_inventory": str(CURRENT_INVENTORY),
        },
        "equal_pages_by_layer": equal_pages_by_layer,
        "first_divergence_counts": first_divergence_counts,
        "aggregate_box_counts": aggregate_box_counts,
        "pages": pages,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("Issue #244 full-68 route artifact comparison")
    print(f"Pages: {len(pages)}")
    print(f"Equal pages by layer: {equal_pages_by_layer}")
    print(f"First divergence counts: {first_divergence_counts}")
    print(f"Aggregate box counts: {aggregate_box_counts}")
    print(f"Report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
