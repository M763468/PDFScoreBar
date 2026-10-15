"""Contracts for maintained-route staff strokes and independent stroke GT."""

import json
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from src.common.barline_strokes import (
    StaffRegion,
    deduplicate_staff_strokes,
    normalize_staff_stroke,
)
from src.pipeline.core import build_probe_run_id
from src.pipeline.steps.staff_strokes import prepare_staff_stroke_candidates

STAVES = [StaffRegion((0, 10, 200, 50), 10), StaffRegion((0, 80, 200, 120), 10)]


def test_split_composite_preserves_staff_membership_and_single_staff_tail():
    assert normalize_staff_stroke((20, 10, 24, 120), STAVES) == [
        (0, (20, 10, 24, 50)),
        (1, (20, 80, 24, 120)),
    ]
    # The rejected overhang ablation created new hard FPs: keep this unchanged.
    assert normalize_staff_stroke((20, 55, 24, 120), STAVES) == [(-1, (20, 55, 24, 120))]


def test_dedup_keeps_canonical_geometry_own_score_and_other_voice():
    rows = [
        {"bbox": [20, 10, 24, 50], "score": 0.6},
        {"bbox": [21, 10, 24, 50], "score": 0.99},
        {"bbox": [20, 80, 24, 120], "score": 0.9},
        {"bbox": [26, 10, 28, 50], "score": 0.8},
    ]
    kept, suppressed = deduplicate_staff_strokes(rows, unit_size=10)
    assert kept == [rows[0], rows[2], rows[3]]
    assert kept[0]["score"] == 0.6
    assert suppressed == [{"bbox": rows[1]["bbox"], "representative": rows[0]["bbox"]}]
    assert len(rows) == 4


@pytest.mark.parametrize("unit", [0, -1, float("nan"), float("inf")])
def test_invalid_unit_fails_explicitly(unit):
    with pytest.raises(ValueError):
        deduplicate_staff_strokes([], unit_size=unit)


def fixture_inputs(tmp_path, monkeypatch, regions=STAVES):
    image = tmp_path / "score" / "page_001.png"
    image.parent.mkdir()
    cv2.imwrite(str(image), np.full((140, 200, 3), 255, np.uint8))
    mask = tmp_path / "staff.png"
    cv2.imwrite(str(mask), np.zeros((140, 200), np.uint8))
    extracted = [
        SimpleNamespace(
            bbox=SimpleNamespace(x1=s.bbox[0], y1=s.bbox[1], x2=s.bbox[2], y2=s.bbox[3]),
            unit_size=s.unit_size,
        )
        for s in regions
    ]
    monkeypatch.setattr(
        "src.pipeline.steps.staff_strokes.StaffExtractor.extract", lambda *args: extracted
    )
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    # A composite HOMR seed was lost by whole-box consensus. Its lower piece
    # must re-enter only when the unchanged SR-or-OMR consensus supports it.
    (baseline / "page_001_detections.json").write_text(json.dumps([[20, 10, 24, 120]]))
    sr = tmp_path / "sr.json"
    omr = tmp_path / "omr.json"
    for path in (sr, omr):
        path.write_text(json.dumps([[20, 80, 24, 120]]))
    support = tmp_path / "hybrid/current_support/score/page_001/result.json"
    support.parent.mkdir(parents=True)
    support.write_text(
        json.dumps(
            dict(
                status="completed",
                current_homr_executed=True,
                image=str(image),
                current_sr_detection=str(sr),
                current_omr=str(omr),
            )
        )
    )
    inventory = tmp_path / "inventory.json"
    inventory.write_text(
        json.dumps(
            {
                "records": [
                    dict(
                        score="score",
                        page="page_001",
                        image=str(image),
                        staff_mask=str(mask),
                        run_dir=str(baseline),
                    )
                ]
            }
        )
    )
    target = (
        tmp_path
        / "probe"
        / build_probe_run_id(image, score_name="score")
        / "pipeline2_no_peak_candidates.json"
    )
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps([[60, 10, 64, 120]]))
    return inventory, support, target, image, omr


def test_adapter_restores_only_consensus_supported_staff_piece(tmp_path, monkeypatch):
    inv, support, target, image, _ = fixture_inputs(tmp_path, monkeypatch)
    units = prepare_staff_stroke_candidates(
        inventory=inv, hybrid_root=tmp_path / "hybrid", probe_root=tmp_path / "probe"
    )
    assert units == {str(image): 10}
    assert json.loads(target.read_text()) == [
        [20, 80, 24, 120],
        [60, 10, 64, 50],
        [60, 80, 64, 120],
    ]
    audit = json.loads(target.with_name("pipeline2_no_peak_staff_strokes.json").read_text())
    assert audit["coordinate_space"] == "source_page"
    assert audit["source_count"] == 1
    assert len(audit["input_sha256"]) == 6


def test_seed_without_either_consensus_source_is_not_restored(tmp_path, monkeypatch):
    inv, _, target, _, omr = fixture_inputs(tmp_path, monkeypatch)
    omr.write_text("[]")
    (tmp_path / "sr.json").write_text("[]")
    prepare_staff_stroke_candidates(
        inventory=inv, hybrid_root=tmp_path / "hybrid", probe_root=tmp_path / "probe"
    )
    assert [20, 80, 24, 120] not in json.loads(target.read_text())


def test_wrong_support_identity_fails_without_replacing_candidates(tmp_path, monkeypatch):
    inv, support, target, _, _ = fixture_inputs(tmp_path, monkeypatch)
    data = json.loads(support.read_text())
    data["image"] = "/wrong/image.png"
    support.write_text(json.dumps(data))
    before = target.read_bytes()
    with pytest.raises(ValueError, match="identity mismatch"):
        prepare_staff_stroke_candidates(
            inventory=inv, hybrid_root=tmp_path / "hybrid", probe_root=tmp_path / "probe"
        )
    assert target.read_bytes() == before


def test_blank_page_preserves_candidates_without_inventing_units(tmp_path, monkeypatch):
    inv, _, target, _, _ = fixture_inputs(tmp_path, monkeypatch, regions=[])
    before = target.read_bytes()
    assert (
        prepare_staff_stroke_candidates(
            inventory=inv, hybrid_root=tmp_path / "hybrid", probe_root=tmp_path / "probe"
        )
        == {}
    )
    assert target.read_bytes() == before


def test_scoring_preserves_raw_scores_and_default_behavior(tmp_path):
    import torch

    from src.pipeline.steps.cnn_scoring import _score_directory

    image = tmp_path / "page.png"
    cv2.imwrite(str(image), np.full((140, 200, 3), 255, np.uint8))
    boxes = [[20, 10, 24, 50], [21, 10, 24, 50], [20, 80, 24, 120]]
    (tmp_path / "pipeline2_no_peak_candidates.json").write_text(json.dumps(boxes))

    class Positive(torch.nn.Module):
        def forward(self, x):
            return torch.ones((len(x), 1))

    kwargs = dict(
        run_dir=tmp_path,
        image_path=image,
        model=Positive(),
        gpu_norm=torch.nn.Identity(),
        threshold=0.5,
        device=torch.device("cpu"),
        batch_size=4,
        apply_nms_enabled=False,
    )
    assert _score_directory(**kwargs)
    assert json.loads((tmp_path / "pipeline2_no_peak_filtered_cnn.json").read_text()) == boxes
    assert _score_directory(**kwargs, stroke_unit_size=10)
    assert json.loads((tmp_path / "pipeline2_no_peak_filtered_cnn.json").read_text()) == [
        boxes[0],
        boxes[2],
    ]
    assert all(
        r["score"] > 0.5
        for r in json.loads((tmp_path / "pipeline2_no_peak_scored.json").read_text())
    )


def test_composite_image_uses_producer_support_identity(tmp_path, monkeypatch):
    inv, support, target, image, _ = fixture_inputs(tmp_path, monkeypatch)
    renamed = image.with_name("OtherScore_page_001.png")
    image.rename(renamed)
    record = json.loads(inv.read_text())
    record["records"][0].update(image=str(renamed), score="OtherScore")
    inv.write_text(json.dumps(record))
    result = json.loads(support.read_text())
    result["image"] = str(renamed)
    new_support = support.parent.parent / renamed.stem / "result.json"
    new_support.parent.mkdir()
    new_support.write_text(json.dumps(result))
    baseline = tmp_path / "baseline"
    (baseline / "page_001_detections.json").rename(baseline / f"{renamed.stem}_detections.json")
    new_target = (
        target.parent.parent / build_probe_run_id(renamed, score_name="OtherScore") / target.name
    )
    new_target.parent.mkdir()
    target.rename(new_target)
    units = prepare_staff_stroke_candidates(
        inventory=inv, hybrid_root=tmp_path / "hybrid", probe_root=tmp_path / "probe"
    )
    assert units == {str(renamed): 10}
    assert [20, 80, 24, 120] in json.loads(new_target.read_text())


@pytest.mark.parametrize("profile, expected_calls", [("maintained_original", 1), ("stage_e", 0)])
def test_adapter_wiring_is_limited_to_maintained_dense_route(
    tmp_path, monkeypatch, profile, expected_calls
):
    from unittest.mock import Mock

    from src.pipeline.detection.dense_orchestrator import DetectorOrchestrator

    route = SimpleNamespace(probe_rescue_root=tmp_path / "probe", execution_summary={})
    monkeypatch.setattr(
        "src.pipeline.detector_routes.dense_full_pipeline.reconstruct_dense_full_pipeline_route",
        lambda **kwargs: route,
    )
    adapter = Mock(return_value={"image": 10})
    monkeypatch.setattr("src.pipeline.steps.staff_strokes.prepare_staff_stroke_candidates", adapter)
    detector = DetectorOrchestrator(
        config={"detection": {"homr_profile": profile, "detector_route": "dense_full_pipeline"}},
        images=[],
        run_id="test",
        run_dir=tmp_path,
        dry_run=False,
    )
    monkeypatch.setattr(
        detector, "_write_dense_inventory", lambda: (tmp_path / "inventory", tmp_path / "exclude")
    )
    detector.hybrid_output_dir = tmp_path / "hybrid"
    detector._run_dense_route()
    assert adapter.call_count == expected_calls
    assert detector._staff_stroke_units == ({"image": 10} if expected_calls else None)
