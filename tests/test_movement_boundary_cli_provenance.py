from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from tools.generate_movement_boundary_candidates import (
    _validate_manifest_source_hash,
    load_json_with_sha256,
)


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
