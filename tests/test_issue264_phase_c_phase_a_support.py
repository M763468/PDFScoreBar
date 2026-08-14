from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from tools.issue264 import phase_c_phase_a_support
from tools.issue264.phase_c_phase_a_support import ensure_phase_a_semantic_support


def _write_mask(path: Path, value: int = 255) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = np.full((20, 30), value, dtype=np.uint8)
    assert cv2.imwrite(str(path), image)


def test_phase_a_support_replay_uses_retained_x4_without_mutating_canonical_staff(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_image = tmp_path / "data" / "Score" / "page_001.png"
    _write_mask(source_image, 200)

    canonical_page = tmp_path / "canonical" / "sr" / "batch" / "page_001"
    canonical_staff = canonical_page / "page_001_proxy_debug_3_staff.png"
    canonical_sr = canonical_page / "page_001.png"
    _write_mask(canonical_staff, 100)
    _write_mask(canonical_sr, 150)
    canonical_staff_bytes = canonical_staff.read_bytes()

    calls: list[dict] = []

    def fake_run(request_path: Path, result_path: Path) -> Path:
        request = json.loads(request_path.read_text(encoding="utf-8"))
        calls.append(request)
        assert Path(request["image"]) == source_image
        assert Path(request["sr_image"]) == canonical_sr

        homr_root = Path(request["output_root"])
        semantic_dir = homr_root / "batch" / "page_001"
        semantic_staff = semantic_dir / "page_001_staff_mask.png"
        _write_mask(semantic_staff, 255)
        _write_mask(semantic_dir / "page_001_connector_symbols.png", 255)
        _write_mask(semantic_dir / "page_001_connector_brace_dot.png", 0)
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(
            json.dumps(
                {
                    "status": "completed",
                    "staff_mask": str(semantic_staff),
                    "connector_complete": True,
                    "historical_detector_artifact_runtime_input": False,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return result_path

    monkeypatch.setattr(phase_c_phase_a_support, "run_current_homr", fake_run)

    mirrored, provenance = ensure_phase_a_semantic_support(
        score="Score",
        page_name="page_001",
        source_image=source_image,
        canonical_staff_mask=canonical_staff,
        replay_root=tmp_path / "replay",
        detection_config={"sr_scale": 4},
        resume=False,
    )

    assert len(calls) == 1
    assert mirrored == (
        tmp_path
        / "replay"
        / "Score"
        / "sr"
        / "batch"
        / "page_001"
        / "page_001_proxy_debug_3_staff.png"
    )
    assert mirrored.read_bytes() == canonical_staff_bytes
    assert canonical_staff.read_bytes() == canonical_staff_bytes
    assert provenance["connector_complete"] is True
    assert provenance["historical_detector_artifact_runtime_input"] is False
    assert provenance["reused"] is False
    assert provenance["connector_artifacts"]["source"] == "proxy_symbol_layers"

    def fail_run(_request_path: Path, _result_path: Path) -> Path:
        pytest.fail("valid fresh current-HOMR result should be reused")

    monkeypatch.setattr(phase_c_phase_a_support, "run_current_homr", fail_run)
    _, resumed = ensure_phase_a_semantic_support(
        score="Score",
        page_name="page_001",
        source_image=source_image,
        canonical_staff_mask=canonical_staff,
        replay_root=tmp_path / "replay",
        detection_config={"sr_scale": 4},
        resume=True,
    )
    assert resumed["reused"] is True
