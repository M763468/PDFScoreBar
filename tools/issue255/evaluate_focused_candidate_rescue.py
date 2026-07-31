#!/usr/bin/env python3
"""Evaluate an Issue #255 focused fresh run against gate05 and accepted targets."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.common import barline_iou
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue252.probe_boundary import normalize_box, target_metrics

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TARGETS = ROOT / "tools/issue255/gate05_targets.json"
DEFAULT_BASELINE = (
    ROOT
    / "logs/issue255_focused_fresh/issue255_focused_fresh_batch_issue255_gate_05.json"
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute() and path.parts[:2] == ("/", "workspace"):
        return ROOT / path.relative_to("/workspace")
    return path if path.is_absolute() else ROOT / path


def _artifact_path(contract: Mapping[str, Any], name: str) -> Path:
    artifacts = contract.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError("Focused contract lacks artifacts")
    record = artifacts.get(name)
    if not isinstance(record, Mapping) or record.get("exists") is not True:
        raise ValueError(f"Focused contract lacks completed artifact: {name}")
    path = _resolve_path(str(record["path"]))
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _records(path: Path) -> list[Mapping[str, Any]]:
    payload = _load_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"Expected list: {path}")
    return [item for item in payload if isinstance(item, Mapping)]


def _match_boxes(
    accepted: Sequence[Sequence[int | float]],
    current: Sequence[Sequence[int | float]],
    *,
    accepted_iou: float = 0.5,
) -> dict[str, int]:
    references = [normalize_box(box) for box in accepted]
    predictions = [normalize_box(box) for box in current]
    unmatched = set(range(len(references)))
    true_positive = 0
    false_positive = 0
    for prediction in predictions:
        ranked = sorted(
            (
                (float(barline_iou(prediction, references[index])), index)
                for index in unmatched
            ),
            reverse=True,
        )
        if ranked and ranked[0][0] > accepted_iou:
            unmatched.remove(ranked[0][1])
            true_positive += 1
        else:
            false_positive += 1
    return {
        "tp": true_positive,
        "fp": false_positive,
        "fn": len(unmatched),
    }


def _best_score(reference: Sequence[int | float], scored: Sequence[Mapping[str, Any]]) -> float | None:
    boxes = [normalize_box(item["bbox"]) for item in scored if isinstance(item.get("bbox"), Sequence)]
    metrics = target_metrics(normalize_box(reference), boxes, accepted_iou=0.5)
    best = metrics.get("best")
    if not isinstance(best, Mapping):
        return None
    best_box = normalize_box(best["bbox"])
    for item in scored:
        bbox = item.get("bbox")
        if isinstance(bbox, Sequence) and normalize_box(bbox) == best_box:
            score = item.get("score")
            return float(score) if isinstance(score, (int, float)) else None
    return None


def _run_by_label(batch: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    runs = batch.get("runs")
    if not isinstance(runs, list):
        raise ValueError("Focused batch lacks runs")
    result = {}
    for run in runs:
        if isinstance(run, Mapping) and run.get("label"):
            result[str(run["label"])] = run
    return result


def _evaluate_page(
    *,
    label: str,
    page_spec: Mapping[str, Any],
    current_run: Mapping[str, Any],
    baseline_run: Mapping[str, Any],
) -> dict[str, Any]:
    current_contract = current_run.get("contract")
    baseline_contract = baseline_run.get("contract")
    if not isinstance(current_contract, Mapping) or not isinstance(baseline_contract, Mapping):
        raise ValueError(f"Incomplete focused contracts for {label}")

    accepted_path = _resolve_path(str(page_spec["accepted_barlines"]))
    accepted = load_json_boxes(accepted_path)
    current_final = load_json_boxes(_artifact_path(current_contract, "final_barlines"))
    baseline_final = load_json_boxes(_artifact_path(baseline_contract, "final_barlines"))
    current_scored = _records(_artifact_path(current_contract, "cnn_scored"))

    count_names = ("cnn_candidates", "cnn_scored", "cnn_accepted", "final_barlines")
    baseline_counts = {
        name: len(_load_json(_artifact_path(baseline_contract, name))) for name in count_names
    }
    current_counts = {
        name: len(_load_json(_artifact_path(current_contract, name))) for name in count_names
    }
    count_delta = {name: current_counts[name] - baseline_counts[name] for name in count_names}

    targets = []
    raw_targets = page_spec.get("targets")
    if not isinstance(raw_targets, list):
        raise ValueError(f"Target list missing for {label}")
    for item in raw_targets:
        if not isinstance(item, Mapping) or not isinstance(item.get("accepted_bbox"), Sequence):
            raise ValueError(f"Invalid target for {label}: {item}")
        reference = normalize_box(item["accepted_bbox"])
        metrics = target_metrics(reference, current_final, accepted_iou=0.5)
        targets.append(
            {
                **dict(item),
                "recovered": bool(metrics["accepted"]),
                "best_final": metrics.get("best"),
                "best_cnn_score": _best_score(reference, current_scored),
            }
        )

    baseline_metrics = _match_boxes(accepted, baseline_final)
    current_metrics = _match_boxes(accepted, current_final)
    return {
        "score": page_spec.get("score"),
        "page": page_spec.get("page"),
        "accepted_reference": str(accepted_path),
        "accepted_reference_runtime_input": False,
        "baseline_counts": baseline_counts,
        "current_counts": current_counts,
        "count_delta": count_delta,
        "baseline_metrics": baseline_metrics,
        "current_metrics": current_metrics,
        "focused_fp_delta": current_metrics["fp"] - baseline_metrics["fp"],
        "focused_fn_delta": current_metrics["fn"] - baseline_metrics["fn"],
        "targets": targets,
    }


def build_report(
    *,
    current_batch: Path,
    baseline_batch: Path,
    targets: Path,
    output: Path,
) -> dict[str, Any]:
    current_payload = _load_json(current_batch.resolve())
    baseline_payload = _load_json(baseline_batch.resolve())
    target_payload = _load_json(targets.resolve())
    if not isinstance(current_payload, Mapping) or current_payload.get("status") != "completed":
        raise ValueError("Current focused batch must be completed")
    if not isinstance(baseline_payload, Mapping) or baseline_payload.get("status") != "completed":
        raise ValueError("Baseline focused batch must be completed")
    if not isinstance(target_payload, Mapping) or not isinstance(target_payload.get("pages"), Mapping):
        raise ValueError("Focused target manifest is invalid")

    current_runs = _run_by_label(current_payload)
    baseline_runs = _run_by_label(baseline_payload)
    pages = {}
    for label, page_spec in target_payload["pages"].items():
        if not isinstance(page_spec, Mapping):
            raise ValueError(f"Invalid page specification: {label}")
        pages[str(label)] = _evaluate_page(
            label=str(label),
            page_spec=page_spec,
            current_run=current_runs[str(label)],
            baseline_run=baseline_runs[str(label)],
        )

    target_rows = [target for page in pages.values() for target in page["targets"]]
    report = {
        "schema_version": "issue255.focused_candidate_rescue_evaluation.v1",
        "status": "completed",
        "baseline_commit": baseline_payload.get("expected_commit"),
        "current_commit": current_payload.get("expected_commit"),
        "accepted_reference_runtime_input": False,
        "pages": pages,
        "gates": {
            "all_targets_recovered": all(target["recovered"] for target in target_rows),
            "focused_fp_delta_zero": all(page["focused_fp_delta"] == 0 for page in pages.values()),
        },
    }
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-batch", type=Path, required=True)
    parser.add_argument("--baseline-batch", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--targets", type=Path, default=DEFAULT_TARGETS)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = build_report(
            current_batch=args.current_batch,
            baseline_batch=args.baseline_batch,
            targets=args.targets,
            output=args.output,
        )
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps({"status": report["status"], "gates": report["gates"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
