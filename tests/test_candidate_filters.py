from pathlib import Path
from unittest import mock
import numpy as np
import cv2
from src.pipeline.steps.candidate_filters import filter_probe_candidates, trim_box_to_ink

def test_filter_probe_candidates_basic():
    image = np.zeros((100, 100), dtype=np.uint8)
    image.fill(255)
    candidates = [(20, 10, 25, 50), (5, 10, 10, 50)]
    for (x1, y1, x2, y2) in candidates:
        image[y1:y2, x1:x2] = 0
    existing = [(50, 10, 55, 50)]
    keep, dropped = filter_probe_candidates(candidates, image, existing, left_margin_ratio=0.12)
    assert len(keep) == 1
    assert keep[0] == (20, 10, 25, 50)

def test_trim_box_to_ink():
    image = np.zeros((100, 100), dtype=np.uint8)
    image.fill(255)
    # Draw a 20px tall line in a 40px box
    image[40:60, 20:25] = 0
    box = (20, 30, 25, 70)
    trimmed = trim_box_to_ink(image, box, ink_threshold=180, min_ink_ratio=0.1)
    assert trimmed[1] == 40
    assert trimmed[3] == 60
