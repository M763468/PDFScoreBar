"""Issue #532: cover/blank pages pass the current x4 route as empty results.

Three cases from the Issue are kept apart:
1. a page without staff evidence (cover, blank) is a normal empty page;
2. a page with staff/notehead evidence but an empty HOMR result fails explicitly;
3. a score page with an incomplete connector pair is an artifact error.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.common.connector_artifacts import (
    connector_mask_paths,
    connector_mask_paths_for_numbering,
    non_score_page_marker_path,
    read_non_score_page_marker,
    write_non_score_page_marker,
)
from src.homr_runtime.empty_detection import (
    EMPTY_DETECTION_REASONS,
    MUSIC_EVIDENCE_WITHOUT_DETECTIONS,
    NON_SCORE_PAGE,
    UNVERIFIED_EMPTY_RESULT,
    HomrEmptyDetectionError,
    capture_empty_detections,
    classification_thresholds,
    classify_empty_detection,
    record_empty_detection,
    segmentation_evidence,
)
from src.pipeline.detection.current_homr_worker import (
    CurrentHomrEmptyResultError,
    _classify_page_content,
)
from src.pipeline.detection.current_support_worker import _require_current_homr_bundle

# HOMR segmentation keeps a fixed 1920 px width; the height follows the page.
SEG_SHAPE = (2700, 1920)


def _fragment(x: float, y: float) -> SimpleNamespace:
    return SimpleNamespace(center=(x, y))


def _staff_lines(mask: np.ndarray, *, top: int, x1: int, x2: int, spacing: int = 24) -> None:
    for line in range(5):
        y = top + line * spacing
        mask[y : y + 3, x1:x2] = 1


def _blank_page_evidence() -> dict:
    """A scanned blank page: border lines at the page edges, nothing inside."""

    staff = np.zeros(SEG_SHAPE, dtype=np.uint8)
    staff[10:14, :] = 1
    staff[-14:-10, :] = 1
    fragments = [_fragment(960, 12), _fragment(960, SEG_SHAPE[0] - 12)]
    return segmentation_evidence(staff, fragments, notehead_count=0)


def _empty_staff_evidence(width_fraction: float) -> dict:
    """One staff without any notes inside the page (Issue #532 case 2)."""

    staff = np.zeros(SEG_SHAPE, dtype=np.uint8)
    x1 = 200
    x2 = x1 + int(SEG_SHAPE[1] * width_fraction)
    _staff_lines(staff, top=1300, x1=x1, x2=x2)
    fragments = [_fragment((x1 + x2) / 2, 1300 + 24 * line) for line in range(5)]
    return segmentation_evidence(staff, fragments, notehead_count=0)


# --- evidence and classification -------------------------------------------------


def test_blank_page_with_scan_border_is_a_non_score_page() -> None:
    evidence = _blank_page_evidence()

    assert evidence["staff_mask_fraction"] > 0
    assert evidence["inner_staff_mask_fraction"] == 0.0
    assert evidence["inner_staff_fragment_count"] == 0
    assert classify_empty_detection(evidence) == NON_SCORE_PAGE


@pytest.mark.parametrize("width_fraction", [0.2, 0.5, 0.9])
def test_staff_without_noteheads_is_not_an_empty_page(width_fraction: float) -> None:
    evidence = _empty_staff_evidence(width_fraction)

    assert evidence["notehead_count"] == 0
    assert classify_empty_detection(evidence) == MUSIC_EVIDENCE_WITHOUT_DETECTIONS


def test_noteheads_without_staffs_is_not_an_empty_page() -> None:
    staff = np.zeros(SEG_SHAPE, dtype=np.uint8)
    evidence = segmentation_evidence(staff, [], notehead_count=4)

    assert classify_empty_detection(evidence) == MUSIC_EVIDENCE_WITHOUT_DETECTIONS


@pytest.mark.parametrize(
    "evidence",
    [None, {}, {"schema_version": "other"}, {"schema_version": "homr.empty_detection_evidence.v1"}],
)
def test_missing_or_unknown_evidence_is_unverified(evidence) -> None:
    assert classify_empty_detection(evidence) == UNVERIFIED_EMPTY_RESULT


def test_fragment_without_location_blocks_the_non_score_route() -> None:
    staff = np.zeros(SEG_SHAPE, dtype=np.uint8)
    evidence = segmentation_evidence(staff, [object()], notehead_count=0)

    assert evidence["unlocated_staff_fragment_count"] == 1
    assert classify_empty_detection(evidence) == MUSIC_EVIDENCE_WITHOUT_DETECTIONS


def test_empty_detection_error_keeps_the_homr_message() -> None:
    for reason in EMPTY_DETECTION_REASONS:
        error = HomrEmptyDetectionError(reason, _blank_page_evidence())
        assert isinstance(error, RuntimeError)
        assert str(error) == reason
    with pytest.raises(ValueError):
        HomrEmptyDetectionError("Something else", {})


def test_empty_detection_records_only_inside_capture(tmp_path: Path) -> None:
    error = HomrEmptyDetectionError("No noteheads found", _blank_page_evidence())
    record_empty_detection(tmp_path / "outside.png", error)  # no-op

    with capture_empty_detections() as records:
        record_empty_detection(tmp_path / "page_001_proxy.png", error)
        record_empty_detection(tmp_path / "plain.png", RuntimeError("No staffs found"))

    assert [record["reason"] for record in records] == ["No noteheads found", "No staffs found"]
    assert records[0]["evidence"]["schema_version"] == "homr.empty_detection_evidence.v1"
    assert records[1]["evidence"] is None


def test_predictor_keeps_empty_result_and_records_evidence(monkeypatch, tmp_path: Path) -> None:
    pytest.importorskip("homr")
    from src.homr_runtime import predictor

    image = tmp_path / "page_001_proxy.png"
    import cv2

    cv2.imwrite(str(image), np.full((40, 30, 3), 255, dtype=np.uint8))
    evidence = _blank_page_evidence()

    def no_noteheads(*_args, **_kwargs):
        raise HomrEmptyDetectionError("No noteheads found", evidence)

    monkeypatch.setattr(predictor, "detect_staffs_with_barlines", no_noteheads)
    with capture_empty_detections() as records:
        predictions, xml_path, shape, _, notehead_mask, staff_mask = predictor.run_homr_on_image(
            image, SimpleNamespace(), SimpleNamespace(), 0.0, {}, False
        )

    assert predictions == [] and xml_path is None and shape == (40, 30)
    assert not notehead_mask.any() and not staff_mask.any()
    assert records == [{"image": str(image), "reason": "No noteheads found", "evidence": evidence}]


# --- current HOMR worker page classification -------------------------------------


def _record(evidence) -> list[dict]:
    return [{"image": "page_001_proxy.png", "reason": "No noteheads found", "evidence": evidence}]


def _classify(tmp_path: Path, records, *, predictions: int = 0, present=None):
    return _classify_page_content(
        image=tmp_path / "page_001.png",
        stem="page_001",
        image_run_dir=tmp_path / "batch" / "page_001",
        empty_records=records,
        prediction_count=predictions,
        connector_present=present or {"symbols": False, "brace_dot": False},
    )


def test_normal_homr_result_stays_a_score_page(tmp_path: Path) -> None:
    content, empty, marker = _classify(tmp_path, [], predictions=12)

    assert (content, empty, marker) == ("score", None, None)
    assert not non_score_page_marker_path(tmp_path / "batch" / "page_001", "page_001").exists()


def test_cover_page_publishes_validated_marker(tmp_path: Path) -> None:
    content, empty, marker = _classify(tmp_path, _record(_blank_page_evidence()))

    assert content == NON_SCORE_PAGE
    assert empty["classification"] == NON_SCORE_PAGE
    assert empty["thresholds"] == classification_thresholds()
    payload = read_non_score_page_marker(marker, stem="page_001")
    assert payload["homr_reason"] == "No noteheads found"


def test_staff_page_without_noteheads_fails_explicitly(tmp_path: Path) -> None:
    with pytest.raises(CurrentHomrEmptyResultError, match="not a verified non-score page"):
        _classify(tmp_path, _record(_empty_staff_evidence(0.5)))
    assert not non_score_page_marker_path(tmp_path / "batch" / "page_001", "page_001").exists()


def test_empty_result_without_evidence_fails_explicitly(tmp_path: Path) -> None:
    with pytest.raises(CurrentHomrEmptyResultError, match="no segmentation evidence"):
        _classify(tmp_path, _record(None))


def test_non_score_page_rejects_predictions_or_connector_artifacts(tmp_path: Path) -> None:
    records = _record(_blank_page_evidence())
    with pytest.raises(CurrentHomrEmptyResultError, match="barline predictions"):
        _classify(tmp_path, records, predictions=1)
    with pytest.raises(CurrentHomrEmptyResultError, match="connector artifacts"):
        _classify(tmp_path, records, present={"symbols": True, "brace_dot": False})


def test_multiple_empty_records_for_one_page_fail(tmp_path: Path) -> None:
    records = _record(_blank_page_evidence()) * 2
    with pytest.raises(CurrentHomrEmptyResultError, match="2 empty results"):
        _classify(tmp_path, records)


# --- x4 support precondition: connector pair one/both missing, both present ------


def _homr_payload(tmp_path: Path, *, symbols: bool, brace_dot: bool, empty: bool = False) -> dict:
    run_dir = tmp_path / "current_homr" / "batch" / "page_001"
    run_dir.mkdir(parents=True, exist_ok=True)
    detection = run_dir / "page_001_detections.json"
    predictions = [] if empty else [{"pred_bbox": [1, 2, 3, 40]}]
    detection.write_text(json.dumps({"image": "page_001.png", "predictions": predictions}))
    staff = run_dir / "page_001_staff_mask.png"
    staff.write_bytes(b"staff")
    connectors = connector_mask_paths(run_dir, "page_001")
    if symbols:
        connectors["symbols"].write_bytes(b"symbols")
    if brace_dot:
        connectors["brace_dot"].write_bytes(b"brace_dot")
    return {
        "image": str(tmp_path / "page_001.png"),
        "page_content": "score",
        "current_sr_detection": str(detection),
        "staff_mask": str(staff),
        "connector_complete": symbols and brace_dot,
        "connector_present": {"symbols": symbols, "brace_dot": brace_dot},
        "connector_symbols": str(connectors["symbols"]) if symbols else None,
        "connector_brace_dot": str(connectors["brace_dot"]) if brace_dot else None,
    }


def _non_score_payload(tmp_path: Path) -> dict:
    payload = _homr_payload(tmp_path, symbols=False, brace_dot=False, empty=True)
    run_dir = Path(payload["staff_mask"]).parent
    evidence = _blank_page_evidence()
    marker = write_non_score_page_marker(
        run_dir,
        "page_001",
        image=payload["image"],
        reason="No noteheads found",
        evidence=evidence,
        thresholds=classification_thresholds(),
    )
    payload.update(
        {
            "page_content": NON_SCORE_PAGE,
            "non_score_page_marker": str(marker),
            "empty_detection": {
                "homr_reason": "No noteheads found",
                "classification": NON_SCORE_PAGE,
                "evidence": evidence,
            },
        }
    )
    return payload


def test_score_page_with_both_connectors_keeps_x4_support(tmp_path: Path) -> None:
    paths = _require_current_homr_bundle(_homr_payload(tmp_path, symbols=True, brace_dot=True))

    assert set(paths) == {"current_sr_detection", "staff_mask", "connector_symbols", "connector_brace_dot"}


@pytest.mark.parametrize("symbols,brace_dot", [(True, False), (False, True), (False, False)])
def test_score_page_with_missing_connector_is_an_artifact_error(
    tmp_path: Path, symbols: bool, brace_dot: bool
) -> None:
    payload = _homr_payload(tmp_path, symbols=symbols, brace_dot=brace_dot)

    with pytest.raises(RuntimeError, match="connector artifacts are incomplete"):
        _require_current_homr_bundle(payload)


def test_legacy_payload_without_page_content_keeps_strict_pair_contract(tmp_path: Path) -> None:
    payload = _homr_payload(tmp_path, symbols=True, brace_dot=False)
    del payload["page_content"]

    with pytest.raises(RuntimeError, match="complete connector semantic pair"):
        _require_current_homr_bundle(payload)


def test_non_score_page_passes_x4_support_without_connectors(tmp_path: Path) -> None:
    paths = _require_current_homr_bundle(_non_score_payload(tmp_path))

    assert set(paths) == {"current_sr_detection", "staff_mask", "non_score_page_marker"}


def test_non_score_page_requires_its_marker(tmp_path: Path) -> None:
    payload = _non_score_payload(tmp_path)
    Path(payload["non_score_page_marker"]).unlink()

    with pytest.raises(FileNotFoundError):
        _require_current_homr_bundle(payload)


def test_non_score_page_rejects_connectors_predictions_and_missing_evidence(
    tmp_path: Path,
) -> None:
    with_connector = _non_score_payload(tmp_path / "a")
    with_connector["connector_symbols"] = "symbols.png"
    with pytest.raises(RuntimeError, match="connector artifacts"):
        _require_current_homr_bundle(with_connector)

    with_predictions = _non_score_payload(tmp_path / "b")
    Path(with_predictions["current_sr_detection"]).write_text(
        json.dumps({"predictions": [{"pred_bbox": [0, 0, 1, 1]}]})
    )
    with pytest.raises(RuntimeError, match="barline predictions"):
        _require_current_homr_bundle(with_predictions)

    without_evidence = _non_score_payload(tmp_path / "c")
    without_evidence["empty_detection"] = {"classification": MUSIC_EVIDENCE_WITHOUT_DETECTIONS}
    with pytest.raises(RuntimeError, match="without non-score evidence"):
        _require_current_homr_bundle(without_evidence)


def test_unknown_page_content_is_rejected(tmp_path: Path) -> None:
    payload = _homr_payload(tmp_path, symbols=True, brace_dot=True)
    payload["page_content"] = "maybe_empty"

    with pytest.raises(ValueError, match="Unknown current-HOMR page_content"):
        _require_current_homr_bundle(payload)


# --- numbering consumer of the declared current_support tree ---------------------


def _hybrid_with_support(tmp_path: Path, stem: str) -> tuple[Path, Path]:
    hybrid = tmp_path / "hybrid"
    staff = hybrid / "baseline" / "batch" / stem / f"{stem}_proxy_debug_3_staff.png"
    staff.parent.mkdir(parents=True)
    staff.write_bytes(b"staff")
    support_dir = hybrid / "current_support" / "images" / stem / "artifacts" / "current_homr"
    run_dir = support_dir / "batch" / stem
    run_dir.mkdir(parents=True)
    return staff, run_dir


def test_numbering_accepts_declared_non_score_page_without_pair(tmp_path: Path) -> None:
    staff, run_dir = _hybrid_with_support(tmp_path, "page_001")
    write_non_score_page_marker(
        run_dir,
        "page_001",
        image="page_001.png",
        reason="No noteheads found",
        evidence=_blank_page_evidence(),
        thresholds=classification_thresholds(),
    )

    assert connector_mask_paths_for_numbering(staff) is None


def test_numbering_still_rejects_undeclared_missing_pair(tmp_path: Path) -> None:
    staff, run_dir = _hybrid_with_support(tmp_path, "page_002")
    # A marker for another page must not excuse this page.
    write_non_score_page_marker(
        run_dir.parent / "page_001",
        "page_001",
        image="page_001.png",
        reason="No noteheads found",
        evidence=_blank_page_evidence(),
        thresholds=classification_thresholds(),
    )

    with pytest.raises(RuntimeError, match="connector semantic pair is missing"):
        connector_mask_paths_for_numbering(staff)


def test_numbering_rejects_marker_next_to_partial_pair(tmp_path: Path) -> None:
    staff, run_dir = _hybrid_with_support(tmp_path, "page_001")
    write_non_score_page_marker(
        run_dir,
        "page_001",
        image="page_001.png",
        reason="No noteheads found",
        evidence=_blank_page_evidence(),
        thresholds=classification_thresholds(),
    )
    connector_mask_paths(run_dir, "page_001")["symbols"].write_bytes(b"symbols")

    with pytest.raises(RuntimeError, match="conflicts with connector artifacts"):
        connector_mask_paths_for_numbering(staff)


def test_numbering_rejects_invalid_marker(tmp_path: Path) -> None:
    staff, run_dir = _hybrid_with_support(tmp_path, "page_001")
    non_score_page_marker_path(run_dir, "page_001").write_text(json.dumps({"stem": "page_001"}))

    with pytest.raises(ValueError, match="Invalid non-score-page marker"):
        connector_mask_paths_for_numbering(staff)
