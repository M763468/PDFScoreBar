from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from src.common.connector_artifacts import (
    connector_mask_paths_for_numbering,
    connector_mask_paths_for_staff_mask,
    describe_connector_artifacts,
    write_connector_masks,
)
from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.pipeline.detection.utils import resolve_paths_from_detection


def _write_mask(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    assert cv2.imwrite(str(path), np.zeros((20, 20), dtype=np.uint8))


def _probe_root(tmp_path: Path, stem: str) -> Path:
    probe_root = tmp_path / "probe"
    page_dir = probe_root / f"eval2_Score_{stem}"
    page_dir.mkdir(parents=True)
    (page_dir / "pipeline2_no_peak_filtered_cnn.json").write_text("[]\n", encoding="utf-8")
    return probe_root


def test_resolver_keeps_staff_geometry_and_numbering_finds_connector_semantics(
    tmp_path: Path,
) -> None:
    stem = "page_001"
    hybrid_root = tmp_path / "hybrid"

    debug_staff = hybrid_root / "sr" / "batch" / stem / f"{stem}_proxy_debug_3_staff.png"
    semantic_dir = (
        hybrid_root
        / "current_support"
        / "Score"
        / stem
        / "artifacts"
        / "current_homr"
        / "batch"
        / stem
    )
    semantic_staff = semantic_dir / f"{stem}_staff_mask.png"
    _write_mask(debug_staff)
    _write_mask(semantic_staff)
    written = write_connector_masks(
        semantic_dir,
        stem,
        {
            "symbols": np.zeros((10, 10), dtype=np.uint8),
            "brace_dot": np.zeros((10, 10), dtype=np.uint8),
        },
    )
    assert written is not None

    resolved = resolve_paths_from_detection(
        {"detection": {}},
        _probe_root(tmp_path, stem),
        hybrid_root,
        [stem],
        [tmp_path / "Score" / f"{stem}.png"],
    )

    staff_mask = Path(resolved[0]["staff_mask"])
    assert staff_mask == debug_staff
    assert connector_mask_paths_for_staff_mask(staff_mask) is None
    assert connector_mask_paths_for_numbering(staff_mask) == written
    assert describe_connector_artifacts(staff_mask)["source"] == "proxy_symbol_layers"


def test_numbering_measures_semantics_in_the_producer_staff_geometry(tmp_path: Path) -> None:
    stem = "page_001"
    hybrid_root = tmp_path / "hybrid"
    debug_staff = hybrid_root / "sr" / "batch" / stem / f"{stem}_proxy_debug_3_staff.png"
    semantic_dir = (
        hybrid_root
        / "current_support"
        / "Score"
        / stem
        / "artifacts"
        / "current_homr"
        / "batch"
        / stem
    )
    semantic_staff = semantic_dir / f"{stem}_staff_mask.png"

    debug_mask = np.zeros((240, 240), dtype=np.uint8)
    debug_mask[20:40, 80:220] = 255
    debug_mask[80:100, 80:220] = 255
    semantic_mask = np.zeros((240, 240), dtype=np.uint8)
    semantic_mask[100:120, 80:220] = 255
    semantic_mask[180:200, 80:220] = 255

    debug_staff.parent.mkdir(parents=True, exist_ok=True)
    semantic_staff.parent.mkdir(parents=True, exist_ok=True)
    assert cv2.imwrite(str(debug_staff), debug_mask)
    assert cv2.imwrite(str(semantic_staff), semantic_mask)

    symbols = np.zeros((240, 240), dtype=np.uint8)
    symbols[120:180, 70:76] = 255
    written = write_connector_masks(
        semantic_dir,
        stem,
        {
            "symbols": symbols,
            "brace_dot": np.zeros((240, 240), dtype=np.uint8),
        },
    )
    assert written is not None

    resolved = resolve_paths_from_detection(
        {"detection": {}},
        _probe_root(tmp_path, stem),
        hybrid_root,
        [stem],
        [tmp_path / "Score" / f"{stem}.png"],
    )
    staff_mask = Path(resolved[0]["staff_mask"])
    assert staff_mask == debug_staff

    pipeline = MeasureNumberingPipeline()
    captured: dict[str, object] = {}

    def capture_build(staves, barlines, image=None, connector_evidence=None):
        captured["geometry_y"] = [(staff.bbox.y1, staff.bbox.y2) for staff in staves]
        captured["connector_evidence"] = connector_evidence
        return []

    pipeline.builder.build_systems = capture_build
    page = pipeline.process_page([], staff_mask, (240, 240))

    assert page.systems == []
    geometry_y = captured["geometry_y"]
    assert geometry_y[0][0] < 50
    evidence = captured["connector_evidence"]
    assert evidence["staff_pairs"][0]["staff_pair"] == [0, 1]
    assert evidence["staff_pairs"][0]["left_connector_present"] is True


def test_resolver_keeps_debug_staff_fallback_without_semantic_pair(tmp_path: Path) -> None:
    stem = "page_001"
    hybrid_root = tmp_path / "hybrid"
    debug_staff = hybrid_root / "sr" / "batch" / stem / f"{stem}_proxy_debug_3_staff.png"
    stable_staff = hybrid_root / "baseline" / "batch" / stem / f"{stem}_staff_mask.png"
    _write_mask(debug_staff)
    _write_mask(stable_staff)

    resolved = resolve_paths_from_detection(
        {"detection": {}},
        _probe_root(tmp_path, stem),
        hybrid_root,
        [stem],
        [tmp_path / "Score" / f"{stem}.png"],
    )

    staff_mask = Path(resolved[0]["staff_mask"])
    assert staff_mask == debug_staff
    assert connector_mask_paths_for_numbering(staff_mask) is None
    assert describe_connector_artifacts(staff_mask)["source"] == "page_image_ink"
