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
)
from tools.issue286.audit_issue294_retained_equal_x import (
    geometry_signature,
    logical_signature,
    resolve_project_path,
    retained_project_root,
    signature,
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
