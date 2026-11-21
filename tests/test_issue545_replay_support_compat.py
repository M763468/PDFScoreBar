"""Issue #545: the geometry replay must reject support code where the patch has no effect."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "issue545"))

from issue545_support_compat import X4_GEOMETRY_SCHEMA, require_geometry_support  # noqa: E402

import src.pipeline.mmr_support_reuse as current_support  # noqa: E402


def _support(schema: str) -> SimpleNamespace:
    return SimpleNamespace(SCHEMA_VERSION=schema, _raw_mapped_bbox=lambda base, cands: (base, ""))


def test_pre_545_support_allows_geometry_candidates() -> None:
    require_geometry_support(_support(X4_GEOMETRY_SCHEMA), production_only=False)


def test_current_support_rejects_geometry_candidates() -> None:
    with pytest.raises(SystemExit, match="PDFSCORE_CODE"):
        require_geometry_support(current_support, production_only=False)


def test_current_support_allows_production_only_replay() -> None:
    require_geometry_support(current_support, production_only=True)


def test_missing_patch_point_is_rejected() -> None:
    with pytest.raises(SystemExit):
        require_geometry_support(
            SimpleNamespace(SCHEMA_VERSION=X4_GEOMETRY_SCHEMA), production_only=False
        )
