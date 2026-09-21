import unittest

from src.measure_numbering.numbering import MeasureNumberer
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
