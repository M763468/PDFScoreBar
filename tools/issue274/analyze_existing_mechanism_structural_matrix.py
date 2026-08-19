#!/usr/bin/env python3
"""Test existing PDFScoreBar mechanisms before proposing a new #274 filter.

This is a retained-artifact / light first-pass experiment.  It does NOT rerun HOMR,
SR, OMR-DLN, Stage-E filtering, CNN, MMR, or numbering.

The structural crop audit established that the focused 2->1 losses are logical
per-staff/per-row identities on one continuous physical barline, not two independent
ink strokes.  The experiment therefore tests mechanisms already present in the
repository before inventing a new identity filter:

1. derive dense bands from the authoritative A/original HOMR staff mask instead of
   from the support-filtered hybrid box set;
2. use the existing ``scan_existing_min_vertical_iou`` guard so an existing seed
   only suppresses a sufficiently corresponding band;
3. audit the existing current-HOMR thin replacement path separately.  In particular
   page_015 already has retained evidence that the pre-thin primary supports the A
   seed with the existing symmetric IoU rule, while the longer PDFScoreBar thin
   replacement does not.

A 68-page static sweep reports how often each vertical-IoU threshold would allow one
existing hybrid seed to suppress multiple A-staff bands.  The three structural pages
also receive a production-parameter first dense-pass replay with A staff-mask bands.

Ownership:
- A/B HOMR masks and primary detections: upstream-HOMR-derived data;
- runtime selection, coordinate mapping, artifact persistence: PDFScoreBar orchestration;
- hybrid consensus, thin replacement, dense probe, suppression: PDFScoreBar extensions.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import cv2
import numpy as np

from src.common import Box
from src.pipeline.probe_detector import detect_probe_scan
from src.pipeline.probe_detector.bands import build_row_stats, staff_bands_from_mask
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue274.analyze_stage_e_first_pass_context_causality import (
    merged_raw,
    target_component,
)

AB_DEFAULT = Path(
    "logs/issue274_homr_unification_analysis/stage_e_ab_01/"
    "issue274_homr_x4_stage_e_ab.json"
)
CAUSAL_DEFAULT = Path(
    "logs/issue274_homr_unification_analysis/stage_e_first_pass_causality_01/"
    "issue274_stage_e_first_pass_context_causality.json"
)
THIN_DEFAULT = Path(
    "logs/issue274_homr_unification_analysis/thin_policy_single_inference_01/"
    "issue274_thin_policy_single_inference_replay.json"
)
OUTPUT_DEFAULT = Path(
    "logs/issue274_homr_unification_analysis/existing_mechanism_structural_matrix_01/"
    "issue274_existing_mechanism_structural_matrix.json"
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def to_workspace(value: str | Path, workspace: Path) -> Path:
    text = str(value)
    if text.startswith("/workspace/"):
        return workspace / text[len("/workspace/") :]
    marker = "/ws_PDFScoreBar/"
    if marker in text:
        return workspace / text.split(marker, 1)[1]
    path = Path(text)
    return path if path.is_absolute() else workspace / path


def norm_box(values: Sequence[Any]) -> Box:
    return tuple(int(round(float(v))) for v in values[:4])  # type: ignore[return-value]


def parse_thresholds(value: str) -> list[float]:
    result = sorted({float(item.strip()) for item in value.split(",") if item.strip()})
    if not result:
        raise ValueError("At least one suppression threshold is required")
    if any(item < 0.0 or item > 1.0 for item in result):
        raise ValueError(f"Thresholds must be in [0,1]: {result}")
    return result


def discover_a_staff_mask(a_path: Path, page: str) -> Path | None:
    parent = a_path.parent
    for name in (
        f"{page}_staff_mask.png",
        f"{page}_proxy_debug_3_staff.png",
        f"{page}_debug_3_staff.png",
    ):
        candidate = parent / name
        if candidate.is_file():
            return candidate
    found: list[Path] = []
    for pattern in ("*_staff_mask.png", "*_proxy_debug_3_staff.png", "*_debug_3_staff.png"):
        found.extend(parent.glob(pattern))
    return sorted(set(found))[0] if found else None


def source_image(score: str, page: str, workspace: Path) -> Path:
    path = workspace / "data" / "evaluation2" / "images" / score / f"{page}.png"
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def load_source_sized_staff_mask(mask_path: Path, image: np.ndarray) -> np.ndarray:
    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise FileNotFoundError(mask_path)
    h, w = image.shape[:2]
    if mask.shape[:2] != (h, w):
        mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
    return mask


def vertical_iou(box: Box, band: tuple[int, int]) -> float:
    y1, y2 = band
    band_h = max(1.0, float(y2 - y1))
    by1, by2 = sorted((float(box[1]), float(box[3])))
    box_h = max(1.0, by2 - by1)
    inter = max(0.0, min(float(y2), by2) - max(float(y1), by1))
    union = max(1.0, band_h + box_h - inter)
    return inter / union


def suppression_eligible_bands(
    box: Box,
    bands: Sequence[tuple[int, int]],
    threshold: float,
) -> list[dict[str, Any]]:
    cy = (box[1] + box[3]) / 2.0
    rows: list[dict[str, Any]] = []
    for index, band in enumerate(bands):
        y1, y2 = band
        # Mirror detect_probe_scan.has_existing(): the existing-box centre must be
        # inside the candidate band before the optional vertical-IoU test.
        if cy < y1 or cy > y2:
            continue
        viou = vertical_iou(box, band)
        if threshold > 0.0 and viou < threshold:
            continue
        rows.append({"band_index": index, "band": [y1, y2], "vertical_iou": viou})
    return rows


def production_probe_with_staff_bands(
    image: np.ndarray,
    staff_mask: np.ndarray,
    existing_boxes: list[Box],
    *,
    threshold: float,
) -> list[Box]:
    return [
        norm_box(box)
        for box in detect_probe_scan(
            base_img=image,
            staff_mask=staff_mask,
            existing_boxes=existing_boxes,
            band_source="staff_mask",
            band_cluster_max_dist=25.0,
            band_min_row_count=1,
            band_scan_line_ratio=0.6,
            band_scan_min_lines=5,
            scan_x_peak_rescue=True,
            scan_rightmost_rescue=True,
            divisi_rescue=True,
            scan_x_peak_rescue_mode="topbottom",
            probe_width=4,
            ink_threshold=240,
            min_ratio=0.60,
            scan_x_peak_ratio_min=0.0,
            scan_rightmost_min_ratio=0.0,
            max_per_band=80,
            scan_center_on_peak=True,
            vertical_closing=0,
            scan_existing_min_vertical_iou=threshold,
        )
    ]


def production_probe_with_supplied_rows(
    image: np.ndarray,
    existing_boxes: list[Box],
    row_stats: list[dict[str, float]],
    *,
    threshold: float,
) -> list[Box]:
    empty = np.zeros(image.shape[:2], dtype=np.uint8)
    return [
        norm_box(box)
        for box in detect_probe_scan(
            base_img=image,
            staff_mask=empty,
            existing_boxes=existing_boxes,
            band_source="row_stats",
            band_cluster_max_dist=25.0,
            band_min_row_count=1,
            row_stats=row_stats,
            band_scan_line_ratio=0.6,
            band_scan_min_lines=5,
            scan_x_peak_rescue=True,
            scan_rightmost_rescue=True,
            divisi_rescue=True,
            scan_x_peak_rescue_mode="topbottom",
            probe_width=4,
            ink_threshold=240,
            min_ratio=0.60,
            scan_x_peak_ratio_min=0.0,
            scan_rightmost_min_ratio=0.0,
            max_per_band=80,
            scan_center_on_peak=True,
            vertical_closing=0,
            scan_existing_min_vertical_iou=threshold,
        )
    ]


def focus_component(
    *,
    image: np.ndarray,
    generated: list[Box],
    existing: list[Box],
    gt_boxes: list[Box],
) -> dict[str, Any]:
    raw = merged_raw(image, generated, existing)
    return {
        "generated_count": len(generated),
        "raw_count": len(raw),
        "target_component": target_component(
            raw,
            gt_boxes,
            generated=set(generated),
            merge_boxes=set(existing),
        ),
    }


def static_full68_suppression_sweep(
    *,
    page_records: Sequence[Mapping[str, Any]],
    workspace: Path,
    thresholds: Sequence[float],
) -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
    totals = {threshold: Counter() for threshold in thresholds}
    page_details: dict[tuple[str, str], dict[str, Any]] = {}

    for record in page_records:
        score = str(record["score"])
        page = str(record["page"])
        a_path = to_workspace(str(record["a_path"]), workspace)
        candidate_hybrid = to_workspace(str(record["candidate_hybrid"]), workspace)
        mask_path = discover_a_staff_mask(a_path, page)
        image_path = source_image(score, page, workspace)
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(image_path)
        if mask_path is None:
            raise FileNotFoundError(f"A staff mask missing for {score}/{page}: {a_path}")
        mask = load_source_sized_staff_mask(mask_path, image)
        bands = [(int(y1), int(y2)) for y1, y2 in staff_bands_from_mask(mask)]
        existing = [norm_box(box) for box in load_json_boxes(candidate_hybrid)]

        threshold_rows: dict[str, Any] = {}
        for threshold in thresholds:
            counts = Counter()
            examples: list[dict[str, Any]] = []
            for box in existing:
                eligible = suppression_eligible_bands(box, bands, threshold)
                counts["seed_count"] += 1
                counts["owned_seed_count"] += int(bool(eligible))
                counts["unowned_seed_count"] += int(not eligible)
                counts["multi_band_seed_count"] += int(len(eligible) > 1)
                counts["eligible_band_edges"] += len(eligible)
                if len(eligible) > 1 and len(examples) < 8:
                    examples.append({"box": list(box), "eligible_bands": eligible})
            totals[threshold].update(counts)
            threshold_rows[f"{threshold:.3f}"] = {**dict(counts), "multi_band_examples": examples}

        page_details[(score, page)] = {
            "a_staff_mask": str(mask_path),
            "staff_band_count": len(bands),
            "staff_bands": [list(band) for band in bands],
            "candidate_hybrid_count": len(existing),
            "thresholds": threshold_rows,
        }

    aggregate = [
        {"threshold": threshold, **dict(totals[threshold])}
        for threshold in thresholds
    ]
    return aggregate, page_details


def find_thin_page(report: Mapping[str, Any], score: str, page: str) -> Mapping[str, Any] | None:
    for row in report.get("pages", []):
        if str(row.get("score")) == score and str(row.get("page")) == page:
            return row
    return None


def thin_primary_preservation_summary(thin_path: Path | None) -> dict[str, Any]:
    if thin_path is None or not thin_path.is_file():
        return {"status": "missing_thin_report", "path": None if thin_path is None else str(thin_path)}
    report = load_json(thin_path)
    row = find_thin_page(report, "Shostakovich-Sym5-Va", "page_015")
    if row is None:
        return {"status": "page_015_missing", "path": str(thin_path)}
    critical = next(
        (
            item
            for item in row.get("critical_cases", [])
            if item.get("baseline_box") == [2296, 2246, 2305, 2344]
        ),
        None,
    )
    if critical is None:
        return {"status": "critical_case_missing", "path": str(thin_path)}
    policies = critical.get("policies", {})
    legacy = policies.get("legacy", {})
    current = policies.get("current", {})
    return {
        "status": "ok",
        "path": str(thin_path),
        "pre_thin_count": row.get("pre_thin_count"),
        "legacy_extra_count": row.get("legacy_extra_count"),
        "current_extra_count": row.get("current_extra_count"),
        "legacy_iou_support": legacy.get("iou_support"),
        "legacy_best": legacy.get("directional_best"),
        "current_iou_support": current.get("iou_support"),
        "current_best": current.get("directional_best"),
        "inference": (
            "legacy_extra_count==0 means the legacy-final target supporter is present before "
            "thin augmentation. If legacy IoU is true while current IoU is false, preserving "
            "the primary channel would allow the existing symmetric-IoU consensus to keep "
            "the A seed without requiring a new directional support rule for this case."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument("--ab-report", type=Path, default=AB_DEFAULT)
    parser.add_argument("--causality-report", type=Path, default=CAUSAL_DEFAULT)
    parser.add_argument("--thin-report", type=Path, default=THIN_DEFAULT)
    parser.add_argument("--output", type=Path, default=OUTPUT_DEFAULT)
    parser.add_argument(
        "--suppression-thresholds",
        default="0,0.50,0.55,0.60,0.65,0.70,0.80",
    )
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    ab_path = to_workspace(args.ab_report, workspace)
    causality_path = to_workspace(args.causality_report, workspace)
    thin_path = to_workspace(args.thin_report, workspace)
    output = to_workspace(args.output, workspace)
    thresholds = parse_thresholds(args.suppression_thresholds)

    ab = load_json(ab_path)
    page_records = ab["hybrid_ab"]["pages"]
    if len(page_records) != 68:
        raise RuntimeError(f"Expected 68 A/B/C pages, got {len(page_records)}")
    causal = load_json(causality_path)
    if causal.get("all_production_replays_match_retained_raw_sets") is not True:
        raise RuntimeError("First-pass causal input failed its production replay sanity gate")

    aggregate, page_static = static_full68_suppression_sweep(
        page_records=page_records,
        workspace=workspace,
        thresholds=thresholds,
    )

    ab_by_key = {(str(row["score"]), str(row["page"])): row for row in page_records}
    focused: list[dict[str, Any]] = []
    for page_row in causal.get("pages", []):
        score = str(page_row["score"])
        page = str(page_row["page"])
        ab_row = ab_by_key[(score, page)]
        image_path = source_image(score, page, workspace)
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(image_path)
        a_path = to_workspace(str(ab_row["a_path"]), workspace)
        b_hybrid_path = to_workspace(str(ab_row["candidate_hybrid"]), workspace)
        mask_path = discover_a_staff_mask(a_path, page)
        if mask_path is None:
            raise FileNotFoundError(f"A staff mask missing for {score}/{page}")
        staff_mask = load_source_sized_staff_mask(mask_path, image)
        staff_bands = [(int(y1), int(y2)) for y1, y2 in staff_bands_from_mask(staff_mask)]
        b_hybrid = [norm_box(box) for box in load_json_boxes(b_hybrid_path)]
        a_boxes = [norm_box(box) for box in load_json_boxes(a_path)]
        a_rows = build_row_stats(a_boxes, cluster_max_dist=25.0, min_row_count=1)

        target_rows: list[dict[str, Any]] = []
        for target in page_row.get("targets", []):
            gt_boxes = [norm_box(box) for box in target["component_gt_bboxes"]]
            variants: dict[str, Any] = {}
            for threshold in thresholds:
                generated_staff = production_probe_with_staff_bands(
                    image,
                    staff_mask,
                    b_hybrid,
                    threshold=threshold,
                )
                variants[f"a_staff_mask__viou_{threshold:.3f}"] = focus_component(
                    image=image,
                    generated=generated_staff,
                    existing=b_hybrid,
                    gt_boxes=gt_boxes,
                )

            # Diagnostic only: A raw barline row-stats are tested separately because A
            # raw boxes may themselves bridge logical rows.  Do not assume this is an
            # authoritative topology source merely because A owns the baseline geometry.
            generated_a_rows = production_probe_with_supplied_rows(
                image,
                b_hybrid,
                a_rows,
                threshold=0.0,
            )
            variants["a_raw_row_stats__viou_0"] = focus_component(
                image=image,
                generated=generated_a_rows,
                existing=b_hybrid,
                gt_boxes=gt_boxes,
            )

            target_rows.append(
                {
                    "gt_index": target["gt_index"],
                    "gt_bbox": target["gt_bbox"],
                    "component_gt_bboxes": [list(box) for box in gt_boxes],
                    "b_production_reference": target["variants"]["candidate_production"],
                    "variants": variants,
                }
            )

        focused.append(
            {
                "score": score,
                "page": page,
                "image": str(image_path),
                "a_staff_mask": str(mask_path),
                "a_staff_bands": [list(band) for band in staff_bands],
                "a_raw_row_stats": a_rows,
                "b_hybrid": str(b_hybrid_path),
                "b_hybrid_count": len(b_hybrid),
                "static_suppression": page_static[(score, page)],
                "targets": target_rows,
            }
        )

    result = {
        "schema_version": "issue274.existing_mechanism_structural_matrix.v1",
        "status": "completed",
        "scope": {
            "full68_static_pages": len(page_records),
            "focused_first_pass_pages": len(focused),
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_dln_reexecuted": False,
            "stage_e_first_dense_reexecuted": True,
            "stage_e_filter_reexecuted": False,
            "stage_e_second_probe_reexecuted": False,
            "cnn_reexecuted": False,
            "mmr_reexecuted": False,
        },
        "ownership": {
            "a_staff_mask_pixels": "upstream_homr_data",
            "b_primary_barline_pixels_geometry": "upstream_homr_derived_data",
            "artifact_selection_coordinate_mapping": "pdfscore_upstream_orchestration",
            "thin_barline_replacement": "pdfscore_extension",
            "hybrid_consensus": "pdfscore_extension",
            "dense_probe": "pdfscore_extension",
            "existing_box_suppression": "pdfscore_extension",
        },
        "historical_guardrail": (
            "Issue #119 records that some evaluation2 GT barlines are logically split per "
            "staff in Divisi-like notation even when the printed ink is continuous. Issue #119 "
            "was later superseded by #120, so its old golden pipeline is provenance, not a "
            "production contract. Physical-ink split_box_vertically is therefore not assumed "
            "to solve the present logical multiplicity."
        ),
        "suppression_thresholds": thresholds,
        "full68_static_suppression_sweep": aggregate,
        "thin_primary_preservation": thin_primary_preservation_summary(thin_path),
        "focused": focused,
        "decision_rules": [
            "Prefer an existing scan_existing_min_vertical_iou threshold only if it restores the focused logical sibling rows and materially reduces multi-band suppression seeds without broadly unowning valid seeds.",
            "If no threshold separates owner vs logical-sibling bands, only then consider a new explicit one-seed/one-band owner rule.",
            "Prefer preserving the pre-thin primary evidence channel over adding a new directional support rule when existing symmetric IoU already supports the A seed.",
            "Do not use A raw barline rows as structural topology unless the focused and broad audit supports them; A raw detections can bridge logical rows too.",
        ],
    }
    write_json(output, result)
    print(json.dumps({"status": "completed", "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
