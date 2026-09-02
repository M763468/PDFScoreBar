from __future__ import annotations

import json
from pathlib import Path

from tools.issue294.evaluate_existing_ab_against_gt import (
    DEFAULT_IOU_THRESHOLD,
    _resolve_gt,
    _summarize_variant,
)


def _write_detection(path: Path, boxes: list[tuple[int, int, int, int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "predictions": [
                    {
                        "pred_bbox": list(box),
                        "orig_bbox": list(box),
                        "system_index": 0,
                        "staff_index": 0,
                    }
                    for box in boxes
                ]
            }
        ),
        encoding="utf-8",
    )


def test_issue294_gt_resolver_prefers_unambiguous_historical_boxes_sorted(
    tmp_path: Path,
) -> None:
    image = tmp_path / "images" / "Score" / "page_013.png"
    gt_root = tmp_path / "annotations"
    gt = gt_root / "page_013" / "boxes_sorted.json"
    gt.parent.mkdir(parents=True)
    gt.write_text("[]\n", encoding="utf-8")

    path, mode = _resolve_gt(gt_root, image)

    assert path == gt.resolve()
    assert mode == "historical_explicit_mapping"


def test_issue294_gt_comparison_uses_issue255_barline_metric(tmp_path: Path) -> None:
    detection = tmp_path / "detections.json"
    _write_detection(
        detection,
        [
            (300, 100, 304, 300),
            (600, 100, 604, 300),
            (900, 100, 904, 300),
        ],
    )
    ground_truth = [
        (300, 100, 304, 300),
        (600, 100, 604, 300),
    ]

    result = _summarize_variant(detection, ground_truth, DEFAULT_IOU_THRESHOLD)

    assert result["gt"] == 2
    assert result["pred"] == 3
    assert result["tp"] == 2
    assert result["fp"] == 1
    assert result["fn"] == 0
    assert result["precision"] == 2 / 3
    assert result["recall"] == 1.0
    assert result["f1"] == 0.8
    assert result["matched_iou"]["mean"] == 1.0
