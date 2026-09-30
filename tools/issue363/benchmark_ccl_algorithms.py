"""Compare OpenCV connected-component algorithms on retained staff masks."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from pathlib import Path

import cv2
import numpy as np


def boxes_for(binary: np.ndarray, algorithm: int | None) -> list[list[int]]:
    if algorithm == "findContours":
        contours, hierarchy = cv2.findContours(binary, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        raw_boxes = (
            []
            if hierarchy is None
            else [
                cv2.boundingRect(contour)
                for contour, node in zip(contours, hierarchy[0])
                if node[3] == -1
            ]
        )
    else:
        if algorithm is None:
            count, _, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
        else:
            count, _, stats, _ = cv2.connectedComponentsWithStatsWithAlgorithm(
                binary, 8, cv2.CV_32S, algorithm
            )
        raw_boxes = [tuple(map(int, stats[i, :4])) for i in range(1, count)]
    h, w = binary.shape
    boxes = []
    for x, y, bw, bh in raw_boxes:
        if bh >= 10 and bw > w * 0.1:
            boxes.append([x, y, x + bw, y + bh])
    return sorted(boxes, key=lambda box: box[1])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("masks", nargs="+", type=Path)
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--repeats", type=int, default=15)
    parser.add_argument(
        "--algorithms", default=None, help="comma-separated subset of algorithm names"
    )
    args = parser.parse_args()
    if args.warmups < 0 or args.repeats < 1:
        parser.error("--warmups must be >= 0 and --repeats must be >= 1")

    algorithms = {"default": None}
    for name in ("CCL_WU", "CCL_GRANA", "CCL_BOLELLI", "CCL_SAUF", "CCL_BBDT", "CCL_SPAGHETTI"):
        value = getattr(cv2, name, None)
        if value is not None:
            algorithms[name] = int(value)
    algorithms["findContours"] = "findContours"
    if args.algorithms:
        requested = args.algorithms.split(",")
        unknown = set(requested) - algorithms.keys()
        if unknown:
            parser.error(f"unknown algorithms: {sorted(unknown)}")
        algorithms = {name: algorithms[name] for name in requested}
    results = []
    for path in args.masks:
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise FileNotFoundError(path)
        _, binary = cv2.threshold(image, 127, 255, cv2.THRESH_BINARY)
        binary = cv2.morphologyEx(
            cv2.dilate(binary, np.ones((20, 1), np.uint8)),
            cv2.MORPH_CLOSE,
            np.ones((1, 50), np.uint8),
        )
        baseline = boxes_for(binary, None)
        row = {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "shape": list(image.shape),
            "algorithms": {},
        }
        for name, algorithm in algorithms.items():
            expected = boxes_for(binary, algorithm)
            for _ in range(args.warmups):
                expected = boxes_for(binary, algorithm)
            samples = []
            for _ in range(args.repeats):
                started = time.perf_counter()
                actual = boxes_for(binary, algorithm)
                samples.append((time.perf_counter() - started) * 1000)
                if actual != expected:
                    raise RuntimeError(f"non-deterministic bbox output: {name} {path}")
            row["algorithms"][name] = {
                "algorithm_id": algorithm,
                "bbox_match_default": expected == baseline,
                "bbox_count": len(expected),
                "median_ms": statistics.median(samples),
                "samples_ms": samples,
            }
        results.append(row)
    print(
        json.dumps(
            {
                "opencv": cv2.__version__,
                "numpy": np.__version__,
                "warmups": args.warmups,
                "repeats": args.repeats,
                "masks": results,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
