"""MMR-only numbering geometry construction and index-layout guards."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Dict

from src.pipeline.core.config import get_nested
from src.pipeline.steps.barlines import normalize_barlines
from src.pipeline.utils.io import load_json, score_to_dict, write_json

logger = logging.getLogger(__name__)


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


def _signature_json(signature: tuple[tuple[int, ...], ...]) -> list[list[int]]:
    return [list(page) for page in signature]


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


def select_mmr_numbering_payload(
    base_payload: Mapping[str, Any],
    candidate_payload: Mapping[str, Any],
    *,
    page_id: str,
) -> tuple[Mapping[str, Any], dict[str, Any]]:
    """Choose an index-safe MMR numbering payload and describe the decision.

    Fresh current-HOMR staff geometry is preferred because it restores the MMR crop
    geometry required by Issue #244.  It may only be used when it preserves the
    Phase A ``[page, system, measure]`` index contract.  If the candidate changes
    the system count or per-system measure counts, keep Phase A base geometry for
    MMR instead of either silently drifting indices or aborting the whole score.

    The rejected candidate is still retained by ``build_mmr_numbering_path`` for
    diagnosis and the fallback decision is recorded in manifest provenance.
    """

    base_signature = numbering_layout_signature(base_payload)
    candidate_signature = numbering_layout_signature(candidate_payload)
    compatible = base_signature == candidate_signature
    decision = {
        "layout_compatible": compatible,
        "base_layout_signature": _signature_json(base_signature),
        "candidate_layout_signature": _signature_json(candidate_signature),
        "numbering_geometry_source": (
            "fresh_current_homr" if compatible else "phase_a_base_fallback"
        ),
        "fallback_reason": None if compatible else "index_layout_mismatch",
    }
    if compatible:
        return candidate_payload, decision

    logger.warning(
        "MMR fresh-HOMR geometry is index-incompatible for %s; using Phase A base geometry "
        "for MMR. base=%s candidate=%s",
        page_id,
        base_signature,
        candidate_signature,
    )
    return base_payload, decision


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
    candidate_payload = score_to_dict(score)
    effective_payload, decision = select_mmr_numbering_payload(
        base_payload,
        candidate_payload,
        page_id=page_id,
    )

    geometry_provenance = ctx["resolved"].setdefault("mmr_staff_geometry", {})
    if not isinstance(geometry_provenance, dict):
        raise ValueError("mmr_staff_geometry provenance must be a mapping")
    geometry_provenance.update(decision)

    output_dir = Path(ctx["intermediate_dir"])
    output_path = output_dir / "numbering_mmr_geometry.json"
    if not decision["layout_compatible"]:
        candidate_path = output_dir / "numbering_mmr_geometry_candidate.json"
        write_json(candidate_path, candidate_payload)
        geometry_provenance["rejected_candidate_numbering_path"] = str(candidate_path)
    else:
        geometry_provenance["rejected_candidate_numbering_path"] = None

    write_json(output_path, effective_payload)
    geometry_provenance["effective_numbering_path"] = str(output_path)
    return output_path
