from pathlib import Path

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
