#!/usr/bin/env python3
"""Analyze residual differences after a focused Stage E reconstruction run.

This analysis is offline. It reads retained fresh-run artifacts and historical
accepted outputs only after detector execution; it never runs HOMR, SR,
OMR-DLN, probe generation, or CNN inference.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue252.probe_boundary import normalize_box, target_metrics, write_json
from tools.issue255.analyze_focused_candidate_multiplicity import (
    _multiplicity,
    _stable_match_details,
)
from tools.issue255.run_focused_stage_e_reconstruction import (
    _drop_evidence,
    _first_loss,
    _layer,
    _scored_layer,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_ROOT = (
    ROOT / "logs/issue255_stage_e_focused/issue255_stage_e_focused_03"
)
REPORT_NAME = "focused_stage_e_reconstruction_report.json"
OUTPUT_NAME = "stage_e_reconstruction_residuals.json"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute() and path.parts[:2] == ("/", "workspace"):
        return ROOT / path.relative_to("/workspace")
    return path if path.is_absolute() else ROOT / path


def _record_path(record: Mapping[str, Any], name: str) -> Path:
    value = record.get("path")
    if not isinstance(value, str):
        raise ValueError(f"Artifact record lacks path: {name}")
    path = _resolve(value).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Artifact missing for {name}: {path}")
    return path


def _scored(path: Path) -> list[dict[str, Any]]:
    payload = _load(path)
    if not isinstance(payload, list):
        raise ValueError(f"Scored payload must be a list: {path}")
    rows = []
    for item in payload:
        if not isinstance(item, Mapping):
            continue
        bbox = item.get("bbox")
        if not isinstance(bbox, Sequence) or isinstance(bbox, (str, bytes)):
            continue
        score = item.get("score")
        rows.append(
            {
                "bbox": normalize_box(bbox),
                "score": float(score) if isinstance(score, (int, float)) else None,
            }
        )
    return rows


def _nearest(
    reference: Sequence[int | float], boxes: Sequence[Any]
) -> dict[str, Any] | None:
    metrics = target_metrics(normalize_box(reference), boxes, accepted_iou=0.5)
    best = metrics.get("best")
    return dict(best) if isinstance(best, Mapping) else None


def _layers(
    reference: tuple[int, int, int, int],
    *,
    raw: Sequence[Any],
    filtered: Sequence[Any],
    issue53: Sequence[Any],
    scored: Sequence[Mapping[str, Any]],
    final: Sequence[Any],
    suggestions: Path,
) -> dict[str, Any]:
    layers = {
        "dense_raw_candidate": _layer(reference, raw),
        "clef_mask_filtering": _layer(reference, filtered),
        "issue53_reconstruction": _layer(reference, issue53),
        "cnn_scored": _scored_layer(reference, scored),
        "cnn_accepted": _layer(reference, final),
        "final_detector_output": _layer(reference, final),
    }
    layers["clef_mask_filtering"]["drop_evidence"] = _drop_evidence(
        suggestions, reference
    )
    return layers


def _combined(
    pages: Mapping[str, Mapping[str, Any]], metric_name: str
) -> dict[str, int]:
    return {
        key: sum(int(page[metric_name][key]) for page in pages.values())
        for key in ("tp", "fp", "fn")
    }


def build_report(run_root: Path) -> dict[str, Any]:
    run_root = run_root.resolve()
    focused_path = run_root / REPORT_NAME
    focused = _load(focused_path)
    if not isinstance(focused, Mapping) or focused.get("status") != "completed":
        raise ValueError(f"Focused Stage E run is not completed: {focused_path}")
    raw_pages = focused.get("pages")
    if not isinstance(raw_pages, Mapping):
        raise ValueError("Focused Stage E report lacks pages")

    pages: dict[str, dict[str, Any]] = {}
    for label, page in raw_pages.items():
        if not isinstance(page, Mapping):
            raise ValueError(f"Invalid page report: {label}")
        artifacts = page.get("artifacts")
        accepted_record = page.get("accepted_reference")
        if not isinstance(artifacts, Mapping) or not isinstance(
            accepted_record, Mapping
        ):
            raise ValueError(f"Incomplete page artifacts: {label}")

        accepted_path = _record_path(accepted_record, f"{label}.accepted_reference")
        control_path = _record_path(
            artifacts["control_final"], f"{label}.control_final"
        )
        raw_path = _record_path(artifacts["dense_raw"], f"{label}.dense_raw")
        filtered_path = _record_path(
            artifacts["filtered"], f"{label}.filtered"
        )
        suggestions_path = _record_path(
            artifacts["filter_suggestions"], f"{label}.filter_suggestions"
        )
        issue53_path = _record_path(artifacts["issue53"], f"{label}.issue53")
        scored_path = _record_path(artifacts["cnn_scored"], f"{label}.cnn_scored")
        final_path = _record_path(artifacts["cnn_accepted"], f"{label}.cnn_accepted")

        accepted = [normalize_box(box) for box in load_json_boxes(accepted_path)]
        control = [normalize_box(box) for box in load_json_boxes(control_path)]
        raw = [normalize_box(box) for box in load_json_boxes(raw_path)]
        filtered = [normalize_box(box) for box in load_json_boxes(filtered_path)]
        issue53 = [normalize_box(box) for box in load_json_boxes(issue53_path)]
        scored = _scored(scored_path)
        final = [normalize_box(box) for box in load_json_boxes(final_path)]

        control_details = _stable_match_details(accepted, control)
        final_details = _stable_match_details(accepted, final)
        control_to_final = _stable_match_details(control, final)

        false_negatives = []
        for bbox in final_details["false_negative_boxes"]:
            reference = normalize_box(bbox)
            layers = _layers(
                reference,
                raw=raw,
                filtered=filtered,
                issue53=issue53,
                scored=scored,
                final=final,
                suggestions=suggestions_path,
            )
            false_negatives.append(
                {
                    "accepted_bbox": list(reference),
                    "control_final": _layer(reference, control),
                    "layers": layers,
                    "first_loss_boundary": _first_loss(layers),
                }
            )

        false_positives = []
        for bbox in final_details["false_positive_boxes"]:
            prediction = normalize_box(bbox)
            layers = _layers(
                prediction,
                raw=raw,
                filtered=filtered,
                issue53=issue53,
                scored=scored,
                final=final,
                suggestions=suggestions_path,
            )
            false_positives.append(
                {
                    "prediction_bbox": list(prediction),
                    "nearest_accepted": _nearest(prediction, accepted),
                    "present_in_control": bool(
                        _layer(prediction, control)["candidate_present"]
                    ),
                    "cnn_score": layers["cnn_scored"].get("cnn_score"),
                    "layers": layers,
                }
            )

        pages[str(label)] = {
            "score": page.get("score"),
            "page": page.get("page"),
            "accepted_reference": str(accepted_path),
            "accepted_reference_runtime_input": False,
            "counts": {
                "accepted": len(accepted),
                "control": len(control),
                "reconstructed": len(final),
            },
            "control_metrics": {
                key: int(control_details[key]) for key in ("tp", "fp", "fn")
            },
            "reconstructed_metrics": {
                key: int(final_details[key]) for key in ("tp", "fp", "fn")
            },
            "control_to_reconstructed": {
                "matched_count": int(control_to_final["tp"]),
                "removed_control_count": int(control_to_final["fn"]),
                "new_reconstructed_count": int(control_to_final["fp"]),
                "removed_control_boxes": control_to_final["false_negative_boxes"],
                "new_reconstructed_boxes": control_to_final["false_positive_boxes"],
            },
            "false_negative_residuals": false_negatives,
            "false_positive_residuals": false_positives,
            "multiplicity": _multiplicity(accepted, final),
        }

    combined_control = _combined(pages, "control_metrics")
    combined_reconstructed = _combined(pages, "reconstructed_metrics")
    return {
        "schema_version": "issue255.stage_e_reconstruction_residuals.v1",
        "status": "completed",
        "analysis_only": True,
        "source_run": str(run_root),
        "source_report": str(focused_path),
        "repository_commit": focused.get("repository", {}).get("commit"),
        "historical_runtime_artifact_dependency_absent": focused.get("gates", {}).get(
            "historical_runtime_artifact_dependency_absent"
        ),
        "pages": pages,
        "combined": {
            "control_metrics": combined_control,
            "reconstructed_metrics": combined_reconstructed,
            "delta": {
                key: combined_reconstructed[key] - combined_control[key]
                for key in ("tp", "fp", "fn")
            },
        },
        "next_gpu_run_required": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_report(args.run_root)
    output = args.output or args.run_root / OUTPUT_NAME
    write_json(output.resolve(), report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "output": str(output.resolve()),
                "combined": report["combined"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
