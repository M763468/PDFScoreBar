"""Compare OpenCV component bounding boxes with contour-derived bounding boxes.

Run this once in each immutable runtime image against the same retained staff
mask corpus. The script deduplicates byte-identical masks and compares the
post-morphology boxes used by StaffExtractor without touching production code.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from pathlib import Path

import cv2
import numpy as np


def staff_boxes(binary: np.ndarray, method: str) -> list[list[int]]:
    if method == "connected_components":
        count, _, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
        rows = [(None, tuple(map(int, stats[i, :4]))) for i in range(1, count)]
    else:
        contours, hierarchy = cv2.findContours(binary, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        rows = []
        if hierarchy is not None:
            for contour, node in zip(contours, hierarchy[0]):
                if node[3] != -1:
                    continue
                points = contour.reshape(-1, 2)
                top_y = int(points[:, 1].min())
                top_row_left = int(points[points[:, 1] == top_y, 0].min())
                rows.append(((top_y, top_row_left), tuple(map(int, cv2.boundingRect(contour)))))
    height, width = binary.shape
    accepted = [
        (order_key, [x, y, x + box_width, y + box_height])
        for order_key, (x, y, box_width, box_height) in rows
        if box_height >= 10 and box_width > width * 0.1
    ]
    # CCL labels are created in top-to-bottom, left-to-right pixel scan order;
    # StaffExtractor then uses a stable y-only sort. The contour path restores
    # that tie ordering using the leftmost foreground pixel on each top row.
    if method == "connected_components":
        return [box for _, box in sorted(accepted, key=lambda row: row[1][1])]
    return [box for _, box in sorted(accepted, key=lambda row: row[0])]


def read_unique_masks(paths: list[Path]) -> list[tuple[str, Path, list[str]]]:
    unique: dict[str, tuple[Path, list[str]]] = {}
    for path in paths:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest not in unique:
            unique[digest] = (path, [])
        unique[digest][1].append(str(path))
    return [(digest, path, aliases) for digest, (path, aliases) in unique.items()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus", type=Path, help="directory containing retained *_staff_mask.png files")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = sorted(args.corpus.rglob("*_staff_mask.png"))
    if not paths:
        parser.error(f"no staff masks found under {args.corpus}")

    results = []
    mismatches = []
    unreadable = []
    component_times = []
    contour_times = []
    for digest, path, aliases in read_unique_masks(paths):
        mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if mask is None:
            unreadable.append({"sha256": digest, "path": str(path), "aliases": aliases})
            continue
        _, binary = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
        processed = cv2.dilate(binary, np.ones((20, 1), np.uint8), iterations=1)
        processed = cv2.morphologyEx(processed, cv2.MORPH_CLOSE, np.ones((1, 50), np.uint8))

        started = time.perf_counter()
        expected = staff_boxes(processed, "connected_components")
        component_ms = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        actual = staff_boxes(processed, "contours")
        contour_ms = (time.perf_counter() - started) * 1000
        component_times.append(component_ms)
        contour_times.append(contour_ms)
        row = {
            "sha256": digest,
            "shape": list(mask.shape),
            "aliases": aliases,
            "component_count": len(expected),
            "contour_count": len(actual),
            "bbox_equal": expected == actual,
            "connected_components_bbox_sha256": hashlib.sha256(
                json.dumps(expected, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "find_contours_bbox_sha256": hashlib.sha256(
                json.dumps(actual, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "connected_components_ms": component_ms,
            "find_contours_ms": contour_ms,
        }
        results.append(row)
        if expected != actual:
            mismatches.append({"sha256": digest, "path": str(path), "expected": expected, "actual": actual})

    payload = {
        "opencv": cv2.__version__,
        "numpy": np.__version__,
        "corpus": str(args.corpus),
        "path_count": len(paths),
        "unique_mask_count": len(results),
        "unreadable_count": len(unreadable),
        "mismatch_count": len(mismatches),
        "connected_components_total_ms": sum(component_times),
        "find_contours_total_ms": sum(contour_times),
        "connected_components_median_ms": statistics.median(component_times),
        "find_contours_median_ms": statistics.median(contour_times),
        "mismatches": mismatches,
        "unreadable": unreadable,
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in (
        "opencv", "numpy", "path_count", "unique_mask_count", "mismatch_count",
        "unreadable_count",
        "connected_components_total_ms", "find_contours_total_ms",
        "connected_components_median_ms", "find_contours_median_ms",
    )}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
