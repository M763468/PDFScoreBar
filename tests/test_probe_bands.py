import unittest

import numpy as np

from src.pipeline.probe_detector.bands import staff_bands_from_mask


class TestStaffBandsFromMask(unittest.TestCase):
    def test_line_like_staff_mask_segments_are_merged_into_staff_bands(self):
        mask = np.zeros((200, 50), dtype=np.uint8)

        # Two staves represented as five thin horizontal lines each.
        for y in (10, 20, 30, 40, 50):
            mask[y : y + 1, 5:45] = 1
        for y in (110, 120, 130, 140, 150):
            mask[y : y + 1, 5:45] = 1

        bands = staff_bands_from_mask(mask)

        self.assertEqual(bands, [(10, 50), (110, 150)])

    def test_region_like_staff_mask_is_not_over_merged(self):
        mask = np.zeros((220, 60), dtype=np.uint8)
        mask[20:65, 5:55] = 1
        mask[120:170, 5:55] = 1

        bands = staff_bands_from_mask(mask)

        self.assertEqual(bands, [(20, 64), (120, 169)])

    def test_line_like_short_nonstaff_fragments_are_filtered_out(self):
        mask = np.zeros((220, 120), dtype=np.uint8)

        # One staff-like group (5 long lines).
        for y in (20, 30, 40, 50, 60):
            mask[y : y + 1, 10:110] = 1

        # Non-staff short horizontal fragments (should not become a staff band).
        for y in (140, 150):
            mask[y : y + 1, 15:35] = 1

        bands = staff_bands_from_mask(mask)

        self.assertEqual(bands, [(20, 60)])


if __name__ == "__main__":
    unittest.main()
