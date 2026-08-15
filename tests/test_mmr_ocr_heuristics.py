import unittest
from pathlib import Path

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

    def test_low_score_j2_majority_replaces_baseline_and_one_bar_is_preserved(self):
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

        result = Processor()._detect_number_with_evidence(
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
        result = Processor()._detect_number_with_evidence(None, system, 0, 0, 10, 10, 1.0, 100, 100)
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
            processor._detect_number_with_evidence(None, {"staves": []}, 0, 0, 1, 1, 1.0, 10, 10),
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
        result = processor._detect_number_with_evidence(None, system, 0, 0, 1, 1, 1.0, 100, 100)
        self.assertEqual(result, (12, 0.0, "base", 0))
        self.assertEqual([stave["bbox"][1] for stave in processor.systems[3]["staves"]], [8, 38])
        self.assertEqual([stave["bbox"][1] for stave in processor.systems[4]["staves"]], [12, 42])


if __name__ == "__main__":
    unittest.main()
