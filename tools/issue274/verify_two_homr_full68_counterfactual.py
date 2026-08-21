#!/usr/bin/env python3
"""Verify Issue #274 with a same-input control-vs-two-HOMR numbering counterfactual.

This is the final causal numbering gate for the HOMR-call reduction.  Earlier
post-hoc checks compared numbering outputs from different production runs.  That is
not a controlled comparison because the authoritative A/original staff segmentation
is rerun and can move or fragment by a few pixels between runs even when the
Issue #274 change is unrelated to A.

For every canonical evaluation2 page this verifier freezes the actual fresh #274
production inputs used by Phase A:

- the fresh authoritative A/original staff mask from the score manifest;
- the fresh current-HOMR connector semantic bundle resolved from that staff path;
- the fresh page image.

It then changes exactly one variable:

- control: retained accepted C/pinned-x4 detector barlines;
- candidate: the actual fresh two-HOMR accepted barlines from the same manifest.

Both variants pass through the same current ``MeasureNumberingPipeline`` on CPU.
The candidate reconstruction must also reproduce the actual fresh production
``numbering_base.json`` exactly (except for page ordinal).  Only then is the
control-vs-candidate topology comparison admissible.

No HOMR, SR, detector, CNN, MMR or OCR inference is rerun.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

import cv2

from src.common.connector_artifacts import describe_connector_artifacts
from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.measure_numbering.serialization import score_to_dict
from src.measure_numbering.types import Score
from tools.issue120.eval_full68_from_intermediates import SCORES
from tools.issue274.analyze_b_downstream_semantic_equivalence import (
    CONTROL_ROOT_DEFAULT,
    accepted_path,
    load_boxes,
    to_workspace,
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_single_page(path: Path) -> Mapping[str, Any]:
    payload = load_json(path)
    if not isinstance(payload, Mapping):
        raise ValueError(f"Expected numbering object: {path}")
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 1 or not isinstance(pages[0], Mapping):
        raise ValueError(f"Expected one serialized page: {path}")
    return pages[0]


def _bbox(value: Any) -> tuple[int, int, int, int]:
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError(f"Invalid bbox: {value!r}")
    return tuple(int(item) for item in value)  # type: ignore[return-value]


def exact_serialized_signature(page: Mapping[str, Any]) -> tuple[Any, ...]:
    """Return the complete serialized numbering contract except page ordinal."""

    systems = page.get("systems")
    empty_systems = page.get("empty_systems")
    if not isinstance(systems, list) or not isinstance(empty_systems, list):
        raise ValueError("Serialized page lacks systems/empty_systems lists")

    system_rows: list[Any] = []
    for system in systems:
        if not isinstance(system, Mapping):
            raise ValueError("Malformed serialized system")
        staves = system.get("staves")
        measures = system.get("measures")
        if not isinstance(staves, list) or not isinstance(measures, list):
            raise ValueError("Serialized system lacks staves/measures")
        system_rows.append(
            (
                tuple(_bbox(staff["bbox"]) for staff in staves if isinstance(staff, Mapping)),
                tuple(
                    (int(measure["number"]), _bbox(measure["bbox"]))
                    for measure in measures
                    if isinstance(measure, Mapping)
                ),
            )
        )

    empty_rows: list[Any] = []
    for system in empty_systems:
        if not isinstance(system, Mapping):
            raise ValueError("Malformed serialized empty system")
        staves = system.get("staves")
        if not isinstance(staves, list):
            raise ValueError("Serialized empty system lacks staves")
        empty_rows.append(
            (
                tuple(_bbox(staff["bbox"]) for staff in staves if isinstance(staff, Mapping)),
                str(system.get("reason", "")),
            )
        )

    return (
        int(page.get("width", -1)),
        int(page.get("height", -1)),
        tuple(system_rows),
        tuple(empty_rows),
    )


def topology_signature(page: Mapping[str, Any]) -> tuple[Any, ...]:
    """Return grouping/numbering topology while ignoring measure-boundary pixel jitter."""

    systems = page.get("systems")
    empty_systems = page.get("empty_systems")
    if not isinstance(systems, list) or not isinstance(empty_systems, list):
        raise ValueError("Serialized page lacks systems/empty_systems lists")

    system_rows: list[Any] = []
    for system in systems:
        if not isinstance(system, Mapping):
            raise ValueError("Malformed serialized system")
        staves = system.get("staves")
        measures = system.get("measures")
        if not isinstance(staves, list) or not isinstance(measures, list):
            raise ValueError("Serialized system lacks staves/measures")
        system_rows.append(
            (
                tuple(_bbox(staff["bbox"]) for staff in staves if isinstance(staff, Mapping)),
                tuple(
                    int(measure["number"]) for measure in measures if isinstance(measure, Mapping)
                ),
            )
        )

    empty_rows: list[Any] = []
    for system in empty_systems:
        if not isinstance(system, Mapping):
            raise ValueError("Malformed serialized empty system")
        staves = system.get("staves")
        if not isinstance(staves, list):
            raise ValueError("Serialized empty system lacks staves")
        empty_rows.append(
            tuple(_bbox(staff["bbox"]) for staff in staves if isinstance(staff, Mapping))
        )

    return (
        int(page.get("width", -1)),
        int(page.get("height", -1)),
        tuple(system_rows),
        tuple(empty_rows),
    )


def geometry_delta(control: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Describe measure-bbox delta only when the causal topology is identical."""

    if topology_signature(control) != topology_signature(candidate):
        return {
            "comparable": False,
            "exact": False,
            "max_abs_x_delta": None,
            "max_abs_y_delta": None,
            "within_2px": False,
            "within_5px": False,
            "within_10px": False,
            "within_15px_dedup_threshold": False,
        }

    max_dx = 0
    max_dy = 0
    exact = True
    for c_system, b_system in zip(control["systems"], candidate["systems"]):
        if not isinstance(c_system, Mapping) or not isinstance(b_system, Mapping):
            raise ValueError("Malformed serialized system")
        c_measures = c_system.get("measures")
        b_measures = b_system.get("measures")
        if not isinstance(c_measures, list) or not isinstance(b_measures, list):
            raise ValueError("Serialized system lacks measures")
        for c_measure, b_measure in zip(c_measures, b_measures):
            if not isinstance(c_measure, Mapping) or not isinstance(b_measure, Mapping):
                raise ValueError("Malformed serialized measure")
            c_box = _bbox(c_measure["bbox"])
            b_box = _bbox(b_measure["bbox"])
            deltas = [abs(a - b) for a, b in zip(c_box, b_box)]
            max_dx = max(max_dx, deltas[0], deltas[2])
            max_dy = max(max_dy, deltas[1], deltas[3])
            exact = exact and all(delta == 0 for delta in deltas)

    return {
        "comparable": True,
        "exact": exact,
        "max_abs_x_delta": max_dx,
        "max_abs_y_delta": max_dy,
        "within_2px": max_dx <= 2 and max_dy <= 2,
        "within_5px": max_dx <= 5 and max_dy <= 5,
        "within_10px": max_dx <= 10 and max_dy <= 10,
        "within_15px_dedup_threshold": max_dx <= 15 and max_dy <= 15,
    }


def run_numbering(
    *,
    boxes: list[tuple[int, int, int, int]],
    staff_mask: Path,
    image: Any,
) -> Mapping[str, Any]:
    h, w = image.shape[:2]
    pipeline = MeasureNumberingPipeline()
    page = pipeline.process_page(
        [list(box) for box in boxes],
        staff_mask,
        (w, h),
        page_number=1,
        assume_one_staff_per_system=False,
        image=image,
    )
    score = Score(pages=[page])
    pipeline.numberer.number_score(score, start_number=1)
    serialized = score_to_dict(score)
    pages = serialized.get("pages")
    if not isinstance(pages, list) or len(pages) != 1 or not isinstance(pages[0], Mapping):
        raise RuntimeError("Counterfactual numbering did not serialize one page")
    return pages[0]


def manifest_pages(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    pages = manifest.get("pages")
    if not isinstance(pages, list):
        raise ValueError("Fresh score manifest lacks pages")
    result: dict[str, Mapping[str, Any]] = {}
    for row in pages:
        if not isinstance(row, Mapping):
            continue
        page_id = str(row.get("page_id", ""))
        if not page_id:
            continue
        if page_id in result:
            raise ValueError(f"Duplicate page_id in fresh manifest: {page_id}")
        result[page_id] = row
    return result


def source_contract(summary: Mapping[str, Any]) -> dict[str, Any]:
    architecture_ok = bool((summary.get("architecture") or {}).get("contract_ok"))
    detector_ok = bool((summary.get("detector") or {}).get("coverage_ok"))
    page_identity_ok = bool(summary.get("page_identity_ok"))
    downstream = summary.get("downstream") or {}
    downstream_ok = (
        isinstance(downstream, Mapping)
        and not downstream.get("contract_bad_pages")
        and int(downstream.get("fallback_page_count", -1)) == 0
    )
    return {
        "architecture_ok": architecture_ok,
        "detector_coverage_ok": detector_ok,
        "page_identity_ok": page_identity_ok,
        "downstream_reuse_ok": downstream_ok,
        "ok": architecture_ok and detector_ok and page_identity_ok and downstream_ok,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--control-root", type=Path, default=CONTROL_ROOT_DEFAULT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    run_root = to_workspace(args.run_root, workspace)
    summary_path = to_workspace(
        args.summary or (run_root / "two_homr_full68_fresh_summary.json"),
        workspace,
    )
    control_root = to_workspace(args.control_root, workspace)
    output = to_workspace(
        args.output or (run_root / "two_homr_full68_counterfactual_v6.json"),
        workspace,
    )

    source_summary = load_json(summary_path)
    if not isinstance(source_summary, Mapping):
        raise ValueError(f"Source summary must be an object: {summary_path}")
    source = source_contract(source_summary)

    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    counts = {
        "pages": 0,
        "candidate_reconstruction_exact": 0,
        "control_candidate_topology_exact": 0,
        "measure_geometry_exact": 0,
        "measure_geometry_within_2px": 0,
        "measure_geometry_within_5px": 0,
        "measure_geometry_within_10px": 0,
        "measure_geometry_within_15px_dedup_threshold": 0,
    }

    for score_name, page_names in SCORES.items():
        manifest_path = run_root / "runs" / score_name / "manifest.json"
        manifest = load_json(manifest_path)
        if not isinstance(manifest, Mapping):
            raise ValueError(f"Fresh manifest must be an object: {manifest_path}")
        config = manifest.get("config") or {}
        steps = config.get("steps") if isinstance(config, Mapping) else None
        if not isinstance(steps, Mapping) or steps.get("apply_barline_overrides") is not False:
            raise RuntimeError(
                f"Counterfactual requires steps.apply_barline_overrides=false: {manifest_path}"
            )
        manifest_by_page = manifest_pages(manifest)

        for page_name in page_names:
            row: dict[str, Any] = {"score": score_name, "page": page_name}
            try:
                manifest_row = manifest_by_page.get(page_name)
                if manifest_row is None:
                    raise KeyError(f"Fresh manifest lacks {score_name}/{page_name}")

                staff_mask = to_workspace(str(manifest_row["staff_mask"]), workspace)
                candidate_path = to_workspace(str(manifest_row["barlines_json"]), workspace)
                image_path = to_workspace(str(manifest_row["image_path"]), workspace)
                control_path = accepted_path(control_root, score_name, page_name)
                actual_path = (
                    run_root
                    / "runs"
                    / score_name
                    / "intermediate"
                    / page_name
                    / "numbering_base.json"
                )

                for required in (staff_mask, candidate_path, image_path, control_path, actual_path):
                    if not required.is_file():
                        raise FileNotFoundError(required)

                connector = describe_connector_artifacts(staff_mask)
                if connector.get("source") != "proxy_symbol_layers":
                    raise RuntimeError(
                        f"Fresh connector contract is not current-HOMR semantic support: {connector}"
                    )

                image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
                if image is None:
                    raise FileNotFoundError(image_path)
                control_boxes = load_boxes(control_path)
                candidate_boxes = load_boxes(candidate_path)

                control_page = run_numbering(
                    boxes=control_boxes,
                    staff_mask=staff_mask,
                    image=image,
                )
                candidate_page = run_numbering(
                    boxes=candidate_boxes,
                    staff_mask=staff_mask,
                    image=image,
                )
                actual_page = load_single_page(actual_path)

                candidate_exact = exact_serialized_signature(
                    candidate_page
                ) == exact_serialized_signature(actual_page)
                topology_equal = topology_signature(control_page) == topology_signature(
                    candidate_page
                )
                geometry = geometry_delta(control_page, candidate_page)

                counts["pages"] += 1
                counts["candidate_reconstruction_exact"] += int(candidate_exact)
                counts["control_candidate_topology_exact"] += int(topology_equal)
                counts["measure_geometry_exact"] += int(bool(geometry["exact"]))
                counts["measure_geometry_within_2px"] += int(bool(geometry["within_2px"]))
                counts["measure_geometry_within_5px"] += int(bool(geometry["within_5px"]))
                counts["measure_geometry_within_10px"] += int(bool(geometry["within_10px"]))
                counts["measure_geometry_within_15px_dedup_threshold"] += int(
                    bool(geometry["within_15px_dedup_threshold"])
                )

                row.update(
                    {
                        "staff_mask": str(staff_mask),
                        "connector_evidence": connector,
                        "control_barlines": str(control_path),
                        "candidate_barlines": str(candidate_path),
                        "actual_numbering_base": str(actual_path),
                        "control_input_box_count": len(control_boxes),
                        "candidate_input_box_count": len(candidate_boxes),
                        "candidate_reconstruction_exact": candidate_exact,
                        "control_candidate_topology_equal": topology_equal,
                        "measure_geometry": geometry,
                    }
                )
                if not topology_equal:
                    row["control_topology"] = topology_signature(control_page)
                    row["candidate_topology"] = topology_signature(candidate_page)
                if not candidate_exact:
                    row["candidate_reconstructed_exact_signature"] = exact_serialized_signature(
                        candidate_page
                    )
                    row["actual_fresh_exact_signature"] = exact_serialized_signature(actual_page)
            except Exception as error:  # noqa: BLE001
                errors.append(
                    {
                        "score": score_name,
                        "page": page_name,
                        "type": type(error).__name__,
                        "message": str(error),
                    }
                )
                row["error"] = errors[-1]
            rows.append(row)

    expected_pages = sum(len(pages) for pages in SCORES.values())
    candidate_link_ok = counts["candidate_reconstruction_exact"] == expected_pages
    topology_ok = counts["control_candidate_topology_exact"] == expected_pages
    gate_pass = (
        source["ok"]
        and not errors
        and counts["pages"] == expected_pages
        and candidate_link_ok
        and topology_ok
    )

    report = {
        "schema_version": "issue274.two_homr_full68_counterfactual.v6",
        "status": "completed",
        "run_root": str(run_root),
        "source_summary": str(summary_path),
        "control_root": str(control_root),
        "expected_page_count": expected_pages,
        "verification_contract": {
            "fixed_inputs": [
                "fresh #274 authoritative A/original staff geometry",
                "fresh #274 current-HOMR connector semantic support",
                "fresh #274 page image",
            ],
            "only_counterfactual_variable": "accepted detector barline set: control C vs fresh two-HOMR B",
            "candidate_reconstruction_must_match_actual_fresh_numbering_exactly": True,
            "control_candidate_gate": "serialized grouping and measure-number topology",
            "measure_bbox_geometry": "reported diagnostically, not used to weaken/replace topology gate",
            "rerun_homr": False,
            "rerun_sr": False,
            "rerun_detector": False,
            "rerun_cnn": False,
            "rerun_mmr": False,
            "rerun_ocr": False,
            "rerun_cpu_numbering": True,
        },
        "source_contract": source,
        "counts": counts,
        "candidate_reconstruction_ok": candidate_link_ok,
        "topology_ok": topology_ok,
        "error_count": len(errors),
        "errors": errors,
        "pages": rows,
        "gate_pass": gate_pass,
        "supersedes": {
            "v5_problem": (
                "compared separate production runs with pixel-exact staff/measure bboxes; "
                "all 68 pages therefore changed even though 60 had identical active grouping/numbering "
                "structure and five more differed only in empty-system segmentation"
            ),
            "causal_fix": (
                "freeze the actual fresh A/connector/image inputs and vary only control-vs-candidate barlines; "
                "also require candidate CPU reconstruction to reproduce actual fresh production exactly"
            ),
        },
    }
    write_json(output, report)
    print(
        json.dumps(
            {
                "gate_pass": gate_pass,
                "source_contract_ok": source["ok"],
                "page_count": counts["pages"],
                "candidate_reconstruction_exact": counts["candidate_reconstruction_exact"],
                "control_candidate_topology_exact": counts["control_candidate_topology_exact"],
                "measure_geometry_exact": counts["measure_geometry_exact"],
                "measure_geometry_within_15px_dedup_threshold": counts[
                    "measure_geometry_within_15px_dedup_threshold"
                ],
                "error_count": len(errors),
                "output": str(output),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if gate_pass else 4


if __name__ == "__main__":
    raise SystemExit(main())
