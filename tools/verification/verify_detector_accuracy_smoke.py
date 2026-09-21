#!/usr/bin/env python3
"""Validate a configured production-representative detector accuracy smoke."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.common.barline_evaluation import greedy_barline_match
from src.pipeline.core.config import load_yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _resolve_repo_path(raw: str | Path) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_boxes(path: Path) -> list[tuple[int, int, int, int]]:
    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, Mapping):
        for key in ("predictions", "boxes"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                payload = candidate
                break

    if not isinstance(payload, list):
        raise ValueError(f"Barline payload must be a list or contain one: {path}")

    result: list[tuple[int, int, int, int]] = []
    for item in payload:
        if isinstance(item, list) and len(item) == 4:
            result.append(tuple(int(value) for value in item))
            continue
        if not isinstance(item, Mapping):
            continue
        bbox = (
            item.get("barline_location")
            or item.get("orig_bbox")
            or item.get("pred_bbox")
            or item.get("bbox")
        )
        if isinstance(bbox, list) and len(bbox) == 4:
            result.append(tuple(int(value) for value in bbox))
    return result


def _without_keys(payload: Mapping[str, Any], ignored: set[str]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in ignored}


def _assert_detection_contract(
    config: Mapping[str, Any],
    validation: Mapping[str, Any],
) -> None:
    reference_path = _resolve_repo_path(str(validation["reference_config"]))
    reference = load_yaml(reference_path)

    actual_detection = config.get("detection")
    reference_detection = reference.get("detection")
    if not isinstance(actual_detection, Mapping) or not isinstance(reference_detection, Mapping):
        raise ValueError("Both smoke and reference configs must define detection mappings")

    allowed_raw = validation.get("allowed_detection_differences", [])
    if not isinstance(allowed_raw, list) or not all(isinstance(item, str) for item in allowed_raw):
        raise ValueError("allowed_detection_differences must be a list of strings")
    allowed = set(allowed_raw)

    actual = _without_keys(actual_detection, allowed)
    expected = _without_keys(reference_detection, allowed)
    if actual != expected:
        raise RuntimeError(
            "Smoke detector contract differs from the production reference config. "
            f"allowed_differences={sorted(allowed)}\n"
            f"smoke={json.dumps(actual, sort_keys=True)}\n"
            f"reference={json.dumps(expected, sort_keys=True)}"
        )


def _resolve_run_dir(config: Mapping[str, Any], explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit if explicit.is_absolute() else REPO_ROOT / explicit

    run = config.get("run")
    if not isinstance(run, Mapping):
        raise ValueError("Config must define run metadata")
    run_id = run.get("run_id")
    output_root = run.get("output_root", "logs/full_pipeline_runs")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("--run-dir is required when config.run.run_id is not fixed")
    return _resolve_repo_path(str(output_root)) / run_id


def verify(config_path: Path, run_dir: Path | None) -> dict[str, Any] | None:
    config = load_yaml(config_path)
    validation_root = config.get("validation")
    if not isinstance(validation_root, Mapping):
        print("No configured detector accuracy validation; skipping post-run accuracy gate.")
        return None

    validation = validation_root.get("detector_accuracy")
    if not isinstance(validation, Mapping):
        print("No configured detector accuracy validation; skipping post-run accuracy gate.")
        return None

    _assert_detection_contract(config, validation)

    resolved_run_dir = _resolve_run_dir(config, run_dir)
    manifest_path = resolved_run_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    page_key = str(validation["page_key"])
    page_id = page_key.rsplit("/", 1)[-1]
    pages = manifest.get("pages")
    if not isinstance(pages, list):
        raise ValueError("Run manifest lacks pages")
    page = next(
        (item for item in pages if isinstance(item, Mapping) and item.get("page_id") == page_id),
        None,
    )
    if page is None:
        raise ValueError(f"Run manifest lacks validation page: {page_id}")

    image_path = _resolve_repo_path(str(page["image_path"]))
    image_sha = _sha256(image_path)
    expected_image_sha = str(validation["expected_input_sha256"]).lower()
    if image_sha != expected_image_sha:
        raise RuntimeError(
            "Rendered smoke input does not match the accepted evaluation image contract: "
            f"expected={expected_image_sha} actual={image_sha}"
        )

    source_reference = page.get("source_reference")
    if not isinstance(source_reference, Mapping):
        raise RuntimeError("Accuracy smoke requires direct PDF-render source provenance")
    source_document = source_reference.get("source_document")
    if not isinstance(source_document, Mapping):
        raise RuntimeError("Accuracy smoke source provenance lacks source_document")
    source_sha = str(source_document.get("sha256", "")).lower()
    expected_source_sha = str(validation["expected_source_pdf_sha256"]).lower()
    if source_sha != expected_source_sha:
        raise RuntimeError(
            f"Accuracy smoke source PDF changed: expected={expected_source_sha} actual={source_sha}"
        )

    gt_path = _resolve_repo_path(str(validation["gt_path"]))
    predictions_path = _resolve_repo_path(str(page["barlines_json"]))
    staff_units_path = _resolve_repo_path(str(validation["staff_units_path"]))

    gt = _load_boxes(gt_path)
    predictions = _load_boxes(predictions_path)

    staff_units = json.loads(staff_units_path.read_text(encoding="utf-8"))
    unit_size = float(staff_units["pages"][page_key]["unit_size"])
    match = greedy_barline_match(
        predictions,
        gt,
        rule_name="center_anchor",
        vov_threshold=0.5,
        unit_size=unit_size,
    )

    summary = {
        "status": "passed",
        "run_dir": str(resolved_run_dir),
        "page_key": page_key,
        "input_sha256": image_sha,
        "source_pdf_sha256": source_sha,
        "prediction_count": len(predictions),
        "gt_count": len(gt),
        "matched": len(match.matches),
        "hard_fp_count": len(match.false_positive_indices),
        "fn_count": len(match.false_negative_indices),
        "soft_count": len(match.soft_matches),
        "barlines_json": str(predictions_path),
    }

    expected_gt_count = int(validation["expected_gt_count"])
    expected_hard_fp = int(validation["expected_hard_fp_count"])
    expected_fn = int(validation["expected_fn_count"])
    expected_soft = int(validation["expected_soft_count"])

    failures: list[str] = []
    if len(gt) != expected_gt_count:
        failures.append(f"gt_count expected={expected_gt_count} actual={len(gt)}")
    if summary["hard_fp_count"] != expected_hard_fp:
        failures.append(f"hard_fp expected={expected_hard_fp} actual={summary['hard_fp_count']}")
    if summary["fn_count"] != expected_fn:
        failures.append(f"fn expected={expected_fn} actual={summary['fn_count']}")
    if summary["soft_count"] != expected_soft:
        failures.append(f"soft expected={expected_soft} actual={summary['soft_count']}")
    if failures:
        summary["status"] = "failed"
        summary["failures"] = failures
        raise RuntimeError(
            "Production-representative detector accuracy smoke failed:\n- "
            + "\n- ".join(failures)
            + "\n"
            + json.dumps(summary, indent=2, ensure_ascii=False)
        )

    summary_path = resolved_run_dir / "detector_accuracy_smoke_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Detector accuracy smoke summary: {summary_path}")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path)
    args = parser.parse_args()

    verify(_resolve_repo_path(args.config), args.run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
