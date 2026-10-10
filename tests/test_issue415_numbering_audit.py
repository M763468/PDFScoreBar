"""Semantic audit controls distinguish recognition, application, and reviewed GT."""

from copy import deepcopy

import pytest

from src.measure_numbering.numbering import MeasureNumberer
from src.measure_numbering.types import Barline, BBox, Page, Score, Staff, System, score_to_dict
from src.pipeline.steps.manual_corrections import apply_mmr_measure_span_corrections
from tools.issue415.audit_numbering import audit_pages, index_overrides, materialized_path


def page(numbers, terminal):
    return dict(
        pages=[
            dict(
                systems=[
                    dict(
                        measures=[
                            dict(number=n, bbox=[i * 20, 0, i * 20 + 19, 40])
                            for i, n in enumerate(numbers)
                        ]
                    )
                ]
            )
        ],
        numbering_metadata=dict(next_number=terminal),
    )


def entry(numbers, terminal, recognized=(), gt=(), name="page_001"):
    payload = page(numbers, terminal)
    return dict(
        page=name, base=deepcopy(payload), final=payload, recognized=list(recognized), gt=list(gt)
    )


def skip(measure, value):
    return dict(system=0, measure=measure, skip=value)


def test_terminal_rest_and_cross_page_application_separate_from_gt():
    a = entry([1, 2], 6, [skip(1, 3)], [skip(1, 1)])
    b = entry([6, 7], 10, [skip(1, 2)], [skip(1, 2)], "page_002")
    report = audit_pages([a, b])
    assert not report["application_errors"]
    assert not report["continuity_errors"]
    assert [
        (r["page"], r["measure"], r["applied_skip"]) for r in report["gt_increment_errors"]
    ] == [("page_001", 1, 3)]
    assert report["recognition"]["skip_mismatch"] == 1
    assert report["absolute_numbering_certified"] is False
    # Losing just the LAST measure's skip must not disappear at EOF.
    b["final"]["numbering_metadata"]["next_number"] = 8
    assert audit_pages([a, b])["application_errors"][0]["page"] == "page_002"


def test_zero_fixture_false_positive_is_not_hidden_by_event_only_scoring():
    report = audit_pages([entry([1, 4], 5, [skip(0, 2)])])
    assert report["recognition"]["unexpected_fp"] == 1
    assert report["gt_increment_errors"][0]["measure"] == 0
    assert not report["application_errors"]


def test_correct_recognition_wrong_application_and_empty_page_continuity():
    empty = entry([], 1, name="empty")
    wrong = entry([1, 2], 3, [skip(0, 2)], [skip(0, 2)])
    report = audit_pages([empty, wrong])
    assert report["application_errors"][0]["measure"] == 0
    assert report["recognition"]["matched_tp"] == 1
    wrong["final"]["pages"][0]["systems"][0]["measures"][0]["number"] = 8
    assert audit_pages([empty, wrong])["continuity_errors"]
    empty["final"]["numbering_metadata"]["next_number"] = 2
    assert audit_pages([empty])["continuity_errors"]


def test_reset_masks_difference_but_cannot_mask_wrong_reset_target_number():
    data = entry([1, 10, 11], 12, [skip(0, 4)], [skip(0, 4)])
    data["resets"] = [dict(system=0, measure=1, number=10)]
    report = audit_pages([data])
    assert not report["application_errors"]
    assert report["reset_masked"][0]["measure"] == 0
    data["resets"][0]["number"] = 1
    assert audit_pages([data])["continuity_errors"]


@pytest.mark.parametrize(
    "overrides", [[skip(9, 1)], [skip(0, 1), skip(0, 2)], [skip(0, -1)], [skip(0, True)]]
)
def test_audit_rejects_missing_duplicate_and_invalid_event_targets(overrides):
    with pytest.raises(ValueError):
        index_overrides(overrides, {(0, 0)})


def test_geometry_drift_cannot_be_rescored_as_same_experiment():
    data = entry([1], 2)
    data["final"]["pages"][0]["systems"][0]["measures"][0]["bbox"][0] = 1
    with pytest.raises(ValueError, match="geometry"):
        audit_pages([data])


def test_host_translation_of_retained_workspace_symlink(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    link = repo / "source"
    link.symlink_to("/workspace/data/source.png")
    assert materialized_path(link, repo) == repo / "data/source.png"


def system(y, count=2):
    return System(
        staves=[
            Staff(
                BBox(90, y, 950, y + 100),
                [Barline(BBox(x, y, x + 2, y + 100)) for x in [100, 300, 500][: count + 1]],
                unit_size=10,
            )
        ]
    )


@pytest.mark.parametrize(
    "operation, expected", [("suppress", [1, 2, 3]), ("set_measure_span", [1, 5, 6])]
)
def test_real_manual_precedence_then_numbering_with_empty_system_and_terminal_rest(
    operation, expected
):
    auto = [dict(page=0, system=0, measure=0, skip=9)]
    item = dict(op=operation, page=0, system=0, measure=0)
    if operation == "set_measure_span":
        item["measure_span"] = 4
    manual = dict(schema_version=1, correction_type="mmr_measure_span", items=[item])
    effective = apply_mmr_measure_span_corrections(auto, manual)
    # One-bar skip=0 is explicit and remains one bar. Last-page rest must consume
    # the extra span in next_number, even though no next measure exists.
    effective += [
        dict(page=0, system=0, measure=1, skip=0),
        dict(page=1, system=0, measure=0, skip=2),
    ]
    score = Score(
        pages=[Page(systems=[System(), system(100)]), Page(systems=[system(300, count=1)])]
    )
    terminal = MeasureNumberer().number_score(score, overrides=effective)
    payload = score_to_dict(score)
    numbers = [m["number"] for p in payload["pages"] for s in p["systems"] for m in s["measures"]]
    assert numbers == expected
    assert terminal == expected[-1] + 3


def test_real_manual_span_and_movement_reset_keep_page_identity():
    score = Score(
        pages=[
            Page(systems=[System(), system(100)]),
            Page(systems=[System(), system(300, count=1)]),
        ]
    )
    effective = apply_mmr_measure_span_corrections(
        [],
        dict(
            schema_version=1,
            correction_type="mmr_measure_span",
            items=[dict(op="set_measure_span", page=1, system=0, measure=0, measure_span=4)],
        ),
    )
    terminal = MeasureNumberer().number_score(
        score, overrides=effective, boundary_resets={(1, 0): 1}
    )
    payload = score_to_dict(score)
    assert [m["number"] for m in payload["pages"][0]["systems"][0]["measures"]] == [1, 2]
    assert payload["pages"][1]["systems"][0]["measures"][0]["number"] == 1
    assert terminal == 5


def test_row_sample_source_hash_and_physical_identity_are_required(tmp_path):
    import hashlib
    import json

    from tools.issue415.audit_numbering import audit_row_samples

    image = tmp_path / "source.png"
    image.write_bytes(b"original source identity")
    numbering = tmp_path / "final/score/outputs/page_001/numbering_final.json"
    numbering.parent.mkdir(parents=True)
    numbering.write_text(json.dumps(page([10], 11)))
    sample = dict(
        score="score",
        page="page_001",
        system=0,
        expected_row_start=1,
        source_image="source.png",
        source_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
        first_measure_bbox=[0, 0, 19, 40],
    )
    manifest = tmp_path / "samples.json"
    manifest.write_text(
        json.dumps(dict(schema_version="issue415.row_start_samples.v1", samples=[sample]))
    )
    report = audit_row_samples(tmp_path, tmp_path / "final", manifest)
    assert report["mismatches"][0]["actual_row_start"] == 10
    assert report["absolute_numbering_certified"] is False
    image.write_bytes(b"changed source")
    with pytest.raises(ValueError, match="SHA-256"):
        audit_row_samples(tmp_path, tmp_path / "final", manifest)
    image.write_bytes(b"original source identity")
    sample["first_measure_bbox"][0] = 2
    manifest.write_text(
        json.dumps(dict(schema_version="issue415.row_start_samples.v1", samples=[sample]))
    )
    with pytest.raises(ValueError, match="physical identity"):
        audit_row_samples(tmp_path, tmp_path / "final", manifest)


def test_consumers_reject_stale_combined_labels_and_foreign_numbering_path(tmp_path):
    import json

    from tools.issue415.audit_numbering import verify_consumers

    base = tmp_path / "final/score"
    files = {
        "outputs/page_001/numbering_final.json": page([1], 2),
        "outputs/numbering_final.json": page([1], 2),
        "review/corrected_final_summary.json": dict(
            final_pdf=str(base / "final.pdf"),
            pages=[
                dict(
                    page_id="page_001",
                    corrected_numbering_final=str(base / "outputs/page_001/numbering_final.json"),
                    row_labels=[dict(row_start_measure_number=1)],
                )
            ],
        ),
    }
    for name, data in files.items():
        path = base / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
    (base / "final.pdf").write_bytes(b"pixel check deferred")
    scores = [dict(score="score", pages=["page_001"])]
    assert (
        verify_consumers(tmp_path, tmp_path / "final", scores, pixels=False)["pdf_pixels_verified"]
        is False
    )
    combined = files["outputs/numbering_final.json"]
    combined["numbering_metadata"]["next_number"] = 7
    (base / "outputs/numbering_final.json").write_text(json.dumps(combined))
    with pytest.raises(ValueError, match="next_number"):
        verify_consumers(tmp_path, tmp_path / "final", scores, pixels=False)
    combined["numbering_metadata"]["next_number"] = 2
    (base / "outputs/numbering_final.json").write_text(json.dumps(combined))
    summary = files["review/corrected_final_summary.json"]
    summary["pages"][0]["row_labels"][0]["row_start_measure_number"] = 42
    (base / "review/corrected_final_summary.json").write_text(json.dumps(summary))
    with pytest.raises(ValueError, match="row label"):
        verify_consumers(tmp_path, tmp_path / "final", scores, pixels=False)
    summary["pages"][0]["row_labels"][0]["row_start_measure_number"] = 1
    summary["pages"][0]["corrected_numbering_final"] = str(tmp_path / "other.json")
    (base / "review/corrected_final_summary.json").write_text(json.dumps(summary))
    with pytest.raises(ValueError, match="another numbering"):
        verify_consumers(tmp_path, tmp_path / "final", scores, pixels=False)


def test_zero_skip_recognition_false_positive_still_fails_quality_gate():
    from tools.issue415.audit_numbering import correctness_failed

    result = audit_pages([entry([1], 2, [skip(0, 0)])])
    assert not result["gt_increment_errors"]
    aggregate = dict(
        application_errors=0,
        gt_increment_errors=0,
        continuity_errors=0,
        reset_masked=0,
        recognition=result["recognition"],
    )
    assert correctness_failed(dict(aggregate=aggregate, row_samples=dict(mismatches=[])))


def test_stale_page_start_metadata_is_separate_from_increment_correctness():
    data = entry([1, 2], 3)
    data["final"]["numbering_metadata"]["start_number"] = 9
    result = audit_pages([data])
    assert not result["application_errors"]
    assert result["continuity_errors"][0]["kind"] == "metadata_start"
