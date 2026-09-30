from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from src.pipeline.detection.omr_dln_worker import run


class _TensorLike:
    def __init__(self, values):
        self._values = np.asarray(values, dtype=float)

    def cpu(self):
        return self

    def numpy(self):
        return self._values


class _Box:
    def __init__(self, values):
        self.xyxy = [_TensorLike(values)]


class _Result:
    def __init__(self, boxes):
        self.boxes = [_Box(values) for values in boxes]


class _Model:
    def __init__(self, boxes):
        self._boxes = boxes
        self.calls = []

    def predict(self, image, **kwargs):
        self.calls.append((image.shape, kwargs))
        return [_Result(self._boxes)]


def test_runtime_worker_uses_precomputed_sr_and_returns_source_coordinates(tmp_path: Path) -> None:
    source = tmp_path / "page_001.png"
    source_image = np.zeros((10, 20, 3), dtype=np.uint8)
    assert cv2.imwrite(str(source), source_image)

    sr_root = tmp_path / "sr" / "batch"
    sr = sr_root / source.stem / source.name
    sr.parent.mkdir(parents=True)
    sr_image = np.zeros((40, 80, 3), dtype=np.uint8)
    assert cv2.imwrite(str(sr), sr_image)

    model = _Model([(8, 4, 40, 36)])
    outputs = run(
        [source],
        output_dir=tmp_path / "omr",
        precomputed_sr=sr_root,
        model=model,
    )

    assert len(outputs) == 1
    assert outputs[0].read_text(encoding="utf-8").strip() == "[[1, 1, 2, 9], [9, 1, 10, 9]]"
    assert model.calls == [
        (
            (40, 80, 3),
            {"conf": 0.25, "save": False, "verbose": False},
        )
    ]


def test_runtime_worker_rejects_missing_precomputed_sr(tmp_path: Path) -> None:
    source = tmp_path / "page_001.png"
    assert cv2.imwrite(str(source), np.zeros((10, 20, 3), dtype=np.uint8))

    try:
        run(
            [source],
            output_dir=tmp_path / "omr",
            precomputed_sr=tmp_path / "missing",
            model=_Model([]),
        )
    except FileNotFoundError as exc:
        assert "No precomputed SR image" in str(exc)
    else:
        raise AssertionError("missing precomputed SR must fail closed")
