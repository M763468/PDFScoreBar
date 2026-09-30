import unittest

from src.measure_numbering.builder import SystemBuilder
from src.measure_numbering.types import BBox, Staff


class TestSystemBuilder(unittest.TestCase):
    def setUp(self):
        self.builder = SystemBuilder()

    def test_single_staff_system(self):
        s1 = Staff(bbox=BBox(0, 100, 1000, 200))
        staves = [s1]

        systems = self.builder.build_systems(staves, [])
        self.assertEqual(len(systems), 1)
        self.assertEqual(len(systems[0].staves), 1)

    def test_explicit_index_grouping(self):
        # Staves with explicit system_index
        s1 = Staff(bbox=BBox(0, 100, 1000, 120), system_index=0)
        s2 = Staff(bbox=BBox(0, 200, 1000, 220), system_index=0)
        s3 = Staff(bbox=BBox(0, 300, 1000, 320), system_index=1)

        systems = self.builder.build_systems([s1, s2, s3], [])

        self.assertEqual(len(systems), 2)
        self.assertEqual(len(systems[0].staves), 2)
        self.assertEqual(len(systems[1].staves), 1)

    # Removed test_gap_clustering as heuristic is removed.


if __name__ == "__main__":
    unittest.main()
