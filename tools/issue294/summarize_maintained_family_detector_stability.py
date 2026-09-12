#!/usr/bin/env python3
"""Summarize retained B/C detector-material stability across Issue #294 full68.

Host-only retained-artifact diagnostic. No inference is executed.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.issue294.audit_full68_retained_semantics import _boxes, _normalise_boxes
from tools.issue294.rescore_full68_mmr_audit import _load_json, _load_matrix_pages, _resolve_project_path
from tools.issue294.run_post277_mapping_guarded_mmr import DEFAULT_MANIFEST


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mask_equal(left: Path, right: Path) -> tuple[bool, bool]:
    if _sha256(left) == _sha256(right):
        return True, True
    a = cv2.imread(str(left), cv2.IMREAD_GRAYSCALE)
    b = cv2.imread(str(right), cv2.IMREAD_GRAYSCALE)
    if a is None:
        raise FileNotFoundError(left)
    if b is None:
        raise FileNotFoundError(right)
    return False, bool(a.shape == b.shape and np.array_equal(a, b))


def run() -> dict[str, Any]:
    manifest = _load_json(DEFAULT_MANIFEST)
    pages = _load_matrix_pages(manifest)
    details: list[dict[str, Any]] = []
    for (score, page_name), page in sorted(pages.items()):
        native = page["modes"]["candidate_native_geometry"]["variants"]
        b = native["B_b377"]
        c = native["C_latest"]
        b_detection = _boxes(str(b["baseline_detection"]))
        c_detection = _boxes(str(c["baseline_detection"]))
        b_final = _normalise_boxes(b["final_barlines"])
        c_final = _normalise_boxes(c["final_barlines"])
        b_staff = _resolve_project_path(str(b["staff_mask"]))
        c_staff = _resolve_project_path(str(c["staff_mask"]))
        hash_equal, pixel_equal = _mask_equal(b_staff, c_staff)
        details.append(
            {
                "score": score,
                "page_name": page_name,
                "baseline_detection_multiset_exact": Counter(b_detection) == Counter(c_detection),
                "baseline_detection_ordered_exact": b_detection == c_detection,
                "staff_mask_sha256_exact": hash_equal,
                "staff_mask_pixel_exact": pixel_equal,
                "final_barlines_ordered_exact": b_final == c_final,
                "final_barlines_multiset_exact": Counter(b_final) == Counter(c_final),
            }
        )

    def _count(field: str) -> int:
        return sum(bool(item[field]) for item in details)

    return {
        "schema_version": "issue294.maintained_family_detector_stability.v1",
        "status": "completed",
        "manifest": str(DEFAULT_MANIFEST),
        "pages": len(details),
        "counts": {
            "baseline_detection_multiset_exact": _count("baseline_detection_multiset_exact"),
            "baseline_detection_ordered_exact": _count("baseline_detection_ordered_exact"),
            "staff_mask_sha256_exact": _count("staff_mask_sha256_exact"),
            "staff_mask_pixel_exact": _count("staff_mask_pixel_exact"),
            "final_barlines_ordered_exact": _count("final_barlines_ordered_exact"),
            "final_barlines_multiset_exact": _count("final_barlines_multiset_exact"),
        },
        "differences": {
            field: [f"{item['score']}/{item['page_name']}" for item in details if not item[field]]
            for field in (
                "baseline_detection_multiset_exact",
                "baseline_detection_ordered_exact",
                "staff_mask_sha256_exact",
                "staff_mask_pixel_exact",
                "final_barlines_ordered_exact",
                "final_barlines_multiset_exact",
            )
        },
    }


def main() -> int:
    try:
        print(json.dumps(run(), indent=2, ensure_ascii=False))
    except Exception as error:  # noqa: BLE001
        print(json.dumps({"status": "failed", "error_type": type(error).__name__, "error": str(error)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
