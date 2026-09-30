import unittest

from src.measure_numbering.numbering import MeasureNumberer
from src.measure_numbering.types import Barline, BBox, Page, Score, Staff, System


class TestMeasureNumberer(unittest.TestCase):
    def setUp(self):
        self.numberer = MeasureNumberer()

    def test_single_system_flow(self):
        # 3 Barlines -> 2 Measures
        b1 = Barline(bbox=BBox(100, 0, 105, 100))
        b2 = Barline(bbox=BBox(200, 0, 205, 100))
        b3 = Barline(bbox=BBox(300, 0, 305, 100))

        s1 = Staff(bbox=BBox(0, 0, 1000, 100))
        s1.barlines = [b1, b2, b3]

        system = System(staves=[s1])

        next_num = self.numberer.number_system(system, start_number=1)

        self.assertEqual(next_num, 3)  # Measures 1, 2 created. Next is 3.
        self.assertEqual(len(system.measures), 2)
        self.assertEqual(system.measures[0].number, 1)
        self.assertEqual(system.measures[1].number, 2)
        self.assertEqual(system.measures[0].start_bar, b1)
        self.assertEqual(system.measures[0].end_bar, b2)

    def test_score_flow(self):
        # Page 1: Sys A (2 meas), Sys B (3 meas)
        # Page 2: Sys C (1 meas)
        # Total measures: 2 + 3 + 1 = 6. Next num = 7.

        # Mock Barlines (Assume simplified list)
        bars_a = [Barline(bbox=BBox(x, 0, x + 1, 10)) for x in [10, 20, 30]]  # 2 intervals
        bars_b = [Barline(bbox=BBox(x, 50, x + 1, 60)) for x in [10, 20, 30, 40]]  # 3 intervals
        bars_c = [Barline(bbox=BBox(x, 100, x + 1, 110)) for x in [10, 50]]  # 1 interval

        s_a = Staff(bbox=BBox(0, 0, 100, 20), barlines=bars_a)
        s_b = Staff(bbox=BBox(0, 40, 100, 60), barlines=bars_b)
        s_c = Staff(bbox=BBox(0, 90, 100, 110), barlines=bars_c)

        sys_a = System(staves=[s_a])
        sys_b = System(staves=[s_b])
        sys_c = System(staves=[s_c])

        page1 = Page(systems=[sys_a, sys_b])
        page2 = Page(systems=[sys_c])
        score = Score(pages=[page1, page2])

        last_num = self.numberer.number_score(score, start_number=1)

        self.assertEqual(last_num, 7)
        self.assertEqual(sys_a.measures[0].number, 1)
        self.assertEqual(sys_b.measures[0].number, 3)  # Starts after Sys A (1,2)
        self.assertEqual(sys_c.measures[0].number, 6)  # Starts after Sys B (3,4,5)


if __name__ == "__main__":
    unittest.main()
