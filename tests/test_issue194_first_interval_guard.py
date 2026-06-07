import unittest

from src.measure_numbering.numbering import MeasureNumberer
from src.measure_numbering.types import Barline, BBox, Staff, System


class TestIssue194FirstIntervalGuard(unittest.TestCase):
    def setUp(self):
        self.numberer = MeasureNumberer()

    def create_system(self, *, staff_bbox, barline_xs):
        staff = Staff(bbox=staff_bbox)
        for x in barline_xs:
            staff.barlines.append(Barline(bbox=BBox(x, staff_bbox.y1, x + 2, staff_bbox.y2)))
        return System(staves=[staff])

    def test_skips_narrow_first_interval_after_ghost_start(self):
        # Mirrors issue #194 page_053: an indented staff inserts a ghost start,
        # and the short clef/key-signature region before the first real barline
        # should not become a measure.
        system = self.create_system(
            staff_bbox=BBox(0, 100, 1600, 267),
            barline_xs=[180, 600, 1000, 1400],
        )

        next_number = self.numberer.number_system(system, start_number=1)

        self.assertEqual(next_number, 4)
        self.assertEqual([m.number for m in system.measures], [1, 2, 3])
        self.assertFalse(system.measures[0].start_bar.is_ghost)
        self.assertEqual(system.measures[0].bbox.x1, 182)
        self.assertEqual(system.measures[0].bbox.x2, 600)

    def test_keeps_normal_width_first_interval_after_ghost_start(self):
        # A ghost-start first interval is only skipped when it is narrow relative
        # to both median interval width and staff height.
        system = self.create_system(
            staff_bbox=BBox(0, 100, 1600, 267),
            barline_xs=[300, 600, 1000, 1400],
        )

        next_number = self.numberer.number_system(system, start_number=1)

        self.assertEqual(next_number, 5)
        self.assertEqual([m.number for m in system.measures], [1, 2, 3, 4])
        self.assertTrue(system.measures[0].start_bar.is_ghost)
        self.assertEqual(system.measures[0].bbox.x1, 1)
        self.assertEqual(system.measures[0].bbox.x2, 300)

    def test_keeps_short_first_interval_without_ghost_start(self):
        # A genuinely short first measure must be kept when the interval starts
        # at a detected barline rather than an implicit ghost start.
        system = self.create_system(
            staff_bbox=BBox(0, 100, 1600, 267),
            barline_xs=[0, 120, 600, 1000],
        )

        next_number = self.numberer.number_system(system, start_number=1)

        self.assertEqual(next_number, 4)
        self.assertEqual([m.number for m in system.measures], [1, 2, 3])
        self.assertFalse(system.measures[0].start_bar.is_ghost)
        self.assertEqual(system.measures[0].bbox.x1, 2)
        self.assertEqual(system.measures[0].bbox.x2, 120)


if __name__ == "__main__":
    unittest.main()
