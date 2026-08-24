"""Compare Issue #284 channels-last artifacts at the actual numbering boundary.

This is a no-inference follow-up. It reuses the retained baseline/candidate
artifacts from run_channels_last_downstream_gate.py, then evaluates connector
evidence and MeasureNumberingPipeline output using the same production geometry
staff-mask selection rule. The goal is to distinguish harmless current-HOMR
metadata/pixel drift from changes that actually cross the hybrid->numbering
contract.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cv2

from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.measure_numbering.serialization import score_to_dict
from src.measure_numbering.types import Score
from src.pipeline.steps.hybrid_consensus import load_json_boxes


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _select_numbering_staff_mask(hybrid_root: Path, stem: str) -> Path:
    """Mirror resolve_paths_from_detection() staff-mask precedence."""
    staff_mask_map: dict[str, Path] = {}
    for path in hybrid_root.rglob("*_debug_3_staff.png"):
        name = path.name
        path_stem = name.replace("_proxy_debug_3_staff.png", "").replace("_debug_3_staff.png", "")
        staff_mask_map[path_stem] = path
    for path in hybrid_root.rglob("*_staff_mask.png"):
        path_stem = path.name.replace("_staff_mask.png", "")
        if path_stem not in staff_mask_map:
            staff_mask_map[path_stem] = path

    result = staff_mask_map.get(stem)
    if result is None or not result.is_file():
        raise FileNotFoundError(
            f"Could not resolve numbering staff mask for {stem} under {hybrid_root}"
        )
    return result.resolve()


def _connector_paths(gate: Mapping[str, Any], side: str) -> dict[str, Path]:
    artifacts = gate["current_homr_artifacts"]
    return {
        "symbols": Path(artifacts["connector_symbols"][side]).resolve(),
        "brace_dot": Path(artifacts["connector_brace_dot"][side]).resolve(),
    }


def _extract_evidence(
    pipeline: MeasureNumberingPipeline,
    *,
    geometry_staff_mask: Path,
    connector_paths: Mapping[str, Path],
    image_size: tuple[int, int],
) -> tuple[list[Any], dict[str, Any]]:
    geometry_staves = pipeline.extractor.extract(geometry_staff_mask, image_size)
    evidence_staves = pipeline._connector_evidence_staves(  # noqa: SLF001 - profiling gate
        geometry_staves,
        geometry_staff_mask,
        image_size,
        connector_paths,
    )
    evidence = pipeline.connector_extractor.extract_from_mask_maps(
        evidence_staves,
        image_size,
        connector_mask_paths=connector_paths,
    )
    return evidence_staves, evidence


def _pair_semantics(candidate: Mapping[str, Any], reference: Mapping[str, Any]) -> dict[str, Any]:
    candidate_pairs = list(candidate.get("staff_pairs", []))
    reference_pairs = list(reference.get("staff_pairs", []))
    count = min(len(candidate_pairs), len(reference_pairs))
    changed_presence: list[int] = []
    changed_stats: list[dict[str, Any]] = []
    threshold = float(reference.get("connector_density_threshold", 0.05))

    for index in range(count):
        cand = candidate_pairs[index]
        ref = reference_pairs[index]
        if cand.get("left_connector_present") != ref.get("left_connector_present"):
            changed_presence.append(index)
        values = {
            "index": index,
            "staff_pair": ref.get("staff_pair"),
            "candidate_left_connector_present": cand.get("left_connector_present"),
            "reference_left_connector_present": ref.get("left_connector_present"),
            "candidate_symbols_vertical_open_density": cand.get("symbols_vertical_open_density"),
            "reference_symbols_vertical_open_density": ref.get("symbols_vertical_open_density"),
            "candidate_brace_dot_vertical_open_density": cand.get(
                "brace_dot_vertical_open_density"
            ),
            "reference_brace_dot_vertical_open_density": ref.get("brace_dot_vertical_open_density"),
        }
        densities = [
            float(values["candidate_symbols_vertical_open_density"] or 0.0),
            float(values["reference_symbols_vertical_open_density"] or 0.0),
            float(values["candidate_brace_dot_vertical_open_density"] or 0.0),
            float(values["reference_brace_dot_vertical_open_density"] or 0.0),
        ]
        values["minimum_abs_margin_to_threshold"] = min(
            abs(value - threshold) for value in densities
        )
        if any(
            cand.get(key) != ref.get(key)
            for key in (
                "symbols_vertical_open_density",
                "brace_dot_vertical_open_density",
                "symbols_density",
                "brace_dot_density",
            )
        ):
            changed_stats.append(values)

    return {
        "candidate_pair_count": len(candidate_pairs),
        "reference_pair_count": len(reference_pairs),
        "same_pair_count": len(candidate_pairs) == len(reference_pairs),
        "left_connector_present_equal": (
            len(candidate_pairs) == len(reference_pairs) and not changed_presence
        ),
        "left_connector_present_diff_indices": changed_presence,
        "changed_density_pair_count": len(changed_stats),
        "changed_density_pairs": changed_stats,
    }


def _run_numbering(
    *,
    barline_boxes: list[list[int]],
    geometry_staff_mask: Path,
    connector_paths: Mapping[str, Path],
    image_bgr: Any,
    image_size: tuple[int, int],
) -> dict[str, Any]:
    pipeline = MeasureNumberingPipeline()
    page = pipeline.process_page(
        barline_boxes,
        geometry_staff_mask,
        image_size,
        page_number=1,
        image=image_bgr,
        connector_mask_paths=connector_paths,
    )
    score = Score()
    score.pages.append(page)
    pipeline.numberer.number_score(score, start_number=1)
    return score_to_dict(score)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()

    gate_path = args.gate.resolve()
    gate = _load_json(gate_path)
    image_path = Path(gate["image"]).resolve()
    hybrid_root = Path(gate["baseline_hybrid_run_root"]).resolve()
    hybrid_reference = Path(gate["hybrid_consensus"]["reference"]).resolve()
    stem = image_path.stem

    image_bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise FileNotFoundError(image_path)
    image_size = (int(image_bgr.shape[1]), int(image_bgr.shape[0]))
    geometry_staff_mask = _select_numbering_staff_mask(hybrid_root, stem)
    barline_boxes = [list(map(int, box)) for box in load_json_boxes(hybrid_reference)]

    baseline_paths = _connector_paths(gate, "reference")
    candidate_paths = _connector_paths(gate, "candidate")
    for path in [
        geometry_staff_mask,
        hybrid_reference,
        *baseline_paths.values(),
        *candidate_paths.values(),
    ]:
        if not path.is_file():
            raise FileNotFoundError(path)

    evidence_pipeline = MeasureNumberingPipeline()
    baseline_evidence_staves, baseline_evidence = _extract_evidence(
        evidence_pipeline,
        geometry_staff_mask=geometry_staff_mask,
        connector_paths=baseline_paths,
        image_size=image_size,
    )
    candidate_evidence_staves, candidate_evidence = _extract_evidence(
        evidence_pipeline,
        geometry_staff_mask=geometry_staff_mask,
        connector_paths=candidate_paths,
        image_size=image_size,
    )
    evidence_semantics = _pair_semantics(candidate_evidence, baseline_evidence)

    baseline_numbering = _run_numbering(
        barline_boxes=barline_boxes,
        geometry_staff_mask=geometry_staff_mask,
        connector_paths=baseline_paths,
        image_bgr=image_bgr,
        image_size=image_size,
    )
    candidate_numbering = _run_numbering(
        barline_boxes=barline_boxes,
        geometry_staff_mask=geometry_staff_mask,
        connector_paths=candidate_paths,
        image_bgr=image_bgr,
        image_size=image_size,
    )

    payload = {
        "schema_version": "issue284.channels_last_numbering_semantics.v1",
        "status": "completed",
        "gate": str(gate_path),
        "image": str(image_path),
        "hybrid_barlines": str(hybrid_reference),
        "hybrid_barline_count": len(barline_boxes),
        "numbering_geometry_staff_mask": str(geometry_staff_mask),
        "numbering_geometry_staff_count": len(
            evidence_pipeline.extractor.extract(geometry_staff_mask, image_size)
        ),
        "baseline_connector_evidence_staff_count": len(baseline_evidence_staves),
        "candidate_connector_evidence_staff_count": len(candidate_evidence_staves),
        "connector_evidence": {
            "baseline": baseline_evidence,
            "candidate": candidate_evidence,
            "semantics": evidence_semantics,
        },
        "baseline_numbering": baseline_numbering,
        "candidate_numbering": candidate_numbering,
        "numbering_output_equal": baseline_numbering == candidate_numbering,
        "hybrid_consensus_equal": bool(gate.get("hybrid_consensus_equal")),
        "omr_predictions_equal": bool(gate.get("omr_predictions_equal")),
    }
    payload["production_focused_semantics_preserved"] = bool(
        payload["hybrid_consensus_equal"]
        and payload["omr_predictions_equal"]
        and evidence_semantics["left_connector_present_equal"]
        and payload["numbering_output_equal"]
    )

    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
