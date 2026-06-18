import unittest

import numpy as np

from src.measure_numbering.connector_aware_builder import (
    ConnectorAwareSystemBuilder as SystemBuilder,
)
from src.measure_numbering.types import Barline, BBox, Staff


class TestIssue197SystemGroupingConnectorEvidence(unittest.TestCase):
    def make_staff_pair(self, *, gap, height=100, width=400):
        s1 = Staff(bbox=BBox(0, 0, width, height))
        s2_y1 = height + gap
        s2 = Staff(bbox=BBox(0, s2_y1, width, s2_y1 + height))
        return s1, s2

    def make_barlines(self, s1, s2, xs):
        bars = []
        for x in xs:
            bars.append(Barline(bbox=BBox(x, s1.bbox.y1, x + 2, s1.bbox.y2)))
            bars.append(Barline(bbox=BBox(x, s2.bbox.y1, x + 2, s2.bbox.y2)))
        return bars

    def make_connection_image(self, s1, s2, xs, width=500):
        height = int(s2.bbox.y2 + 20)
        image = np.full((height, width), 255, dtype=np.uint8)
        for x in xs:
            image[int(s1.bbox.y2) : int(s2.bbox.y1), x : x + 2] = 0
        return image

    def test_connector_evidence_rescues_near_threshold_false_split(self):
        builder = SystemBuilder()
        s1, s2 = self.make_staff_pair(gap=153)
        xs = [100, 200, 300]
        barlines = self.make_barlines(s1, s2, xs)
        image = self.make_connection_image(s1, s2, xs)

        systems = builder.build_systems(
            [s1, s2],
            barlines,
            image=image,
            connector_evidence={
                "staff_pairs": [
                    {
                        "staff_pair": [0, 1],
                        "left_connector_present": True,
                    }
                ]
            },
        )

        self.assertEqual(len(systems), 1)
        self.assertEqual(len(systems[0].staves), 2)

    def test_near_threshold_pair_is_not_rescued_without_connector_evidence(self):
        builder = SystemBuilder()
        s1, s2 = self.make_staff_pair(gap=153)
        xs = [100, 200, 300]
        barlines = self.make_barlines(s1, s2, xs)
        image = self.make_connection_image(s1, s2, xs)

        systems = builder.build_systems([s1, s2], barlines, image=image)

        self.assertEqual(len(systems), 2)

    def test_low_alignment_connection_with_explicit_no_connector_is_guarded(self):
        builder = SystemBuilder()
        s1, s2 = self.make_staff_pair(gap=90)
        xs = [100, 300]
        barlines = self.make_barlines(s1, s2, xs)
        image = self.make_connection_image(s1, s2, xs)

        systems = builder.build_systems(
            [s1, s2],
            barlines,
            image=image,
            connector_evidence={
                "staff_pairs": [
                    {
                        "staff_pair": [0, 1],
                        "left_connector_present": False,
                    }
                ]
            },
        )

        self.assertEqual(len(systems), 2)

    def test_high_alignment_connection_with_explicit_no_connector_is_guarded(self):
        builder = SystemBuilder()
        s1, s2 = self.make_staff_pair(gap=90)
        xs = [60, 120, 180, 240, 300]
        barlines = self.make_barlines(s1, s2, xs)
        image = self.make_connection_image(s1, s2, xs)

        systems = builder.build_systems(
            [s1, s2],
            barlines,
            image=image,
            connector_evidence={
                "staff_pairs": [
                    {
                        "staff_pair": [0, 1],
                        "left_connector_present": False,
                    }
                ]
            },
        )

        self.assertEqual(len(systems), 2)

    def test_low_alignment_connection_without_connector_evidence_keeps_legacy_merge(self):
        builder = SystemBuilder()
        s1, s2 = self.make_staff_pair(gap=90)
        xs = [100, 300]
        barlines = self.make_barlines(s1, s2, xs)
        image = self.make_connection_image(s1, s2, xs)

        systems = builder.build_systems([s1, s2], barlines, image=image)

        self.assertEqual(len(systems), 1)
        self.assertEqual(len(systems[0].staves), 2)

    def test_connector_density_schema_is_accepted(self):
        builder = SystemBuilder()
        s1, s2 = self.make_staff_pair(gap=153)
        xs = [100, 200, 300]
        barlines = self.make_barlines(s1, s2, xs)
        image = self.make_connection_image(s1, s2, xs)

        systems = builder.build_systems(
            [s1, s2],
            barlines,
            image=image,
            connector_evidence={
                "0-1": {
                    "symbols_vertical_open_density": 0.071,
                    "brace_dot_vertical_open_density": 0.140,
                }
            },
        )

        self.assertEqual(len(systems), 1)


if __name__ == "__main__":
    unittest.main()
