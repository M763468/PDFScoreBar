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


def split_score_page_from_composite_stem(stem: str) -> tuple[str, str] | None:
    """Split composite stems like ``Score_page_001`` into score and page.

    Regular page stems such as ``page_001`` return ``None``. This keeps the
    default pipeline path unchanged while supporting composite benchmark image names.
    """
    marker = "_page_"
    idx = stem.rfind(marker)
    if idx < 0:
        return None
    score = stem[:idx]
    page = f"page_{stem[idx + len(marker):]}"
    return score, page
