
# [EXPERIMENTAL] Temporary debug script to check mask dimensions and values.
# Created on 2026-01-04.

import cv2
import numpy as np
from pathlib import Path

path = Path("data/training/images/page_10.png")
if not path.exists():
    print(f"Path does not exist: {path}")
else:
    img = cv2.imread(str(path))
    if img is None:
        print("Failed to read image")
    else:
        print(f"Shape: {img.shape}")
