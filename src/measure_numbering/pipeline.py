import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from .builder import SystemBuilder
from .numbering import MeasureNumberer
from .types import Barline, BBox, Page, Score, Staff

logger = logging.getLogger(__name__)


class StaffExtractor:
    """Extracts staff regions (BBoxes) from a binary staff mask image."""

    def __init__(self, min_height: int = 10, min_width_ratio: float = 0.1):
        self.min_height = min_height
        self.min_width_ratio = min_width_ratio

    def extract(self, mask_path: Path, target_size: Tuple[int, int]) -> List[Staff]:
        mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
        if mask is None:
            raise FileNotFoundError(f"Staff mask not found: {mask_path}")

        h_mask, w_mask = mask.shape[:2]
        target_w, target_h = target_size
        scale_x = target_w / w_mask
        scale_y = target_h / h_mask

        # Binarize
        _, bin_mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)

        # Merge staff lines and horizontal fragments
        # Vertical kernel to merge 5 lines into one band
        v_kernel = np.ones((20, 1), np.uint8)
        # Horizontal kernel to bridge small gaps between staff fragments
        h_kernel = np.ones((1, 50), np.uint8)

        processed = cv2.dilate(bin_mask, v_kernel, iterations=1)
        processed = cv2.morphologyEx(processed, cv2.MORPH_CLOSE, h_kernel)

        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(processed, connectivity=8)

        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(processed, connectivity=8)

        staves = []
        for i in range(1, num_labels):
            x = stats[i, cv2.CC_STAT_LEFT]
            y = stats[i, cv2.CC_STAT_TOP]
            w = stats[i, cv2.CC_STAT_WIDTH]
            h = stats[i, cv2.CC_STAT_HEIGHT]

            if h >= self.min_height and w > target_w * self.min_width_ratio:
                # Scale coordinates to match original image/barline space
                bbox = BBox(
                    int(x * scale_x),
                    int(y * scale_y),
                    int((x + w) * scale_x),
                    int((y + h) * scale_y),
                )
                staves.append(Staff(bbox=bbox))

        # Sort by vertical position
        return sorted(staves, key=lambda s: s.bbox.y1)


class MeasureNumberingPipeline:
    """
    Integrated pipeline to assign measure numbers to a score
    using detected barlines and staff masks.
    """

    def __init__(self):
        self.extractor = StaffExtractor()
        self.builder = SystemBuilder()
        self.numberer = MeasureNumberer()

    def process_page(
        self,
        barline_boxes: List[List[int]],
        staff_mask_path: Path,
        image_size: Tuple[int, int],
        page_number: int = 1,
        assume_one_staff_per_system: bool = False,
        image: Optional[np.ndarray] = None,
        connector_evidence: Optional[Dict[Any, Any]] = None,
    ) -> Page:
        """
        Processes a single page and returns a populated Page object.
        """
        # 1. Extract Staves from mask
        staves = self.extractor.extract(staff_mask_path, image_size)

        # 2. Create Barline objects
        barlines = [Barline(bbox=BBox(*box)) for box in barline_boxes]

        # 3. Infer Systems
        if assume_one_staff_per_system:
            for i, staff in enumerate(staves):
                staff.system_index = i

        # 4. Group staves into systems and assign barlines
        # Image is passed for connectivity check in geometric grouping.
        # Connector evidence is generated upstream from durable proxy/symbol intermediates.
        systems = self.builder.build_systems(
            staves,
            barlines,
            image=image,
            connector_evidence=connector_evidence,
        )

        page = Page(
            systems=systems, page_number=page_number, width=image_size[0], height=image_size[1]
        )

        return page

    def run_sequential(self, page_data_list: List[dict], start_number: int = 1) -> Score:
        """
        Processes multiple pages sequentially, maintaining measure count.
        page_data_list elements should contain:
        - 'barlines': List of [x1, y1, x2, y2]
        - 'staff_mask': Path
        - 'image_size': (W, H)
        - 'page_number': int
        - 'image': Optional[np.ndarray] (Source image for connectivity checks)
        - 'connector_evidence': Optional structured system connector evidence
        """
        score = Score()
        for data in page_data_list:
            page = self.process_page(
                data["barlines"],
                Path(data["staff_mask"]),
                data["image_size"],
                data.get("page_number", 1),
                image=data.get("image"),
                connector_evidence=data.get("connector_evidence"),
            )
            score.pages.append(page)

        # Assign numbers across the entire score
        self.numberer.number_score(score, start_number=start_number)

        return score
