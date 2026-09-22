import unittest

import cv2
import numpy as np

from src.pipeline.detection.config import get_probe_kwargs
from src.pipeline.probe_detector import detect_probe_scan
from src.pipeline.probe_detector.bands import resolve_x_domains
from src.pipeline.steps.probe_scan import _resolve_scale_aware_probe_kwargs


class TestProbeXDomains(unittest.TestCase):
    def test_full_width_mode_preserves_entire_image(self):
        domains = resolve_x_domains(
            mode="full_width",
            bands=[(10, 40), (60, 90)],
            staff_mask=np.zeros((100, 200), dtype=np.uint8),
            existing_boxes=[],
            image_width=200,
            pad=12,
        )

        self.assertEqual(domains, [(0, 199), (0, 199)])

    def test_staff_mask_mode_uses_band_local_span_and_padding(self):
        mask = np.zeros((100, 200), dtype=np.uint8)
        mask[20:41, 50:151] = 1

        domains = resolve_x_domains(
            mode="staff_mask",
            bands=[(20, 40)],
            staff_mask=mask,
            existing_boxes=[],
            image_width=200,
            pad=10,
        )

        self.assertEqual(domains, [(40, 160)])

    def test_staff_mask_mode_fails_open_when_span_is_missing(self):
        domains = resolve_x_domains(
            mode="staff_mask",
            bands=[(20, 40)],
            staff_mask=np.zeros((100, 200), dtype=np.uint8),
            existing_boxes=[],
            image_width=200,
            pad=10,
        )

        self.assertEqual(domains, [(0, 199)])

    def test_existing_boxes_mode_uses_boxes_in_same_band(self):
        domains = resolve_x_domains(
            mode="existing_boxes",
            bands=[(20, 40)],
            staff_mask=np.zeros((100, 200), dtype=np.uint8),
            existing_boxes=[
                (30, 22, 34, 38),
                (140, 21, 144, 39),
                (5, 70, 9, 90),
            ],
            image_width=200,
            pad=5,
        )

        self.assertEqual(domains, [(25, 149)])

    def test_scale_aware_padding_is_resolved_from_existing_box_height(self):
        resolved = _resolve_scale_aware_probe_kwargs(
            {"scan_x_domain_pad_unit_ratio": 1.5},
            [(10, 10, 14, 50), (100, 10, 104, 50)],
        )

        self.assertEqual(resolved["scan_x_domain_pad"], 15)
        self.assertNotIn("scan_x_domain_pad_unit_ratio", resolved)

    def test_detection_config_forwards_x_domain_options(self):
        kwargs = get_probe_kwargs(
            {
                "scan_x_domain_mode": "staff_mask",
                "scan_x_domain_pad_unit_ratio": 1.0,
            }
        )

        self.assertEqual(kwargs["scan_x_domain_mode"], "staff_mask")
        self.assertEqual(kwargs["scan_x_domain_pad_unit_ratio"], 1.0)


class TestProbeXDomainDetection(unittest.TestCase):
    @staticmethod
    def _base_image(*, outside_height: int = 41, inside_height: int = 41) -> np.ndarray:
        image = np.full((100, 200, 3), 255, dtype=np.uint8)
        if outside_height > 0:
            cv2.rectangle(
                image,
                (18, 20),
                (21, 20 + outside_height - 1),
                (0, 0, 0),
                -1,
            )
        if inside_height > 0:
            cv2.rectangle(
                image,
                (118, 20),
                (121, 20 + inside_height - 1),
                (0, 0, 0),
                -1,
            )
        return image

    @staticmethod
    def _staff_mask() -> np.ndarray:
        mask = np.zeros((100, 200), dtype=np.uint8)
        for y in (20, 25, 30, 35, 40):
            mask[y, 80:161] = 1
        return mask

    @staticmethod
    def _centers(boxes):
        return sorted(int(round((box[0] + box[2]) / 2.0)) for box in boxes)

    def _detect(
        self,
        image: np.ndarray,
        *,
        mode: str | None = None,
        staff_mask: np.ndarray | None = None,
        max_per_band: int = 10,
        min_ratio: float = 0.5,
    ):
        kwargs = {}
        if mode is not None:
            kwargs["scan_x_domain_mode"] = mode
        return detect_probe_scan(
            base_img=image,
            staff_mask=(
                staff_mask if staff_mask is not None else np.zeros(image.shape[:2], dtype=np.uint8)
            ),
            existing_boxes=[],
            band_source="row_stats",
            row_stats=[{"center": 30.0, "top": 20.0, "bottom": 60.0}],
            probe_width=4,
            ink_threshold=180,
            min_ratio=min_ratio,
            min_peak_distance=8,
            refine_window=2,
            max_per_band=max_per_band,
            vertical_closing=0,
            **kwargs,
        )

    def test_default_mode_is_exactly_full_width(self):
        image = self._base_image()

        implicit = self._detect(image)
        explicit = self._detect(image, mode="full_width")

        self.assertEqual(implicit, explicit)
        self.assertEqual(len(implicit), 2)

    def test_staff_mask_domain_excludes_margin_candidate(self):
        image = self._base_image()

        full_width = self._detect(image, mode="full_width")
        bounded = self._detect(image, mode="staff_mask", staff_mask=self._staff_mask())

        self.assertEqual(len(full_width), 2)
        self.assertEqual(len(bounded), 1)
        self.assertTrue(110 <= self._centers(bounded)[0] <= 130)

    def test_missing_staff_span_falls_back_to_full_width_detection(self):
        image = self._base_image()
        empty_mask = np.zeros(image.shape[:2], dtype=np.uint8)

        full_width = self._detect(image, mode="full_width")
        bounded = self._detect(image, mode="staff_mask", staff_mask=empty_mask)

        self.assertEqual(bounded, full_width)

    def test_bounded_domain_prevents_margin_peak_from_consuming_candidate_budget(self):
        image = self._base_image(outside_height=41, inside_height=31)

        full_width = self._detect(
            image,
            mode="full_width",
            max_per_band=1,
            min_ratio=0.5,
        )
        bounded = self._detect(
            image,
            mode="staff_mask",
            staff_mask=self._staff_mask(),
            max_per_band=1,
            min_ratio=0.5,
        )

        self.assertEqual(len(full_width), 1)
        self.assertEqual(len(bounded), 1)
        self.assertTrue(self._centers(full_width)[0] < 50)
        self.assertTrue(110 <= self._centers(bounded)[0] <= 130)


if __name__ == "__main__":
    unittest.main()
