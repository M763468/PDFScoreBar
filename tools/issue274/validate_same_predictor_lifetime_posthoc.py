#!/usr/bin/env python3
"""Post-hoc validation for Issue #274 same-predictor lifetime experiment.

This validator performs no inference.  It corrects the comparison boundary in
``run_same_predictor_lifetime_equivalence.py`` by comparing retained pre-#265 x4
staff/notehead masks after the production coordinate normalization introduced by
PR #265, while keeping connector semantic masks in their native HOMR
segmentation-mask coordinates.

The input report must be a completed same-predictor experiment whose page-local
artifacts are still present on disk.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import cv2
import numpy as np

from src.common.connector_artifacts import connector_mask_paths


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_mask(path: Path) -> np.ndarray:
    mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise FileNotFoundError(path)
    return mask


def _mask_exact(left: Path, right: Path) -> dict[str, Any]:
    lhs = _load_mask(left)
    rhs = _load_mask(right)
    return {
        "left": str(left),
        "right": str(right),
        "left_shape": list(lhs.shape),
        "right_shape": list(rhs.shape),
        "left_sha256": _sha256(left),
        "right_sha256": _sha256(right),
        "shape_equal": lhs.shape == rhs.shape,
        "array_exact": bool(lhs.shape == rhs.shape and np.array_equal(lhs, rhs)),
        "binary_exact": bool(lhs.shape == rhs.shape and np.array_equal(lhs > 0, rhs > 0)),
    }


def _normalize_retained_x4_mask(retained: Path, shared: Path) -> dict[str, Any]:
    old = _load_mask(retained)
    new = _load_mask(shared)
    resized = cv2.resize(
        old,
        (int(new.shape[1]), int(new.shape[0])),
        interpolation=cv2.INTER_NEAREST,
    )
    raw_ratio = [
        float(old.shape[0]) / float(new.shape[0]),
        float(old.shape[1]) / float(new.shape[1]),
    ]
    return {
        "retained": str(retained),
        "shared": str(shared),
        "retained_shape": list(old.shape),
        "shared_shape": list(new.shape),
        "retained_over_shared_shape_ratio": raw_ratio,
        "normalization": "cv2.INTER_NEAREST retained-x4 -> shared/source-page size",
        "normalized_array_exact": bool(np.array_equal(resized, new)),
        "normalized_binary_exact": bool(np.array_equal(resized > 0, new > 0)),
        "normalized_different_pixels": int(np.count_nonzero(resized != new)),
        "normalized_different_binary_pixels": int(np.count_nonzero((resized > 0) != (new > 0))),
    }


def _path_from_comparison(block: Mapping[str, Any], side: str) -> Path:
    raw = block.get(side)
    if not isinstance(raw, str) or not raw:
        raise ValueError(f"Comparison lacks {side} path")
    path = Path(raw)
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _connector_compare(retained_detection: Path, shared_detection: Path) -> dict[str, Any]:
    retained_paths = connector_mask_paths(
        retained_detection.parent, retained_detection.stem.removesuffix("_detections")
    )
    shared_paths = connector_mask_paths(
        shared_detection.parent, shared_detection.stem.removesuffix("_detections")
    )
    result: dict[str, Any] = {}
    for key in ("symbols", "brace_dot"):
        left = retained_paths[key]
        right = shared_paths[key]
        if not left.is_file() or not right.is_file():
            result[key] = {
                "retained": str(left),
                "shared": str(right),
                "complete": False,
                "exact": False,
            }
            continue
        comparison = _mask_exact(left, right)
        comparison["complete"] = True
        comparison["exact"] = bool(comparison["array_exact"])
        result[key] = comparison
    result["complete"] = all(bool(result[key].get("complete")) for key in ("symbols", "brace_dot"))
    result["all_exact"] = all(bool(result[key].get("exact")) for key in ("symbols", "brace_dot"))
    result["coordinate_space"] = "homr_segmentation_mask"
    return result


def run(report_path: Path, output_path: Path) -> Path:
    source = _load_json(report_path)
    if not isinstance(source, Mapping) or source.get("status") != "completed":
        raise ValueError(f"Expected completed same-predictor report: {report_path}")
    pages = source.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("Same-predictor report has no pages")

    page_results: list[dict[str, Any]] = []
    for page in pages:
        if not isinstance(page, Mapping):
            raise ValueError("Invalid page result")
        comparisons = page.get("comparisons")
        if not isinstance(comparisons, Mapping):
            raise ValueError("Page lacks comparisons")
        original = comparisons["independent_original_vs_shared_original"]
        x4 = comparisons["retained_b_x4_vs_shared_after_original"]

        retained_det = _path_from_comparison(x4["detections"], "left")
        shared_det = _path_from_comparison(x4["detections"], "right")
        retained_staff = _path_from_comparison(x4["staff_mask"], "left")
        shared_staff = _path_from_comparison(x4["staff_mask"], "right")
        retained_note = _path_from_comparison(x4["notehead_mask"], "left")
        shared_note = _path_from_comparison(x4["notehead_mask"], "right")

        staff = _normalize_retained_x4_mask(retained_staff, shared_staff)
        notehead = _normalize_retained_x4_mask(retained_note, shared_note)
        connectors = _connector_compare(retained_det, shared_det)

        original_exact = bool(
            original["detections"]["exact_geometry_and_indices_equal"]
            and original["staff_mask"].get("array_exact")
            and original["notehead_mask"].get("array_exact")
        )
        x4_detection_exact = bool(x4["detections"]["exact_geometry_and_indices_equal"])
        normalized_x4_exact = bool(
            staff["normalized_array_exact"] and notehead["normalized_array_exact"]
        )
        page_pass = bool(
            original_exact
            and x4_detection_exact
            and normalized_x4_exact
            and connectors["all_exact"]
            and page.get("shared_predictor_lifetime", {}).get("same_object_for_both_calls") is True
        )
        page_results.append(
            {
                "canonical_page": page.get("canonical_page"),
                "score": page.get("score"),
                "page": page.get("page"),
                "original_artifacts_exact": original_exact,
                "x4_detection_exact": x4_detection_exact,
                "x4_staff_after_pr265_normalization": staff,
                "x4_notehead_after_pr265_normalization": notehead,
                "x4_connector_semantics": connectors,
                "same_predictor_object": page.get("shared_predictor_lifetime", {}).get(
                    "same_object_for_both_calls"
                ),
                "page_pass": page_pass,
            }
        )

    all_pass = all(bool(page["page_pass"]) for page in page_results)
    payload = {
        "schema_version": "issue274.same_predictor_lifetime_posthoc.v1",
        "status": "completed",
        "source_report": str(report_path),
        "decision": (
            "same_predictor_lifetime_equivalent_under_current_artifact_contract"
            if all_pass
            else "same_predictor_lifetime_requires_further_investigation"
        ),
        "inference_reexecuted": False,
        "contract_interpretation": {
            "retained_b_origin": "pre-PR265 x4-space staff/notehead masks",
            "current_contract": "source-page staff/notehead masks via nearest-neighbor normalization",
            "connector_contract": "symbols/brace_dot remain in HOMR segmentation-mask coordinates",
        },
        "summary": {
            "pages": len(page_results),
            "pass_pages": sum(1 for page in page_results if page["page_pass"]),
            "original_exact_pages": sum(
                1 for page in page_results if page["original_artifacts_exact"]
            ),
            "x4_detection_exact_pages": sum(
                1 for page in page_results if page["x4_detection_exact"]
            ),
            "x4_normalized_staff_exact_pages": sum(
                1
                for page in page_results
                if page["x4_staff_after_pr265_normalization"]["normalized_array_exact"]
            ),
            "x4_normalized_notehead_exact_pages": sum(
                1
                for page in page_results
                if page["x4_notehead_after_pr265_normalization"]["normalized_array_exact"]
            ),
            "x4_connector_exact_pages": sum(
                1 for page in page_results if page["x4_connector_semantics"]["all_exact"]
            ),
        },
        "pages": page_results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        type=Path,
        default=Path(
            "logs/issue274_homr_unification_analysis/same_predictor_lifetime_02/"
            "issue274_same_predictor_lifetime_equivalence.json"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "logs/issue274_homr_unification_analysis/same_predictor_lifetime_02/"
            "issue274_same_predictor_lifetime_posthoc.json"
        ),
    )
    args = parser.parse_args()
    try:
        path = run(args.report.resolve(), args.output.resolve())
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1
    payload = _load_json(path)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "decision": payload["decision"],
                "summary": payload["summary"],
                "output": str(path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
