import copy
import hashlib
from pathlib import Path

import pytest

from tools.issue255.full68_restoration import (
    EXPECTED_CURRENT_GT_METRICS,
    canonical_pages,
    inventory_from_upstream_report,
    metric_mismatches,
    validate_upstream_report,
)


def _artifact(path: Path) -> dict[str, object]:
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _full_report(tmp_path: Path) -> dict[str, object]:
    artifact_files = {}
    for name in (
        "image",
        "fresh_baseline",
        "fresh_sr_x4_image",
        "public_profile_sr",
        "current_omr",
        "restored_hybrid",
        "staff_mask",
        "clef_mask",
    ):
        path = tmp_path / f"{name}.dat"
        path.write_bytes(name.encode())
        artifact_files[name] = _artifact(path)

    pages = {}
    for page in canonical_pages():
        pages[page["key"]] = {
            "status": "completed",
            "score": page["score"],
            "page": page["page"],
            "historical_artifact_used_as_runtime_input": False,
            "detector_input_contract": {
                "mode": "fresh_upstream",
                "fresh_upstream_authoritative": True,
                "override_keys": [],
                "schema_version": "pipeline.detector_input_contract.v1",
            },
            "artifacts": copy.deepcopy(artifact_files),
        }
    return {
        "status": "completed",
        "authoritative_full68": True,
        "historical_artifact_used_as_runtime_input": False,
        "pages": pages,
    }


def test_canonical_pages_are_68_and_unique() -> None:
    pages = canonical_pages()

    assert len(pages) == 68
    assert len({page["key"] for page in pages}) == 68
    assert all(Path(page["image"]).name == f"{page['page']}.png" for page in pages)


def test_validate_upstream_report_accepts_required_fresh_fields_with_metadata(
    tmp_path: Path,
) -> None:
    report = _full_report(tmp_path)

    pages = validate_upstream_report(report)

    assert len(pages) == 68


def test_validate_upstream_report_rejects_historical_runtime_dependency(
    tmp_path: Path,
) -> None:
    report = _full_report(tmp_path)
    report["historical_artifact_used_as_runtime_input"] = True

    with pytest.raises(ValueError, match="Historical runtime artifact dependency"):
        validate_upstream_report(report)


def test_validate_upstream_report_rejects_changed_artifact(tmp_path: Path) -> None:
    report = _full_report(tmp_path)
    first_page = next(iter(report["pages"].values()))
    image_path = Path(first_page["artifacts"]["image"]["path"])
    image_path.write_bytes(b"changed-after-report")

    with pytest.raises(ValueError, match="Artifact hash mismatch"):
        validate_upstream_report(report)


def test_inventory_from_upstream_report_preserves_canonical_page_identity(
    tmp_path: Path,
) -> None:
    report = _full_report(tmp_path)

    inventory = inventory_from_upstream_report(report)

    assert len(inventory) == 68
    assert inventory[0]["score"] == canonical_pages()[0]["score"]
    assert inventory[0]["page"] == canonical_pages()[0]["page"]
    assert inventory[0]["hybrid_predictions"].endswith("restored_hybrid.dat")


def test_metric_mismatches_accepts_current_gt_historical_target() -> None:
    assert metric_mismatches(EXPECTED_CURRENT_GT_METRICS) == {}


def test_metric_mismatches_reports_changed_detector_metric() -> None:
    actual = dict(EXPECTED_CURRENT_GT_METRICS)
    actual["fp"] = 2

    assert metric_mismatches(actual) == {"fp": {"expected": 1, "actual": 2}}
