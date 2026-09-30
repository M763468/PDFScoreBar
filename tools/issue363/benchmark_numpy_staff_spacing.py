"""Compare the NumPy-only staff-spacing estimator on retained staff masks."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import time
from pathlib import Path

import numpy as np
from PIL import Image

from src.measure_numbering.pipeline import StaffExtractor


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("masks", nargs="+", type=Path)
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--repeats", type=int, default=100)
    args = parser.parse_args()
    if args.warmups < 0 or args.repeats < 1:
        parser.error("--warmups must be >= 0 and --repeats must be >= 1")

    extractor = StaffExtractor()
    results = []
    for path in args.masks:
        raw = np.asarray(Image.open(path).convert("L"))
        binary = np.where(raw > 127, 255, 0).astype(np.uint8)
        signature = hashlib.sha256(binary.tobytes()).hexdigest()
        expected = None

        def estimate():
            nonlocal expected
            actual = extractor._estimate_unit_size(binary, scale_y=1.0)
            if expected is None:
                expected = actual
            elif actual != expected:
                raise RuntimeError(f"estimate changed across repetitions for {path}")
            return actual

        for _ in range(args.warmups):
            estimate()
        samples = []
        for _ in range(args.repeats):
            start = time.perf_counter()
            estimate()
            samples.append((time.perf_counter() - start) * 1000)

        results.append(
            {
                "path": str(path.resolve()),
                "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "array_sha256": signature,
                "shape_hw": list(binary.shape),
                "unit_size": expected,
                "median_ms": statistics.median(samples),
                "min_ms": min(samples),
                "max_ms": max(samples),
                "samples_ms": samples,
            }
        )

    print(
        json.dumps(
            {
                "runtime": {"python": platform.python_version(), "numpy": np.__version__},
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
