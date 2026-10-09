"""Generate the original, synthetic 3div./4div. score excerpts for Issue #218.

Run from any directory with: python3 tests/fixtures/system_grouping/generate_issue218.py
No score scans, model output, fonts, or external assets are required.
"""

import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent


def generate(staff_count):
    # One close pair and one rescue-distance pair in each divisi chain.
    gaps = [72, 123] + ([72] if staff_count == 4 else []) + [72]
    tops = [100]
    for gap in gaps:
        tops.append(tops[-1] + 80 + gap)
    width, height = 600, tops[-1] + 180
    staff_mask = np.zeros((height, width), dtype=np.uint8)
    symbols = np.zeros_like(staff_mask)
    image = np.full_like(staff_mask, 255)
    cv2.putText(image, f"{staff_count}div. - synthetic excerpt", (100, 50), 0, 0.7, 0, 1)
    boxes = []
    staves = []
    for top in tops:
        staves.append({"bbox": [100, top, 502, top + 80], "unit_size": 20})
        for offset in (0, 20, 40, 60, 80):
            staff_mask[top + offset : top + offset + 1, 100:502] = 255
        for x in (100, 300, 500):
            boxes.append([x, top, x + 2, top + 80])
            image[top : top + 81, x : x + 2] = 0
        # Simple quarter notes in the two measures; only the connector is in
        # the semantic symbols mask, so note ink cannot predetermine grouping.
        for x in (170, 370):
            cv2.ellipse(image, (x, top + 60), (9, 6), -20, 0, 360, 0, -1)
            image[top + 20 : top + 61, x + 7 : x + 9] = 0

    for index in range(staff_count - 1):
        # Broad left/system-start connector: survives the default density gate.
        symbols[tops[index] + 80 : tops[index + 1], 100:112] = 255

    # Deliberate non-left ink bridge to the independent following system.
    # It is aligned with a barline and challenges the false-merge guard, but
    # is outside the extractor's left/system-start ROI.
    image[tops[-2] + 80 : tops[-1], 500:502] = 0
    cv2.putText(image, "independent system", (100, tops[-1] - 20), 0, 0.5, 0, 1)
    image[staff_mask > 0] = 0
    image[symbols > 0] = 0

    stem = f"issue218_{staff_count}div"
    for suffix, pixels in (("score", image), ("staff", staff_mask), ("symbols", symbols)):
        if not cv2.imwrite(str(ROOT / f"{stem}_{suffix}.png"), pixels):
            raise RuntimeError(f"Could not write {stem}_{suffix}.png")

    fixture = {
        "provenance": "Original synthetic score excerpt for Issue #218; no model inference",
        "image_size": [width, height],
        "staves": staves,
        "barlines": boxes,
        "expected_connector_presence": [True] * (staff_count - 1) + [False],
        "expected_systems": [list(range(staff_count)), [staff_count]],
        "expected_measure_numbers": [[1, 2], [3, 4]],
    }
    (ROOT / f"{stem}.json").write_text(json.dumps(fixture, indent=2) + "\n")


if __name__ == "__main__":
    for count in (3, 4):
        generate(count)
