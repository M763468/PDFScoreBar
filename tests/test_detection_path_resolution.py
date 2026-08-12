from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from src.common.connector_artifacts import describe_connector_artifacts, write_connector_masks
from src.pipeline.detection.utils import resolve_paths_from_detection


def _write_mask(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    assert cv2.imwrite(str(path), np.zeros((20, 20), dtype=np.uint8))


def _probe_root(tmp_path: Path, stem: str) -> Path:
    probe_root = tmp_path / "probe"
    page_dir = probe_root / f"eval2_Score_{stem}"
    page_dir.mkdir(parents=True)
    (page_dir / "pipeline2_no_peak_filtered_cnn.json").write_text("[]\n", encoding="utf-8")
    return probe_root


def test_resolver_prefers_staff_mask_with_complete_connector_pair(tmp_path: Path) -> None:
    stem = "page_001"
    hybrid_root = tmp_path / "hybrid"

    debug_staff = hybrid_root / "sr" / "batch" / stem / f"{stem}_proxy_debug_3_staff.png"
    semantic_dir = (
        hybrid_root
        / "current_support"
        / "Score"
        / stem
        / "artifacts"
        / "current_homr"
        / "batch"
        / stem
    )
    semantic_staff = semantic_dir / f"{stem}_staff_mask.png"
    _write_mask(debug_staff)
    _write_mask(semantic_staff)
    write_connector_masks(
        semantic_dir,
        stem,
        {
            "symbols": np.zeros((10, 10), dtype=np.uint8),
            "brace_dot": np.zeros((10, 10), dtype=np.uint8),
        },
    )

    resolved = resolve_paths_from_detection(
        {"detection": {}},
        _probe_root(tmp_path, stem),
        hybrid_root,
        [stem],
        [tmp_path / "Score" / f"{stem}.png"],
    )

    staff_mask = Path(resolved[0]["staff_mask"])
    assert staff_mask == semantic_staff
    assert describe_connector_artifacts(staff_mask)["source"] == "proxy_symbol_layers"


def test_resolver_keeps_debug_staff_fallback_without_semantic_pair(tmp_path: Path) -> None:
    stem = "page_001"
    hybrid_root = tmp_path / "hybrid"
    debug_staff = hybrid_root / "sr" / "batch" / stem / f"{stem}_proxy_debug_3_staff.png"
    stable_staff = hybrid_root / "baseline" / "batch" / stem / f"{stem}_staff_mask.png"
    _write_mask(debug_staff)
    _write_mask(stable_staff)

    resolved = resolve_paths_from_detection(
        {"detection": {}},
        _probe_root(tmp_path, stem),
        hybrid_root,
        [stem],
        [tmp_path / "Score" / f"{stem}.png"],
    )

    assert Path(resolved[0]["staff_mask"]) == debug_staff
