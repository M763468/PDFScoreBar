
import unittest
from src.measure_numbering.types import Score, Page, System, Staff, Barline, BBox
from src.measure_numbering.numbering import MeasureNumberer

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
            staff.barlines.append(Barline(bbox=BBox(x, 100, x+2, 200)))
        
        system = System(staves=[staff])
        page.systems.append(system)
        score.pages.append(page)
        return score

    def test_anacrusis_override(self):
        score = self.create_mock_score()
        # Set first measure to number 0
        overrides = [
            {"page": 0, "system": 0, "measure": 0, "set_number": 0}
        ]
        self.numberer.number_score(score, start_number=1, overrides=overrides)
        
        measures = score.pages[0].systems[0].measures
        self.assertEqual(measures[0].number, 0)
        self.assertEqual(measures[1].number, 1)
        self.assertEqual(measures[2].number, 2)

    def test_skip_override(self):
        score = self.create_mock_score()
        # Second measure (index 1) skips 3 additional measures (total 4 measure jump)
        overrides = [
            {"page": 0, "system": 0, "measure": 1, "skip": 3}
        ]
        self.numberer.number_score(score, start_number=1, overrides=overrides)
        
        measures = score.pages[0].systems[0].measures
        self.assertEqual(measures[0].number, 1)
        self.assertEqual(measures[1].number, 2) # This one is the long rest
        self.assertEqual(measures[2].number, 6) # 2 + (1+3) = 6
        self.assertEqual(measures[3].number, 7)

if __name__ == "__main__":
    unittest.main()
