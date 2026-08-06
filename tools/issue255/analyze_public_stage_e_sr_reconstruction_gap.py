#!/usr/bin/env python3
"""Compare retained historical/public SR images, outputs, and execution metadata.

This is an offline Issue #255 restoration analysis. Historical artifacts are
comparison inputs only and are never connected to detector execution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from tools.issue252.probe_boundary import normalize_box, write_json
from tools.issue255.run_public_baseline_stage_e_reconstruction import (
    _resolve_repo_artifact,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_ROOT = ROOT / "logs/issue255_stage_e_public_baseline/issue255_public_stage_e_01"
PROVENANCE_NAME = "public_stage_e_hybrid_component_provenance.json"
COUNTERFACTUAL_NAME = "public_stage_e_consensus_counterfactual.json"
PUBLIC_REPORT_NAME = "public_baseline_stage_e_reconstruction_report.json"
OUTPUT_NAME = "public_stage_e_sr_reconstruction_gap.json"
CURRENT_CONFIG = ROOT / "configs/dense_full_pipeline.yaml"
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg")


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _path(value: Any, name: str) -> Path:
    if isinstance(value, Mapping):
        value = value.get("path")
    if not isinstance(value, (str, Path)):
        raise ValueError(f"Missing path for {name}")
    path = _resolve_repo_artifact(value)
    if not path.is_file():
        raise FileNotFoundError(f"Missing artifact for {name}: {path}")
    return path


def _optional_path(value: Any) -> Path | None:
    if isinstance(value, Mapping):
        value = value.get("path")
    if not isinstance(value, (str, Path)):
        return None
    path = _resolve_repo_artifact(value)
    return path if path.is_file() else None


def _json_record(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "content": _load(path),
    }


def _find_ancestor_file(path: Path, filename: str) -> Path | None:
    for parent in (path.parent, *path.parents):
        candidate = parent / filename
        if candidate.is_file():
            return candidate.resolve()
    return None


def _find_sr_image(detection_path: Path, page: str) -> Path | None:
    for suffix in IMAGE_SUFFIXES:
        candidate = detection_path.parent / f"{page}{suffix}"
        if candidate.is_file():
            return candidate.resolve()
    candidates = []
    for suffix in IMAGE_SUFFIXES:
        candidates.extend(detection_path.parent.glob(f"{page}*{suffix}"))
    usable = [
        path
        for path in candidates
        if not any(
            token in path.name.lower()
            for token in ("mask", "debug", "overlay", "annotated", "span")
        )
    ]
    return usable[0].resolve() if len(usable) == 1 else None


def _run_id_from_hybrid_path(path: Path) -> str | None:
    parts = path.parts
    try:
        index = parts.index("hybrid_output")
    except ValueError:
        return None
    return parts[index + 1] if index + 1 < len(parts) else None


def _find_public_run_contract(sr_detection: Path) -> Path | None:
    run_id = _run_id_from_hybrid_path(sr_detection)
    if run_id is None:
        return None
    root = ROOT / "logs/issue255_public_baseline_ab"
    matches = list(
        root.glob(f"**/runs/{run_id}/issue255_public_baseline_ab_run_contract.json")
    )
    return matches[0].resolve() if len(matches) == 1 else None


def _image_record(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise FileNotFoundError(f"Failed to read image: {path}")
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "shape": [int(value) for value in image.shape],
        "mean": float(image.mean()),
        "stddev": float(image.std()),
    }


def _image_comparison(historical: Path | None, public: Path | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "historical": _image_record(historical),
        "public": _image_record(public),
        "both_available": historical is not None and public is not None,
    }
    if historical is None or public is None:
        result["classification"] = "sr_image_artifact_missing"
        return result
    historical_image = cv2.imread(str(historical), cv2.IMREAD_GRAYSCALE)
    public_image = cv2.imread(str(public), cv2.IMREAD_GRAYSCALE)
    if historical_image is None or public_image is None:
        raise FileNotFoundError("Failed to read one or more SR images")
    result["same_shape"] = historical_image.shape == public_image.shape
    result["byte_exact"] = _sha256(historical) == _sha256(public)
    if historical_image.shape != public_image.shape:
        result["classification"] = "sr_image_geometry_differs"
        return result
    difference = np.abs(
        historical_image.astype(np.int16) - public_image.astype(np.int16)
    )
    result.update(
        {
            "mean_absolute_difference": float(difference.mean()),
            "p95_absolute_difference": float(np.percentile(difference, 95)),
            "max_absolute_difference": int(difference.max()),
            "changed_pixel_ratio": float(np.count_nonzero(difference) / difference.size),
            "ink240_disagreement_ratio": float(
                np.count_nonzero((historical_image < 240) != (public_image < 240))
                / difference.size
            ),
        }
    )
    result["classification"] = (
        "sr_images_byte_exact"
        if result["byte_exact"]
        else "sr_image_generation_differs"
    )
    return result


def _targets(counterfactual_page: Mapping[str, Any]) -> list[tuple[int, int, int, int]]:
    target_groups = counterfactual_page.get("target_cluster_members")
    if not isinstance(target_groups, Mapping):
        return []
    boxes: set[tuple[int, int, int, int]] = set()
    for side in ("historical", "public"):
        rows = target_groups.get(side)
        if not isinstance(rows, list):
            continue
        for row in rows:
            bbox = row.get("bbox") if isinstance(row, Mapping) else None
            if isinstance(bbox, Sequence) and not isinstance(bbox, (str, bytes)):
                boxes.add(normalize_box(bbox))
    return sorted(boxes)


def _scaled_box(
    bbox: Sequence[int | float],
    *,
    scale_x: float,
    scale_y: float,
) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = normalize_box(bbox)
    return (
        int(round(x1 * scale_x)),
        int(round(y1 * scale_y)),
        int(round(x2 * scale_x)),
        int(round(y2 * scale_y)),
    )


def _draw_targets(
    image: np.ndarray,
    targets: Sequence[tuple[int, int, int, int]],
    *,
    scale_x: float,
    scale_y: float,
) -> None:
    for index, bbox in enumerate(targets, start=1):
        x1, y1, x2, y2 = _scaled_box(
            bbox,
            scale_x=scale_x,
            scale_y=scale_y,
        )
        cv2.rectangle(image, (x1, y1), (x2, y2), (0, 0, 255), 3)
        cv2.putText(
            image,
            f"target{index}",
            (x1, max(20, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )


def _write_sr_comparison(
    *,
    original_path: Path,
    historical_sr: Path | None,
    public_sr: Path | None,
    targets: Sequence[tuple[int, int, int, int]],
    output: Path,
) -> dict[str, Any] | None:
    if historical_sr is None or public_sr is None or not targets:
        return None
    original = cv2.imread(str(original_path))
    historical = cv2.imread(str(historical_sr))
    public = cv2.imread(str(public_sr))
    if original is None or historical is None or public is None:
        raise FileNotFoundError("Failed to read SR comparison images")

    target_x1 = min(box[0] for box in targets) - 100
    target_y1 = min(box[1] for box in targets) - 100
    target_x2 = max(box[2] for box in targets) + 100
    target_y2 = max(box[3] for box in targets) + 100
    target_x1 = max(0, target_x1)
    target_y1 = max(0, target_y1)
    target_x2 = min(original.shape[1], target_x2)
    target_y2 = min(original.shape[0], target_y2)

    panels = []
    panel_records = []
    for label, image in (("historical SR", historical), ("public SR", public)):
        scale_x = image.shape[1] / original.shape[1]
        scale_y = image.shape[0] / original.shape[0]
        annotated = image.copy()
        _draw_targets(
            annotated,
            targets,
            scale_x=scale_x,
            scale_y=scale_y,
        )
        x1 = int(round(target_x1 * scale_x))
        y1 = int(round(target_y1 * scale_y))
        x2 = int(round(target_x2 * scale_x))
        y2 = int(round(target_y2 * scale_y))
        crop = annotated[y1:y2, x1:x2].copy()
        cv2.putText(
            crop,
            label,
            (12, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )
        panels.append(crop)
        panel_records.append(
            {
                "label": label,
                "scale_x": scale_x,
                "scale_y": scale_y,
                "crop_bbox_sr_pixels": [x1, y1, x2, y2],
            }
        )

    target_height = min(panel.shape[0] for panel in panels)
    resized = [
        cv2.resize(
            panel,
            (
                int(round(panel.shape[1] * target_height / panel.shape[0])),
                target_height,
            ),
            interpolation=cv2.INTER_AREA,
        )
        for panel in panels
    ]
    comparison = cv2.hconcat(resized)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), comparison):
        raise RuntimeError(f"Failed to write image: {output}")
    return {
        "path": str(output),
        "original_crop_bbox": [target_x1, target_y1, target_x2, target_y2],
        "targets": [list(box) for box in targets],
        "panels": panel_records,
    }


def _page_classification(
    *,
    consensus_classification: Any,
    image_comparison: Mapping[str, Any],
) -> str:
    if consensus_classification != "current_consensus_reproduces_both_from_component_inputs":
        return "consensus_reconstruction_still_incomplete"
    image_classification = image_comparison.get("classification")
    if image_classification == "sr_images_byte_exact":
        return "sr_detector_or_runtime_differs_on_same_sr_image"
    if image_classification in {
        "sr_image_generation_differs",
        "sr_image_geometry_differs",
    }:
        return "sr_image_generation_is_first_unresolved_boundary"
    return "sr_image_artifact_or_provenance_incomplete"


def build_report(run_root: Path) -> dict[str, Any]:
    run_root = run_root.resolve()
    provenance_path = run_root / PROVENANCE_NAME
    counterfactual_path = run_root / COUNTERFACTUAL_NAME
    public_report_path = run_root / PUBLIC_REPORT_NAME
    provenance = _load(provenance_path)
    counterfactual = _load(counterfactual_path)
    public_report = _load(public_report_path)
    for name, payload in (
        ("component provenance", provenance),
        ("consensus counterfactual", counterfactual),
        ("public Stage E report", public_report),
    ):
        if not isinstance(payload, Mapping) or payload.get("status") != "completed":
            raise ValueError(f"Incomplete {name}")

    provenance_pages = provenance.get("pages")
    counterfactual_pages = counterfactual.get("pages")
    public_pages = public_report.get("pages")
    if not all(
        isinstance(value, Mapping)
        for value in (provenance_pages, counterfactual_pages, public_pages)
    ):
        raise ValueError("One or more source reports lack pages")

    pages: dict[str, Any] = {}
    for label, provenance_page in provenance_pages.items():
        if not isinstance(provenance_page, Mapping):
            continue
        counterfactual_page = counterfactual_pages.get(label)
        public_page = public_pages.get(label)
        if not isinstance(counterfactual_page, Mapping) or not isinstance(
            public_page, Mapping
        ):
            raise ValueError(f"Missing page metadata: {label}")
        component_paths = provenance_page.get("component_paths")
        artifacts = public_page.get("artifacts")
        if not isinstance(component_paths, Mapping) or not isinstance(
            artifacts, Mapping
        ):
            raise ValueError(f"Missing artifact paths: {label}")
        historical_paths = component_paths.get("historical")
        public_paths = component_paths.get("public")
        if not isinstance(historical_paths, Mapping) or not isinstance(
            public_paths, Mapping
        ):
            raise ValueError(f"Missing SR component paths: {label}")

        historical_detection = _path(
            historical_paths.get("sr"),
            f"{label}.historical_sr_detection",
        )
        public_detection = _path(
            public_paths.get("sr"),
            f"{label}.public_sr_detection",
        )
        page_id = str(provenance_page.get("page"))
        historical_sr_image = _find_sr_image(historical_detection, page_id)
        public_sr_image = _find_sr_image(public_detection, page_id)
        image_comparison = _image_comparison(historical_sr_image, public_sr_image)
        original_path = _path(artifacts.get("image"), f"{label}.original_image")
        target_boxes = _targets(counterfactual_page)
        visual = _write_sr_comparison(
            original_path=original_path,
            historical_sr=historical_sr_image,
            public_sr=public_sr_image,
            targets=target_boxes,
            output=run_root / "diagnostics" / f"{label}_sr_image_comparison.png",
        )

        historical_run_config = _find_ancestor_file(
            historical_detection,
            "run_config.json",
        )
        historical_metrics = _find_ancestor_file(
            historical_detection,
            "metrics.json",
        )
        public_run_contract = _find_public_run_contract(public_detection)
        handoff = public_page.get("source_contract")
        public_handoff = (
            handoff.get("public_baseline_handoff")
            if isinstance(handoff, Mapping)
            else None
        )
        profile_provenance = (
            _optional_path(public_handoff.get("provenance_path"))
            if isinstance(public_handoff, Mapping)
            else None
        )
        classification = _page_classification(
            consensus_classification=counterfactual_page.get("classification"),
            image_comparison=image_comparison,
        )

        pages[str(label)] = {
            "score": provenance_page.get("score"),
            "page": page_id,
            "consensus_classification": counterfactual_page.get("classification"),
            "classification": classification,
            "historical_sr_detection": str(historical_detection),
            "public_sr_detection": str(public_detection),
            "historical_sr_image": str(historical_sr_image)
            if historical_sr_image is not None
            else None,
            "public_sr_image": str(public_sr_image)
            if public_sr_image is not None
            else None,
            "sr_image_comparison": image_comparison,
            "target_sr_image_comparison": visual,
            "metadata": {
                "historical_run_config": _json_record(historical_run_config),
                "historical_metrics": _json_record(historical_metrics),
                "public_run_contract": _json_record(public_run_contract),
                "public_profile_provenance": _json_record(profile_provenance),
                "current_config": {
                    "path": str(CURRENT_CONFIG),
                    "sha256": _sha256(CURRENT_CONFIG),
                },
            },
            "historical_sr_commit_recorded": bool(
                historical_run_config
                and isinstance(_load(historical_run_config), Mapping)
                and isinstance(_load(historical_run_config).get("git"), Mapping)
                and any(_load(historical_run_config)["git"].values())
            ),
            "next_gpu_run_required": False,
        }

    return {
        "schema_version": "issue255.public_stage_e_sr_reconstruction_gap.v1",
        "status": "completed",
        "analysis_only": True,
        "historical_artifacts_used_for_analysis_only": True,
        "source_run": str(run_root),
        "source_provenance": str(provenance_path),
        "source_counterfactual": str(counterfactual_path),
        "source_public_report": str(public_report_path),
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
                    label: page["classification"]
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
