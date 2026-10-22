"""Attach current-x4 MMR support without rebuilding Phase-A numbering."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Set

from src.pipeline.mmr_support_reuse import build_mmr_support


def build_mmr_page_context(
    orchestrator: Any,
    page_ids: List[str],
    excluded_page_ids: Set[str],
    page_ctx: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    mmr_ctx = {page_id: dict(ctx) for page_id, ctx in page_ctx.items()}
    for page_id in page_ids:
        if page_id in excluded_page_ids:
            continue
        ctx = mmr_ctx[page_id]
        numbering_base = Path(ctx["numbering_base"])
        if not numbering_base.is_file():
            continue
        current_mask = Path(ctx["resolved"].get("current_homr_staff_mask", ""))
        if not current_mask.is_file():
            raise FileNotFoundError(
                f"Dense MMR support requires current-HOMR staff mask for {page_id}: {current_mask}"
            )
        output_path = Path(ctx["intermediate_dir"]) / "mmr_support.json"
        support = build_mmr_support(
            numbering_base_path=numbering_base,
            current_homr_staff_mask=current_mask,
            output_path=output_path,
        )
        ctx["mmr_support"] = output_path
        ctx["resolved"]["mmr_support"] = support["provenance"]
    return mmr_ctx
