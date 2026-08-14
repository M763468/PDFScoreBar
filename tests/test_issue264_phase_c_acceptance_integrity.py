from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools.issue264.phase_c_acceptance_integrity import (
    REQUIRED_NON_INDEX_GATES,
    validate_resume_contract,
    verify_source_report,
)
from tools.issue264.rescore_phase_c_mmr_geometry_rebased import (
    _artifact_path,
    _verify_source_acceptance,
)


def _detail(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    return {
        "path": str(path),
        "size": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _source_report(
    path: Path,
    *,
    invocation_id: str = "invocation-current",
    git_head: str = "head-current",
) -> dict[str, object]:
    gates = {name: True for name in REQUIRED_NON_INDEX_GATES}
    gates.update(
        {
            "unexpected_fp_zero": False,
            "missed_fn_not_above_3": False,
            "skip_mismatch_not_above_6": False,
        }
    )
    payload: dict[str, object] = {
        "repository": {"git_head": git_head},
        "gates": gates,
        "acceptance_provenance": {
            "invocation_id": invocation_id,
            "producer_contract": {"git_head": git_head, "contract": "current"},
        },
        "generated_artifacts": [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def test_artifact_path_accepts_bytes_matching_recorded_provenance(tmp_path: Path) -> None:
    artifact = tmp_path / "numbering_base.json"
    artifact.write_text('{"pages": []}\n', encoding="utf-8")

    resolved = _artifact_path({"numbering_base": _detail(artifact)}, "numbering_base")

    assert resolved == artifact


def test_artifact_path_rejects_size_change(tmp_path: Path) -> None:
    artifact = tmp_path / "overrides_mmr.json"
    artifact.write_text('{"overrides": []}\n', encoding="utf-8")
    detail = _detail(artifact)
    detail["size"] = int(detail["size"]) + 1

    with pytest.raises(ValueError, match="size changed"):
        _artifact_path({"overrides_mmr": detail}, "overrides_mmr")


def test_artifact_path_rejects_hash_change_with_same_size(tmp_path: Path) -> None:
    artifact = tmp_path / "overrides_mmr.json"
    artifact.write_text('{"overrides": []}\n', encoding="utf-8")
    detail = _detail(artifact)
    detail["sha256"] = "0" * 64

    with pytest.raises(ValueError, match="hash changed"):
        _artifact_path({"overrides_mmr": detail}, "overrides_mmr")


def test_source_gate_allows_only_direct_index_score_failures(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    _source_report(report)

    result = verify_source_report(
        report,
        expected_invocation_id="invocation-current",
        expected_git_head="head-current",
    )

    assert result["status"] == "passed"
    assert result["ignored_direct_index_gate_failures"] == [
        "missed_fn_not_above_3",
        "skip_mismatch_not_above_6",
        "unexpected_fp_zero",
    ]


def test_source_gate_rejects_non_index_failure(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    payload = _source_report(report)
    payload["gates"]["focused_physical"] = False  # type: ignore[index]
    report.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="non-index source gates failed"):
        verify_source_report(
            report,
            expected_invocation_id="invocation-current",
            expected_git_head="head-current",
        )


def test_standalone_rescore_rejects_non_index_source_failure(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    payload = _source_report(report)
    payload["gates"]["final_numbering_files_68"] = False  # type: ignore[index]

    with pytest.raises(ValueError, match="non-index source gates failed"):
        _verify_source_acceptance(payload)


def test_standalone_rescore_allows_direct_index_only_failures(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    payload = _source_report(report)

    verified = _verify_source_acceptance(payload)

    assert "focused_physical" in verified
    assert "final_numbering_files_68" in verified
    assert "unexpected_fp_zero" not in verified


def test_source_gate_rejects_stale_invocation(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    _source_report(report, invocation_id="invocation-old")

    with pytest.raises(ValueError, match="invocation mismatch"):
        verify_source_report(
            report,
            expected_invocation_id="invocation-current",
            expected_git_head="head-current",
        )


def test_resume_rejects_different_producer_contract(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    _source_report(report)

    with pytest.raises(ValueError, match="producer revision/config/input contract changed"):
        validate_resume_contract(
            report,
            current_producer_contract={"git_head": "head-current", "contract": "changed"},
        )


def test_phase_c_wrapper_runs_integrity_rebase_and_final_lint() -> None:
    wrapper = Path("scripts/validate_issue264_phase_c_mmr.sh").read_text(encoding="utf-8")

    assert "ISSUE264_INVOCATION_ID" in wrapper
    assert "phase_c_acceptance_integrity.py" in wrapper
    assert "--expected-invocation-id" in wrapper
    assert "--expected-git-head" in wrapper
    assert "rescore_phase_c_mmr_geometry_rebased.py" in wrapper
    assert "direct-index runner exit:" in wrapper
    assert "requested_image_id" in wrapper
    assert "docker rm -f \"$container\"" in wrapper
    assert "make lint" in wrapper