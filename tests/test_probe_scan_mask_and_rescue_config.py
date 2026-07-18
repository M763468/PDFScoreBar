import json
from pathlib import Path

import cv2
import numpy as np

from src.pipeline.core.config import load_yaml
from src.pipeline.detection.config import get_probe_kwargs
from src.pipeline.steps import probe_scan
from src.pipeline.steps.probe_scan import (
    _build_clef_mask_map,
    _extract_aligned_expansion_rescue_cfg,
)


def test_same_staff_mask_is_rejected_and_distinct_clef_is_retained(tmp_path: Path) -> None:
    staff = tmp_path / "page_004_staff_mask.png"
    clef = tmp_path / "page_004_clef_mask.png"
    staff.write_bytes(b"staff")
    clef.write_bytes(b"clef")

    assert _build_clef_mask_map(tmp_path, {"page_004": staff}) == {"page_004": clef}
    clef.unlink()
    assert _build_clef_mask_map(tmp_path, {"page_004": staff}) == {}


def test_aligned_rescue_defaults_off_and_extracts_without_probe_leakage() -> None:
    kwargs, cfg = _extract_aligned_expansion_rescue_cfg({"probe_width": 4})

    assert kwargs == {"probe_width": 4}
    assert cfg["enabled"] is False


def test_canonical_dense_config_enables_rescue() -> None:
    config = load_yaml(Path("configs/dense_full_pipeline.yaml"))
    kwargs = get_probe_kwargs(config["detection"])

    assert kwargs["aligned_expansion_rescue_enabled"] is True
    assert kwargs["aligned_expansion_preserve_raw"] is False


def _run_rescue_wiring_case(
    tmp_path: Path,
    monkeypatch,
    *,
    rescue_enabled: bool | None,
    preserve_raw: bool = False,
):
    image = tmp_path / "Score" / "page_001.png"
    image.parent.mkdir(parents=True)
    assert cv2.imwrite(str(image), np.full((20, 20), 255, dtype=np.uint8))

    bands = tmp_path / "bands" / "Score" / "page_001"
    bands.mkdir(parents=True)
    (bands / "pipeline2_no_peak_candidates.json").write_text("[[8, 4, 10, 12]]")

    scan_calls = []

    def fake_detect_probe_scan(**kwargs):
        scan_calls.append(kwargs)
        if kwargs.get("scan_disable_existing_suppression"):
            return [(8, 2, 10, 16), (8, 2, 10, 15)]
        return [(12, 4, 14, 12)]

    filter_calls = []

    def fake_filter_probe_candidates(*, candidates, **_kwargs):
        filter_calls.append(list(candidates))
        if len(filter_calls) == 1:
            return list(candidates), []
        return [], [
            {"bbox": [8, 2, 10, 16], "reasons": ["low_paper_overlap"]},
            {"bbox": [8, 2, 10, 15], "reasons": ["low_paper_overlap"]},
            {
                "bbox": [8, 2, 10, 16],
                "reasons": ["low_paper_overlap", "left_margin_zone"],
            },
        ]

    def fake_trim(_image, box, **_kwargs):
        if tuple(box) in {(8, 2, 10, 16), (8, 2, 10, 15)}:
            return (8, 3, 10, int(box[3]) - 1)
        return tuple(box)

    monkeypatch.setattr(probe_scan, "detect_probe_scan", fake_detect_probe_scan)
    monkeypatch.setattr(probe_scan, "filter_probe_candidates", fake_filter_probe_candidates)
    monkeypatch.setattr(probe_scan, "trim_box_to_ink", fake_trim)

    detect_kwargs = {"probe_width": 4}
    if rescue_enabled is not None:
        detect_kwargs["aligned_expansion_rescue_enabled"] = rescue_enabled
    if preserve_raw:
        detect_kwargs["aligned_expansion_preserve_raw"] = True

    output_root = tmp_path / "output"
    processed = probe_scan.run_probe_scan_batch(
        images=[image],
        output_root=output_root,
        bands_from=tmp_path / "bands",
        staff_mask_dir=None,
        clef_mask_dir=None,
        ink_threshold=180,
        min_height_ratio=0.0,
        min_width_ratio=0.0,
        detect_probe_kwargs=detect_kwargs,
        enable_heuristic_filters=True,
        disable_seed_splitting=True,
    )
    candidates = json.loads(
        next(output_root.glob("*/pipeline2_no_peak_candidates.json")).read_text()
    )
    return processed, scan_calls, filter_calls, candidates, output_root


def test_aligned_expansion_rescue_disabled_keeps_primary_wiring_and_candidates(
    tmp_path, monkeypatch
):
    default = _run_rescue_wiring_case(tmp_path / "default", monkeypatch, rescue_enabled=None)
    explicit_false = _run_rescue_wiring_case(tmp_path / "false", monkeypatch, rescue_enabled=False)

    for result in (default, explicit_false):
        processed, scan_calls, filter_calls, candidates, output_root = result
        assert processed == 1
        assert len(scan_calls) == 1
        assert len(filter_calls) == 1
        assert scan_calls[0].get("scan_disable_existing_suppression") is None
        assert candidates == [[8, 4, 10, 12], [12, 4, 14, 12]]
        assert not (output_root / "aligned_expansion_rescue_summary.json").exists()

    assert default[3] == explicit_false[3]


def test_aligned_expansion_rescue_adds_one_trimmed_candidate_without_removing_primary(
    tmp_path, monkeypatch
):
    processed, scan_calls, filter_calls, candidates, output_root = _run_rescue_wiring_case(
        tmp_path, monkeypatch, rescue_enabled=True
    )

    assert processed == 1
    assert len(scan_calls) == 2
    assert len(filter_calls) == 2
    assert scan_calls[0].get("scan_disable_existing_suppression") is None
    assert scan_calls[1]["scan_disable_existing_suppression"] is True
    assert scan_calls[1]["band_row_pad_ratio"] == 0.25
    assert candidates == [[8, 3, 10, 14], [8, 4, 10, 12], [12, 4, 14, 12]]

    summary = json.loads((output_root / "aligned_expansion_rescue_summary.json").read_text())
    assert summary["aligned_selection_count"] == 1
    assert summary["trimmed_addition_count"] == 1
    assert summary["max_additions_per_existing_box"] == 1
    assert summary["pages"][0]["sole_low_paper_overlap_candidate_count"] == 2


def test_aligned_expansion_rescue_preserves_raw_only_when_explicitly_enabled(tmp_path, monkeypatch):
    _processed, scan_calls, _filter_calls, candidates, output_root = _run_rescue_wiring_case(
        tmp_path, monkeypatch, rescue_enabled=True, preserve_raw=True
    )

    assert len(scan_calls) == 2
    assert [8, 2, 10, 15] in candidates
    assert [8, 3, 10, 14] not in candidates
    summary = json.loads((output_root / "aligned_expansion_rescue_summary.json").read_text())
    assert summary["preserve_raw"] is True
