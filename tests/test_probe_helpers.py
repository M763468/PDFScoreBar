import numpy as np
import pytest

from src.pipeline.probe_detector.existing import ExistingBarlines
from src.pipeline.probe_detector.measurements import project_staff_band, select_signal_peaks
from src.pipeline.probe_detector.types import BandProjectionConfig


def test_existing_suppression_requires_vertical_overlap_and_preserves_nearest_band():
    boxes = [(9, 10, 11, 20), (11, 11, 13, 19), (9, 40, 11, 50)]
    existing = ExistingBarlines(
        boxes, x_merge_tol=4, min_vertical_iou=0.5, disable_suppression=False
    )
    assert existing.has_existing_for_suppression(10, 10, 20)
    assert not existing.has_existing_for_suppression(10, 0, 60)
    assert not existing.has_existing_for_suppression(30, 10, 20)
    assert existing.closest_existing_band(10, 10, 20) == (10, 20)
    assert existing.closest_existing_band(10, 25, 35) is None
    existing.disable_suppression = True
    assert existing.has_existing(10, 10, 20)
    assert not existing.has_existing_for_suppression(10, 10, 20)


def test_peak_ties_keep_leftmost_then_apply_distance_in_score_order():
    ratios = np.array([0.0, 0.8, 0.8, 0.0, 0.9, 0.0, 0.8, 0.0])
    count, selected = select_signal_peaks(
        ratios,
        effective_min=0.5,
        domain_x1=0,
        domain_x2=7,
        min_peak_distance=3,
        max_per_band=0,
    )
    assert count == 4
    assert selected == [(4, 0.9), (1, 0.8)]


def test_peak_domain_and_limit_are_applied_before_returning_selection():
    ratios = np.array([0.0, 0.8, 0.0, 0.9, 0.0, 1.0, 0.0])
    count, selected = select_signal_peaks(
        ratios,
        effective_min=0.5,
        domain_x1=0,
        domain_x2=4,
        min_peak_distance=1,
        max_per_band=1,
    )
    assert count == 2
    assert selected == [(3, 0.9)]
    assert select_signal_peaks(
        ratios,
        effective_min=1.1,
        domain_x1=0,
        domain_x2=6,
        min_peak_distance=1,
        max_per_band=0,
    ) == (0, [])


def _projection_config(**changes):
    from dataclasses import replace

    return replace(
        BandProjectionConfig(
            band_source="row_stats",
            band_scan_pad_ratio=0.0,
            band_scan_pad=0,
            band_row_pad_ratio=0.0,
            band_row_pad_staff_mult=0.0,
            staff_space=0.0,
            band_height_mode="staff",
            band_height_min=10,
            band_height_scale=1.0,
            extend_scale=1.0,
        ),
        **changes,
    )


def test_band_projection_keeps_domain_halo_and_extension_ratios():
    ink = np.zeros((40, 20), np.uint8)
    ink[8:22, 6] = 1
    projection = project_staff_band(
        ink,
        y1=10,
        y2=19,
        existing_boxes=[],
        global_height=0,
        kernel=np.ones(1, np.int32),
        width=1,
        x_domain=(4, 8),
        config=_projection_config(extend_scale=2.0),
    )
    assert (projection.band_y1, projection.band_y2, projection.band_h) == (10, 19, 10)
    assert (projection.ext_y1, projection.ext_y2) == (4, 24)
    assert (projection.top_h, projection.bottom_h) == (6, 5)
    assert projection.projected_columns == 7
    assert projection.ratios[6] == 1.0
    assert np.count_nonzero(projection.ratios) == 1
    assert projection.ext_ratios[6] == pytest.approx(14 / 21)
    assert projection.ext_top_ratios[6] == pytest.approx(2 / 6)
    assert projection.ext_bottom_ratios[6] == pytest.approx(2 / 5)


def test_row_padding_ratio_precedes_staff_padding_and_clips_at_image_boundary():
    projection = project_staff_band(
        np.ones((20, 12), np.uint8),
        y1=1,
        y2=10,
        existing_boxes=[],
        global_height=0,
        kernel=np.ones(1, np.int32),
        width=1,
        x_domain=(0, 11),
        config=_projection_config(
            band_row_pad_ratio=0.2, band_row_pad_staff_mult=10, staff_space=5
        ),
    )
    assert (projection.band_y1, projection.band_y2, projection.band_h) == (0, 12, 13)
    assert projection.ext_ratios is None
    assert projection.top_h == projection.bottom_h == 0
    np.testing.assert_array_equal(projection.ratios, np.ones(12))


def _candidate_scan_config(**changes):
    from dataclasses import replace

    from src.pipeline.probe_detector.types import CandidateScanConfig

    return replace(
        CandidateScanConfig(
            band_source="horiz_scan",
            band_scan_width=4,
            band_scan_line_ratio=0.5,
            band_scan_min_lines=100,
            extend_scale=1.0,
            save_row_profile=True,
            scan_center_on_peak=False,
            scan_fallback_pred_band=False,
            scan_peak_band_height=0,
            scan_x_peak_rescue=True,
            scan_x_peak_segment_height=5,
            scan_x_peak_segment_source="scan_band",
            scan_x_peak_ignore_staff_peak=True,
            scan_x_peak_ignore_radius=1,
            scan_x_peak_window=3,
            scan_x_peak_ratio_min=1.0,
        ),
        **changes,
    )


@pytest.mark.parametrize("fallback,expected_ignored", [(False, 2), (True, 0)])
def test_candidate_measurement_keeps_fallback_and_staff_peak_exclusion(fallback, expected_ignored):
    from src.pipeline.probe_detector.measurements import measure_candidate_scan

    ink = np.ones((40, 20), np.uint8)
    projection = project_staff_band(
        ink,
        y1=10,
        y2=19,
        existing_boxes=[],
        global_height=0,
        kernel=np.ones(1, np.int32),
        width=1,
        x_domain=(4, 12),
        config=_projection_config(),
    )
    measurement = measure_candidate_scan(
        ink,
        local_idx=8,
        pred_band=(12, 16),
        staff_band=(10, 19),
        x_domain=(4, 12),
        projection=projection,
        width=1,
        kernel=np.ones(1, np.int32),
        config=_candidate_scan_config(scan_fallback_pred_band=fallback),
    )
    assert measurement.scan_ratio == 1.0
    assert measurement.scan_x_peak_ratio == 1.0
    assert measurement.scan_x_peak_segment_pass == 1.0
    assert measurement.scan_peak_ratio_local == 1.0
    assert measurement.record_base["scan_x_peak_ignored_rows"] == expected_ignored
    assert measurement.record_base["scan_peak_row"] == 10
    assert measurement.record_base["scan_row_profile"] == [1.0] * 10
    # A fallback measurement is not falsely reported as a detected scan band.
    assert measurement.record_base["scan_band"] is None
    assert measurement.record_base["pred_band"] == [12, 16]
    assert measurement.record_base["scan_x_domain"] == [4, 12]


def test_develop_probe_debug_remains_opt_in_and_writes_artifacts(tmp_path):
    from src.pipeline.probe_detector import detect_probe_scan

    image = np.full((70, 100, 3), 255, np.uint8)
    image[15:45, 50:52] = 0
    mask = np.zeros(image.shape[:2], np.uint8)
    mask[15:45, :] = 1
    kwargs = dict(band_source="staff_mask", min_ratio=0.1)
    plain = detect_probe_scan(image, mask, [], **kwargs)
    path = tmp_path / "debug.png"
    debug = detect_probe_scan(image, mask, [], debug_path=path, **kwargs)
    assert debug == plain
    assert path.is_file() and path.with_suffix(".json").is_file()


def test_develop_wide_split_opt_in_calls_existing_implementation(tmp_path, monkeypatch):
    import cv2

    from src.pipeline.steps import probe_scan
    from src.pipeline.utils import wide_split_utils

    image = np.full((70, 100, 3), 255, np.uint8)
    image[15:45, 42:44] = 0
    image[15:45, 57:59] = 0
    path = tmp_path / "Score/page_001.png"
    path.parent.mkdir()
    cv2.imwrite(str(path), image)
    monkeypatch.setattr(probe_scan, "detect_probe_scan", lambda *a, **k: [(38, 15, 63, 45)])
    monkeypatch.setattr(probe_scan, "_load_bands_for_image", lambda **k: [(38, 15, 63, 45)])
    calls = []
    original = wide_split_utils.split_wide_candidates

    def observe(**kwargs):
        result = original(**kwargs)
        calls.append(result)
        return result

    monkeypatch.setattr(wide_split_utils, "split_wide_candidates", observe)
    count = probe_scan.run_probe_scan_batch(
        images=[path],
        output_root=tmp_path / "out",
        bands_from=None,
        staff_mask_dir=None,
        ink_threshold=180,
        min_height_ratio=0,
        min_width_ratio=0,
        disable_seed_splitting=True,
        detect_probe_kwargs={"post_split_wide_candidates": True},
    )
    assert count == 1 and len(calls) == 1


def test_develop_numbering_overlay_and_cli_entrypoint_remain_available(tmp_path):
    import subprocess
    import sys

    import cv2

    from src.measure_numbering.cli import render_overlay
    from src.measure_numbering.types import BBox, Measure, Page, Score, Staff, System

    path = tmp_path / "page.png"
    image = np.full((100, 120, 3), 255, np.uint8)
    cv2.imwrite(str(path), image)
    bbox = BBox(10, 30, 110, 80)
    score = Score(
        pages=[
            Page(
                systems=[
                    System(
                        staves=[Staff(bbox=bbox)],
                        measures=[Measure(number=1, start_bar=None, end_bar=None, bbox=bbox)],
                    )
                ]
            )
        ]
    )
    output = tmp_path / "overlay.png"
    render_overlay(score, path, output)
    assert output.is_file()
    assert np.any(cv2.imread(str(output)) != image)
    result = subprocess.run(
        [sys.executable, "-m", "src.measure_numbering.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "--output-overlay" in result.stdout
