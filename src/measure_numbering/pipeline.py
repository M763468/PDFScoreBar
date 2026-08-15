import logging
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

import cv2
import numpy as np

from src.common.connector_artifacts import connector_mask_paths_for_numbering

from .connector_aware_builder import ConnectorAwareSystemBuilder
from .connector_evidence import SystemConnectorEvidenceExtractor
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

        _, bin_mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)

        v_kernel = np.ones((20, 1), np.uint8)
        h_kernel = np.ones((1, 50), np.uint8)

        processed = cv2.dilate(bin_mask, v_kernel, iterations=1)
        processed = cv2.morphologyEx(processed, cv2.MORPH_CLOSE, h_kernel)

        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(processed, connectivity=8)

        staves = []
        for i in range(1, num_labels):
            x = stats[i, cv2.CC_STAT_LEFT]
            y = stats[i, cv2.CC_STAT_TOP]
            w = stats[i, cv2.CC_STAT_WIDTH]
            h = stats[i, cv2.CC_STAT_HEIGHT]

            if h >= self.min_height and w > target_w * self.min_width_ratio:
                bbox = BBox(
                    int(x * scale_x),
                    int(y * scale_y),
                    int((x + w) * scale_x),
                    int((y + h) * scale_y),
                )
                staves.append(Staff(bbox=bbox))

        return sorted(staves, key=lambda s: s.bbox.y1)


class MeasureNumberingPipeline:
    """Integrated pipeline to assign measure numbers to a score."""

    def __init__(self):
        self.extractor = StaffExtractor()
        self.connector_extractor = SystemConnectorEvidenceExtractor()
        self.builder = ConnectorAwareSystemBuilder()
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
        connector_masks: Optional[Mapping[str, np.ndarray]] = None,
        connector_mask_paths: Optional[Mapping[str, Path | str]] = None,
        connector_evidence_output_path: Optional[Path] = None,
    ) -> Page:
        staves = self.extractor.extract(staff_mask_path, image_size)

        if connector_evidence is None and not connector_masks and not connector_mask_paths:
            connector_mask_paths = connector_mask_paths_for_numbering(staff_mask_path)

        if connector_evidence is None:
            if connector_masks or connector_mask_paths:
                evidence_staves = self._connector_evidence_staves(
                    staves,
                    staff_mask_path,
                    image_size,
                    connector_mask_paths,
                )
                connector_evidence = self.connector_extractor.extract_from_mask_maps(
                    evidence_staves,
                    image_size,
                    connector_masks=connector_masks,
                    connector_mask_paths=connector_mask_paths,
                )
            elif image is not None:
                connector_evidence = self.connector_extractor.extract(
                    staves,
                    image_size,
                    symbol_mask=self._image_to_connector_mask(image),
                    source="page_image_ink",
                    include_absent_pairs=False,
                    connector_density_threshold=0.01,
                )

        if connector_evidence is not None and connector_evidence_output_path is not None:
            self.connector_extractor.write_json(connector_evidence, connector_evidence_output_path)

        barlines = [Barline(bbox=BBox(*box)) for box in barline_boxes]

        if assume_one_staff_per_system:
            for i, staff in enumerate(staves):
                staff.system_index = i

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
        score = Score()
        for data in page_data_list:
            page = self.process_page(
                data["barlines"],
                Path(data["staff_mask"]),
                data["image_size"],
                data.get("page_number", 1),
                image=data.get("image"),
                connector_evidence=data.get("connector_evidence"),
                connector_masks=data.get("connector_masks"),
                connector_mask_paths=data.get("connector_mask_paths"),
                connector_evidence_output_path=data.get("connector_evidence_output_path"),
            )
            score.pages.append(page)

        self.numberer.number_score(score, start_number=start_number)

        return score

    def _connector_evidence_staves(
        self,
        geometry_staves: List[Staff],
        staff_mask_path: Path,
        image_size: Tuple[int, int],
        connector_mask_paths: Optional[Mapping[str, Path | str]],
    ) -> List[Staff]:
        """Measure semantic masks against the staff geometry from the same producer.

        The selected Proxy/SR staff geometry remains authoritative for system
        construction. When connector masks are resolved from current-HOMR support,
        use the sibling current-HOMR staff mask only to define connector-evidence
        ROIs, then apply that ordered pair evidence to the unchanged numbering
        geometry.
        """
        if not connector_mask_paths:
            return geometry_staves

        symbols_value = connector_mask_paths.get("symbols")
        if symbols_value is None:
            symbols_value = connector_mask_paths.get("symbol")
        if symbols_value is None:
            return geometry_staves

        symbols_path = Path(symbols_value)
        suffix = "_connector_symbols.png"
        if not symbols_path.name.endswith(suffix):
            return geometry_staves

        stem = symbols_path.name[: -len(suffix)]
        semantic_staff_path = symbols_path.with_name(f"{stem}_staff_mask.png")
        if semantic_staff_path == staff_mask_path or not semantic_staff_path.is_file():
            return geometry_staves

        semantic_staves = self.extractor.extract(semantic_staff_path, image_size)
        if len(semantic_staves) != len(geometry_staves):
            logger.warning(
                "Connector semantic staff count mismatch for %s: geometry=%d semantic=%d; "
                "keeping numbering geometry for evidence",
                staff_mask_path,
                len(geometry_staves),
                len(semantic_staves),
            )
            return geometry_staves

        return semantic_staves

    def _image_to_connector_mask(self, image: np.ndarray) -> np.ndarray:
        if image.ndim == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        if gray.size == 0:
            return gray.astype(np.uint8)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        return binary
