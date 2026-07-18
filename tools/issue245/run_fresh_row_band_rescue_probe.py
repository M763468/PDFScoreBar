#!/usr/bin/env python3
"""Evaluate fresh-route row-band rescue options on the focused Issue #245 residuals.

This investigation tool reuses saved current artifacts. It does not run HOMR,
Real-ESRGAN, OMR, CNN, MMR, numbering, or the full-68 evaluation. The image,
current mixed hybrid seeds, staff mask, production probe settings, and
heuristic filters are fixed; only the band selection strategy is varied.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Sequence

import cv2

from src.common import barline_iou
from src.pipeline.probe_detector.bands import build_row_stats, staff_bands_from_mask
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from src.pipeline.steps.probe_scan import run_probe_scan_batch

Box = tuple[int, int, int, int]
DEFAULT_MAIN_REPO = Path("/home/masaki_muramatsu/ws_PDFScoreBar")
DEFAULT_DRIFT_REPORT = Path(
    "logs/issue245_accuracy_first_stage_e/hybrid_row_band_source_drift.json"
)
DEFAULT_OUTPUT = Path("logs/issue245_accuracy_first_stage_e/fresh_row_band_rescue_probe")
TARGETS = (
    {
        "score": "Shostakovich-Sym5-Va",
        "page": "page_013",
        "reference": (1679, 1202, 1683, 1296),
    },
    {
        "score": "Sibelius-Violin_Concerto-Viola",
        "page": "page_004",
        "reference": (1514, 4015, 1518, 4195),
    },
    {
        "score": "Sibelius-Violin_Concerto-Viola",
        "page": "page_004",
        "reference": (1924, 4015, 1928, 4195),
    },
)
VARIANTS: dict[str, dict[str, Any]] = {
    "row_stats_control": {"band_source": "row_stats"},
    "row_stats_pad_025": {"band_source": "row_stats", "band_row_pad_ratio": 0.25},
    "row_stats_pad_050": {"band_source": "row_stats", "band_row_pad_ratio": 0.50},
    "row_stats_pad_075": {"band_source": "row_stats", "band_row_pad_ratio": 0.75},
    "staff_mask": {"band_source": "staff_mask"},
}
PRODUCTION_PROBE_KWARGS: dict[str, Any] = {
    "probe_width": 4,
    "max_per_band": 80,
    "scan_gap_rescue": True,
    "scan_gap_threshold_ratio": 1.5,
    "scan_gap_rescue_min_ratio": 0.3,
    "scan_x_peak_rescue": True,
    "scan_rightmost_rescue": True,
    "scan_center_on_peak": True,
}
PRODUCTION_FILTER_KWARGS: dict[str, Any] = {
    "left_margin_ratio": 0.12,
    "clef_left_ratio": 0.25,
    "min_height_median_ratio": 0.6,
    "ink_threshold": 180,
    "min_ink_ratio": 0.18,
    "paper_threshold": 200,
    "min_paper_overlap_ratio": 0.6,
    "min_staff_overlap_ratio": 0.02,
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_input(path: Path, *, main_repo: Path) -> Path:
    expanded = path.expanduser()
    candidates = (
        [expanded] if expanded.is_absolute() else [Path.cwd() / expanded, main_repo / expanded]
    )
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.exists():
            return resolved
    raise FileNotFoundError(f"Input not found: {path}; tried={candidates}")


def _resolve_artifact(path_value: str, *, main_repo: Path) -> Path:
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (main_repo / path).resolve()


def _normalize_box(value: Sequence[Any]) -> Box:
    if len(value) != 4:
        raise ValueError(f"Invalid bbox: {value!r}")
    return tuple(int(round(float(part))) for part in value)  # type: ignore[return-value]


def _best_match(reference: Box, candidates: Iterable[Box]) -> dict[str, Any]:
    ranked = sorted(
        ((candidate, float(barline_iou(reference, candidate))) for candidate in candidates),
        key=lambda item: (-item[1], item[0]),
    )
    best_box, best_iou = ranked[0] if ranked else (None, 0.0)
    return {
        "accepted": best_iou > 0.5,
        "max_iou": best_iou,
        "best_bbox": list(best_box) if best_box is not None else None,
    }


def _semantic_delta(control: Iterable[Box], variant: Iterable[Box]) -> dict[str, Any]:
    control_counter = Counter(control)
    variant_counter = Counter(variant)
    added = list((variant_counter - control_counter).elements())
    removed = list((control_counter - variant_counter).elements())
    return {
        "added_count": len(added),
        "removed_count": len(removed),
        "added_examples": [list(box) for box in sorted(added)[:20]],
        "removed_examples": [list(box) for box in sorted(removed)[:20]],
    }


def _classify_target(variant_matches: dict[str, dict[str, Any]]) -> str:
    if variant_matches["row_stats_control"]["accepted"]:
        return "already_present_in_control"
    for name in ("row_stats_pad_025", "row_stats_pad_050", "row_stats_pad_075"):
        if variant_matches[name]["accepted"]:
            return f"restored_by_{name}"
    if variant_matches["staff_mask"]["accepted"]:
        return "restored_by_staff_mask"
    return "unresolved"


def _find_page_record(report: dict[str, Any], score: str, page: str) -> dict[str, Any]:
    matches = [
        item
        for item in report.get("targets", [])
        if isinstance(item, dict)
        and str(item.get("score")) == score
        and str(item.get("page")) == page
    ]
    if not matches:
        raise ValueError(f"No drift-report record for {score}/{page}")
    return matches[0]


def _find_mask(directory: Path, stem: str, suffixes: Sequence[str]) -> Path | None:
    candidates: list[Path] = []
    for suffix in suffixes:
        candidates.extend(directory.rglob(f"{stem}{suffix}"))
        candidates.extend(directory.rglob(f"{stem}_proxy{suffix}"))
    return sorted({path.resolve() for path in candidates})[0] if candidates else None


def _candidate_output(root: Path) -> Path:
    matches = sorted(root.rglob("pipeline2_no_peak_candidates.json"))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one probe candidate output under {root}, got {len(matches)}")
    return matches[0]


def _mask_bands(mask_path: Path | None, image_path: Path) -> list[list[int]]:
    if mask_path is None:
        return []
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    if image is None or mask is None:
        return []
    if mask.shape[:2] != image.shape[:2]:
        mask = cv2.resize(mask, (image.shape[1], image.shape[0]), interpolation=cv2.INTER_NEAREST)
    return [list(band) for band in staff_bands_from_mask(mask)]


def _run_page_variant(
    *,
    image_path: Path,
    score: str,
    mixed_hybrid_path: Path,
    mask_dir: Path,
    output_root: Path,
    variant_kwargs: dict[str, Any],
) -> tuple[Path, list[Box]]:
    probe_kwargs = dict(PRODUCTION_PROBE_KWARGS)
    probe_kwargs.update(variant_kwargs)
    run_probe_scan_batch(
        images=[image_path],
        output_root=output_root,
        bands_from=mixed_hybrid_path,
        staff_mask_dir=mask_dir,
        clef_mask_dir=mask_dir,
        ink_threshold=240,
        min_ratio=0.60,
        min_height_ratio=0.006,
        min_width_ratio=0.0,
        score_name=score,
        band_cluster_max_dist=25.0,
        band_min_row_count=1,
        vertical_closing=4,
        detect_probe_kwargs=probe_kwargs,
        enable_heuristic_filters=True,
        candidate_filter_kwargs=dict(PRODUCTION_FILTER_KWARGS),
    )
    output_path = _candidate_output(output_root)
    return output_path, [_normalize_box(box) for box in load_json_boxes(output_path)]


def build_report(*, main_repo: Path, drift_report_path: Path, output_root: Path) -> dict[str, Any]:
    drift_report = _load_json(drift_report_path)
    page_keys = sorted({(str(item["score"]), str(item["page"])) for item in TARGETS})
    pages: list[dict[str, Any]] = []
    target_results: list[dict[str, Any]] = []

    for score, page in page_keys:
        record = _find_page_record(drift_report, score, page)
        paths = record.get("paths", {})
        current_sr_path = _resolve_artifact(str(paths["current_sr"]), main_repo=main_repo)
        mixed_hybrid_path = _resolve_artifact(str(paths["mixed_hybrid"]), main_repo=main_repo)
        image_path = (
            main_repo / "data" / "evaluation2" / "images" / score / f"{page}.png"
        ).resolve()
        if not image_path.is_file():
            raise FileNotFoundError(image_path)
        mask_dir = current_sr_path.parent
        staff_mask_path = _find_mask(
            mask_dir,
            page,
            ("_staff_mask.png", "_debug_3_staff.png"),
        )
        clef_mask_path = _find_mask(
            mask_dir,
            page,
            ("_clef_mask.png", "_clefs_keys_mask.png", "_debug_2_clefs.png"),
        )
        existing_boxes = [_normalize_box(box) for box in load_json_boxes(mixed_hybrid_path)]
        row_stats = build_row_stats(existing_boxes, cluster_max_dist=25.0, min_row_count=1)

        variants: dict[str, dict[str, Any]] = {}
        variant_boxes: dict[str, list[Box]] = {}
        page_root = output_root / score / page
        for variant_name, variant_kwargs in VARIANTS.items():
            variant_root = page_root / variant_name
            output_path, boxes = _run_page_variant(
                image_path=image_path,
                score=score,
                mixed_hybrid_path=mixed_hybrid_path,
                mask_dir=mask_dir,
                output_root=variant_root,
                variant_kwargs=variant_kwargs,
            )
            variant_boxes[variant_name] = boxes
            variants[variant_name] = {
                "settings": variant_kwargs,
                "output": str(output_path),
                "candidate_count": len(boxes),
            }

        control_boxes = variant_boxes["row_stats_control"]
        for variant_name, boxes in variant_boxes.items():
            variants[variant_name]["delta_from_control"] = _semantic_delta(control_boxes, boxes)

        page_targets = [item for item in TARGETS if item["score"] == score and item["page"] == page]
        for target in page_targets:
            reference = _normalize_box(target["reference"])
            matches = {name: _best_match(reference, boxes) for name, boxes in variant_boxes.items()}
            result = {
                "score": score,
                "page": page,
                "reference": list(reference),
                "variant_matches": matches,
                "classification": _classify_target(matches),
            }
            target_results.append(result)

        pages.append(
            {
                "score": score,
                "page": page,
                "image": str(image_path),
                "current_sr": str(current_sr_path),
                "mixed_hybrid": str(mixed_hybrid_path),
                "staff_mask": str(staff_mask_path) if staff_mask_path else None,
                "clef_mask": str(clef_mask_path) if clef_mask_path else None,
                "row_stats": [
                    {
                        "center": float(stat["center"]),
                        "top": int(stat["top"]),
                        "bottom": int(stat["bottom"]),
                    }
                    for stat in row_stats
                ],
                "staff_mask_bands": _mask_bands(staff_mask_path, image_path),
                "variants": variants,
            }
        )

    return {
        "schema_version": "issue245.fresh_row_band_rescue_probe.v1",
        "status": "completed",
        "production_default_changed": False,
        "upstream_inference_run": False,
        "cnn_or_mmr_run": False,
        "drift_report": str(drift_report_path),
        "production_probe_settings": {
            "ink_threshold": 240,
            "min_ratio": 0.60,
            "min_height_ratio": 0.006,
            "min_width_ratio": 0.0,
            "band_cluster_max_dist": 25.0,
            "band_min_row_count": 1,
            "vertical_closing": 4,
            "detect_probe_kwargs": PRODUCTION_PROBE_KWARGS,
            "candidate_filter_kwargs": PRODUCTION_FILTER_KWARGS,
        },
        "variants": VARIANTS,
        "pages": pages,
        "targets": target_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--main-repo-root",
        type=Path,
        default=Path(os.environ.get("ISSUE245_MAIN_REPO_ROOT", DEFAULT_MAIN_REPO)),
    )
    parser.add_argument("--drift-report", type=Path, default=DEFAULT_DRIFT_REPORT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    main_repo = args.main_repo_root.expanduser().resolve()
    drift_report = _resolve_input(args.drift_report, main_repo=main_repo)
    output_root = args.output_root.expanduser()
    if not output_root.is_absolute():
        output_root = (Path.cwd() / output_root).resolve()
    if output_root.exists():
        if not args.force:
            raise FileExistsError(f"Output already exists: {output_root}")
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    report = build_report(
        main_repo=main_repo,
        drift_report_path=drift_report,
        output_root=output_root,
    )
    report_path = output_root / "fresh_row_band_rescue_probe_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for target in report["targets"]:
        print(
            f"{target['score']}/{target['page']} reference={target['reference']} "
            f"classification={target['classification']}"
        )
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
