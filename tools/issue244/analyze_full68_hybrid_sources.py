#!/usr/bin/env python3
"""Compare historical and current hybrid detector source artifacts for Issue #244."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from src.pipeline.steps.hybrid_consensus import (
    apply_hybrid_consensus_filter,
    load_json_boxes,
)
from tools.issue244.compare_full68_route_artifacts import (
    CURRENT_INVENTORY,
    canonical_records,
    current_records_by_canonical_key,
    resolve_path,
    tolerant_match_count,
)

DEFAULT_REPORT = Path(
    "logs/issue244_full_regression/full68_hybrid_source_comparison.json"
)
LAYER_ORDER = ("baseline", "sr", "omr", "hybrid")
EXPLICIT_KEYS = {
    "baseline": ("baseline_predictions", "baseline_detections", "baseline_json"),
    "sr": ("sr_predictions", "sr_detections", "sr_json"),
    "omr": ("omr_predictions", "omr_detections", "omr_json"),
}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _roots(record: dict[str, Any]) -> list[Path]:
    hybrid = resolve_path(str(record["hybrid_predictions"]))
    candidates = [hybrid.parent]
    if record.get("run_dir"):
        candidates.insert(0, resolve_path(str(record["run_dir"])))
    if hybrid.parent.name == "hybrid_results":
        candidates.append(hybrid.parent.parent)
    return list(dict.fromkeys(candidates))


def _first_existing(paths: Iterable[Path]) -> Path | None:
    return next((path for path in paths if path.is_file()), None)


def _component_matches(path: Path, component: str) -> bool:
    if path.suffix.lower() != ".json":
        return False
    text = "/".join(part.lower() for part in path.parts)
    name = path.name.lower()
    if any(token in name for token in ("hybrid", "inventory", "summary")):
        return False
    if component == "baseline":
        return "baseline" in text and any(
            token in name for token in ("prediction", "detection", "baseline")
        )
    if component == "sr":
        return (
            "omr" not in text
            and ("/sr/" in f"/{text}/" or name.startswith("sr_") or "homr_sr" in name)
            and any(token in name for token in ("prediction", "detection", "sr"))
        )
    if component == "omr":
        return "omr" in text and any(
            token in name for token in ("prediction", "detection", "omr")
        )
    return False


def _resolve_component(record: dict[str, Any], component: str) -> Path:
    image = resolve_path(str(record["image"]))
    hybrid = resolve_path(str(record["hybrid_predictions"]))
    stem = image.stem
    roots = _roots(record)

    explicit = _first_existing(
        resolve_path(str(record[key]))
        for key in EXPLICIT_KEYS[component]
        if record.get(key)
    )
    if explicit is not None:
        return explicit

    if hybrid.parent.name == "hybrid_results":
        root = hybrid.parent.parent
        structured = {
            "baseline": root / "baseline" / "batch" / stem / f"{stem}_detections.json",
            "sr": root / "sr" / "batch" / stem / f"{stem}_detections.json",
            "omr": root / "omr_sr" / stem / "predictions.json",
        }[component]
        if structured.is_file():
            return structured

    flat_names = {
        "baseline": (
            "baseline_predictions.json",
            "baseline_detections.json",
            "homr_baseline_predictions.json",
            "homr_baseline.json",
            "baseline.json",
        ),
        "sr": (
            "sr_predictions.json",
            "sr_detections.json",
            "homr_sr_predictions.json",
            "homr_sr.json",
            "sr.json",
        ),
        "omr": (
            "omr_predictions.json",
            "omr_dln_predictions.json",
            "omr_sr_predictions.json",
            "omr_detections.json",
            "omr.json",
        ),
    }
    exact = _first_existing(
        root / name for root in roots for name in flat_names[component]
    )
    if exact is not None:
        return exact

    matches = sorted(
        {
            path
            for root in roots
            if root.is_dir()
            for path in root.rglob("*.json")
            if _component_matches(path, component)
        },
        key=lambda path: (len(path.parts), str(path)),
    )
    if matches:
        return matches[0]

    nearby = [
        str(path)
        for root in roots
        if root.is_dir()
        for path in sorted(root.rglob("*.json"))[:40]
    ]
    raise RuntimeError(
        f"Could not resolve {component} artifact for {record.get('score')}/"
        f"{record.get('page')}. roots={[str(root) for root in roots]} "
        f"inventory_keys={sorted(record)} nearby_json={nearby}"
    )


def _component_paths(record: dict[str, Any]) -> dict[str, Path]:
    return {
        "baseline": _resolve_component(record, "baseline"),
        "sr": _resolve_component(record, "sr"),
        "omr": _resolve_component(record, "omr"),
        "hybrid": resolve_path(str(record["hybrid_predictions"])),
    }


def _normalize_box(value: Any) -> tuple[int, int, int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        return None
    try:
        return tuple(int(round(float(item))) for item in value[:4])  # type: ignore[return-value]
    except (TypeError, ValueError):
        return None


def _fallback_boxes(payload: Any) -> list[tuple[int, int, int, int]]:
    if isinstance(payload, dict):
        for key in ("predictions", "detections", "boxes", "barlines", "results"):
            if isinstance(payload.get(key), list):
                return _fallback_boxes(payload[key])
        return []
    if not isinstance(payload, list):
        return []
    boxes = []
    for item in payload:
        value = item
        if isinstance(item, dict):
            value = (
                item.get("orig_bbox")
                or item.get("pred_bbox")
                or item.get("bbox")
                or item.get("box")
                or item.get("barline_location")
            )
        box = _normalize_box(value)
        if box is not None:
            boxes.append(box)
    return boxes


def _load_boxes(path: Path) -> list[tuple[int, int, int, int]]:
    if not path.exists():
        raise FileNotFoundError(path)
    boxes = [tuple(int(value) for value in box) for box in load_json_boxes(path)]
    if boxes:
        return boxes
    return _fallback_boxes(json.loads(path.read_text(encoding="utf-8")))


def _compare_boxes(
    historical: list[tuple[int, int, int, int]],
    current: list[tuple[int, int, int, int]],
) -> dict[str, Any]:
    matched = tolerant_match_count(historical, current)
    return {
        "historical_count": len(historical),
        "current_count": len(current),
        "tolerant_matches": matched,
        "historical_only": len(historical) - matched,
        "current_only": len(current) - matched,
        "semantic_equal": matched == len(historical) == len(current),
    }


def _consensus_reproduction(paths: dict[str, Path]) -> dict[str, Any]:
    baseline = _load_boxes(paths["baseline"])
    sr = _load_boxes(paths["sr"])
    omr = _load_boxes(paths["omr"])
    stored = _load_boxes(paths["hybrid"])
    recomputed = [
        tuple(int(value) for value in box)
        for box in apply_hybrid_consensus_filter(
            baseline_boxes=baseline,
            sr_boxes=sr,
            omr_boxes=omr,
        )
    ]
    comparison = _compare_boxes(stored, recomputed)
    comparison["stored_count"] = comparison.pop("historical_count")
    comparison["recomputed_count"] = comparison.pop("current_count")
    comparison["stored_only"] = comparison.pop("historical_only")
    comparison["recomputed_only"] = comparison.pop("current_only")
    return comparison


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    canonical = canonical_records()
    current_by_key = current_records_by_canonical_key(canonical)
    aggregate = {
        layer: {
            "historical": 0,
            "current": 0,
            "tolerant_matches": 0,
            "historical_only": 0,
            "current_only": 0,
            "semantic_equal_pages": 0,
        }
        for layer in LAYER_ORDER
    }
    first_divergence_counts: dict[str, int] = {}
    reproduction = {
        "historical": {"semantic_equal_pages": 0, "mismatch_pages": []},
        "current": {"semantic_equal_pages": 0, "mismatch_pages": []},
    }
    pages: dict[str, Any] = {}

    for canonical_record in canonical:
        key = (str(canonical_record["score"]), str(canonical_record["page"]))
        current_record = current_by_key[key]
        historical_paths = _component_paths(canonical_record)
        current_paths = _component_paths(current_record)

        layer_results: dict[str, Any] = {}
        first_divergence: str | None = None
        for layer in LAYER_ORDER:
            historical_boxes = _load_boxes(historical_paths[layer])
            current_boxes = _load_boxes(current_paths[layer])
            comparison = _compare_boxes(historical_boxes, current_boxes)
            comparison["historical_path"] = str(historical_paths[layer])
            comparison["current_path"] = str(current_paths[layer])
            layer_results[layer] = comparison

            stats = aggregate[layer]
            stats["historical"] += comparison["historical_count"]
            stats["current"] += comparison["current_count"]
            stats["tolerant_matches"] += comparison["tolerant_matches"]
            stats["historical_only"] += comparison["historical_only"]
            stats["current_only"] += comparison["current_only"]
            if comparison["semantic_equal"]:
                stats["semantic_equal_pages"] += 1
            elif first_divergence is None:
                first_divergence = layer

        first_key = first_divergence or "none"
        first_divergence_counts[first_key] = (
            first_divergence_counts.get(first_key, 0) + 1
        )

        reproduction_results = {
            "historical": _consensus_reproduction(historical_paths),
            "current": _consensus_reproduction(current_paths),
        }
        for source, result in reproduction_results.items():
            if result["semantic_equal"]:
                reproduction[source]["semantic_equal_pages"] += 1
            else:
                reproduction[source]["mismatch_pages"].append(f"{key[0]}/{key[1]}")

        pages[f"{key[0]}/{key[1]}"] = {
            "first_divergent_component": first_divergence,
            "layers": layer_results,
            "consensus_reproduction": reproduction_results,
        }

    for stats in aggregate.values():
        stats["symmetric_difference"] = stats["historical_only"] + stats["current_only"]

    report = {
        "schema": "issue244.full68_hybrid_source_comparison.v2",
        "page_count": len(canonical),
        "current_inventory": str(CURRENT_INVENTORY),
        "layer_order": list(LAYER_ORDER),
        "aggregate": aggregate,
        "first_divergence_counts": first_divergence_counts,
        "consensus_reproduction_with_current_code": reproduction,
        "pages": pages,
    }
    _write_json(args.report, report)

    print("Issue #244 full-68 hybrid source comparison")
    print(f"Pages: {len(canonical)}")
    print(f"First divergence counts: {first_divergence_counts}")
    for layer in LAYER_ORDER:
        print(f"  {layer}: {aggregate[layer]}")
    print(f"Consensus reproduction: {reproduction}")
    print(f"Report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
