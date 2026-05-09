import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from src.pipeline.probe_detector import detect_probe_scan


def _load_detection_config_module():
    path = Path(__file__).resolve().parents[1] / "src/pipeline/detection/config.py"
    spec = importlib.util.spec_from_file_location("pipeline_detection_config", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _synthetic_tall_band_image():
    img = np.full((120, 140, 3), 255, dtype=np.uint8)
    staff_mask = np.zeros((120, 140), dtype=np.uint8)
    staff_mask[10:110, 10:130] = 1

    # Staff lines provide a non-zero local background for x-peak comparison.
    for y in (25, 45, 65, 85, 105):
        cv2.line(img, (10, y), (130, y), (0, 0, 0), 1)

    # This barline is visually clear but occupies only part of the tall band:
    # area ratio stays below min_ratio=0.85 while x-peak is strong.
    cv2.rectangle(img, (69, 25), (72, 94), (0, 0, 0), -1)
    return img, staff_mask


class TestProbeDetectorXPeakLowRatio(unittest.TestCase):
    def test_low_ratio_xpeak_rescue_is_opt_in(self):
        img, staff_mask = _synthetic_tall_band_image()

        default_candidates = detect_probe_scan(
            base_img=img,
            staff_mask=staff_mask,
            existing_boxes=[],
            ink_threshold=180,
            min_ratio=0.85,
            probe_width=4,
            max_per_band=20,
        )

        rescued_candidates = detect_probe_scan(
            base_img=img,
            staff_mask=staff_mask,
            existing_boxes=[],
            ink_threshold=180,
            min_ratio=0.85,
            probe_width=4,
            max_per_band=20,
            scan_x_peak_low_ratio_rescue=True,
            scan_x_peak_low_ratio_min=0.30,
            scan_x_peak_low_ratio_min_run_ratio=0.50,
            scan_x_peak_ratio_min=1.5,
        )

        self.assertFalse(any(abs(((b[0] + b[2]) / 2.0) - 71) <= 4 for b in default_candidates))
        self.assertTrue(any(abs(((b[0] + b[2]) / 2.0) - 71) <= 4 for b in rescued_candidates))

    def test_debug_status_records_xpeak_low_ratio_rescue(self):
        img, staff_mask = _synthetic_tall_band_image()

        with tempfile.TemporaryDirectory() as tmpdir:
            debug_path = Path(tmpdir) / "probe_debug.png"
            detect_probe_scan(
                base_img=img,
                staff_mask=staff_mask,
                existing_boxes=[],
                ink_threshold=180,
                min_ratio=0.85,
                probe_width=4,
                max_per_band=20,
                scan_x_peak_low_ratio_rescue=True,
                scan_x_peak_low_ratio_min=0.30,
                scan_x_peak_low_ratio_min_run_ratio=0.50,
                scan_x_peak_ratio_min=1.5,
                debug_path=debug_path,
            )

            records = json.loads(debug_path.with_suffix(".json").read_text())["records"]

        self.assertIn("scan_ratio_low_xpeak_rescued", {rec["status"] for rec in records})

    def test_probe_kwargs_include_low_ratio_xpeak_rescue_keys(self):
        config_module = _load_detection_config_module()
        kwargs = config_module.get_probe_kwargs(
            {
                "scan_x_peak_low_ratio_rescue": True,
                "scan_x_peak_low_ratio_min": 0.3,
                "scan_x_peak_low_ratio_min_run_ratio": 0.5,
            }
        )

        self.assertEqual(
            kwargs,
            {
                "scan_x_peak_low_ratio_rescue": True,
                "scan_x_peak_low_ratio_min": 0.3,
                "scan_x_peak_low_ratio_min_run_ratio": 0.5,
            },
        )


if __name__ == "__main__":
    unittest.main()
