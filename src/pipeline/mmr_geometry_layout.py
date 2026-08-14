"""MMR-only numbering geometry construction and index-layout guards."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Dict

from src.pipeline.core.config import get_nested
from src.pipeline.steps.barlines import normalize_barlines
from src.pipeline.utils.io import load_json, score_to_dict, write_json


def numbering_layout_signature(payload: Mapping[str, Any]) -> tuple[tuple[int, ...], ...]:
    pages = payload.get("pages")
    if not isinstance(pages, list):
        raise ValueError("Numbering payload lacks pages")
    result: list[tuple[int, ...]] = []
    for page in pages:
        if not isinstance(page, Mapping) or not isinstance(page.get("systems"), list):
            raise ValueError("Numbering page lacks systems")
        counts: list[int] = []
        for system in page["systems"]:
            if not isinstance(system, Mapping) or not isinstance(system.get("measures"), list):
                raise ValueError("Numbering system lacks measures")
            counts.append(len(system["measures"]))
        result.append(tuple(counts))
    return tuple(result)


def require_compatible_mmr_layout(
    base_payload: Mapping[str, Any], mmr_payload: Mapping[str, Any], *, page_id: str
) -> None:
    base_signature = numbering_layout_signature(base_payload)
    mmr_signature = numbering_layout_signature(mmr_payload)
    if base_signature != mmr_signature:
        raise RuntimeError(
            "MMR staff geometry changed the numbering index layout for "
            f"{page_id}: base={base_signature} mmr={mmr_signature}"
        )


def build_mmr_numbering_path(
    orchestrator: Any, *, page_id: str, ctx: Dict[str, Any], staff_mask: Path
) -> Path:
    from src.measure_numbering.pipeline import MeasureNumberingPipeline
    from src.measure_numbering.types import Score
    from src.pipeline.utils.images import load_image

    base_payload = load_json(Path(ctx["numbering_base"]))
    if "numbering_pipeline" not in orchestrator._persistence:
        orchestrator._persistence["numbering_pipeline"] = MeasureNumberingPipeline()
    numbering_pipeline = orchestrator._persistence["numbering_pipeline"]

    if "corrected_barlines" in ctx:
        barline_boxes = ctx["corrected_barlines"]
    else:
        barline_boxes = normalize_barlines(load_json(Path(ctx["resolved"]["barlines_json"])))

    image = load_image(Path(ctx["image_path"]))
    height, width = image.shape[:2]
    page_obj = numbering_pipeline.process_page(
        barline_boxes,
        staff_mask,
        (width, height),
        page_number=int(ctx["index"]),
        assume_one_staff_per_system=bool(
            get_nested(orchestrator.config, "numbering", "force_single_system", default=False)
        ),
        image=image,
    )
    score = Score()
    score.pages.append(page_obj)
    numbering_pipeline.numberer.number_score(score, start_number=1)
    mmr_payload = score_to_dict(score)
    require_compatible_mmr_layout(base_payload, mmr_payload, page_id=page_id)

    output_path = Path(ctx["intermediate_dir"]) / "numbering_mmr_geometry.json"
    write_json(output_path, mmr_payload)
    return output_path
