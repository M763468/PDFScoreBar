from __future__ import annotations

import pytest

from tools.generate_movement_boundary_candidates import _validate_manifest_source_hash


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
