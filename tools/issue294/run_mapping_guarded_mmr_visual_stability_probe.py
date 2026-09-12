#!/usr/bin/env python3
"""Probe primary-measure MMR crop stability and export visual review sheets.

This Issue #294 experiment is intentionally focused on retained keys whose causal
matrix identified the primary measure bbox as the source of a frozen/native MMR
delta.  It does not rerun detector, HOMR, SR, OMR, or full68 MMR.  It reruns only
CNN/OCR for a small, symmetric x1 sweep around candidate-native geometry and writes
annotated image sheets so the printed score content can be inspected directly.

The sweep is candidate-native-relative.  Historical frozen-A geometry is recorded
only as a reference marker; it is not used to choose the sweep offsets.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np
import torch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.measure_numbering.mmr import MMRClassifier, MMROCREngine, MMRProcessor
from src.measure_numbering.rapidocr_provider import (
    collect_rapidocr_providers,
    create_mmr_rapidocr,
    providers_include_cuda,
)
from tools.issue294.rescore_full68_mmr_audit import (
    _load_json,
    _load_matrix_pages,
    _resolve_project_path,
)

DEFAULT_MODEL = PROJECT_ROOT / "tools/mmr_training/models/mmr_classifier_best.pth"
SWEEP_FRACTIONS = (-0.04, -0.02, -0.01, 0.0, 0.01, 0.02, 0.04)
PANEL_SIZE = (500, 300)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def primary_measure_causal(record: Mapping[str, Any]) -> bool:
    """Return whether the causal matrix implicates primary measure geometry."""

    classification = record.get("classification", {})
    if classification.get("reverting_primary_measure_restores_frozen") is True:
        return True
    frozen = classification.get("frozen_final_skip")
    native = classification.get("native_final_skip")
    components = classification.get("primary_component_results", {})
    return bool(
        frozen != native
        and components.get("primary_measure_native_only") == native
        and components.get("primary_staff_native_only") == frozen
    )


def x1_offsets(width: int, fractions: Sequence[float] = SWEEP_FRACTIONS) -> list[dict[str, Any]]:
    if width <= 0:
        raise ValueError("measure width must be positive")
    return [
        {"fraction": float(fraction), "dx1": int(round(width * float(fraction)))}
        for fraction in fractions
    ]


def _probe_primary(
    processor: MMRProcessor,
    image: np.ndarray,
    measure_bbox: Sequence[int],
    staff_bboxes: Sequence[Sequence[int]],
) -> dict[str, Any]:
    x1, y1, x2, y2 = (int(value) for value in measure_bbox)
    h_img, w_img = image.shape[:2]
    margin = 20
    cx1, cy1 = max(0, x1 - margin), max(0, y1 - margin)
    cx2, cy2 = min(w_img, x2 + margin), min(h_img, y2 + margin)
    probability = float(processor.classifier.predict(image[cy1:cy2, cx1:cx2]))
    system = {"staves": [{"bbox": [int(value) for value in bbox]} for bbox in staff_bboxes]}
    found_num, score, debug, evidence = processor._detect_number_with_evidence(
        image, system, x1, y1, x2, y2, probability, w_img, h_img
    )
    valid, status, vetoed = processor._valid_status(found_num, probability, score, evidence)
    return {
        "measure_bbox": [x1, y1, x2, y2],
        "cnn_probability": probability,
        "found_num": found_num,
        "skip": (int(found_num) - 1) if valid and found_num is not None else None,
        "score": float(score),
        "debug": str(debug),
        "one_bar_evidence": int(evidence),
        "valid": bool(valid),
        "status": str(status),
        "vetoed": bool(vetoed),
    }


def _crop_bounds(
    image: np.ndarray,
    measure_bbox: Sequence[int],
    staff_bboxes: Sequence[Sequence[int]],
) -> tuple[int, int, int, int]:
    x1, _y1, x2, _y2 = (int(value) for value in measure_bbox)
    h_img, w_img = image.shape[:2]
    if staff_bboxes:
        top = min(int(bbox[1]) for bbox in staff_bboxes)
        bottom = max(int(bbox[3]) for bbox in staff_bboxes)
    else:
        top, bottom = int(measure_bbox[1]), int(measure_bbox[3])
    return (
        max(0, x1 - 180),
        max(0, top - 120),
        min(w_img, x2 + 60),
        min(h_img, bottom + 120),
    )


def _letterbox(image: np.ndarray, width: int, height: int) -> np.ndarray:
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    if image is None or image.size == 0:
        return canvas
    h, w = image.shape[:2]
    scale = min(width / max(1, w), height / max(1, h))
    resized = cv2.resize(
        image,
        (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
        interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR,
    )
    rh, rw = resized.shape[:2]
    y0, x0 = (height - rh) // 2, (width - rw) // 2
    canvas[y0 : y0 + rh, x0 : x0 + rw] = resized
    return canvas


def _panel(image: np.ndarray, label: str) -> np.ndarray:
    body = _letterbox(image, PANEL_SIZE[0], PANEL_SIZE[1] - 42)
    panel = np.full((PANEL_SIZE[1], PANEL_SIZE[0], 3), 255, dtype=np.uint8)
    panel[42:, :] = body
    cv2.putText(
        panel, label[:68], (8, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1, cv2.LINE_AA
    )
    return panel


def _context_panel(
    image: np.ndarray,
    frozen_bbox: Sequence[int],
    native_bbox: Sequence[int],
    staff_bboxes: Sequence[Sequence[int]],
    offsets: Sequence[Mapping[str, Any]],
) -> np.ndarray:
    boxes = [list(frozen_bbox), list(native_bbox), *[list(item) for item in staff_bboxes]]
    x1 = max(0, min(int(box[0]) for box in boxes) - 240)
    y1 = max(0, min(int(box[1]) for box in boxes) - 180)
    x2 = min(image.shape[1], max(int(box[2]) for box in boxes) + 160)
    y2 = min(image.shape[0], max(int(box[3]) for box in boxes) + 180)
    crop = image[y1:y2, x1:x2].copy()

    def rect(box: Sequence[int], color: tuple[int, int, int], thickness: int) -> None:
        bx1, by1, bx2, by2 = (int(value) for value in box)
        cv2.rectangle(crop, (bx1 - x1, by1 - y1), (bx2 - x1, by2 - y1), color, thickness)

    rect(frozen_bbox, (0, 160, 0), 2)
    rect(native_bbox, (0, 0, 220), 2)
    for bbox in staff_bboxes:
        rect(bbox, (160, 160, 160), 1)

    native_x1 = int(native_bbox[0])
    for item in offsets:
        sx = native_x1 + int(item["dx1"]) - x1
        if 0 <= sx < crop.shape[1]:
            cv2.line(crop, (sx, 0), (sx, crop.shape[0] - 1), (180, 180, 180), 1)
    cv2.putText(
        crop,
        "green=frozen reference  red=native  gray=sweep x1",
        (8, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (0, 0, 0),
        1,
        cv2.LINE_AA,
    )
    return crop


def _review_crop(
    image: np.ndarray,
    measure_bbox: Sequence[int],
    staff_bboxes: Sequence[Sequence[int]],
) -> np.ndarray:
    x1, y1, x2, y2 = _crop_bounds(image, measure_bbox, staff_bboxes)
    crop = image[y1:y2, x1:x2].copy()
    mx1, _my1, mx2, _my2 = (int(value) for value in measure_bbox)
    cv2.line(crop, (mx1 - x1, 0), (mx1 - x1, max(0, crop.shape[0] - 1)), (0, 0, 220), 2)
    cv2.line(crop, (mx2 - x1, 0), (mx2 - x1, max(0, crop.shape[0] - 1)), (220, 0, 0), 1)
    return crop


def _contact_sheet(panels: Sequence[np.ndarray]) -> np.ndarray:
    if len(panels) != 9:
        raise ValueError("review contact sheet requires exactly 9 panels")
    rows = [np.hstack(panels[index : index + 3]) for index in range(0, 9, 3)]
    return np.vstack(rows)


def run(
    manifest_path: Path,
    causal_path: Path,
    model_path: Path,
    output_dir: Path,
    output_json: Path,
) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    causal = _load_json(causal_path)
    if not isinstance(manifest, Mapping) or manifest.get("status") != "completed":
        raise ValueError("Full68 manifest is not completed")
    if not isinstance(causal, Mapping) or causal.get("status") != "completed":
        raise ValueError("Causal matrix is not completed")
    if causal.get("reproduction_failures"):
        raise RuntimeError("Causal matrix has reproduction failures")
    if not model_path.is_file():
        raise FileNotFoundError(model_path)

    selected = [record for record in causal.get("records", []) if primary_measure_causal(record)]
    if not selected:
        raise RuntimeError("No primary-measure-causal records found")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("Focused visual stability probe requires CUDA")
    classifier = MMRClassifier(model_path, device)
    rapidocr = create_mmr_rapidocr("cuda")
    providers = collect_rapidocr_providers(rapidocr)
    if not providers_include_cuda(providers):
        raise RuntimeError(f"RapidOCR did not activate CUDA: {providers}")
    processor = MMRProcessor(
        model_path=model_path,
        device=device,
        classifier=classifier,
        ocr_engine=MMROCREngine(ocr_engine=rapidocr),
    )

    matrix_pages = _load_matrix_pages(manifest)
    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    native_zero_failures: list[dict[str, Any]] = []

    for record in selected:
        page_id = str(record["page_id"])
        matrix_key = (str(record["score"]), str(record["page_name"]))
        matrix_page = matrix_pages.get(matrix_key)
        if matrix_page is None:
            raise RuntimeError(f"Full68 matrix lacks {page_id}: {matrix_key}")
        image_path = _resolve_project_path(str(matrix_page["image"]))
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(image_path)

        frozen = record["conditions"]["frozen_all"]
        native = record["conditions"]["native_all"]
        frozen_bbox = [int(value) for value in frozen["primary_measure_bbox"]]
        native_bbox = [int(value) for value in native["primary_measure_bbox"]]
        staff_bboxes = [[int(value) for value in bbox] for bbox in native["primary_staff_bboxes"]]
        width = native_bbox[2] - native_bbox[0]
        offsets = x1_offsets(width)
        expected = record["expected"]["candidate_native_geometry"]
        frozen_skip = record["classification"]["frozen_final_skip"]
        causal_native_skip = record["classification"]["native_final_skip"]

        sweep: list[dict[str, Any]] = []
        for item in offsets:
            bbox = list(native_bbox)
            bbox[0] += int(item["dx1"])
            result = _probe_primary(processor, image, bbox, staff_bboxes)
            result.update(item)
            result["expected_hit"] = result["skip"] == expected
            sweep.append(result)

        zero = next(item for item in sweep if abs(float(item["fraction"])) < 1e-12)
        zero_ok = zero["skip"] == causal_native_skip
        if not zero_ok:
            native_zero_failures.append(
                {
                    "page_id": page_id,
                    "key": record["key"],
                    "causal_native_skip": causal_native_skip,
                    "probed_native_primary_skip": zero["skip"],
                }
            )

        frozen_dx1 = frozen_bbox[0] - native_bbox[0]
        frozen_fraction = frozen_dx1 / width if width else 0.0
        image_name = f"{page_id}_key_{'_'.join(str(value) for value in record['key'])}_review.png"
        image_output = output_dir / image_name

        panels: list[np.ndarray] = []
        panels.append(
            _panel(
                _context_panel(image, frozen_bbox, native_bbox, staff_bboxes, offsets),
                f"{page_id} key={record['key']} expected={expected}",
            )
        )
        panels.append(
            _panel(
                _review_crop(
                    image, frozen_bbox, [list(bbox) for bbox in frozen["primary_staff_bboxes"]]
                ),
                f"frozen ref dx1={frozen_dx1:+d}px skip={frozen_skip}",
            )
        )
        for item in sweep:
            label = f"native x1 {item['fraction']:+.0%} ({item['dx1']:+d}px) skip={item['skip']}"
            panels.append(_panel(_review_crop(image, item["measure_bbox"], staff_bboxes), label))
        sheet = _contact_sheet(panels)
        if not cv2.imwrite(str(image_output), sheet):
            raise RuntimeError(f"Failed to write review image: {image_output}")

        records.append(
            {
                "page_id": page_id,
                "score": record["score"],
                "page_name": record["page_name"],
                "key": record["key"],
                "expected_skip": expected,
                "causal_frozen_skip": frozen_skip,
                "causal_native_skip": causal_native_skip,
                "frozen_reference": {
                    "primary_measure_bbox": frozen_bbox,
                    "dx1_from_native_px": frozen_dx1,
                    "dx1_from_native_fraction": frozen_fraction,
                },
                "native_reference": {
                    "primary_measure_bbox": native_bbox,
                    "primary_staff_bboxes": staff_bboxes,
                },
                "sweep": sweep,
                "expected_hit_fractions": [
                    item["fraction"] for item in sweep if item["expected_hit"]
                ],
                "distinct_valid_skips": sorted(
                    {int(item["skip"]) for item in sweep if item["skip"] is not None}
                ),
                "native_zero_matches_causal_native": zero_ok,
                "review_image": str(image_output),
            }
        )

    report = {
        "schema_version": "issue294.mapping_guarded_mmr_visual_stability_probe.v1",
        "status": "completed",
        "execution_contract": {
            "production_code_modified": False,
            "detector_reexecuted": False,
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_reexecuted": False,
            "full68_mmr_reexecuted": False,
            "focused_cnn_ocr_reexecuted": True,
            "candidate_native_relative_sweep": True,
            "frozen_A_used_only_as_reference": True,
            "visual_review_images_exported": True,
        },
        "runtime": {"device": str(device), "rapidocr_providers": providers},
        "sweep_contract": {
            "edge": "primary_measure_x1_only",
            "fractions_of_candidate_native_measure_width": list(SWEEP_FRACTIONS),
            "selection": "records causally attributable to primary measure geometry",
        },
        "records": records,
        "native_zero_failures": native_zero_failures,
        "gates": {
            "causal_matrix_reproduction_clean": True,
            "primary_measure_causal_record_count_nonzero": bool(records),
            "all_native_zero_primary_results_reproduced": not native_zero_failures,
        },
    }
    _write_json(output_json, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--full68-manifest",
        type=Path,
        default=PROJECT_ROOT / "logs/issue294/issue294_full68_refresh_02/full68_host.json",
    )
    parser.add_argument(
        "--causal-matrix",
        type=Path,
        default=PROJECT_ROOT
        / "logs/issue294/issue294_full68_refresh_02/mapping_guarded_mmr_causal_matrix_01.json",
    )
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT
        / "logs/issue294/issue294_full68_refresh_02/mmr_visual_stability_review_01",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=PROJECT_ROOT
        / "logs/issue294/issue294_full68_refresh_02/mapping_guarded_mmr_visual_stability_probe_01.json",
    )
    args = parser.parse_args()
    report = run(
        args.full68_manifest,
        args.causal_matrix,
        args.model,
        args.output_dir,
        args.output_json,
    )
    summary = {
        "status": report["status"],
        "record_count": len(report["records"]),
        "all_native_zero_primary_results_reproduced": report["gates"][
            "all_native_zero_primary_results_reproduced"
        ],
        "review_images": [record["review_image"] for record in report["records"]],
        "output": str(args.output_json),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if report["gates"]["all_native_zero_primary_results_reproduced"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
