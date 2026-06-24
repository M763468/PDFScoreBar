from pathlib import Path

import numpy as np
import torch

from src.measure_numbering.mmr import MMROCREngine, MMRProcessor


def _box(x1, y1, x2, y2):
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


class MaskedEmptyUnmaskedNumberOCR:
    enable_rotation_tta = False

    def mask_hbar_candidates(self, img, staff_top_rel, staff_height):
        masked = img.copy()
        masked[:] = 255
        return masked

    def preprocess_variant(self, img, mode="standard", angle=0):
        return img

    def ocr_engine(self, proc_img):
        if int(proc_img[0, 0, 0]) == 255:
            return [], None
        return [[_box(45, 45, 95, 125), "3", 0.99]], None

    def collect_one_bar_evidence(self, ocr_result):
        return MMROCREngine(ocr_engine=object()).collect_one_bar_evidence(ocr_result)

    def select_best_candidate(self, ocr_res, img_width, img_height):
        return MMROCREngine(ocr_engine=object()).select_best_candidate(
            ocr_res, img_width, img_height
        )


class MaskedNumberUnmaskedDifferentNumberOCR:
    enable_rotation_tta = False

    def mask_hbar_candidates(self, img, staff_top_rel, staff_height):
        masked = img.copy()
        masked[:] = 255
        return masked

    def preprocess_variant(self, img, mode="standard", angle=0):
        return img

    def ocr_engine(self, proc_img):
        if int(proc_img[0, 0, 0]) == 255:
            return [[_box(45, 45, 95, 125), "3", 0.99]], None
        return [[_box(45, 45, 95, 125), "4", 0.99]], None

    def collect_one_bar_evidence(self, ocr_result):
        return MMROCREngine(ocr_engine=object()).collect_one_bar_evidence(ocr_result)

    def select_best_candidate(self, ocr_res, img_width, img_height):
        return MMROCREngine(ocr_engine=object()).select_best_candidate(
            ocr_res, img_width, img_height
        )


class MaskedEmptyUnmaskedLowScoreOCR(MaskedEmptyUnmaskedNumberOCR):
    def ocr_engine(self, proc_img):
        if int(proc_img[0, 0, 0]) == 255:
            return [], None
        return [[_box(0, 0, 10, 10), "9", 0.99]], None


def _processor(ocr_engine):
    return MMRProcessor(
        model_path=Path("unused"),
        device=torch.device("cpu"),
        classifier=object(),
        ocr_engine=ocr_engine,
    )


def test_unmasked_current_crop_fallback_recovers_number_when_masked_has_no_candidate():
    processor = _processor(MaskedEmptyUnmaskedNumberOCR())
    image = np.zeros((220, 220, 3), dtype=np.uint8)
    system = {"staves": [{"bbox": [0, 40, 200, 140]}]}

    found_num, score, debug, one_bar_evidence_count = processor._detect_number_with_evidence(
        image=image,
        system=system,
        x1=20,
        y1=50,
        x2=140,
        y2=130,
        prob=0.99,
        w_img=220,
        h_img=220,
    )

    assert found_num == 3
    assert score > 0
    assert "unmasked_fallback_standard" in debug
    assert one_bar_evidence_count == 0


def test_unmasked_fallback_is_not_used_when_masked_path_has_candidate():
    processor = _processor(MaskedNumberUnmaskedDifferentNumberOCR())
    image = np.zeros((220, 220, 3), dtype=np.uint8)
    system = {"staves": [{"bbox": [0, 40, 200, 140]}]}

    found_num, _score, debug, _one_bar_evidence_count = processor._detect_number_with_evidence(
        image=image,
        system=system,
        x1=20,
        y1=50,
        x2=140,
        y2=130,
        prob=0.99,
        w_img=220,
        h_img=220,
    )

    assert found_num == 3
    assert "unmasked_fallback_standard" not in debug


def test_unmasked_fallback_rejects_non_positive_score_candidate():
    processor = _processor(MaskedEmptyUnmaskedLowScoreOCR())
    image = np.zeros((220, 220, 3), dtype=np.uint8)
    system = {"staves": [{"bbox": [0, 40, 200, 140]}]}

    found_num, score, debug, _one_bar_evidence_count = processor._detect_number_with_evidence(
        image=image,
        system=system,
        x1=20,
        y1=50,
        x2=140,
        y2=130,
        prob=0.99,
        w_img=220,
        h_img=220,
    )

    assert found_num is None
    assert score == 0
    assert debug == ""


class CurrentEmptyLeftWideNumberOCR:
    enable_rotation_tta = False

    def mask_hbar_candidates(self, img, staff_top_rel, staff_height):
        masked = img.copy()
        masked[:] = 255
        return masked

    def preprocess_variant(self, img, mode="standard", angle=0):
        return img

    def ocr_engine(self, proc_img):
        h, w = proc_img.shape[:2]
        if int(proc_img[0, 0, 0]) == 255:
            return [], None
        if w < 300:
            return [], None
        return [[_box(w * 0.45, h * 0.25, w * 0.55, h * 0.45), "S3", 0.99]], None

    def collect_one_bar_evidence(self, ocr_result):
        return MMROCREngine(ocr_engine=object()).collect_one_bar_evidence(ocr_result)

    def select_best_candidate(self, ocr_res, img_width, img_height):
        return MMROCREngine(ocr_engine=object()).select_best_candidate(
            ocr_res, img_width, img_height
        )


class CurrentEmptyLeftWideLowScoreOCR(CurrentEmptyLeftWideNumberOCR):
    def ocr_engine(self, proc_img):
        h, w = proc_img.shape[:2]
        if int(proc_img[0, 0, 0]) == 255:
            return [], None
        if w < 300:
            return [], None
        return [[_box(w * 0.90, h * 0.05, w * 0.98, h * 0.20), "31", 0.99]], None


def test_left_wide_unmasked_fallback_recovers_positive_score_candidate():
    processor = _processor(CurrentEmptyLeftWideNumberOCR())
    image = np.zeros((260, 420, 3), dtype=np.uint8)
    system = {"staves": [{"bbox": [0, 50, 400, 160]}]}

    found_num, score, debug, _one_bar_evidence_count = processor._detect_number_with_evidence(
        image=image,
        system=system,
        x1=180,
        y1=70,
        x2=300,
        y2=150,
        prob=0.99,
        w_img=420,
        h_img=260,
    )

    assert found_num == 3
    assert score > 0
    assert "left_wide_unmasked_fallback_standard" in debug


def test_left_wide_unmasked_fallback_rejects_negative_score_candidate():
    processor = _processor(CurrentEmptyLeftWideLowScoreOCR())
    image = np.zeros((260, 420, 3), dtype=np.uint8)
    system = {"staves": [{"bbox": [0, 50, 400, 160]}]}

    found_num, score, debug, _one_bar_evidence_count = processor._detect_number_with_evidence(
        image=image,
        system=system,
        x1=180,
        y1=70,
        x2=300,
        y2=150,
        prob=0.99,
        w_img=420,
        h_img=260,
    )

    assert found_num is None
    assert score == 0
    assert debug == ""
