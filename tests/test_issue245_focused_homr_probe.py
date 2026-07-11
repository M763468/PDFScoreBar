from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from tools.issue245.run_focused_homr_probe import (
    detection_path,
    normalize_box,
    tolerant_match_count,
    vertical_overlap_ratio,
)
from tools.issue245.run_homr_evaluator_compat import install_download_weights_compat
from tools.issue245.run_page001_homr_probe import resolve_handoff_image


def test_normalize_box_rounds_numeric_coordinates() -> None:
    assert normalize_box([1.2, 2.6, 3.4, 4.8]) == (1, 3, 3, 5)
    assert normalize_box([1, 2, 3]) is None
    assert normalize_box([1, 2, "bad", 4]) is None


def test_vertical_overlap_ratio_uses_shorter_box_height() -> None:
    assert vertical_overlap_ratio((0, 10, 2, 30), (0, 20, 2, 40)) == 0.5
    assert vertical_overlap_ratio((0, 10, 2, 20), (0, 21, 2, 30)) == 0.0


def test_tolerant_match_count_is_one_to_one() -> None:
    historical = [(10, 0, 12, 100), (30, 0, 32, 100)]
    current = [(11, 0, 13, 100), (12, 0, 14, 100), (31, 0, 33, 100)]

    assert tolerant_match_count(historical, current) == 2


def test_tolerant_match_count_rejects_large_x_distance_or_low_overlap() -> None:
    historical = [(10, 0, 12, 100)]

    assert tolerant_match_count(historical, [(23, 0, 25, 100)]) == 0
    assert tolerant_match_count(historical, [(11, 80, 13, 180)]) == 0


def test_detection_path_matches_each_route_layout() -> None:
    root = Path("logs/issue245")
    image = Path("data/evaluation2/images/Score/page_001.png")

    assert detection_path(root, "run", image, in_process=True) == (
        root / "run/baseline/batch/page_001/page_001_detections.json"
    )
    assert detection_path(root, "run", image, in_process=False) == (
        root / "run/page_001/page_001_detections.json"
    )


def test_resolve_handoff_image_uses_path_relative_to_handoff(tmp_path: Path) -> None:
    review_root = tmp_path / "review"
    image = review_root / "pages/page_001/source.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"png")
    handoff = review_root / "manual_correction_input.json"
    handoff.write_text(
        json.dumps(
            {
                "pages": [
                    {
                        "page_id": "page_001",
                        "source_image": "pages/page_001/source.png",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert resolve_handoff_image(handoff, "page_001") == image.resolve()


def test_install_download_weights_compat_passes_gpu_choice() -> None:
    calls: list[bool] = []
    evaluator = SimpleNamespace(
        torch=SimpleNamespace(
            cuda=SimpleNamespace(is_available=lambda: True),
        ),
        download_weights=lambda use_gpu_inference: calls.append(use_gpu_inference),
    )

    assert install_download_weights_compat(evaluator) is True
    evaluator.download_weights()

    assert calls == [True]


def test_install_download_weights_compat_handles_missing_torch() -> None:
    calls: list[bool] = []
    evaluator = SimpleNamespace(
        download_weights=lambda use_gpu_inference: calls.append(use_gpu_inference),
    )

    assert install_download_weights_compat(evaluator) is False
    evaluator.download_weights()

    assert calls == [False]
