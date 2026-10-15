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


@pytest.mark.parametrize("support_case", ["missing", "ambiguous", "same_physical_result"])
def test_symlink_support_requires_one_physical_verified_result(tmp_path, monkeypatch, support_case):
    import shutil

    inv, support, target, image, _ = fixture_inputs(tmp_path, monkeypatch)
    alias = tmp_path / "alias"
    alias.symlink_to(image.parent, target_is_directory=True)
    alias_image = alias / image.name
    data = json.loads(inv.read_text())
    data["records"][0]["image"] = str(alias_image)
    inv.write_text(json.dumps(data))
    renamed = target.parent.with_name(build_probe_run_id(alias_image))
    target.parent.rename(renamed)
    target = renamed / target.name
    before = target.read_bytes()
    other = support.parents[2] / alias.name / image.stem / "result.json"
    if support_case == "missing":
        support.unlink()
    else:
        other.parent.mkdir(parents=True)
        if support_case == "ambiguous":
            shutil.copyfile(support, other)
        else:
            other.symlink_to(support)
    kwargs = dict(inventory=inv, hybrid_root=tmp_path / "hybrid", probe_root=tmp_path / "probe")
    if support_case == "same_physical_result":
        assert prepare_staff_stroke_candidates(**kwargs) == {str(image.resolve()): 10}
    else:
        error = FileNotFoundError if support_case == "missing" else ValueError
        match = "Missing current-x4" if support_case == "missing" else "Ambiguous current-x4"
        with pytest.raises(error, match=match):
            prepare_staff_stroke_candidates(**kwargs)
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


@pytest.mark.parametrize("relative_image", [False, True])
@pytest.mark.parametrize("symlink_kind", [None, "directory", "file"])
@pytest.mark.parametrize("support_identity", ["original", "resolved"])
def test_composite_image_probe_adapter_cnn_connection(
    tmp_path, monkeypatch, relative_image, symlink_kind, support_identity
):
    import shutil

    import torch

    from src.pipeline.detection.dense_orchestrator import DetectorOrchestrator
    from src.pipeline.detector_routes.dense_full_pipeline import (
        load_route_image_paths,
        regenerate_probe_rescue_candidates,
    )
    from src.pipeline.steps import cnn_scoring

    _, support, _, image, _ = fixture_inputs(tmp_path, monkeypatch)
    renamed = tmp_path / "images/OtherScore_page_001.png"
    renamed.parent.mkdir()
    image.rename(renamed)
    if symlink_kind:
        alias = tmp_path / "alias"
        if symlink_kind == "directory":
            alias.symlink_to(renamed.parent, target_is_directory=True)
        else:
            alias.mkdir()
            stored = renamed.with_name("stored.png")
            renamed.rename(stored)
            (alias / renamed.name).symlink_to(stored)
        renamed = alias / renamed.name
    # Use the real inventory writer and probe producer. Do not fabricate the
    # adapter's candidate directory: that hid the previous run-ID mismatch.
    hybrid = tmp_path / "hybrid"
    baseline = hybrid / "baseline/batch" / renamed.stem
    baseline.parent.mkdir(parents=True)
    shutil.move(str(tmp_path / "baseline"), baseline)
    (baseline / "page_001_detections.json").rename(baseline / f"{renamed.stem}_detections.json")
    for suffix in ["staff_mask", "clef_mask"]:
        shutil.copyfile(tmp_path / "staff.png", baseline / f"{renamed.stem}_{suffix}.png")
    hybrid_results = hybrid / "hybrid_results"
    hybrid_results.mkdir()
    seeds = [[60, 10, 64, 50], [60, 80, 64, 120]]
    (hybrid_results / f"{renamed.stem}_hybrid.json").write_text(json.dumps(seeds))
    result = json.loads(support.read_text())
    result["image"] = str(renamed.resolve())
    producer_image = renamed.resolve() if support_identity == "resolved" else renamed
    new_support = (
        hybrid
        / "current_support"
        / producer_image.parent.name
        / producer_image.stem
        / "result.json"
    )
    new_support.parent.mkdir(parents=True)
    new_support.write_text(json.dumps(result))
    monkeypatch.chdir(tmp_path)
    image_arg = renamed.relative_to(tmp_path) if relative_image else renamed
    detector = DetectorOrchestrator(
        config={
            "detection": {
                "homr_profile": "maintained_original",
                "detector_route": "dense_full_pipeline",
                "cnn_model_manifest": "manifest.json",
                "cnn_threshold": 0.5,
                "cnn_apply_nms": False,
            }
        },
        images=[image_arg],
        run_id="test",
        run_dir=tmp_path / "run",
        dry_run=False,
    )
    detector.hybrid_output_dir = hybrid
    inventory, exclude = detector._write_dense_inventory()
    record = json.loads(inventory.read_text())["records"][0]
    assert (record["score"], record["page"]) == ("OtherScore", "page_001")
    assert record["image"] == str(renamed.absolute())
    # Reconstruction consumes the inventory paths, not the original image list.
    # Resolving here would silently change the producer's directory/stem again.
    route_images = load_route_image_paths(inventory=inventory, exclude=exclude, expected_pages=1)
    assert route_images == [renamed.absolute()]
    filtered = tmp_path / "filtered"
    seed_path = filtered / record["score"] / record["page"] / "pipeline2_no_peak_candidates.json"
    seed_path.parent.mkdir(parents=True)
    seed_path.write_text(json.dumps(seeds))
    probe = regenerate_probe_rescue_candidates(
        image_paths=route_images, filtered_root=filtered, route_root=tmp_path / "route"
    )
    candidate_files = list(probe.glob("*/pipeline2_no_peak_candidates.json"))
    assert len(candidate_files) == 1
    target = candidate_files[0]
    assert target.parent.name == f"eval2_{renamed.parent.name}_OtherScore_page_001"
    units = prepare_staff_stroke_candidates(
        inventory=inventory, hybrid_root=hybrid, probe_root=probe
    )
    assert units == {str(renamed.resolve()): 10}
    assert [20, 80, 24, 120] in json.loads(target.read_text())

    class Positive(torch.nn.Module):
        def forward(self, x):
            return torch.ones((len(x), 1))

    model_path = tmp_path / "model.pth"
    model_path.touch()
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr(
        "src.pipeline.detection.dense_orchestrator._resolve_verified_cnn_artifact",
        lambda *args, **kwargs: model_path,
    )
    monkeypatch.setattr(cnn_scoring, "_load_model", lambda *args: Positive())
    detector._dense_route = SimpleNamespace(filtered_root=filtered)
    detector.probe_output_dir = probe
    detector._staff_stroke_units = units
    detector._run_cnn_scoring()
    assert json.loads(target.with_name("pipeline2_no_peak_scored.json").read_text())
    assert json.loads(target.with_name("pipeline2_no_peak_filtered_cnn.json").read_text())
    assert target.with_name("pipeline2_no_peak_stroke_dedup.json").is_file()


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


@pytest.mark.parametrize("image_form", ["absolute", "relative", "symlink"])
def test_batch_scoring_resolves_units_and_writes_dedup_audit(tmp_path, monkeypatch, image_form):
    import torch

    from src.pipeline.steps import cnn_scoring

    image = tmp_path / "score/page_001.png"
    image.parent.mkdir()
    cv2.imwrite(str(image), np.full((140, 200, 3), 255, np.uint8))
    monkeypatch.chdir(tmp_path)
    if image_form == "relative":
        image_arg = image.relative_to(tmp_path)
    elif image_form == "symlink":
        alias = tmp_path / "alias"
        alias.symlink_to(image.parent, target_is_directory=True)
        image_arg = alias / image.name
    else:
        image_arg = image
    folder = tmp_path / "probe" / build_probe_run_id(image_arg, score_name="score")
    folder.mkdir(parents=True)
    boxes = [[20, 10, 24, 50], [21, 10, 24, 50], [20, 80, 24, 120]]
    (folder / "pipeline2_no_peak_candidates.json").write_text(json.dumps(boxes))

    class Positive(torch.nn.Module):
        def forward(self, x):
            return torch.ones((len(x), 1))

    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr(cnn_scoring, "_resolve_model_path", lambda _: tmp_path / "model")
    monkeypatch.setattr(cnn_scoring, "_load_model", lambda *args: Positive())
    assert (
        cnn_scoring.run_cnn_scoring_batch(
            probe_output_root=folder.parent,
            images=[image_arg],
            score_name="score",
            model_path=None,
            threshold=0.5,
            apply_nms_enabled=False,
            stroke_dedup_units={str(image.resolve()): 10},
        )
        == 1
    )
    assert json.loads((folder / "pipeline2_no_peak_filtered_cnn.json").read_text()) == [
        boxes[0],
        boxes[2],
    ]
    audit = json.loads((folder / "pipeline2_no_peak_stroke_dedup.json").read_text())
    assert audit == {
        "unit_size": 10,
        "suppressed": [{"bbox": boxes[1], "representative": boxes[0]}],
    }


@pytest.mark.parametrize("mixed", [False, True])
def test_unknown_staff_unit_preserves_whole_page_and_records_reason(tmp_path, monkeypatch, mixed):
    unknown = SimpleNamespace(bbox=(0, 80, 200, 120), unit_size=None)
    inv, _, target, _, _ = fixture_inputs(
        tmp_path, monkeypatch, regions=([STAVES[0]] if mixed else []) + [unknown]
    )
    before = target.read_bytes()
    assert (
        prepare_staff_stroke_candidates(
            inventory=inv, hybrid_root=tmp_path / "hybrid", probe_root=tmp_path / "probe"
        )
        == {}
    )
    assert target.read_bytes() == before
    audit = json.loads(target.with_name("pipeline2_no_peak_staff_strokes.json").read_text())
    assert audit["status"] == "no_staff_unit_size"
    assert audit["staff_count"] == (2 if mixed else 1)
    assert audit["unestimated_staff_count"] == 1


def test_real_one_line_percussion_mask_does_not_abort(tmp_path, monkeypatch):
    from src.measure_numbering.pipeline import StaffExtractor

    extract = StaffExtractor.extract
    inv, _, target, _, _ = fixture_inputs(tmp_path, monkeypatch)
    monkeypatch.setattr(StaffExtractor, "extract", extract)
    mask = np.zeros((140, 200), np.uint8)
    cv2.line(mask, (10, 50), (190, 50), 255, 2)
    mask_path = tmp_path / "staff.png"
    cv2.imwrite(str(mask_path), mask)
    staves = StaffExtractor().extract(mask_path, (200, 140))
    assert len(staves) == 1 and staves[0].unit_size is None
    before = target.read_bytes()
    assert (
        prepare_staff_stroke_candidates(
            inventory=inv, hybrid_root=tmp_path / "hybrid", probe_root=tmp_path / "probe"
        )
        == {}
    )
    assert target.read_bytes() == before
    audit = json.loads(target.with_name("pipeline2_no_peak_staff_strokes.json").read_text())
    assert audit["status"] == "no_staff_unit_size"


@pytest.mark.parametrize("candidates", [[], [None, [1, 2, 3]]])
@pytest.mark.parametrize("stroke_unit_size", [10, None])
def test_empty_scoring_replaces_or_clears_previous_dedup_audit(
    tmp_path, candidates, stroke_unit_size
):
    import torch

    from src.pipeline.steps.cnn_scoring import _score_directory

    image = tmp_path / "page.png"
    cv2.imwrite(str(image), np.full((140, 200, 3), 255, np.uint8))
    (tmp_path / "pipeline2_no_peak_candidates.json").write_text(json.dumps(candidates))
    audit = tmp_path / "pipeline2_no_peak_stroke_dedup.json"
    audit.write_text(json.dumps({"unit_size": 999, "suppressed": [{"bbox": [1, 2, 3, 4]}]}))

    class MustNotRun(torch.nn.Module):
        def forward(self, x):
            pytest.fail("Empty pages must not invoke CNN inference")

    assert _score_directory(
        run_dir=tmp_path,
        image_path=image,
        model=MustNotRun(),
        gpu_norm=torch.nn.Identity(),
        threshold=0.5,
        device=torch.device("cpu"),
        batch_size=4,
        apply_nms_enabled=False,
        stroke_unit_size=stroke_unit_size,
    )
    for name in ["pipeline2_no_peak_scored.json", "pipeline2_no_peak_filtered_cnn.json"]:
        assert json.loads((tmp_path / name).read_text()) == []
    if stroke_unit_size is None:
        assert not audit.exists()
    else:
        assert json.loads(audit.read_text()) == {"unit_size": 10, "suppressed": []}
