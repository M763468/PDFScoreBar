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

    def test_override_indices_follow_visible_measure_indices(self):
        system = self.create_system(
            staff_bbox=BBox(0, 100, 1600, 267),
            barline_xs=[180, 600, 1000, 1400],
        )

        next_number = self.numberer.number_system(
            system,
            start_number=1,
            overrides={0: {"skip": 2}},
        )

        self.assertEqual(next_number, 6)
        self.assertEqual([m.number for m in system.measures], [1, 4, 5])
        self.assertEqual(system.measures[0].attribute.skip, 2)

    def test_median_uses_real_following_intervals_for_ghost_start(self):
        system = self.create_system(
            staff_bbox=BBox(0, 100, 1600, 267),
            barline_xs=[180, 360, 1000],
        )

        next_number = self.numberer.number_system(system, start_number=1)

        self.assertEqual(next_number, 3)
        self.assertEqual([m.number for m in system.measures], [1, 2])
        self.assertFalse(system.measures[0].start_bar.is_ghost)
        self.assertEqual(system.measures[0].bbox.x1, 182)
        self.assertEqual(system.measures[0].bbox.x2, 360)


if __name__ == "__main__":
    unittest.main()
