#!/usr/bin/env python3
"""Compare focused fresh Stage E inputs/layers with recovered historical ones.

Offline reconstruction analysis only. No detector or model inference is run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import cv2

from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue252.probe_boundary import normalize_box, write_json

ROOT = Path(__file__).resolve().parents[2]
CANDIDATES = "pipeline2_no_peak_candidates.json"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute() and path.parts[:2] == ("/", "workspace"):
        return ROOT / path.relative_to("/workspace")
    return path if path.is_absolute() else ROOT / path


def _record(payload: Any, score: str, page: str) -> Mapping[str, Any]:
    records = payload.get("records") if isinstance(payload, Mapping) else None
    if not isinstance(records, list):
        raise ValueError("Inventory records must be a list")
    matches = [
        item
        for item in records
        if isinstance(item, Mapping)
        and str(item.get("score")) == score
        and str(item.get("page")) == page
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected one record for {score}/{page}: {len(matches)}")
    return matches[0]


def _artifact(record: Mapping[str, Any], key: str) -> Path:
    value = record.get(key)
    if value:
        path = _resolve(str(value))
        if path.is_file():
            return path
    if key != "clef_mask":
        raise FileNotFoundError(f"Missing {key}: {record}")

    staff_raw = record.get("staff_mask")
    if staff_raw:
        staff = _resolve(str(staff_raw))
        for old, new in (
            ("_proxy_debug_3_staff.png", "_proxy_debug_7_clefs_keys.png"),
            ("_debug_3_staff.png", "_debug_7_clefs_keys.png"),
        ):
            candidate = Path(str(staff).replace(old, new))
            if candidate.is_file():
                return candidate

    run_dir_raw = record.get("run_dir")
    if run_dir_raw:
        run_dir = _resolve(str(run_dir_raw))
        found = sorted(run_dir.rglob("*_debug_7_clefs_keys.png"))
        page = str(record.get("page", ""))
        for candidate in found:
            if not page or page in candidate.name:
                return candidate
        if found:
            return found[0]
    raise FileNotFoundError(f"Cannot resolve historical clef mask: {record}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _boxes(path: Path) -> set[tuple[int, int, int, int]]:
    return {normalize_box(box) for box in load_json_boxes(path)}


def _box_comparison(historical: Path, current: Path) -> dict[str, Any]:
    historical_boxes = _boxes(historical)
    current_boxes = _boxes(current)
    extra = sorted(current_boxes - historical_boxes)
    missing = sorted(historical_boxes - current_boxes)
    return {
        "historical_path": str(historical),
        "current_path": str(current),
        "historical_sha256": _sha256(historical),
        "current_sha256": _sha256(current),
        "historical_count": len(historical_boxes),
        "current_count": len(current_boxes),
        "exact_match": not extra and not missing,
        "extra_in_current_count": len(extra),
        "missing_from_current_count": len(missing),
        "extra_in_current": [list(box) for box in extra],
        "missing_from_current": [list(box) for box in missing],
    }


def _mask_comparison(historical: Path, current: Path) -> dict[str, Any]:
    rows = {}
    for name, path in (("historical", historical), ("current", current)):
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise FileNotFoundError(path)
        rows[name] = {
            "path": str(path),
            "sha256": _sha256(path),
            "shape": [int(image.shape[0]), int(image.shape[1])],
            "nonzero_pixels": int(cv2.countNonZero(image)),
        }
    rows["byte_identical"] = rows["historical"]["sha256"] == rows["current"]["sha256"]
    return rows


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    run_root = args.run_root.resolve()
    focused = _load(run_root / "focused_stage_e_reconstruction_report.json")
    fresh_inventory = _load(run_root / "fresh_inventory.json")
    historical_inventory = _load(args.historical_inventory.resolve())
    report_pages = focused.get("pages")
    if not isinstance(report_pages, Mapping):
        raise ValueError("Focused report lacks pages")

    pages = {}
    for label, page_report in report_pages.items():
        if not isinstance(page_report, Mapping):
            raise ValueError(label)
        score, page = str(page_report["score"]), str(page_report["page"])
        historical_record = _record(historical_inventory, score, page)
        fresh_record = _record(fresh_inventory, score, page)
        snapshot = run_root / "fresh_source_snapshot" / score / page

        current_raw = (
            run_root / "dense_route/dense_candidate_reconstruction/"
            "probe_candidates_from_inventory" / score / page / CANDIDATES
        )
        current_filtered = (
            run_root / "dense_route/dense_candidate_reconstruction/"
            "probe_candidates_filtered" / score / page / CANDIDATES
        )
        historical_raw = args.historical_raw_root.resolve() / score / page / CANDIDATES
        historical_filtered = args.historical_filtered_root.resolve() / score / page / CANDIDATES

        layers = {
            "dense_raw": _box_comparison(historical_raw, current_raw),
            "clef_filtered": _box_comparison(historical_filtered, current_filtered),
        }
        first_divergence = next(
            (name for name, value in layers.items() if not value["exact_match"]),
            "exact_match",
        )
        sources = {
            "hybrid_predictions": _box_comparison(
                _artifact(historical_record, "hybrid_predictions"),
                snapshot / "hybrid.json",
            ),
            "staff_mask": _mask_comparison(
                _artifact(historical_record, "staff_mask"),
                snapshot / "staff_mask.png",
            ),
            "clef_mask": _mask_comparison(
                _artifact(historical_record, "clef_mask"),
                snapshot / "clef_mask.png",
            ),
        }
        pages[str(label)] = {
            "score": score,
            "page": page,
            "first_exact_divergence": first_divergence,
            "layer_comparisons": layers,
            "source_comparisons": sources,
            "historical_inventory_record": dict(historical_record),
            "fresh_inventory_record": dict(fresh_record),
        }

    return {
        "schema_version": "issue255.stage_e_historical_input_comparison.v1",
        "status": "completed",
        "analysis_only": True,
        "restoration_scope_only": True,
        "source_run": str(run_root),
        "pages": pages,
        "next_gpu_run_required": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument(
        "--historical-inventory",
        type=Path,
        default=ROOT / "logs/issue36_prep/20260208_bench_inventory.json",
    )
    parser.add_argument(
        "--historical-raw-root",
        type=Path,
        default=ROOT / "logs/issue36_prep/probe_candidates_from_bench_v12",
    )
    parser.add_argument(
        "--historical-filtered-root",
        type=Path,
        default=ROOT / "logs/issue36_prep/probe_candidates_filtered_v12",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or (args.run_root.resolve() / "stage_e_historical_input_comparison.json")
    report = build_report(args)
    write_json(output, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "output": str(output),
                "pages": {
                    label: value["first_exact_divergence"]
                    for label, value in report["pages"].items()
                },
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
