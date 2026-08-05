#!/usr/bin/env python3
"""Evaluate Stage E hybrid consensus counterfactuals and render focused overlays.

This analysis is offline. Historical artifacts are comparison inputs only. The
script does not execute HOMR, SR, OMR-DLN, probe generation, filtering, Issue53,
or CNN inference, and it never connects historical artifacts to detector runtime.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import cv2

from src.common import barline_iou
from src.pipeline.steps.hybrid_consensus import (
    apply_hybrid_consensus_filter,
    load_json_boxes,
)
from tools.issue252.probe_boundary import normalize_box, target_metrics, write_json
from tools.issue255.run_public_baseline_stage_e_reconstruction import (
    _resolve_repo_artifact,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_ROOT = ROOT / "logs/issue255_stage_e_public_baseline/issue255_public_stage_e_01"
PROVENANCE_NAME = "public_stage_e_hybrid_component_provenance.json"
PUBLIC_REPORT_NAME = "public_baseline_stage_e_reconstruction_report.json"
OUTPUT_NAME = "public_stage_e_consensus_counterfactual.json"
ACCEPTED_IOU = 0.5
VARIANT_COMPONENTS = {
    "historical_sr_historical_omr": ("historical", "historical"),
    "historical_sr_public_omr": ("historical", "public"),
    "public_sr_historical_omr": ("public", "historical"),
    "public_sr_public_omr": ("public", "public"),
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _path(value: Any, name: str) -> Path:
    if isinstance(value, Mapping):
        value = value.get("path")
    if not isinstance(value, (str, Path)):
        raise ValueError(f"Missing path for {name}")
    path = _resolve_repo_artifact(value)
    if not path.is_file():
        raise FileNotFoundError(f"Missing artifact for {name}: {path}")
    return path


def _boxes(path: Path) -> list[tuple[int, int, int, int]]:
    return [normalize_box(box) for box in load_json_boxes(path)]


def _box_set(boxes: Sequence[Sequence[int | float]]) -> set[tuple[int, int, int, int]]:
    return {normalize_box(box) for box in boxes}


def _comparison(
    actual: Sequence[Sequence[int | float]],
    reference: Sequence[Sequence[int | float]],
) -> dict[str, Any]:
    actual_set = _box_set(actual)
    reference_set = _box_set(reference)
    return {
        "actual_count": len(actual_set),
        "reference_count": len(reference_set),
        "exact_common_count": len(actual_set & reference_set),
        "actual_only_count": len(actual_set - reference_set),
        "reference_only_count": len(reference_set - actual_set),
        "exact_match": actual_set == reference_set,
    }


def _support_match(
    bbox: Sequence[int | float],
    boxes: Sequence[tuple[int, int, int, int]],
) -> dict[str, Any]:
    metrics = target_metrics(normalize_box(bbox), boxes, accepted_iou=ACCEPTED_IOU)
    best = metrics.get("best")
    return {
        "accepted": bool(metrics.get("accepted")),
        "best": dict(best) if isinstance(best, Mapping) else None,
    }


def _has_support(
    bbox: Sequence[int | float],
    boxes: Sequence[tuple[int, int, int, int]],
) -> bool:
    query = normalize_box(bbox)
    return any(barline_iou(query, candidate) > ACCEPTED_IOU for candidate in boxes)


def _consensus(
    baseline: Sequence[tuple[int, int, int, int]],
    sr: Sequence[tuple[int, int, int, int]],
    omr: Sequence[tuple[int, int, int, int]],
) -> list[tuple[int, int, int, int]]:
    rows = apply_hybrid_consensus_filter(
        baseline_boxes=baseline,
        sr_boxes=sr,
        omr_boxes=omr,
        iou_thresh=ACCEPTED_IOU,
    )
    return [normalize_box(box) for box in rows]


def _support_summary(
    baseline: Sequence[tuple[int, int, int, int]],
    sr: Sequence[tuple[int, int, int, int]],
    omr: Sequence[tuple[int, int, int, int]],
) -> dict[str, int]:
    counts = {"both": 0, "sr_only": 0, "omr_only": 0, "neither": 0}
    for box in baseline:
        sr_match = _has_support(box, sr)
        omr_match = _has_support(box, omr)
        if sr_match and omr_match:
            counts["both"] += 1
        elif sr_match:
            counts["sr_only"] += 1
        elif omr_match:
            counts["omr_only"] += 1
        else:
            counts["neither"] += 1
    return counts


def _target_members(page: Mapping[str, Any]) -> dict[str, list[tuple[int, int, int, int]]]:
    members = page.get("row_cluster_members")
    if not isinstance(members, Mapping):
        return {"historical": [], "public": []}
    result: dict[str, list[tuple[int, int, int, int]]] = {}
    for side in ("historical", "public"):
        rows = members.get(side)
        boxes: list[tuple[int, int, int, int]] = []
        if isinstance(rows, list):
            for row in rows:
                bbox = row.get("bbox") if isinstance(row, Mapping) else None
                if isinstance(bbox, Sequence) and not isinstance(bbox, (str, bytes)):
                    boxes.append(normalize_box(bbox))
        result[side] = sorted(set(boxes))
    return result


def _target_report(
    bbox: tuple[int, int, int, int],
    *,
    components: Mapping[str, Mapping[str, Sequence[tuple[int, int, int, int]]]],
    variants: Mapping[str, Sequence[tuple[int, int, int, int]]],
) -> dict[str, Any]:
    return {
        "bbox": list(bbox),
        "historical_support": {
            "sr": _support_match(bbox, list(components["historical"]["sr"])),
            "omr": _support_match(bbox, list(components["historical"]["omr"])),
        },
        "public_support": {
            "sr": _support_match(bbox, list(components["public"]["sr"])),
            "omr": _support_match(bbox, list(components["public"]["omr"])),
        },
        "included_in_variants": {
            name: bbox in _box_set(boxes) for name, boxes in variants.items()
        },
    }


def _variant_classification(
    variants: Mapping[str, Sequence[tuple[int, int, int, int]]],
    historical_hybrid: Sequence[tuple[int, int, int, int]],
    public_hybrid: Sequence[tuple[int, int, int, int]],
) -> str:
    hh_matches = _box_set(variants["historical_sr_historical_omr"]) == _box_set(
        historical_hybrid
    )
    pp_matches = _box_set(variants["public_sr_public_omr"]) == _box_set(public_hybrid)
    if hh_matches and pp_matches:
        return "current_consensus_reproduces_both_from_component_inputs"
    if hh_matches:
        return "current_consensus_reproduces_historical_only"
    if pp_matches:
        return "current_consensus_reproduces_public_only"
    return "consensus_or_artifact_contract_still_differs"


def _draw_box(
    image: Any,
    bbox: tuple[int, int, int, int],
    color: tuple[int, int, int],
    label: str,
    thickness: int,
) -> None:
    x1, y1, x2, y2 = bbox
    cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)
    cv2.putText(
        image,
        label,
        (x1, max(18, y1 - 5)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        color,
        1,
        cv2.LINE_AA,
    )


def _best_box(match: Mapping[str, Any]) -> tuple[int, int, int, int] | None:
    best = match.get("best")
    bbox = best.get("bbox") if isinstance(best, Mapping) else None
    if isinstance(bbox, Sequence) and not isinstance(bbox, (str, bytes)):
        return normalize_box(bbox)
    return None


def _write_overlay(
    *,
    image_path: Path,
    output_path: Path,
    targets: Mapping[str, Sequence[tuple[int, int, int, int]]],
    components: Mapping[str, Mapping[str, Sequence[tuple[int, int, int, int]]]],
) -> dict[str, Any] | None:
    all_targets = [box for side in targets.values() for box in side]
    if not all_targets:
        return None
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"Failed to read image: {image_path}")

    records: list[dict[str, Any]] = []
    for side, color, prefix in (
        ("historical", (255, 0, 0), "H-base"),
        ("public", (0, 0, 255), "P-base"),
    ):
        for index, bbox in enumerate(targets[side], start=1):
            _draw_box(image, bbox, color, f"{prefix}{index}", 3)
            records.append({"kind": f"{side}_baseline_target", "bbox": list(bbox)})
            for sr_side, sr_color, sr_label in (
                ("historical", (255, 255, 0), "H-SR"),
                ("public", (255, 0, 255), "P-SR"),
            ):
                match = _support_match(bbox, list(components[sr_side]["sr"]))
                best_bbox = _best_box(match)
                if best_bbox is None:
                    continue
                _draw_box(image, best_bbox, sr_color, f"{sr_label}{index}", 1)
                records.append(
                    {
                        "kind": f"{sr_side}_sr_nearest",
                        "target_side": side,
                        "bbox": list(best_bbox),
                        "accepted": match["accepted"],
                    }
                )

    xs = [value for row in records for value in (row["bbox"][0], row["bbox"][2])]
    ys = [value for row in records for value in (row["bbox"][1], row["bbox"][3])]
    margin_x = 80
    margin_y = 70
    x1 = max(0, min(xs) - margin_x)
    y1 = max(0, min(ys) - margin_y)
    x2 = min(image.shape[1], max(xs) + margin_x)
    y2 = min(image.shape[0], max(ys) + margin_y)
    crop = image[y1:y2, x1:x2].copy()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), crop):
        raise RuntimeError(f"Failed to write overlay: {output_path}")
    return {
        "path": str(output_path),
        "crop_bbox": [x1, y1, x2, y2],
        "records": records,
        "legend": {
            "blue": "historical baseline cluster member",
            "red": "public baseline cluster member",
            "cyan": "nearest historical SR box",
            "magenta": "nearest public SR box",
        },
    }


def build_report(run_root: Path) -> dict[str, Any]:
    run_root = run_root.resolve()
    provenance_path = run_root / PROVENANCE_NAME
    public_report_path = run_root / PUBLIC_REPORT_NAME
    provenance = _load(provenance_path)
    public_report = _load(public_report_path)
    for name, payload in (
        ("component provenance", provenance),
        ("public Stage E report", public_report),
    ):
        if not isinstance(payload, Mapping) or payload.get("status") != "completed":
            raise ValueError(f"Incomplete {name}")

    provenance_pages = provenance.get("pages")
    public_pages = public_report.get("pages")
    if not isinstance(provenance_pages, Mapping) or not isinstance(public_pages, Mapping):
        raise ValueError("Source report pages are missing")

    pages: dict[str, Any] = {}
    for label, page in provenance_pages.items():
        if not isinstance(page, Mapping):
            continue
        public_page = public_pages.get(label)
        if not isinstance(public_page, Mapping):
            raise ValueError(f"Missing public page metadata: {label}")
        component_paths = page.get("component_paths")
        if not isinstance(component_paths, Mapping):
            raise ValueError(f"Missing component paths: {label}")

        paths: dict[str, dict[str, Path]] = {}
        components: dict[str, dict[str, list[tuple[int, int, int, int]]]] = {}
        for side in ("historical", "public"):
            side_paths = component_paths.get(side)
            if not isinstance(side_paths, Mapping):
                raise ValueError(f"Missing {side} component paths: {label}")
            paths[side] = {}
            components[side] = {}
            for stage in ("baseline", "sr", "omr", "hybrid"):
                path = _path(side_paths.get(stage), f"{label}.{side}.{stage}")
                paths[side][stage] = path
                components[side][stage] = _boxes(path)

        historical_baseline = components["historical"]["baseline"]
        public_baseline = components["public"]["baseline"]
        if _box_set(historical_baseline) != _box_set(public_baseline):
            raise ValueError(f"Baseline is not exact between sides: {label}")

        variants = {
            name: _consensus(
                public_baseline,
                components[sr_side]["sr"],
                components[omr_side]["omr"],
            )
            for name, (sr_side, omr_side) in VARIANT_COMPONENTS.items()
        }
        historical_hybrid = components["historical"]["hybrid"]
        public_hybrid = components["public"]["hybrid"]
        targets = _target_members(page)
        artifacts = public_page.get("artifacts")
        if not isinstance(artifacts, Mapping):
            raise ValueError(f"Missing public artifacts: {label}")
        image_path = _path(artifacts.get("image"), f"{label}.image")
        overlay = _write_overlay(
            image_path=image_path,
            output_path=run_root / "diagnostics" / f"{label}_sr_consensus_overlay.png",
            targets=targets,
            components=components,
        )

        pages[str(label)] = {
            "score": page.get("score"),
            "page": page.get("page"),
            "baseline_exact": True,
            "component_counts": {
                side: {stage: len(boxes) for stage, boxes in stages.items()}
                for side, stages in components.items()
            },
            "support_summaries": {
                side: _support_summary(
                    public_baseline,
                    components[side]["sr"],
                    components[side]["omr"],
                )
                for side in ("historical", "public")
            },
            "variants": {
                name: {
                    "count": len(boxes),
                    "vs_historical_hybrid": _comparison(boxes, historical_hybrid),
                    "vs_public_hybrid": _comparison(boxes, public_hybrid),
                }
                for name, boxes in variants.items()
            },
            "classification": _variant_classification(
                variants,
                historical_hybrid,
                public_hybrid,
            ),
            "target_cluster_members": {
                side: [
                    _target_report(box, components=components, variants=variants)
                    for box in boxes
                ]
                for side, boxes in targets.items()
            },
            "overlay": overlay,
            "component_paths": {
                side: {stage: str(path) for stage, path in stages.items()}
                for side, stages in paths.items()
            },
        }

    return {
        "schema_version": "issue255.public_stage_e_consensus_counterfactual.v1",
        "status": "completed",
        "analysis_only": True,
        "historical_artifacts_used_for_analysis_only": True,
        "source_run": str(run_root),
        "source_provenance": str(provenance_path),
        "source_public_report": str(public_report_path),
        "accepted_iou": ACCEPTED_IOU,
        "pages": pages,
        "next_gpu_run_required": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_report(args.run_root)
    output = args.output or args.run_root / OUTPUT_NAME
    write_json(output.resolve(), report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "output": str(output.resolve()),
                "pages": {
                    label: {
                        "classification": page["classification"],
                        "overlay": (
                            page["overlay"]["path"]
                            if isinstance(page.get("overlay"), Mapping)
                            else None
                        ),
                    }
                    for label, page in report["pages"].items()
                },
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
