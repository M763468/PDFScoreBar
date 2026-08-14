"""Build a Phase B-only page context without mutating base numbering paths."""

from __future__ import annotations

from typing import Any, Dict, List, Set

from src.pipeline.mmr_geometry_layout import build_mmr_numbering_path
from src.pipeline.mmr_staff_support import prepare_mmr_staff_masks


def build_mmr_page_context(
    orchestrator: Any,
    page_ids: List[str],
    excluded_page_ids: Set[str],
    page_ctx: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    mmr_ctx = {page_id: dict(ctx) for page_id, ctx in page_ctx.items()}
    masks = prepare_mmr_staff_masks(orchestrator, page_ids, excluded_page_ids, page_ctx)
    for page_id, staff_mask in masks.items():
        mmr_ctx[page_id]["numbering_base"] = build_mmr_numbering_path(
            orchestrator,
            page_id=page_id,
            ctx=page_ctx[page_id],
            staff_mask=staff_mask,
        )
    return mmr_ctx
