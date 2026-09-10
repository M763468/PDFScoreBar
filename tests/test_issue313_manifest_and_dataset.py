from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from src.common.barline_units import PageStaffUnit
from tools.cnn_classifier.build_cnn_dataset import _validate_eval2_image_frame
from tools.issue313.build_staff_units_manifest import build_manifest


def test_eval2_builder_rejects_x4_original_dimension_mismatch(tmp_path: Path) -> None:
    image_path = tmp_path / "page.png"
    image = np.zeros((200, 300, 3), dtype=np.uint8)
    assert cv2.imwrite(str(image_path), image)
    unit = PageStaffUnit(
        unit_size=12.0,
        coordinate_width=600,
        coordinate_height=400,
        source_kind="staff_mask",
        source_path="external://issue313-phase1/homr_staff_mask/score/page_001_staff_mask.png",
        source_sha256="a" * 64,
    )

    with pytest.raises(ValueError, match="dimensions mismatch"):
        _validate_eval2_image_frame(
            image_path, image, page_unit=unit, score="score", page="page_001"
        )


def test_staff_units_generator_emits_portable_provenance(tmp_path: Path) -> None:
    mask_path = tmp_path / "local" / "mask.png"
    mask_path.parent.mkdir()
    Image.new("L", (3640, 5155), 0).save(mask_path)
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(
        json.dumps(
            {
                "pages": [
                    {
                        "group": "Sibelius-Violin_Concerto-Viola_page_004",
                        "unit_size": 26.0,
                        "geometry": {"mask": str(mask_path)},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = build_manifest(audit_path)
    page = result["pages"]["Sibelius-Violin_Concerto-Viola/page_004"]
    assert page["source_kind"] == "homr_staff_mask_snapshot"
    assert page["source_path"] == (
        "external://issue313-phase1/homr_staff_mask/"
        "Sibelius-Violin_Concerto-Viola/page_004_staff_mask.png"
    )
    assert not page["source_path"].startswith("/")
    assert page["source_sha256"] == hashlib.sha256(mask_path.read_bytes()).hexdigest()
