"""Regression tests for the resolution-independent center-anchor contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.common.barline_evaluation import is_barline_match
from src.common.barline_units import (
    STAFF_UNITS_SCHEMA_VERSION,
    load_page_staff_units,
    require_page_staff_unit,
)


def _manifest(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": STAFF_UNITS_SCHEMA_VERSION,
                "pages": {
                    "score/page_001": {
                        "unit_size": 24.0,
                        "coordinate_width": 1000,
                        "coordinate_height": 1400,
                        "source_kind": "staff_mask",
                        "source_path": "artifacts/page_001_staff_mask.png",
                        "source_sha256": "a" * 64,
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def test_center_anchor_is_resolution_independent_with_staff_units() -> None:
    """Exact 2x geometry has the same normalized center-anchor decision."""
    base_gt = (100, 80, 104, 220)
    base_pred = (105, 80, 109, 220)
    scaled_gt = (200, 160, 208, 440)
    scaled_pred = (210, 160, 218, 440)

    assert is_barline_match(base_pred, base_gt, rule_name="center_anchor", unit_size=12.0)
    assert is_barline_match(scaled_pred, scaled_gt, rule_name="center_anchor", unit_size=24.0)

    assert not is_barline_match(
        (107, 80, 111, 220), base_gt, rule_name="center_anchor", unit_size=12.0
    )
    assert not is_barline_match(
        (214, 160, 222, 440), scaled_gt, rule_name="center_anchor", unit_size=24.0
    )


def test_center_anchor_requires_one_explicit_distance_contract() -> None:
    gt = (100, 80, 104, 220)
    pred = (106, 80, 110, 220)

    with pytest.raises(ValueError, match="requires unit_size"):
        is_barline_match(pred, gt, rule_name="center_anchor")
    with pytest.raises(ValueError, match="unit_size or legacy"):
        is_barline_match(
            pred,
            gt,
            rule_name="center_anchor",
            unit_size=12.0,
            xdist_threshold=12.0,
        )


def test_staff_unit_manifest_preserves_page_provenance(tmp_path: Path) -> None:
    manifest_path = tmp_path / "staff_units.json"
    _manifest(manifest_path)

    units = load_page_staff_units(manifest_path)
    page = require_page_staff_unit(units, "score", "page_001")
    assert page.unit_size == 24.0
    assert page.coordinate_width == 1000
    assert page.source_kind == "staff_mask"

    with pytest.raises(ValueError, match="no entry"):
        require_page_staff_unit(units, "score", "page_002")
