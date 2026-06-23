from pathlib import Path

import numpy as np
import torch

from src.measure_numbering.mmr import MMROCREngine, MMRProcessor


def _box(x1, y1, x2, y2):
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def test_collect_one_bar_evidence_keeps_single_one_and_ignores_eleven():
    ocr = MMROCREngine(ocr_engine=object())
    ocr_result = [
        [_box(0, 0, 10, 20), "1", 0.99],
        [_box(100, 0, 120, 20), "(1.", 0.82],
        [_box(300, 0, 340, 20), "11.", 0.70],
        [_box(500, 0, 520, 20), "B", 0.90],
    ]

    evidence = ocr.collect_one_bar_evidence(ocr_result)

    assert [item["text"] for item in evidence] == ["1", "(1."]
    assert [item["source"] for item in evidence] == ["raw", "raw"]


def test_collect_one_bar_evidence_ignores_one_merged_into_multidigit():
    ocr = MMROCREngine(ocr_engine=object())
    ocr_result = [
        [_box(0, 0, 10, 20), "1", 0.99],
        [_box(15, 0, 25, 20), "5", 0.98],
    ]

    assert ocr.collect_one_bar_evidence(ocr_result) == []


def test_count_one_bar_evidence_is_compatible_with_minimal_injected_ocr():
    class MinimalOCR:
        pass

    processor = MMRProcessor(
        model_path=Path("unused"),
        device=torch.device("cpu"),
        classifier=object(),
        ocr_engine=MinimalOCR(),
    )

    assert processor._count_high_confidence_one_bar_evidence([]) == 0


class OneEvidencePerVariantOCR:
    enable_rotation_tta = False

    def __init__(self):
        self.variant = None

    def mask_hbar_candidates(self, img, staff_top_rel, staff_height):
        return img

    def preprocess_variant(self, img, mode="standard", angle=0):
        self.variant = (mode, angle)
        return img

    def ocr_engine(self, proc_img):
        return [
            [_box(0, 0, 10, 20), "1", 0.99],
            [_box(300, 0, 340, 20), "11.", 0.70],
        ], None

    def collect_one_bar_evidence(self, ocr_result):
        return MMROCREngine(ocr_engine=object()).collect_one_bar_evidence(ocr_result)

    def select_best_candidate(self, ocr_res, img_width, img_height):
        return 11, -1.0, f"variant={self.variant}"


def test_detect_number_preserves_three_value_contract():
    processor = MMRProcessor(
        model_path=Path("unused"),
        device=torch.device("cpu"),
        classifier=object(),
        ocr_engine=OneEvidencePerVariantOCR(),
    )
    image = np.zeros((200, 200, 3), dtype=np.uint8)
    system = {"staves": [{"bbox": [0, 50, 200, 100]}]}

    result = processor._detect_number(
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

    assert result == (11, -1.0, "variant=('standard', 0),variant=standard:0")


def test_detect_number_uses_max_one_bar_evidence_across_variants_not_sum():
    processor = MMRProcessor(
        model_path=Path("unused"),
        device=torch.device("cpu"),
        classifier=object(),
        ocr_engine=OneEvidencePerVariantOCR(),
    )
    image = np.zeros((200, 200, 3), dtype=np.uint8)
    system = {"staves": [{"bbox": [0, 50, 200, 100]}]}

    found_num, final_score, _debug, one_bar_evidence_count = processor._detect_number_with_evidence(
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

    assert found_num == 11
    assert final_score == -1.0
    assert one_bar_evidence_count == 1


def test_one_bar_veto_targets_marginal_cnn_negative_ocr_score_only():
    processor = MMRProcessor(
        model_path=Path("unused"),
        device=torch.device("cpu"),
        classifier=object(),
        ocr_engine=MMROCREngine(ocr_engine=object()),
    )

    assert processor._should_veto_one_bar_rest(
        found_num=11,
        prob=0.5410270690917969,
        final_score=-27.44786803610333,
        one_bar_evidence_count=2,
    )
    assert not processor._should_veto_one_bar_rest(
        found_num=11,
        prob=0.999,
        final_score=-27.44786803610333,
        one_bar_evidence_count=2,
    )
    assert not processor._should_veto_one_bar_rest(
        found_num=11,
        prob=0.5410270690917969,
        final_score=0.1,
        one_bar_evidence_count=2,
    )
    assert not processor._should_veto_one_bar_rest(
        found_num=11,
        prob=0.5410270690917969,
        final_score=-27.44786803610333,
        one_bar_evidence_count=1,
    )
    assert not processor._should_veto_one_bar_rest(
        found_num=None,
        prob=0.5410270690917969,
        final_score=-27.44786803610333,
        one_bar_evidence_count=2,
    )
