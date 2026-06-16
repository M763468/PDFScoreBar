from pathlib import Path

import numpy as np
import pytest

try:
    from src.measure_numbering.mmr import MMRProcessor
except ModuleNotFoundError as exc:  # pragma: no cover
    pytest.skip(f"MMR dependencies unavailable: {exc}", allow_module_level=True)


class VariantOCR:
    enable_rotation_tta = False

    def __init__(self):
        self.variant = None

    def mask_hbar_candidates(self, img, staff_top_rel, staff_height):
        return img

    def preprocess_variant(self, img, mode="standard", angle=0):
        self.variant = (mode, angle)
        return img

    def ocr_engine(self, proc_img):
        return [self.variant], None

    def select_best_candidate(self, ocr_res, img_width, img_height):
        if ocr_res[0] == ("standard", 0):
            return 5, 95.0, "standard"
        if ocr_res[0] == ("no_dilate", 0):
            return 15, 101.0, "no_dilate"
        return None, 0, ""


def test_detect_number_uses_best_scored_variant_not_first_valid_variant():
    processor = MMRProcessor(
        model_path=Path("unused.pth"),
        device=object(),
        classifier=object(),
        ocr_engine=VariantOCR(),
        threshold=0.5,
        rescue_threshold=0.1,
    )
    image = np.zeros((200, 200, 3), dtype=np.uint8)
    system = {"staves": [{"bbox": [0, 50, 200, 100]}]}

    num, score, debug = processor._detect_number(
        image=image,
        system=system,
        x1=20,
        y1=40,
        x2=120,
        y2=110,
        prob=0.99,
        w_img=200,
        h_img=200,
    )

    assert num == 15
    assert score == 101.0
    assert "variant=no_dilate:0" in debug
