import unittest

import numpy as np

from src.measure_numbering.numbering import MeasureNumberer
from src.measure_numbering.pipeline import StaffExtractor
from src.measure_numbering.types import Barline, BBox, Page, Score, Staff, System


class TestNumberingOverrides(unittest.TestCase):
    def setUp(self):
        self.numberer = MeasureNumberer()

    def create_mock_score(self):
        # Create a score with 1 page, 1 system, 5 barlines (4 measures)
        score = Score()
        page = Page(page_number=0)
        staff = Staff(bbox=BBox(0, 100, 1000, 200))
        # 5 barlines at x=100, 300, 500, 700, 900
        for x in [100, 300, 500, 700, 900]:
            staff.barlines.append(Barline(bbox=BBox(x, 100, x + 2, 200)))

        system = System(staves=[staff])
        page.systems.append(system)
        score.pages.append(page)
        return score

    def test_equal_x_dedup_prefers_wider_independent_of_input_order(self):
        def make_system(reverse: bool) -> System:
            narrow = Barline(bbox=BBox(100, 100, 107, 150))
            wide = Barline(bbox=BBox(100, 160, 109, 210))
            right_top = Barline(bbox=BBox(300, 100, 307, 150))
            right_bottom = Barline(bbox=BBox(300, 160, 307, 210))
            top = Staff(bbox=BBox(90, 100, 400, 150), barlines=[narrow, right_top])
            bottom = Staff(bbox=BBox(90, 160, 400, 210), barlines=[wide, right_bottom])
            staves = [bottom, top] if reverse else [top, bottom]
            return System(staves=staves)

        forward = make_system(reverse=False)
        reverse = make_system(reverse=True)

        self.numberer.number_system(forward, start_number=1)
        self.numberer.number_system(reverse, start_number=1)

        self.assertEqual(forward.measures[0].bbox.x1, 109)
        self.assertEqual(reverse.measures[0].bbox.x1, 109)
        self.assertEqual(forward.measures[0].start_bar.bbox, BBox(100, 160, 109, 210))
        self.assertEqual(reverse.measures[0].start_bar.bbox, BBox(100, 160, 109, 210))

    def test_equal_x_equal_width_uses_geometry_tiebreak_independent_of_input_order(self):
        def make_system(reverse: bool) -> System:
            top = Barline(bbox=BBox(100, 100, 108, 150))
            bottom = Barline(bbox=BBox(100, 160, 108, 210))
            right = Barline(bbox=BBox(300, 100, 308, 210))
            candidates = [bottom, top] if reverse else [top, bottom]
            return System(
                staves=[
                    Staff(
                        bbox=BBox(90, 100, 400, 210),
                        barlines=[*candidates, right],
                    )
                ]
            )

        forward = make_system(reverse=False)
        reverse = make_system(reverse=True)

        self.numberer.number_system(forward, start_number=1)
        self.numberer.number_system(reverse, start_number=1)

        expected = BBox(100, 100, 108, 150)
        self.assertEqual(forward.measures[0].start_bar.bbox, expected)
        self.assertEqual(reverse.measures[0].start_bar.bbox, expected)

    def test_distinct_x_dedup_keeps_earlier_x_even_if_later_barline_is_wider(self):
        early = Barline(bbox=BBox(100, 100, 104, 200))
        later_wide = Barline(bbox=BBox(110, 100, 130, 200))
        right = Barline(bbox=BBox(300, 100, 304, 200))
        system = System(
            staves=[
                Staff(
                    bbox=BBox(90, 100, 400, 200),
                    barlines=[later_wide, right, early],
                )
            ]
        )

        self.numberer.number_system(system, start_number=1)

        self.assertEqual(system.measures[0].start_bar.bbox, early.bbox)
        self.assertEqual(system.measures[0].bbox.x1, early.bbox.x2)

    def test_staff_unit_estimator_scales_with_staff_line_spacing(self):
        extractor = StaffExtractor()

        def make_mask(spacing: int) -> np.ndarray:
            mask = np.zeros((spacing * 8, 200), dtype=np.uint8)
            for row in [spacing, spacing * 2, spacing * 3, spacing * 4, spacing * 5]:
                mask[row : row + 1, :] = 255
            return mask

        self.assertAlmostEqual(
            extractor._estimate_unit_size(make_mask(10), scale_y=1.0), 10.0
        )
        self.assertAlmostEqual(
            extractor._estimate_unit_size(make_mask(20), scale_y=1.0), 20.0
        )

    def test_numbering_geometry_thresholds_are_resolution_independent(self):
        def make_system(scale: int) -> System:
            unit = 10 * scale
            y1 = 100 * scale
            y2 = y1 + 4 * unit
            staff = Staff(
                bbox=BBox(0, y1, 120 * scale, y2),
                unit_size=float(unit),
                barlines=[
                    Barline(bbox=BBox(10 * scale, y1, 12 * scale, y2)),
                    # 1.0 unit away: must deduplicate under the 1.2-unit rule.
                    Barline(bbox=BBox(20 * scale, y1, 22 * scale, y2)),
                    Barline(bbox=BBox(80 * scale, y1, 82 * scale, y2)),
                ],
            )
            return System(staves=[staff])

        base = make_system(1)
        doubled = make_system(2)
        self.numberer.number_system(base, start_number=1)
        self.numberer.number_system(doubled, start_number=1)

        self.assertEqual(len(base.measures), 1)
        self.assertEqual(len(doubled.measures), 1)
        self.assertEqual(base.measures[0].start_bar.bbox.x1, 10)
        self.assertEqual(doubled.measures[0].start_bar.bbox.x1, 20)
        self.assertEqual(doubled.measures[0].bbox.x1, base.measures[0].bbox.x1 * 2)
        self.assertEqual(doubled.measures[0].bbox.x2, base.measures[0].bbox.x2 * 2)

    def test_implicit_start_threshold_scales_with_resolution(self):
        def make_system(scale: int) -> System:
            unit = 10 * scale
            y1 = 100 * scale
            y2 = y1 + 4 * unit
            return System(
                staves=[
                    Staff(
                        bbox=BBox(0, y1, 120 * scale, y2),
                        unit_size=float(unit),
                        barlines=[
                            Barline(bbox=BBox(50 * scale, y1, 52 * scale, y2)),
                            Barline(bbox=BBox(100 * scale, y1, 102 * scale, y2)),
                        ],
                    )
                ]
            )

        for scale in (1, 2):
            system = make_system(scale)
            self.numberer.number_system(system, start_number=1)
            self.assertTrue(system.measures[0].start_bar.is_ghost)

    def test_min_measure_width_scales_with_resolution(self):
        def make_system(scale: int) -> System:
            unit = 10 * scale
            y1 = 100 * scale
            y2 = y1 + 4 * unit
            return System(
                staves=[
                    Staff(
                        bbox=BBox(0, y1, 120 * scale, y2),
                        unit_size=float(unit),
                        barlines=[
                            Barline(bbox=BBox(10 * scale, y1, 15 * scale, y2)),
                            # x1 distance is 1.3 units (not deduped), but the
                            # interval after the first bar is only 0.8 unit.
                            Barline(bbox=BBox(23 * scale, y1, 25 * scale, y2)),
                            Barline(bbox=BBox(80 * scale, y1, 82 * scale, y2)),
                        ],
                    )
                ]
            )

        for scale in (1, 2):
            system = make_system(scale)
            self.numberer.number_system(system, start_number=1)
            self.assertEqual(len(system.measures), 1)
            self.assertEqual(system.measures[0].start_bar.bbox.x1, 23 * scale)

    def test_anacrusis_override(self):
        score = self.create_mock_score()
        # Set first measure to number 0
        overrides = [{"page": 0, "system": 0, "measure": 0, "set_number": 0}]
        self.numberer.number_score(score, start_number=1, overrides=overrides)

        measures = score.pages[0].systems[0].measures
        self.assertEqual(measures[0].number, 0)
        self.assertEqual(measures[1].number, 1)
        self.assertEqual(measures[2].number, 2)

    def test_skip_override(self):
        score = self.create_mock_score()
        # Second measure (index 1) skips 3 additional measures (total 4 measure jump)
        overrides = [{"page": 0, "system": 0, "measure": 1, "skip": 3}]
        self.numberer.number_score(score, start_number=1, overrides=overrides)

        measures = score.pages[0].systems[0].measures
        self.assertEqual(measures[0].number, 1)
        self.assertEqual(measures[1].number, 2)  # This one is the long rest
        self.assertEqual(measures[2].number, 6)  # 2 + (1+3) = 6
        self.assertEqual(measures[3].number, 7)


if __name__ == "__main__":
    unittest.main()
