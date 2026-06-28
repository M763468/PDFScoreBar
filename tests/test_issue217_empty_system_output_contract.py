import unittest

from src.measure_numbering.serialization import score_to_dict
from src.measure_numbering.types import Barline, BBox, Measure, Page, Score, Staff, System


class TestIssue217EmptySystemOutputContract(unittest.TestCase):
    def make_numbered_system(self):
        staff = Staff(bbox=BBox(0, 100, 1000, 180))
        first_bar = Barline(bbox=BBox(100, 100, 102, 180))
        second_bar = Barline(bbox=BBox(300, 100, 302, 180))
        third_bar = Barline(bbox=BBox(500, 100, 502, 180))
        return System(
            staves=[staff],
            measures=[
                Measure(
                    number=1,
                    start_bar=first_bar,
                    end_bar=second_bar,
                    bbox=BBox(100, 100, 300, 180),
                ),
                Measure(
                    number=2,
                    start_bar=second_bar,
                    end_bar=third_bar,
                    bbox=BBox(300, 100, 500, 180),
                ),
            ],
        )

    def make_empty_system(self):
        return System(staves=[Staff(bbox=BBox(10, 10, 200, 40))], measures=[])

    def test_score_to_dict_separates_empty_systems_from_numbered_systems(self):
        score = Score(
            pages=[
                Page(
                    page_number=1,
                    width=1000,
                    height=2000,
                    systems=[self.make_empty_system(), self.make_numbered_system()],
                )
            ]
        )

        data = score_to_dict(score)
        page = data["pages"][0]

        self.assertEqual(len(page["systems"]), 1)
        self.assertEqual([m["number"] for m in page["systems"][0]["measures"]], [1, 2])

        self.assertIn("empty_systems", page)
        self.assertEqual(len(page["empty_systems"]), 1)
        self.assertEqual(page["empty_systems"][0]["reason"], "no_measures")
        self.assertEqual(page["empty_systems"][0]["staves"][0]["bbox"], [10, 10, 200, 40])
        self.assertNotIn("measures", page["empty_systems"][0])

    def test_serialized_system_ranges_do_not_include_empty_systems(self):
        score = Score(
            pages=[
                Page(
                    page_number=1,
                    width=1000,
                    height=2000,
                    systems=[
                        self.make_empty_system(),
                        self.make_numbered_system(),
                        self.make_empty_system(),
                    ],
                )
            ]
        )

        page = score_to_dict(score)["pages"][0]
        measure_ranges = [
            [system["measures"][0]["number"], system["measures"][-1]["number"]]
            for system in page["systems"]
        ]

        self.assertEqual(measure_ranges, [[1, 2]])
        self.assertEqual(len(page["empty_systems"]), 2)


if __name__ == "__main__":
    unittest.main()
