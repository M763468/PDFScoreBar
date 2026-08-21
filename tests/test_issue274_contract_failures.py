from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from src.common.connector_artifacts import write_connector_masks
from src.measure_numbering.pipeline import MeasureNumberingPipeline
from tools.issue274.verify_two_homr_full68_numbering_posthoc import _phase_c_contract


def _write_mask(path: Path, rows: list[tuple[int, int]]) -> None:
    mask = np.zeros((240, 240), dtype=np.uint8)
    for y1, y2 in rows:
        mask[y1:y2, 60:220] = 255
    path.parent.mkdir(parents=True, exist_ok=True)
    assert cv2.imwrite(str(path), mask)


def _phase_c_report(*, include_fresh_semantic_gate: bool = True) -> dict:
    gates = {
        "page_count_68": True,
        "expected_fixture_total_182": True,
        "zero_expected_pages_scored": True,
        "page_033_one_bar_veto": True,
        "fresh_current_homr_mmr_geometry_all_pages": True,
        "focused_physical": True,
        "phase_b_page_042_five_overrides": True,
        "final_numbering_files_68": True,
    }
    if include_fresh_semantic_gate:
        gates["phase_a_fresh_current_homr_semantics_68"] = True
    return {
        "schema": "issue264.phase_c_mmr_regression.v1",
        "pages": [{} for _ in range(68)],
        "generated_artifacts": [{} for _ in range(68)],
        "evaluation_inputs": {
            "phase_a_semantic_support": {
                "producer": "src.pipeline.detection.current_homr_worker",
                "runtime_input": "retained canonical x4 SR images",
                "detector_reexecuted": False,
                "real_esrgan_reexecuted": False,
                "omr_dln_reexecuted": False,
                "historical_detector_artifact_runtime_input": False,
                "pages": 68,
            }
        },
        "gates": gates,
    }


def test_phase_c_numbering_baseline_accepts_pre_stamp_pr265_semantic_run() -> None:
    contract = _phase_c_contract(_phase_c_report())

    assert contract["ok"] is True
    assert contract["has_acceptance_provenance"] is False
    assert contract["acceptance_provenance_required"] is False


def test_phase_c_numbering_baseline_rejects_pre_pr265_semantic_run() -> None:
    contract = _phase_c_contract(_phase_c_report(include_fresh_semantic_gate=False))

    assert contract["ok"] is False
    assert contract["non_index_gate_failures"]


def test_connector_semantic_staff_count_mismatch_is_contract_error(tmp_path: Path) -> None:
    stem = "page_001"
    geometry_staff = tmp_path / "sr" / "batch" / stem / f"{stem}_proxy_debug_3_staff.png"
    semantic_dir = tmp_path / "current_support" / "Score" / stem / "artifacts" / "current_homr"
    semantic_staff = semantic_dir / f"{stem}_staff_mask.png"

    _write_mask(geometry_staff, [(20, 40), (100, 120)])
    _write_mask(semantic_staff, [(20, 40), (100, 120), (180, 200)])
    connector_paths = write_connector_masks(
        semantic_dir,
        stem,
        {
            "symbols": np.zeros((240, 240), dtype=np.uint8),
            "brace_dot": np.zeros((240, 240), dtype=np.uint8),
        },
    )
    assert connector_paths is not None

    with pytest.raises(RuntimeError, match="Connector semantic staff count mismatch"):
        MeasureNumberingPipeline().process_page(
            [],
            geometry_staff,
            (240, 240),
            connector_mask_paths=connector_paths,
        )


def test_connector_semantic_missing_staff_is_contract_error(tmp_path: Path) -> None:
    stem = "page_001"
    geometry_staff = tmp_path / "sr" / "batch" / stem / f"{stem}_proxy_debug_3_staff.png"
    semantic_dir = tmp_path / "current_support" / "Score" / stem / "artifacts" / "current_homr"

    _write_mask(geometry_staff, [(20, 40), (100, 120)])
    connector_paths = write_connector_masks(
        semantic_dir,
        stem,
        {
            "symbols": np.zeros((240, 240), dtype=np.uint8),
            "brace_dot": np.zeros((240, 240), dtype=np.uint8),
        },
    )
    assert connector_paths is not None

    with pytest.raises(RuntimeError, match="artifact contract is incomplete"):
        MeasureNumberingPipeline().process_page(
            [],
            geometry_staff,
            (240, 240),
            connector_mask_paths=connector_paths,
        )
