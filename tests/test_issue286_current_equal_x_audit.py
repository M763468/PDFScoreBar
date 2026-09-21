import subprocess
import sys
from pathlib import Path

from src.measure_numbering.types import Barline, BBox, Page, Staff, System
from tools.issue286.audit_current_full68_equal_x import (
    apply_selector,
    canonical_keys,
    contract_diff,
    groups,
    number,
    resolve_artifact,
    summarize as summarize_current,
)
from tools.issue286.audit_issue294_retained_equal_x import (
    geometry_signature,
    logical_signature,
    resolve_project_path,
    retained_project_root,
    retained_to_current_replay_difference,
    runtime_contract_drift,
    signature,
    summarize as summarize_issue294,
)


def _synthetic_page() -> Page:
    left_narrow = Barline(BBox(100, 0, 107, 40))
    left_wide = Barline(BBox(100, 50, 109, 90))
    right_top = Barline(BBox(300, 0, 307, 40))
    right_bottom = Barline(BBox(300, 50, 307, 90))
    top = Staff(BBox(90, 0, 400, 40), barlines=[left_narrow, right_top])
    bottom = Staff(BBox(90, 50, 400, 90), barlines=[left_wide, right_bottom])
    return Page(
        systems=[System(staves=[top, bottom])],
        page_number=1,
        width=400,
        height=100,
    )


def test_current_issue286_manifest_contract_has_68_pages() -> None:
    assert len(canonical_keys()) == 68


def test_exact_x_selectors_change_geometry_not_topology() -> None:
    page = _synthetic_page()

    narrow_page, _ = apply_selector(page, "narrower")
    wide_page, _ = apply_selector(page, "wider")

    narrow = number(narrow_page)
    wide = number(wide_page)

    narrow_measure = narrow["pages"][0]["systems"][0]["measures"][0]
    wide_measure = wide["pages"][0]["systems"][0]["measures"][0]

    assert narrow_measure["number"] == wide_measure["number"] == 1
    assert narrow_measure["bbox"][0] == 107
    assert wide_measure["bbox"][0] == 109


def test_selector_does_not_prune_distinct_x_near_duplicates() -> None:
    page = _synthetic_page()
    system = page.systems[0]
    system.staves[0].barlines.append(Barline(BBox(110, 0, 118, 40)))

    exact_x, _ = groups(system)
    assert 100 in exact_x
    assert 110 not in exact_x

    selected, _ = apply_selector(page, "staff_order_first")
    assert any(barline.bbox.x1 == 110 for barline in selected.systems[0].staves[0].barlines)


def test_contract_diff_reports_current_producer_drift() -> None:
    expected = {"detection": {"homr_profile": "maintained_original"}}
    actual = {"detection": {"homr_profile": "stage_e_verified"}}

    assert contract_diff(expected, actual) == [
        {
            "path": "$.detection.homr_profile",
            "expected": "maintained_original",
            "actual": "stage_e_verified",
        }
    ]


def test_workspace_manifest_paths_rebase_to_active_checkout(tmp_path: Path) -> None:
    resolved = resolve_artifact("/workspace/logs/example/result.json", project_root=tmp_path)

    assert resolved == (tmp_path / "logs/example/result.json").resolve()


def test_issue294_signature_preserves_empty_system_as_diagnostic() -> None:
    page = _synthetic_page()
    page.systems.append(System(staves=[Staff(BBox(90, 100, 400, 140))]))

    payload = signature(page)

    assert payload["pages"][0]["system_count"] == 2
    assert payload["pages"][0]["systems"][1]["measure_count"] == 0
    assert len(logical_signature(payload)["pages"][0]["systems"]) == 1


def test_issue294_geometry_signature_tracks_representative_bbox() -> None:
    page = _synthetic_page()
    narrow_page, _ = apply_selector(page, "narrower")
    wide_page, _ = apply_selector(page, "wider")

    narrow = signature(narrow_page)
    wide = signature(wide_page)

    assert logical_signature(narrow) == logical_signature(wide)
    assert geometry_signature(narrow) != geometry_signature(wide)
    assert geometry_signature(narrow)[0][0] == 107
    assert geometry_signature(wide)[0][0] == 109


def test_issue294_paths_rebase_to_retained_manifest_root(tmp_path: Path) -> None:
    retained_root = tmp_path / "retained"
    manifest = retained_root / "logs/issue294/run/full68_host.json"
    target = retained_root / "logs/issue294/child/report.json"
    manifest.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    manifest.write_text("{}\n", encoding="utf-8")
    target.write_text("{}\n", encoding="utf-8")

    inferred_root = retained_project_root(manifest)
    resolved = resolve_project_path(
        "/home/user/ws_PDFScoreBar_issue294/logs/issue294/child/report.json",
        artifact_roots=(inferred_root,),
    )

    assert inferred_root == retained_root
    assert resolved == target.resolve()


def test_issue286_audit_scripts_are_directly_executable() -> None:
    project_root = Path(__file__).resolve().parents[1]
    scripts = (
        "tools/issue286/audit_current_full68_equal_x.py",
        "tools/issue286/audit_issue294_retained_equal_x.py",
    )

    for script in scripts:
        result = subprocess.run(
            [sys.executable, script, "--help"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, (
            f"{script} failed as a direct CLI: stdout={result.stdout!r} "
            f"stderr={result.stderr!r}"
        )



def test_issue294_summary_separates_retained_replay_drift_from_selector_delta() -> None:
    page_key = ("Score", "page_001")
    selectors = {
        name: {
            "logical_equal_to_current_replay": True,
            "geometry_equal_to_current_replay": True,
        }
        for name in (
            "staff_order_first",
            "staff_order_last",
            "topmost",
            "bottommost",
            "narrower",
            "wider",
            "tallest",
            "shortest",
        )
    }
    summary = summarize_issue294(
        {
            page_key: {
                "equal_x_ties": [],
                "retained_to_current_replay": {
                    "logical_equal": False,
                    "geometry_equal": False,
                    "difference": {"page_differences": [{"page_index": 0}]},
                },
                "selectors": selectors,
            }
        }
    )

    assert summary["retained_to_current_replay_logical_mismatch_pages"] == [
        "Score/page_001"
    ]
    assert summary["retained_to_current_replay_geometry_mismatch_pages"] == [
        "Score/page_001"
    ]
    assert summary["retained_to_current_replay_difference_details"] == {
        "Score/page_001": {"page_differences": [{"page_index": 0}]}
    }
    for result in summary["selectors"].values():
        assert result["logical_changed_from_current_replay_pages"] == []
        assert result["geometry_changed_from_current_replay_pages"] == []


def test_issue294_retained_replay_difference_identifies_system_fields() -> None:
    retained = {
        "total_measures": 2,
        "pages": [
            {
                "page_number": 1,
                "system_count": 1,
                "total_measures": 2,
                "systems": [
                    {
                        "staff_count": 2,
                        "measure_count": 2,
                        "measure_numbers": [1, 2],
                        "measure_bboxes": [[0, 0, 10, 20], [10, 0, 20, 20]],
                    }
                ],
            }
        ],
    }
    replay = {
        "total_measures": 1,
        "pages": [
            {
                "page_number": 1,
                "system_count": 1,
                "total_measures": 1,
                "systems": [
                    {
                        "staff_count": 2,
                        "measure_count": 1,
                        "measure_numbers": [1],
                        "measure_bboxes": [[0, 0, 20, 20]],
                    }
                ],
            }
        ],
    }

    difference = retained_to_current_replay_difference(retained, replay)

    assert difference["retained_total_measures"] == 2
    assert difference["current_replay_total_measures"] == 1
    system = difference["page_differences"][0]["system_differences"][0]
    assert system["measure_count"] == {"retained": 2, "current_replay": 1}
    assert system["measure_numbers"] == {
        "retained": [1, 2],
        "current_replay": [1],
    }



def test_issue294_runtime_contract_drift_reports_wrong_or_missing_versions() -> None:
    drift = runtime_contract_drift(
        {
            "python_major_minor": "3.12",
            "packages": {
                "numpy": "0.0.0",
                "opencv-python-headless": "4.10.0.84",
            },
        }
    )

    assert {
        "component": "python_major_minor",
        "expected": "3.11",
        "actual": "3.12",
    } in drift
    assert {
        "component": "numpy",
        "expected": "1.26.4",
        "actual": "0.0.0",
    } in drift
    assert {
        "component": "scipy",
        "expected": "1.15.3",
        "actual": None,
    } in drift
    assert all(item["component"] != "opencv-python-headless" for item in drift)



def test_generic_issue286_summary_separates_replay_drift_from_selector_delta() -> None:
    selectors = {
        name: {
            "topology_equal_to_current_replay": True,
            "semantic_equal_to_current_replay": True,
        }
        for name in (
            "staff_order_first",
            "staff_order_last",
            "topmost",
            "bottommost",
            "narrower",
            "wider",
            "tallest",
            "shortest",
        )
    }
    summary = summarize_current(
        {
            ("Score", "page_001"): {
                "equal_x_ties": [],
                "retained_to_current_replay": {
                    "semantic_equal": False,
                    "topology_equal": False,
                },
                "selectors": selectors,
            }
        }
    )

    assert summary["retained_to_current_replay_semantic_mismatch_pages"] == [
        "Score/page_001"
    ]
    assert summary["retained_to_current_replay_topology_mismatch_pages"] == [
        "Score/page_001"
    ]
    for result in summary["selectors"].values():
        assert result["topology_changed_from_current_replay_pages"] == []
        assert result["semantic_changed_from_current_replay_pages"] == []



def test_issue286_exact_image_runner_has_valid_bash_syntax() -> None:
    project_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            "bash",
            "-n",
            "tools/issue286/run_issue294_retained_audit_container.sh",
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
