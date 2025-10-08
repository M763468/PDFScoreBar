#!/usr/bin/env python3
"""Lightweight smoke test for run_omerer environment-variable overrides."""

from __future__ import annotations

import json
import sys
from pathlib import Path as _Path
REPO_ROOT = _Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import os
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import List

import cv2
from PIL import Image

from src.archive.oemer import run_omerer


def _write_dummy_assets(tmpdir: Path) -> tuple[Path, Path]:
    image_path = tmpdir / "page_3.png"
    dummy = 255 * (cv2.getGaussianKernel(128, 21) @ cv2.getGaussianKernel(128, 21).T)
    dummy = dummy.astype("uint8")
    cv2.imwrite(str(image_path), dummy)

    gt_boxes = [
        {"barline_location": [10, 5, 14, 120]},
        {"barline_location": [90, 5, 94, 120]},
    ]
    gt_path = tmpdir / "boxes_sorted.json"
    gt_path.write_text(json.dumps(gt_boxes, indent=2))
    return image_path, gt_path


def run_smoke() -> Path:
    with TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        image_path, gt_path = _write_dummy_assets(tmpdir)
        output_root = tmpdir / "oemer_outputs"
        output_root.mkdir(parents=True, exist_ok=True)
        run_id = "smoketest_run"

        env = {
            "OEMER_OUTPUT_ROOT": str(output_root),
            "OEMER_RUN_PREFIX": "smoketest",
            "OEMER_FORCE_RUN_ID": run_id,
            "OEMER_IMAGE_OVERRIDE": str(image_path),
            "OEMER_GROUND_TRUTH": str(gt_path),
            "OEMER_TARGET_PAGES": "3",
        }

        dummy_barlines = [
            SimpleNamespace(bbox=(10, 5, 14, 120)),
            SimpleNamespace(bbox=(90, 5, 94, 120)),
        ]

        with ExitStack() as stack:
            for key, value in env.items():
                stack.enter_context(_temp_env(key, value))
            stack.enter_context(_patch(run_omerer, "clear_data", lambda: None))
            stack.enter_context(_patch(run_omerer, "extract", lambda args: None))
            stack.enter_context(_patch(run_omerer, "teaser", lambda: Image.new("RGB", (32, 32), "white")))
            stack.enter_context(_patch(run_omerer.layers, "get_layer", lambda name: dummy_barlines if name == "barlines" else []))
            stack.enter_context(_patch(run_omerer.oemer_symbol_extraction, "extract", lambda *a, **k: []))

            run_omerer.main()

        run_root = output_root / run_id
        metrics_path = run_root / "metrics.json"
        assert metrics_path.exists(), "metrics.json was not written"
        metrics = json.loads(metrics_path.read_text())
        images: List[dict] = metrics.get("images", [])
        assert images and images[0]["true_positives"] == 2, "Expected both dummy barlines to match"
        return run_root


def _patch(obj, name: str, value):
    from unittest.mock import patch

    return patch.object(obj, name, value)


def _temp_env(key: str, value: str):
    from contextlib import ContextDecorator

    class _Env(ContextDecorator):
        def __enter__(self):
            self._prev = os.environ.get(key)
            os.environ[key] = value
            return self

        def __exit__(self, exc_type, exc, tb):
            if self._prev is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = self._prev
            return False

    return _Env()


if __name__ == "__main__":
    run_dir = run_smoke()
    print(f"Smoke test completed; artifacts at {run_dir}")
