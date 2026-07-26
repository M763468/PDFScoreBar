from __future__ import annotations

import hashlib
from pathlib import Path

import cv2
import numpy as np

from src.common.connector_artifacts import (
    connector_mask_paths_for_staff_mask,
    describe_connector_artifacts,
    write_connector_masks,
)
from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.pipeline.core.manifest import build_manifest
from src.pipeline.detection.connector_artifacts import (
    capture_homr_threshold_masks,
    install_homr_connector_artifact_capture,
)


def _write_mask(path: Path, mask: np.ndarray) -> None:
    assert cv2.imwrite(str(path), mask)


def test_stable_connector_artifact_contract_records_hashes_and_shape(tmp_path: Path) -> None:
    staff_path = tmp_path / "score_staff_mask.png"
    symbols = np.zeros((120, 80), dtype=np.uint8)
    brace_dot = np.zeros((120, 80), dtype=np.uint8)
    symbols[20:80, 5:8] = 1
    brace_dot[30:90, 8:10] = 1

    _write_mask(staff_path, np.zeros((240, 160), dtype=np.uint8))
    written = write_connector_masks(
        tmp_path,
        "score",
        {"symbols": symbols, "brace_dot": brace_dot},
    )

    assert written is not None
    resolved = connector_mask_paths_for_staff_mask(staff_path)
    assert resolved == written

    description = describe_connector_artifacts(staff_path)
    assert description["source"] == "proxy_symbol_layers"
    assert description["coordinate_space"] == "homr_segmentation_mask"
    assert description["include_absent_pairs"] is True
    assert description["masks"]["symbols"]["shape"] == [120, 80]
    assert description["masks"]["brace_dot"]["shape"] == [120, 80]

    expected_hash = hashlib.sha256(written["symbols"].read_bytes()).hexdigest()
    assert description["masks"]["symbols"]["sha256"] == expected_hash


def test_missing_semantic_pair_keeps_explicit_page_image_fallback(tmp_path: Path) -> None:
    staff_path = tmp_path / "score_staff_mask.png"
    _write_mask(staff_path, np.zeros((20, 20), dtype=np.uint8))
    _write_mask(tmp_path / "score_connector_symbols.png", np.zeros((10, 10), dtype=np.uint8))

    assert connector_mask_paths_for_staff_mask(staff_path) is None
    description = describe_connector_artifacts(staff_path)
    assert description == {
        "source": "page_image_ink",
        "coordinate_space": "page_image",
        "include_absent_pairs": False,
        "masks": {},
    }


def test_numbering_auto_resolves_connector_masks_from_staff_mask_siblings(
    tmp_path: Path,
) -> None:
    staff_path = tmp_path / "score_staff_mask.png"
    staff_mask = np.zeros((200, 200), dtype=np.uint8)
    staff_mask[30:50, 20:180] = 255
    _write_mask(staff_path, staff_mask)
    write_connector_masks(
        tmp_path,
        "score",
        {
            "symbols": np.zeros((100, 100), dtype=np.uint8),
            "brace_dot": np.zeros((100, 100), dtype=np.uint8),
        },
    )

    pipeline = MeasureNumberingPipeline()
    captured: dict[str, object] = {}

    def fake_extract_from_mask_maps(staves, image_size, **kwargs):
        captured.update(kwargs)
        return {"generated": True, "source": "proxy_symbol_layers", "staff_pairs": []}

    pipeline.connector_extractor.extract_from_mask_maps = fake_extract_from_mask_maps
    pipeline.builder.build_systems = lambda *args, **kwargs: []

    page = pipeline.process_page([], staff_path, (200, 200), image=np.full((200, 200), 255))

    assert page.systems == []
    paths = captured["connector_mask_paths"]
    assert paths == {
        "symbols": tmp_path / "score_connector_symbols.png",
        "brace_dot": tmp_path / "score_connector_brace_dot.png",
    }


def test_manifest_records_the_same_connector_contract(tmp_path: Path) -> None:
    staff_path = tmp_path / "score_staff_mask.png"
    _write_mask(staff_path, np.zeros((20, 20), dtype=np.uint8))
    write_connector_masks(
        tmp_path,
        "score",
        {
            "symbols": np.zeros((10, 10), dtype=np.uint8),
            "brace_dot": np.zeros((10, 10), dtype=np.uint8),
        },
    )

    manifest = build_manifest(
        {},
        run_id="issue254",
        run_dir=tmp_path,
        images=[tmp_path / "score.png"],
        page_ids=["page_001"],
        page_runs=["score"],
        resolved=[{"barlines_json": "barlines.json", "staff_mask": str(staff_path)}],
        commands=[],
        page_statuses=[],
        barline_override_stats={},
    )

    connector = manifest["pages"][0]["connector_evidence"]
    assert connector["source"] == "proxy_symbol_layers"
    assert connector["coordinate_space"] == "homr_segmentation_mask"
    assert connector["include_absent_pairs"] is True


def test_capture_boundary_collects_masks_even_when_debug_writer_does_nothing() -> None:
    class FakeDebug:
        def write_threshold_image(self, suffix, image):
            return None

    symbols = np.ones((4, 5), dtype=np.uint8)
    brace_dot = np.eye(4, 5, dtype=np.uint8)
    debug = FakeDebug()

    with capture_homr_threshold_masks(FakeDebug) as captured:
        debug.write_threshold_image("symbols", symbols)
        debug.write_threshold_image("brace_dot", brace_dot)
        debug.write_threshold_image("staff", symbols)

    assert np.array_equal(captured["symbols"], symbols)
    assert np.array_equal(captured["brace_dot"], brace_dot)
    assert set(captured) == {"symbols", "brace_dot"}


def test_predictor_wrapper_persists_stable_masks_without_changing_return_value(
    tmp_path: Path,
) -> None:
    class FakeDebug:
        def write_threshold_image(self, suffix, image):
            return None

    class FakePredictor:
        def predict(
            self,
            image_path,
            xml_args,
            sr_scale=1,
            timeout_s=0.0,
            image_run_dir=None,
        ):
            debug = FakeDebug()
            debug.write_threshold_image("symbols", np.ones((6, 7), dtype=np.uint8))
            debug.write_threshold_image("brace_dot", np.ones((6, 7), dtype=np.uint8))
            return ("unchanged", sr_scale, timeout_s)

    # Install against the test class, then provide its Debug class explicitly through the
    # capture function used by the wrapper.
    import src.pipeline.detection.connector_artifacts as module

    original_capture = module.capture_homr_threshold_masks
    module.capture_homr_threshold_masks = lambda: original_capture(FakeDebug)
    try:
        assert install_homr_connector_artifact_capture(FakePredictor)
        result = FakePredictor().predict(
            tmp_path / "score.png",
            object(),
            sr_scale=2,
            timeout_s=3.0,
            image_run_dir=tmp_path,
        )
    finally:
        module.capture_homr_threshold_masks = original_capture

    assert result == ("unchanged", 2, 3.0)
    assert (tmp_path / "score_connector_symbols.png").is_file()
    assert (tmp_path / "score_connector_brace_dot.png").is_file()
