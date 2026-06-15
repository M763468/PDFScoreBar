import unittest

try:
    from src.measure_numbering.mmr import MMROCREngine
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
    MMROCREngine = None
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


if __name__ == "__main__":
    unittest.main()
