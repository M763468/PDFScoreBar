from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tools.issue264.rescore_phase_c_mmr_geometry_rebased import _artifact_path


def _detail(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    return {
        "path": str(path),
        "size": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


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


def test_phase_c_wrapper_runs_rebased_acceptance_and_final_lint() -> None:
    wrapper = Path("scripts/validate_issue264_phase_c_mmr.sh").read_text(encoding="utf-8")

    assert "rescore_phase_c_mmr_geometry_rebased.py" in wrapper
    assert "direct-index runner exit:" in wrapper
    assert "make lint" in wrapper
