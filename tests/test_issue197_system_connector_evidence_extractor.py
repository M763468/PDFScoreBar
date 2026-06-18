import json
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from src.measure_numbering.connector_evidence import SystemConnectorEvidenceExtractor
from src.measure_numbering.types import BBox, Staff


class TestIssue197SystemConnectorEvidenceExtractor(unittest.TestCase):
    def setUp(self):
        self.extractor = SystemConnectorEvidenceExtractor()
        self.image_size = (400, 400)
        self.staves = [
            Staff(bbox=BBox(100, 50, 350, 100)),
            Staff(bbox=BBox(100, 190, 350, 240)),
            Staff(bbox=BBox(100, 320, 350, 370)),
        ]

    def test_extracts_left_connector_from_symbol_mask(self):
        symbol_mask = np.zeros((400, 400), dtype=np.uint8)
        symbol_mask[100:190, 90:110] = 255

        evidence = self.extractor.extract(
            self.staves,
            self.image_size,
            symbol_mask=symbol_mask,
        )

        pairs = evidence["staff_pairs"]
        self.assertTrue(evidence["generated"])
        self.assertTrue(pairs[0]["left_connector_present"])
        self.assertGreaterEqual(pairs[0]["symbols_vertical_open_density"], 0.05)
        self.assertFalse(pairs[1]["left_connector_present"])

    def test_extracts_left_connector_from_brace_dot_mask(self):
        brace_dot_mask = np.zeros((400, 400), dtype=np.uint8)
        brace_dot_mask[100:190, 90:110] = 255

        evidence = self.extractor.extract(
            self.staves,
            self.image_size,
            brace_dot_mask=brace_dot_mask,
        )

        self.assertTrue(evidence["staff_pairs"][0]["left_connector_present"])
        self.assertGreaterEqual(
            evidence["staff_pairs"][0]["brace_dot_vertical_open_density"],
            0.05,
        )

    def test_extract_from_paths_and_write_json(self):
        symbol_mask = np.zeros((400, 400), dtype=np.uint8)
        symbol_mask[100:190, 90:110] = 255

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            symbol_path = tmp / "symbols.png"
            output_path = tmp / "system_connector_evidence.json"
            cv2.imwrite(str(symbol_path), symbol_mask)

            evidence = self.extractor.extract_from_paths(
                self.staves,
                self.image_size,
                symbol_mask_path=symbol_path,
            )
            self.extractor.write_json(evidence, output_path)

            loaded = json.loads(output_path.read_text())
            self.assertTrue(loaded["generated"])
            self.assertTrue(loaded["staff_pairs"][0]["left_connector_present"])


if __name__ == "__main__":
    unittest.main()
