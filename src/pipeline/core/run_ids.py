"""Utilities for consistent per-page run directory naming."""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def build_probe_run_id_from_parts(score_name: str, stem: str) -> str:
    return f"eval2_{score_name}_{stem}"


def build_probe_run_id(image_path: Path, score_name: Optional[str] = None) -> str:
    """Build run id used by probe_scan/cnn_scoring page directories."""
    resolved_score_name = score_name or image_path.parent.name
    return build_probe_run_id_from_parts(resolved_score_name, image_path.stem)
