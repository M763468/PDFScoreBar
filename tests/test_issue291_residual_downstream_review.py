from pathlib import Path

from tools.issue291 import render_residual_downstream_review as review


def test_issue291_residual_registry_matches_corrected_contract() -> None:
    fp_boxes = [box for case in review.CASES if case.kind == "fp" for box in case.boxes]
    fn_boxes = [box for case in review.CASES if case.kind == "fn" for box in case.boxes]

    assert len(review.CASES) == 4
    assert len(fp_boxes) == 3
    assert len(fn_boxes) == 2
    assert (580, 4005, 584, 4115) in fp_boxes
    assert (2713, 3166, 2720, 3274) in fn_boxes
    assert (2715, 2481, 2720, 2582) in fn_boxes


def test_relevant_system_indices_selects_target_row() -> None:
    records = [
        {"system_index": 0, "bbox": (100, 100, 500, 200)},
        {"system_index": 0, "bbox": (500, 100, 900, 200)},
        {"system_index": 1, "bbox": (100, 400, 500, 500)},
        {"system_index": 1, "bbox": (500, 400, 900, 500)},
    ]

    assert review.relevant_system_indices(records, [(650, 430, 655, 470)]) == {1}


def test_resolve_recorded_path_rebases_workspace_path(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    expected = project_root / "logs" / "retained" / "numbering_final.json"
    expected.parent.mkdir(parents=True)
    expected.write_text("{}\n", encoding="utf-8")

    actual = review.resolve_recorded_path(
        "/workspace/logs/retained/numbering_final.json",
        roots=(),
        project_root=project_root,
    )

    assert actual == expected.resolve()
