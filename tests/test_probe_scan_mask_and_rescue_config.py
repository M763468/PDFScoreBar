from pathlib import Path

from src.pipeline.core.config import load_yaml
from src.pipeline.detection.config import get_probe_kwargs
from src.pipeline.steps.probe_scan import (
    _build_clef_mask_map,
    _extract_aligned_expansion_rescue_cfg,
)


def test_same_staff_mask_is_rejected_and_distinct_clef_is_retained(tmp_path: Path) -> None:
    staff = tmp_path / "page_004_staff_mask.png"
    clef = tmp_path / "page_004_clef_mask.png"
    staff.write_bytes(b"staff")
    clef.write_bytes(b"clef")

    assert _build_clef_mask_map(tmp_path, {"page_004": staff}) == {"page_004": clef}
    clef.unlink()
    assert _build_clef_mask_map(tmp_path, {"page_004": staff}) == {}


def test_aligned_rescue_defaults_off_and_extracts_without_probe_leakage() -> None:
    kwargs, cfg = _extract_aligned_expansion_rescue_cfg({"probe_width": 4})

    assert kwargs == {"probe_width": 4}
    assert cfg["enabled"] is False


def test_canonical_dense_config_enables_rescue() -> None:
    config = load_yaml(Path("configs/dense_full_pipeline.yaml"))
    kwargs = get_probe_kwargs(config["detection"])

    assert kwargs["aligned_expansion_rescue_enabled"] is True
    assert kwargs["aligned_expansion_preserve_raw"] is False
