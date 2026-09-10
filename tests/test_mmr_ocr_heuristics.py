import unittest
from pathlib import Path

import numpy as np
import torch

try:
    from src.measure_numbering.mmr import MMROCREngine, MMRProcessor
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
    MMROCREngine = None
    MMRProcessor = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


def _box(x1, y1, x2, y2):
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


@unittest.skipIf(MMROCREngine is None, f"MMR OCR dependencies unavailable: {IMPORT_ERROR}")
class TestMMROCRHeuristics(unittest.TestCase):
    def setUp(self):
        self.ocr = MMROCREngine(ocr_engine=object())

    def test_blacklisted_text_without_digits_is_rejected(self):
        num, score, debug = self.ocr.select_best_candidate(
            [[_box(40, 25, 60, 75), "con sord.", 0.99]],
            img_width=100,
            img_height=100,
        )

        self.assertIsNone(num)
        self.assertEqual(score, 0)
        self.assertEqual(debug, "")

    def test_digit_with_blacklisted_direction_remains_candidate(self):
        num, _, debug = self.ocr.select_best_candidate(
            [[_box(40, 25, 60, 75), "7 (con sord.)", 0.99]],
            img_width=100,
            img_height=100,
        )

        self.assertEqual(num, 7)
        self.assertIn("blacklist_digit", debug)

    def test_digit_with_blacklisted_instrument_remains_candidate(self):
        num, _, debug = self.ocr.select_best_candidate(
            [
                [_box(40, 25, 55, 75), "(VC) 5", 0.99],
                [_box(82, 25, 98, 75), "10]", 0.99],
            ],
            img_width=100,
            img_height=100,
        )

        self.assertEqual(num, 5)
        self.assertIn("blacklist_digit", debug)

    def test_attached_digit_in_blacklisted_text_is_rejected(self):
        for text in ["VC5", "Ob2"]:
            with self.subTest(text=text):
                num, score, debug = self.ocr.select_best_candidate(
                    [[_box(40, 25, 60, 75), text, 0.99]],
                    img_width=100,
                    img_height=100,
                )

                self.assertIsNone(num)
                self.assertEqual(score, 0)
                self.assertEqual(debug, "")

    def test_raw_single_digit_survives_ambiguous_high_count_merge_candidate(self):
        num, _, debug = self.ocr.select_best_candidate(
            [
                [_box(48, 25, 53, 75), "3", 0.99],
                [_box(76, 25, 81, 75), "9", 0.99],
            ],
            img_width=100,
            img_height=100,
        )

        self.assertEqual(num, 3)
        self.assertIn("raw", debug)

    def test_legitimate_split_two_digit_candidate_still_wins(self):
        num, _, debug = self.ocr.select_best_candidate(
            [
                [_box(43, 25, 48, 75), "1", 0.99],
                [_box(50, 25, 55, 75), "5", 0.99],
            ],
            img_width=100,
            img_height=100,
        )

        self.assertEqual(num, 15)
        self.assertIn("merged", debug)

    def test_legitimate_split_high_count_candidate_still_wins(self):
        num, _, debug = self.ocr.select_best_candidate(
            [
                [_box(43, 25, 48, 75), "3", 0.99],
                [_box(50, 25, 55, 75), "9", 0.99],
            ],
            img_width=100,
            img_height=100,
        )

        self.assertEqual(num, 39)
        self.assertIn("merged", debug)

    def test_low_score_j2_fallback_replaces_baseline_and_preserves_one_bar(self):
        class Processor(MMRProcessor):
            def __init__(self):
                super().__init__(
                    Path("unused"), torch.device("cpu"), classifier=object(), ocr_engine=object()
                )
                self.values = iter(
                    [
                        (97, -44.0, "base", 1),
                        (5, 24.0, "x-", 0),
                        (5, 25.0, "x+", 0),
                        (5, 23.0, "y-", 0),
                        (6, -44.0, "y+", 0),
                    ]
                )

            def _detect_number_with_evidence_once(self, *args):
                return next(self.values)

        result = Processor()._detect_number_with_evidence_j2(
            None, {"staves": []}, 0, 0, 10, 10, 1.0, 100, 100
        )
        self.assertEqual(result[0], 5)
        self.assertEqual(result[3], 1)
        self.assertIn("j2_consensus=3of5", result[2])

    def test_low_score_j2_no_majority_keeps_baseline_without_mutating_staves(self):
        class Processor(MMRProcessor):
            def __init__(self):
                super().__init__(
                    Path("unused"), torch.device("cpu"), classifier=object(), ocr_engine=object()
                )
                self.values = iter(
                    [
                        (12, 0.0, "base", 0),
                        (2, 1.0, "x-", 0),
                        (3, 1.0, "x+", 0),
                        (4, 1.0, "y-", 0),
                        (5, 1.0, "y+", 0),
                    ]
                )

            def _detect_number_with_evidence_once(self, *args):
                return next(self.values)

        system = {"staves": [{"bbox": [0, 10, 50, 30]}, {"bbox": [0, 40, 50, 60]}]}
        result = Processor()._detect_number_with_evidence_j2(
            None, system, 0, 0, 10, 10, 1.0, 100, 100
        )
        self.assertEqual(result, (12, 0.0, "base", 0))
        self.assertEqual(system["staves"][0]["bbox"], [0, 10, 50, 30])
        self.assertEqual(system["staves"][1]["bbox"], [0, 40, 50, 60])

    def test_j2_non_trigger_calls_once_and_returns_exact_baseline(self):
        class Processor(MMRProcessor):
            def __init__(self):
                super().__init__(
                    Path("unused"), torch.device("cpu"), classifier=object(), ocr_engine=object()
                )
                self.calls = 0

            def _detect_number_with_evidence_once(self, *args):
                self.calls += 1
                return (8, 5.1, "baseline", 2)

        processor = Processor()
        self.assertEqual(
            processor._detect_number_with_evidence_j2(
                None, {"staves": []}, 0, 0, 1, 1, 1.0, 10, 10
            ),
            (8, 5.1, "baseline", 2),
        )
        self.assertEqual(processor.calls, 1)

    def test_j2_excludes_one_votes_and_applies_all_staff_y_shifts(self):
        class Processor(MMRProcessor):
            def __init__(self):
                super().__init__(
                    Path("unused"), torch.device("cpu"), classifier=object(), ocr_engine=object()
                )
                self.systems = []
                self.values = iter(
                    [
                        (12, 0.0, "base", 0),
                        (1, 1.0, "x-", 0),
                        (1, 1.0, "x+", 0),
                        (2, 1.0, "y-", 0),
                        (2, 1.0, "y+", 0),
                    ]
                )

            def _detect_number_with_evidence_once(self, _image, system, *args):
                self.systems.append(system)
                return next(self.values)

        system = {"staves": [{"bbox": [0, 10, 50, 30]}, {"bbox": [0, 40, 50, 60]}]}
        processor = Processor()
        result = processor._detect_number_with_evidence_j2(None, system, 0, 0, 1, 1, 1.0, 100, 100)
        self.assertEqual(result, (12, 0.0, "base", 0))
        self.assertEqual([stave["bbox"][1] for stave in processor.systems[3]["staves"]], [8, 38])
        self.assertEqual([stave["bbox"][1] for stave in processor.systems[4]["staves"]], [12, 42])

    def test_targeted_high_score_one_shot_is_authoritative(self):
        processor = _TargetedHarness(
            baseline=(9, 5.1, "baseline", 0),
            full_span=(6, 40.0),
            shifted=(6, 40.0),
        )

        self.assertEqual(_run_targeted(processor), (9, 5.1, "baseline", 0))
        self.assertEqual((processor.full_span_calls, processor.shifted_calls), (0, 0))
        self.assertEqual(processor.j2_calls, 0)

    def test_targeted_low_score_uses_full_span_retry_first(self):
        processor = _TargetedHarness(
            baseline=(97, -44.0, "baseline", 0),
            full_span=(5, 24.0),
            shifted=(6, 40.0),
        )

        result = _run_targeted(processor)

        self.assertEqual(result[:2], (5, 24.0))
        self.assertIn("full_span_unmasked_heavy_dilate", result[2])
        self.assertEqual((processor.full_span_calls, processor.shifted_calls), (1, 0))
        self.assertEqual(processor.j2_calls, 0)

    def test_targeted_none_uses_scale_relative_second_retry(self):
        processor = _TargetedHarness(
            baseline=(None, 0.0, "baseline", 0),
            full_span=(None, 0.0),
            shifted=(6, 24.0),
        )

        result = _run_targeted(processor)

        self.assertEqual(result[:2], (6, 24.0))
        self.assertIn("scale_relative_x1_masked_no_dilate", result[2])
        self.assertEqual(processor.shifted_bbox, [101, 0, 200, 20])
        self.assertEqual(processor.j2_calls, 0)

    def test_targeted_unresolved_low_score_uses_j2_fallback(self):
        processor = _TargetedHarness(
            baseline=(37, -10.0, "baseline", 0),
            full_span=(None, 0.0),
            shifted=(111, -68.0),
            j2=(37, 29.0, "j2", 0),
        )

        self.assertEqual(_run_targeted(processor), (37, 29.0, "j2", 0))
        self.assertEqual(processor.j2_calls, 1)

    def test_targeted_unresolved_none_keeps_one_shot_without_j2_repeat(self):
        processor = _TargetedHarness(
            baseline=(None, 0.0, "baseline", 0),
            full_span=(None, 0.0),
            shifted=(111, -68.0),
            j2=(7, 20.0, "unexpected", 0),
        )

        self.assertEqual(_run_targeted(processor), (None, 0.0, "baseline", 0))
        self.assertEqual(processor.j2_calls, 0)

    def test_targeted_low_cnn_and_one_bar_sensitive_cases_keep_j2(self):
        cases = (
            (0.4, (8, -5.0, "baseline", 0)),
            (0.55, (11, -16.0, "baseline", 2)),
        )
        for prob, baseline in cases:
            with self.subTest(prob=prob, baseline=baseline):
                processor = _TargetedHarness(
                    baseline=baseline,
                    full_span=(2, 40.0),
                    shifted=(2, 40.0),
                    j2=(None, 0.0, "j2", baseline[3]),
                )

                self.assertEqual(_run_targeted(processor, prob=prob)[0], None)
                self.assertEqual((processor.full_span_calls, processor.shifted_calls), (0, 0))
                self.assertEqual(processor.j2_calls, 1)

    def test_targeted_retry_requires_unique_span_with_positive_score(self):
        self.assertTrue(MMRProcessor._targeted_retry_candidate_acceptable(3, 0.1))
        self.assertFalse(MMRProcessor._targeted_retry_candidate_acceptable(3, 0.0))
        self.assertFalse(MMRProcessor._targeted_retry_candidate_acceptable(1, 50.0))
        self.assertFalse(MMRProcessor._targeted_retry_candidate_acceptable(None, 50.0))
        self.assertEqual(
            MMRProcessor._aggregate_targeted_staff_results([(3, 10.0), (4, 20.0)]),
            (None, 0.0),
        )

    def test_targeted_x1_shift_is_measure_width_relative(self):
        self.assertEqual(
            MMRProcessor._targeted_shift_x1([398, 1350, 836, 1506]),
            [402, 1350, 836, 1506],
        )

    def test_targeted_retry_helpers_preserve_crop_and_preprocessing_contract(self):
        processor = object.__new__(MMRProcessor)
        processor.ocr = _TargetedRetryOCR()
        image = np.zeros((300, 500, 3), dtype=np.uint8)
        staff_bbox = [0, 100, 400, 140]

        self.assertEqual(
            processor._run_targeted_full_span_staff(image, [100, 0, 200, 20], staff_bbox, 500, 300),
            (6, 24.0),
        )
        self.assertEqual(processor.ocr.preprocess_calls, [((60, 100, 3), "heavy_dilate")])
        self.assertEqual(processor.ocr.mask_calls, [])

        self.assertEqual(
            processor._run_targeted_shifted_staff(image, [101, 0, 200, 20], staff_bbox, 500, 300),
            (6, 24.0),
        )
        self.assertEqual(
            processor.ocr.preprocess_calls[-1],
            ((80, 115, 3), "no_dilate"),
        )
        self.assertEqual(processor.ocr.mask_calls, [((80, 115, 3), 20.0, 40.0)])

    def test_targeted_shifted_crop_scales_with_staff_height_and_uses_clamped_offset(self):
        processor = object.__new__(MMRProcessor)
        processor.ocr = _TargetedRetryOCR()
        image = np.zeros((300, 500, 3), dtype=np.uint8)

        self.assertEqual(
            processor._run_targeted_shifted_staff(
                image, [101, 0, 200, 20], [0, 100, 400, 180], 500, 300
            ),
            (6, 24.0),
        )
        self.assertEqual(processor.ocr.preprocess_calls[-1], ((160, 131, 3), "no_dilate"))
        self.assertEqual(processor.ocr.mask_calls[-1], ((160, 131, 3), 40.0, 80.0))

        self.assertEqual(
            processor._run_targeted_shifted_staff(
                image, [101, 0, 200, 20], [0, 10, 400, 50], 500, 300
            ),
            (6, 24.0),
        )
        self.assertEqual(processor.ocr.preprocess_calls[-1], ((70, 115, 3), "no_dilate"))
        self.assertEqual(processor.ocr.mask_calls[-1], ((70, 115, 3), 10.0, 40.0))


_TargetedHarnessBase = MMRProcessor if MMRProcessor is not None else object


class _TargetedHarness(_TargetedHarnessBase):
    def __init__(self, *, baseline, full_span, shifted, j2=(None, 0.0, "j2", 0)):
        self.threshold = 0.5
        self.baseline = baseline
        self.full_span = full_span
        self.shifted = shifted
        self.j2 = j2
        self.full_span_calls = 0
        self.shifted_calls = 0
        self.j2_calls = 0
        self.shifted_bbox = None

    def _detect_number_with_evidence_once(self, *args):
        return self.baseline

    def _detect_number_with_evidence_j2(self, *args):
        self.j2_calls += 1
        return self.j2

    def _run_targeted_full_span_staff(self, *args):
        self.full_span_calls += 1
        return self.full_span

    def _run_targeted_shifted_staff(self, _image, measure_bbox, *args):
        self.shifted_calls += 1
        self.shifted_bbox = measure_bbox
        return self.shifted


class _TargetedRetryOCR:
    def __init__(self):
        self.preprocess_calls = []
        self.mask_calls = []
        self.ocr_engine = lambda _image: ([], 0.0)

    def mask_hbar_candidates(self, crop, margin_y, staff_height):
        self.mask_calls.append((crop.shape, margin_y, staff_height))
        return crop

    def preprocess_variant(self, crop, mode, angle):
        self.preprocess_calls.append((crop.shape, mode))
        self.assert_angle_zero(angle)
        return crop

    @staticmethod
    def assert_angle_zero(angle):
        if angle != 0:
            raise AssertionError(f"Unexpected retry rotation: {angle}")

    @staticmethod
    def select_best_candidate(_ocr_result, _width, _height):
        return 6, 24.0, "candidate"


def _run_targeted(processor, *, prob=0.99):
    return processor._detect_number_with_evidence(
        None,
        {"staves": [{"bbox": [0, 0, 100, 20]}]},
        100,
        0,
        200,
        20,
        prob,
        1000,
        1000,
    )


if __name__ == "__main__":
    unittest.main()