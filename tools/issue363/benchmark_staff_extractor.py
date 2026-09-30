"""Measure staff-mask extraction against retained production mask inputs.

Run this file from the repository root under each runtime being compared. It only reads
the input masks and emits JSON to stdout; callers should retain that output under
logs/issue363/.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import statistics
import time
from pathlib import Path

import cv2
import numpy as np

from src.measure_numbering.pipeline import StaffExtractor


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("masks", nargs="+", type=Path)
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--repeats", type=int, default=15)
    args = parser.parse_args()
    if args.warmups < 0 or args.repeats < 1:
        parser.error("--warmups must be >= 0 and --repeats must be >= 1")

    result = {
        "runtime": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "opencv": cv2.__version__,
            "scipy": importlib.metadata.version("scipy"),
            "scikit_learn": importlib.metadata.version("scikit-learn"),
        },
        "warmups": args.warmups,
        "repeats": args.repeats,
        "masks": [],
    }

    extractor = StaffExtractor()
    operations = (
        "dilate",
        "morphologyEx",
        "findContours",
    )
    original_operations = {name: getattr(cv2, name) for name in operations}
    operation_times: dict[str, list[float]] = {name: [] for name in operations}
    current_operation_times: dict[str, float] = {}

    for operation_name, original in original_operations.items():

        def timed_operation(*op_args, _name=operation_name, _original=original, **op_kwargs):
            start = time.perf_counter()
            try:
                return _original(*op_args, **op_kwargs)
            finally:
                current_operation_times[_name] = (
                    current_operation_times.get(_name, 0.0) + (time.perf_counter() - start) * 1000
                )

        setattr(cv2, operation_name, timed_operation)

    for path in args.masks:
        resolved = path.resolve()
        image = cv2.imread(str(resolved), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise FileNotFoundError(resolved)
        digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
        target_size = (image.shape[1], image.shape[0])
        expected = None

        def extract():
            staves = extractor.extract(resolved, target_size)
            return [
                [staff.bbox.x1, staff.bbox.y1, staff.bbox.x2, staff.bbox.y2] for staff in staves
            ]

        for _ in range(args.warmups):
            current_operation_times.clear()
            expected = extract()
        samples = []
        for _ in range(args.repeats):
            current_operation_times.clear()
            start = time.perf_counter()
            actual = extract()
            samples.append((time.perf_counter() - start) * 1000)
            for operation_name in operations:
                operation_times[operation_name].append(
                    current_operation_times.get(operation_name, 0.0)
                )
            if expected is None:
                expected = actual
            elif actual != expected:
                raise RuntimeError(f"non-deterministic extraction result for {resolved}")

        result["masks"].append(
            {
                "path": str(resolved),
                "sha256": digest,
                "shape_hw": list(image.shape),
                "dtype": str(image.dtype),
                "staves": expected,
                "median_ms": statistics.median(samples),
                "min_ms": min(samples),
                "max_ms": max(samples),
                "samples_ms": samples,
                "operation_medians_ms": {
                    name: statistics.median(operation_times[name][-args.repeats :])
                    for name in operations
                },
                "operation_samples_ms": {
                    name: operation_times[name][-args.repeats :] for name in operations
                },
            }
        )

    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
