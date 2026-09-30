"""Compare scipy.ndimage.label on retained full-resolution binary masks."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import time
from pathlib import Path

import numpy as np
import scipy
from PIL import Image
from scipy import ndimage


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("masks", nargs="+", type=Path)
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--repeats", type=int, default=15)
    args = parser.parse_args()
    if args.warmups < 0 or args.repeats < 1:
        parser.error("--warmups must be >= 0 and --repeats must be >= 1")

    results = []
    for path in args.masks:
        raw = np.asarray(Image.open(path).convert("L"))
        binary = (raw > 127).astype(np.uint8)
        expected = None

        def label():
            nonlocal expected
            labels, count = ndimage.label(binary)
            signature = hashlib.sha256(labels.tobytes()).hexdigest()
            actual = (int(count), str(labels.dtype), signature)
            if expected is None:
                expected = actual
            elif actual != expected:
                raise RuntimeError(f"label output changed across repetitions for {path}")
            return actual

        for _ in range(args.warmups):
            label()
        samples = []
        for _ in range(args.repeats):
            start = time.perf_counter()
            label()
            samples.append((time.perf_counter() - start) * 1000)

        results.append(
            {
                "path": str(path.resolve()),
                "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "shape_hw": list(binary.shape),
                "foreground_fraction": float(binary.mean()),
                "components": expected[0],
                "label_dtype": expected[1],
                "label_sha256": expected[2],
                "median_ms": statistics.median(samples),
                "min_ms": min(samples),
                "max_ms": max(samples),
                "samples_ms": samples,
            }
        )

    print(
        json.dumps(
            {
                "runtime": {
                    "python": platform.python_version(),
                    "numpy": np.__version__,
                    "scipy": scipy.__version__,
                },
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
