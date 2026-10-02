import json

import pytest

from tools.review_correction.state import CorrectionState


def _state(tmp_path, *, movement=False, two_pages=False):
    root = tmp_path / "review"
    root.mkdir()
    (root / "source.png").write_bytes(b"source-a")
    (root / "numbering.json").write_text("{}", encoding="utf-8")
    handoff = root / "manual_correction_input.json"
    handoff.write_text('{"schema_version": 1}', encoding="utf-8")
    pages = [
        {
            "name": "page_001",
            "page": 0,
            "image": "source.png",
            "numbering": "numbering.json",
            "manual_outputs": {
                "mmr_measure_span": "corrections/mmr.json",
                "measure_construction": "corrections/measure.json",
            },
        }
    ]
    if two_pages:
        (root / "source_2.png").write_bytes(b"source-b")
        pages.append({**pages[0], "name": "page_002", "page": 1, "image": "source_2.png"})
    if movement:
        pages[0]["manual_outputs"]["movement_boundary"] = "corrections/movement_review.json"
        pages[0]["movement_boundary_resolved_output"] = "corrections/movement_resolved.json"
    return CorrectionState(root, pages, handoff), root


def _recorded(path, kind, items):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"schema_version": 1, "correction_type": kind, "items": items}),
        encoding="utf-8",
    )


def test_staged_edit_then_recorded_and_mixed_page_types(tmp_path):
    state, root = _state(tmp_path)
    state.set_pending(0, "mmr_measure_span", [{"page": 0, "op": "set_span"}])
    snap = state.snapshot()
    assert snap["states"][0]["edit_status"] == "pending"
    assert snap["states"][0]["recording_status"] == "not_recorded"

    _recorded(root / "corrections/mmr.json", "mmr_measure_span", [{"page": 0, "op": "set_span"}])
    state.note_record_success(0, "mmr_measure_span")
    _recorded(root / "corrections/measure.json", "measure_construction", [{"page": 0, "op": "insert"}])
    snap = state.snapshot()
    mmr = next(item for item in snap["states"] if item["correction_type"] == "mmr_measure_span")
    measure = next(item for item in snap["states"] if item["correction_type"] == "measure_construction")
    assert mmr["recording_status"] == measure["recording_status"] == "recorded"
    assert snap["package"]["counts"]["recorded"] == 2


def test_shared_correction_file_only_marks_the_page_with_recorded_items(tmp_path):
    state, root = _state(tmp_path, two_pages=True)
    _recorded(root / "corrections/mmr.json", "mmr_measure_span", [{"page": 0, "op": "set_span"}])
    per_page = {entry["page"]: entry for entry in state.snapshot()["states"] if entry["correction_type"] == "mmr_measure_span"}
    assert per_page["0"]["recording_status"] == "recorded"
    assert per_page["1"]["recording_status"] == "not_recorded"


def test_movement_boundary_is_recorded_immediately_and_identity_includes_finalized_output(tmp_path):
    state, root = _state(tmp_path, movement=True)
    _recorded(root / "corrections/movement_review.json", "movement_boundary", [{"page": 0, "op": "boundary"}])
    (root / "corrections/movement_resolved.json").write_text(
        '{"schema_version":"issue268.movement_boundaries.v1","boundaries":[{"page":0}]}',
        encoding="utf-8",
    )
    state.note_record_success(0, "movement_boundary")
    before = state.capture_identity()
    assert next(s for s in state.snapshot()["states"] if s["correction_type"] == "movement_boundary")["recording_status"] == "recorded"
    (root / "corrections/movement_resolved.json").write_text(
        '{"schema_version":"issue268.movement_boundaries.v1","boundaries":[]}',
        encoding="utf-8",
    )
    assert state.capture_identity()["corrections_identity"] != before["corrections_identity"]


def test_changed_or_removed_recorded_correction_stales_last_result(tmp_path):
    state, root = _state(tmp_path)
    correction = root / "corrections/mmr.json"
    _recorded(correction, "mmr_measure_span", [{"page": 0, "op": "set_span"}])
    identity = state.begin_apply()
    result = state.finish_apply(identity, corrected_run="run-1", final_pdf_sha256="abc")
    assert state.snapshot()["package"]["current_result"] == result

    correction.unlink()
    snap = state.snapshot()
    assert snap["states"][0]["application_status"] == "stale"
    assert snap["package"]["current_result"] is None
    assert snap["package"]["last_successful_result"] == result


def test_failed_record_and_apply_keep_previous_successful_result(tmp_path):
    state, root = _state(tmp_path)
    first = state.begin_apply()
    successful = state.finish_apply(first, corrected_run="run-1", final_pdf_sha256="abc")
    state.note_record_error(0, "mmr_measure_span", "disk full")
    state.fail_apply("engine failed")
    snap = state.snapshot()
    assert snap["package"]["last_successful_result"] == successful
    assert snap["package"]["current_result"] == successful
    assert snap["package"]["status"] == "error"
    assert {s["error"] for s in snap["states"]} == {"disk full", "engine failed"}
    state.note_record_success(0, "mmr_measure_span")
    retry = state.begin_apply()
    assert retry == state.capture_identity()
    state.fail_apply("retry failed")


def test_apply_cannot_start_with_pending_edits_and_stale_completion_keeps_success(tmp_path):
    state, root = _state(tmp_path)
    previous = state.begin_apply()
    prior_result = state.finish_apply(previous, corrected_run="run-1")
    state.set_pending(0, "mmr_measure_span", [{"page": 0}])
    with pytest.raises(ValueError, match="pending edits"):
        state.begin_apply()
    state.clear_pending(0, "mmr_measure_span")
    identity = state.begin_apply()
    (root / "source.png").write_bytes(b"source-b")
    with pytest.raises(ValueError, match="inputs changed"):
        state.finish_apply(identity, corrected_run="run-2")
    assert state.snapshot()["package"]["last_successful_result"] == prior_result
    assert state.snapshot()["package"]["status"] == "error"


def test_state_metadata_rejects_symlink(tmp_path):
    root = tmp_path / "review"
    (root / "corrections").mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text('{"schema_version":1,"last_successful_result":null}', encoding="utf-8")
    (root / "corrections" / ".correction_state.json").symlink_to(outside)
    handoff = root / "manual_correction_input.json"
    handoff.write_text('{"schema_version":1}', encoding="utf-8")
    with pytest.raises(ValueError, match="must not be a symlink"):
        CorrectionState(root, [], handoff)
