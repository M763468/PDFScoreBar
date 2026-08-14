#!/usr/bin/env python3
"""Isolate Issue #264 Phase-A/Phase-B layout divergence from retained artifacts.

This diagnostic does not run detector, HOMR, SR, OMR-DLN, MMR CNN, or OCR.
For pages where the Phase-B MMR geometry candidate changed the Phase-A index
layout, it re-runs only the lightweight numbering/grouping construction across
four retained-artifact combinations:

1. Phase-A staff geometry + Phase-A current-HOMR connector semantics
2. Phase-A staff geometry + page-image-ink connector evidence
3. Phase-B retained staff geometry + Phase-A current-HOMR connector semantics
4. Phase-B retained staff geometry + page-image-ink connector evidence

The matrix separates staff-geometry producer effects from connector-evidence
source effects without regenerating any heavy upstream artifact.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

import cv2

from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.measure_numbering.serialization import score_to_dict
from src.measure_numbering.types import Score
from src.pipeline.steps.barlines import normalize_barlines

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_RUN = "issue255_production_restore_full68_top_level_worker_01"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _resolve_project_path(value: str | Path) -> Path:
    raw = Path(value)
    if raw.exists():
        return raw
    if not raw.is_absolute():
        candidate = PROJECT_ROOT / raw
        if candidate.exists():
            return candidate
    text = str(raw)
    if "/workspace/" in text:
        candidate = PROJECT_ROOT / text.split("/workspace/", 1)[1]
        if candidate.exists():
            return candidate
    parts = raw.parts
    if "ws_PDFScoreBar" in parts:
        index = parts.index("ws_PDFScoreBar")
        candidate = PROJECT_ROOT.joinpath(*parts[index + 1 :])
        if candidate.exists():
            return candidate
    raise FileNotFoundError(raw)


def _barlines_path(score: str, score_page: str) -> Path:
    image_stem = f"{score}_{score_page}"
    return (
        PROJECT_ROOT
        / "logs/verification/detector_full68"
        / CANONICAL_RUN
        / "production_runs"
        / score
        / "intermediate/dense_full_pipeline_route/dense_candidate_reconstruction"
        / "probe_rescue_candidates"
        / f"eval2_{image_stem}"
        / "pipeline2_no_peak_filtered_cnn.json"
    )


def _layout_signature(payload: Mapping[str, Any]) -> list[int]:
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 1:
        raise ValueError("Expected one-page numbering payload")
    systems = pages[0].get("systems")
    if not isinstance(systems, list):
        raise ValueError("Numbering payload lacks systems")
    return [len(system.get("measures", [])) for system in systems]


def _staff_membership(payload: Mapping[str, Any]) -> list[int]:
    page = payload["pages"][0]
    return [len(system.get("staves", [])) for system in page.get("systems", [])]


def _semantic_connector_paths(page: Mapping[str, Any]) -> dict[str, Path]:
    support = page.get("phase_a_semantic_support")
    if not isinstance(support, Mapping):
        raise ValueError(f"{page.get('page_id')} lacks phase_a_semantic_support")
    description = support.get("connector_artifacts")
    if not isinstance(description, Mapping):
        raise ValueError("Phase-A support lacks connector_artifacts")
    masks = description.get("masks")
    if not isinstance(masks, Mapping):
        raise ValueError("Phase-A support lacks connector masks")
    result: dict[str, Path] = {}
    for key in ("symbols", "brace_dot"):
        detail = masks.get(key)
        if not isinstance(detail, Mapping) or not detail.get("path"):
            raise ValueError(f"Phase-A support lacks {key} connector mask")
        result[key] = _resolve_project_path(str(detail["path"]))
    return result


def _page_image_ink_evidence(
    pipeline: MeasureNumberingPipeline,
    *,
    staff_mask: Path,
    image,
    image_size: tuple[int, int],
):
    staves = pipeline.extractor.extract(staff_mask, image_size)
    return pipeline.connector_extractor.extract(
        staves,
        image_size,
        symbol_mask=pipeline._image_to_connector_mask(image),  # noqa: SLF001
        source="page_image_ink",
        include_absent_pairs=False,
        connector_density_threshold=0.01,
    )


def _rebuild(
    *,
    barline_boxes: list[list[int]],
    staff_mask: Path,
    image,
    page_number: int,
    connector_mode: str,
    semantic_paths: Mapping[str, Path],
) -> dict[str, Any]:
    height, width = image.shape[:2]
    image_size = (width, height)
    pipeline = MeasureNumberingPipeline()

    kwargs: dict[str, Any] = {}
    if connector_mode == "semantic":
        kwargs["connector_mask_paths"] = semantic_paths
    elif connector_mode == "page_image_ink":
        kwargs["connector_evidence"] = _page_image_ink_evidence(
            pipeline,
            staff_mask=staff_mask,
            image=image,
            image_size=image_size,
        )
    else:
        raise ValueError(f"Unsupported connector mode: {connector_mode}")

    page = pipeline.process_page(
        barline_boxes,
        staff_mask,
        image_size,
        page_number=page_number,
        image=image,
        **kwargs,
    )
    score = Score()
    score.pages.append(page)
    pipeline.numberer.number_score(score, start_number=1)
    return score_to_dict(score)


def _classify(
    variants: Mapping[str, Mapping[str, Any]],
    *,
    base_signature: list[int],
    candidate_signature: list[int],
) -> dict[str, Any]:
    signatures = {name: _layout_signature(payload) for name, payload in variants.items()}
    return {
        "signatures": signatures,
        "matches_phase_a_base": {
            name: signature == base_signature for name, signature in signatures.items()
        },
        "matches_phase_b_candidate": {
            name: signature == candidate_signature for name, signature in signatures.items()
        },
        "staff_change_with_semantics_changes_layout": (
            signatures["phase_a_staff__semantic"] != signatures["phase_b_staff__semantic"]
        ),
        "evidence_change_with_phase_a_staff_changes_layout": (
            signatures["phase_a_staff__semantic"] != signatures["phase_a_staff__page_image_ink"]
        ),
        "evidence_change_with_phase_b_staff_changes_layout": (
            signatures["phase_b_staff__semantic"] != signatures["phase_b_staff__page_image_ink"]
        ),
    }


def run(report_path: Path, output_path: Path) -> Path:
    report = _load_json(report_path)
    if not isinstance(report, Mapping):
        raise ValueError("Phase-C report must be a mapping")
    raw_pages = report.get("pages")
    if not isinstance(raw_pages, list):
        raise ValueError("Phase-C report lacks pages")

    results: list[dict[str, Any]] = []
    for raw_page in raw_pages:
        if not isinstance(raw_page, Mapping):
            continue
        decision = raw_page.get("mmr_layout_decision")
        if not isinstance(decision, Mapping):
            continue
        if decision.get("numbering_geometry_source") != "phase_a_base_fallback":
            continue

        page_id = str(raw_page["page_id"])
        score = str(raw_page["score"])
        score_page = str(raw_page["score_page"])
        image_path = _resolve_project_path(str(raw_page["image"]))
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(image_path)

        support = raw_page["phase_a_semantic_support"]
        if not isinstance(support, Mapping):
            raise ValueError(f"{page_id} lacks Phase-A support")
        phase_a_staff = _resolve_project_path(str(support["mirrored_proxy_staff_mask"]))
        provenance = raw_page.get("mmr_geometry_provenance")
        if not isinstance(provenance, Mapping) or not provenance.get("staff_mask"):
            raise ValueError(f"{page_id} lacks Phase-B staff-mask provenance")
        phase_b_staff = _resolve_project_path(str(provenance["staff_mask"]))
        semantic_paths = _semantic_connector_paths(raw_page)

        barlines_path = _barlines_path(score, score_page)
        raw_barlines = _load_json(barlines_path)
        barline_boxes = normalize_barlines(raw_barlines)

        variants = {
            "phase_a_staff__semantic": _rebuild(
                barline_boxes=barline_boxes,
                staff_mask=phase_a_staff,
                image=image,
                page_number=int(raw_page["global_index"]) + 1,
                connector_mode="semantic",
                semantic_paths=semantic_paths,
            ),
            "phase_a_staff__page_image_ink": _rebuild(
                barline_boxes=barline_boxes,
                staff_mask=phase_a_staff,
                image=image,
                page_number=int(raw_page["global_index"]) + 1,
                connector_mode="page_image_ink",
                semantic_paths=semantic_paths,
            ),
            "phase_b_staff__semantic": _rebuild(
                barline_boxes=barline_boxes,
                staff_mask=phase_b_staff,
                image=image,
                page_number=int(raw_page["global_index"]) + 1,
                connector_mode="semantic",
                semantic_paths=semantic_paths,
            ),
            "phase_b_staff__page_image_ink": _rebuild(
                barline_boxes=barline_boxes,
                staff_mask=phase_b_staff,
                image=image,
                page_number=int(raw_page["global_index"]) + 1,
                connector_mode="page_image_ink",
                semantic_paths=semantic_paths,
            ),
        }

        base_signature = [int(value) for value in decision["base_layout_signature"]]
        candidate_signature = [int(value) for value in decision["candidate_layout_signature"]]
        classification = _classify(
            variants,
            base_signature=base_signature,
            candidate_signature=candidate_signature,
        )
        results.append(
            {
                "page_id": page_id,
                "score": score,
                "score_page": score_page,
                "phase_a_staff": str(phase_a_staff),
                "phase_b_staff": str(phase_b_staff),
                "semantic_connector_paths": {
                    key: str(path) for key, path in semantic_paths.items()
                },
                "base_layout_signature": base_signature,
                "candidate_layout_signature": candidate_signature,
                "variants": {
                    name: {
                        "layout_signature": _layout_signature(payload),
                        "staff_membership": _staff_membership(payload),
                    }
                    for name, payload in variants.items()
                },
                "classification": classification,
            }
        )

    payload = {
        "schema": "issue264.phase_b_layout_divergence_diagnostic.v1",
        "source_report": str(report_path),
        "heavy_inference_reexecuted": False,
        "detector_reexecuted": False,
        "homr_reexecuted": False,
        "sr_reexecuted": False,
        "mmr_reexecuted": False,
        "pages": results,
        "page_count": len(results),
    }
    _write_json(output_path, payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"report: {output_path}")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run(args.report, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
