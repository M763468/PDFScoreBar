from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.generate_movement_boundary_candidates import (
    _validate_manifest_source_hash,
    load_json_with_sha256,
)
from tools.movement_boundary_review import _export_from_handoff


def _manifest(digest: str) -> dict:
    return {
        "pages": [
            {
                "source_reference": {
                    "kind": "direct_pdf_render",
                    "source_page": 0,
                    "source_document": {"sha256": digest},
                }
            }
        ]
    }


def test_candidate_cli_requires_manifest_pdf_hash_match() -> None:
    digest = "a" * 64
    _validate_manifest_source_hash(_manifest(digest), digest)
    with pytest.raises(ValueError, match="does not match"):
        _validate_manifest_source_hash(_manifest(digest), "b" * 64)


def test_candidate_cli_allows_external_manifest_without_source_mapping() -> None:
    _validate_manifest_source_hash({"pages": [{"page_id": "page_001"}]}, "a" * 64)


def test_load_json_with_sha256_hashes_exact_consumed_bytes(tmp_path) -> None:
    path = tmp_path / "artifact.json"
    payload = b'{"pages": []}\n'
    path.write_bytes(payload)

    loaded, digest = load_json_with_sha256(path)

    assert loaded == {"pages": []}
    assert digest == hashlib.sha256(payload).hexdigest()


def test_movement_boundary_clis_support_direct_script_execution(tmp_path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    for script in (
        repo_root / "tools" / "generate_movement_boundary_candidates.py",
        repo_root / "tools" / "movement_boundary_review.py",
    ):
        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr


def test_movement_boundary_export_honors_configured_review_output(tmp_path) -> None:
    package = tmp_path / "review"
    custom_dir = package / "custom"
    custom_dir.mkdir(parents=True)

    evidence_path = package / "movement_boundary_evidence.json"
    evidence_path.write_text(
        json.dumps(
            {
                "schema_version": "issue333.movement_boundary_evidence.v1",
                "candidates": [
                    {
                        "id": "page:0:system:0",
                        "page": 0,
                        "system": 0,
                        "state": "ambiguous_review_required",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    custom_review = custom_dir / "movement_review.json"
    custom_review.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "correction_type": "movement_boundary",
                "items": [
                    {
                        "op": "boundary",
                        "page": 0,
                        "system": 0,
                        "reason": "test",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    handoff = package / "manual_correction_input.json"
    handoff.write_text(
        json.dumps(
            {
                "movement_boundary_evidence": "movement_boundary_evidence.json",
                "movement_boundary_resolved_output": "custom/resolved.json",
                "correction_outputs": {
                    "movement_boundary": "custom/movement_review.json",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    resolved = _export_from_handoff(handoff, overwrite=False)

    assert resolved["boundaries"] == [
        {
            "page": 0,
            "system": 0,
            "reset_number": 1,
            "source": "reviewed_candidate",
            "provenance": resolved["boundaries"][0]["provenance"],
        }
    ]
    assert (custom_dir / "resolved.json").exists()
