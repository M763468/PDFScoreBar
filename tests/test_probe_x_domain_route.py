import json
from unittest.mock import patch

import cv2
import numpy as np

from src.pipeline.detector_routes.dense_full_pipeline import regenerate_probe_rescue_candidates
from tools.verification.gt_preparation.generate_probe_candidates_from_inventory import _run_one


def test_inventory_generation_loads_staff_mask_for_row_stats_x_domain(tmp_path):
    image_path = tmp_path / "page_001.png"
    staff_mask_path = tmp_path / "page_001_staff_mask.png"
    existing_path = tmp_path / "hybrid.json"
    output_root = tmp_path / "out"

    image = np.full((100, 200, 3), 255, dtype=np.uint8)
    staff_mask = np.zeros((100, 200), dtype=np.uint8)
    staff_mask[20:41, 60:161] = 255
    assert cv2.imwrite(str(image_path), image)
    assert cv2.imwrite(str(staff_mask_path), staff_mask)
    existing_path.write_text(
        json.dumps({"predictions": [{"bbox": [100, 20, 104, 60]}]}),
        encoding="utf-8",
    )

    captured = {}

    def fake_detect_probe_scan(*, staff_mask, band_source, scan_stats, **kwargs):
        captured["mask_nonzero"] = int(np.count_nonzero(staff_mask))
        captured["band_source"] = band_source
        captured["kwargs"] = kwargs
        scan_stats.update(
            {
                "full_width_columns": 200,
                "eligible_domain_columns": 120,
                "projected_columns": 128,
            }
        )
        return []

    with patch(
        "tools.verification.gt_preparation.generate_probe_candidates_from_inventory.detect_probe_scan",
        side_effect=fake_detect_probe_scan,
    ):
        result = _run_one(
            record={
                "score": "Score",
                "page": "page_001",
                "image": str(image_path),
                "staff_mask": str(staff_mask_path),
                "hybrid_predictions": str(existing_path),
            },
            output_root=output_root,
            ink_threshold=240,
            min_ratio=0.6,
            min_height_ratio=0.006,
            min_width_ratio=0.0,
            probe_width=4,
            max_per_band=80,
            band_scan_line_ratio=0.6,
            band_scan_min_lines=5,
            band_source="row_stats",
            band_cluster_max_dist=25.0,
            scan_x_peak_rescue=True,
            scan_x_domain_mode="staff_mask",
            scan_x_domain_pad=None,
            scan_x_domain_pad_unit_ratio=1.0,
        )

    assert captured["mask_nonzero"] > 0
    assert captured["band_source"] == "row_stats"
    assert captured["kwargs"]["scan_x_domain_mode"] == "staff_mask"
    assert captured["kwargs"]["scan_x_domain_pad"] == 10
    assert result["scan_x_domain_mode"] == "staff_mask"
    assert result["probe_stats"]["eligible_domain_columns"] == 120


def test_dense_probe_rescue_forwards_x_domain_without_changing_y_band_source(tmp_path):
    route_root = tmp_path / "route"
    filtered_root = tmp_path / "filtered"
    filtered_root.mkdir()
    image = tmp_path / "page_001.png"
    mask = tmp_path / "page_001_staff_mask.png"

    with patch(
        "src.pipeline.detector_routes.dense_full_pipeline.run_probe_scan_batch",
        return_value=1,
    ) as mock_batch:
        regenerate_probe_rescue_candidates(
            image_paths=[image],
            filtered_root=filtered_root,
            route_root=route_root,
            probe_x_domain_kwargs={
                "scan_x_domain_mode": "staff_mask",
                "scan_x_domain_pad_unit_ratio": 1.0,
            },
            staff_mask_paths={"page_001": mask},
            collect_probe_stats=True,
        )

    kwargs = mock_batch.call_args.kwargs
    assert kwargs["detect_probe_kwargs"]["band_source"] == "row_stats"
    assert kwargs["detect_probe_kwargs"]["scan_x_domain_mode"] == "staff_mask"
    assert kwargs["detect_probe_kwargs"]["scan_x_domain_pad_unit_ratio"] == 1.0
    assert kwargs["staff_mask_paths"] == {"page_001": mask}
    assert kwargs["stats_summary_out"].name == "probe_scan_stats_summary.json"
