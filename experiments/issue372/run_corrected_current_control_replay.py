#!/usr/bin/env python3
"""Replay only the Issue #372 current-control downstream contract and compare it
with the completed fresh production combined run.

No detector/HOMR/SR/OMR-DLN inference is rerun. Current-control barlines come
from retained x4-gap control artifacts; MMR/final numbering are replayed fresh
with the corrected score-local page-index contract.
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

import torch

from experiments.issue372.run_fresh_downstream_semantic_replay import (
    EXPECTED_PAGES,
    _extract_boxes,
    _find_page_file,
    _prepare_runtime,
    _run_variant_downstream,
)
from src.measure_numbering.mmr import MMRClassifier, MMROCREngine
from tools.issue120 import eval_full68_from_intermediates as full68_eval


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _production_rows(report: Mapping[str, Any]) -> dict[tuple[str, str], Mapping[str, Any]]:
    rows: dict[tuple[str, str], Mapping[str, Any]] = {}
    for score_summary in report["score_summaries"]:
        score = str(score_summary["score"])
        for page, row in score_summary["page_results"].items():
            rows[(score, str(page))] = row
    if len(rows) != EXPECTED_PAGES:
        raise RuntimeError(f"Expected {EXPECTED_PAGES} production pages, got {len(rows)}")
    return rows


def _control_barlines(
    x4_run_root: Path,
) -> tuple[dict[tuple[str, str], list[tuple[int, int, int, int]]], int]:
    source_root = x4_run_root / "control" / "aggregate_probe_output"
    if not source_root.is_dir():
        raise FileNotFoundError(source_root)
    rows = {}
    total = 0
    for score, pages in full68_eval.SCORES.items():
        for page in pages:
            path = _find_page_file(
                source_root,
                score,
                page,
                "pipeline2_no_peak_filtered_cnn.json",
            )
            boxes = _extract_boxes(_load(path))
            rows[(score, page)] = boxes
            total += len(boxes)
    if len(rows) != EXPECTED_PAGES:
        raise RuntimeError(f"Expected {EXPECTED_PAGES} control pages, got {len(rows)}")
    return rows, total


def _measure_counts(logical: Mapping[str, Any]) -> list[int]:
    return [int(system["measure_count"]) for system in logical["systems"]]


def _number_sequences(logical: Mapping[str, Any]) -> list[list[Any]]:
    return [list(system["numbers"]) for system in logical["systems"]]


def _mmr_semantics(rows: Any) -> list[tuple[int, int, int]]:
    if not isinstance(rows, list):
        return []
    result = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        try:
            result.append((int(row["system"]), int(row["measure"]), int(row["skip"])))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(result)


def run(args: argparse.Namespace) -> dict[str, Any]:
    production_report = _load(args.production_report.resolve())
    if not isinstance(production_report, Mapping):
        raise ValueError("production report must be an object")
    production = _production_rows(production_report)

    x4_run_root = args.x4_run_root.resolve()
    issue43_root = args.issue43_repo_root.resolve()
    image_root = args.image_root.resolve()
    model_path = args.mmr_model.resolve()
    output_root = args.output_root.resolve()
    for required in (x4_run_root, issue43_root, image_root, model_path):
        if not required.exists():
            raise FileNotFoundError(required)
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"Output root must be new/empty: {output_root}")

    runtime = _prepare_runtime(
        x4_run_root=x4_run_root,
        issue43_repo_root=issue43_root,
        image_root=image_root,
    )
    barlines, total = _control_barlines(x4_run_root)
    if total != 3643:
        raise RuntimeError(f"Unexpected current-control barline total: {total}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("Corrected current-control replay requires CUDA")
    classifier = MMRClassifier(model_path, device)
    ocr_engine = MMROCREngine(enable_rotation_tta=False)

    output_root.mkdir(parents=True, exist_ok=True)
    print("=== corrected downstream variant: current_control ===", flush=True)
    control = _run_variant_downstream(
        label="current_control_corrected",
        barlines=barlines,
        runtime=runtime,
        output_root=output_root,
        model_path=model_path,
        device=device,
        classifier=classifier,
        ocr_engine=ocr_engine,
        mmr_threshold=float(args.mmr_threshold),
        rescue_threshold=float(args.mmr_rescue_threshold),
    )

    changed = []
    topology_changed = []
    mmr_changed = []
    number_changed = []
    for key in sorted(control):
        score, page = key
        left = control[key]
        right = production[key]
        control_counts = _measure_counts(left["continued_logical"])
        prod_counts = _measure_counts(right["continued_logical"])
        control_nums = _number_sequences(left["continued_logical"])
        prod_nums = _number_sequences(right["continued_logical"])
        control_mmr = _mmr_semantics(left["mmr_overrides"])
        prod_mmr = _mmr_semantics(right["mmr_overrides"])
        start_delta = int(right["continued_start_number"]) - int(left["continued_start_number"])
        next_delta = int(right["continued_next_number"]) - int(left["continued_next_number"])

        row = {
            "score": score,
            "page": page,
            "topology_equal": control_counts == prod_counts,
            "mmr_equal": control_mmr == prod_mmr,
            "number_values_equal": control_nums == prod_nums,
            "control_start": int(left["continued_start_number"]),
            "production_start": int(right["continued_start_number"]),
            "start_delta": start_delta,
            "control_next": int(left["continued_next_number"]),
            "production_next": int(right["continued_next_number"]),
            "next_delta": next_delta,
            "control_measure_counts": control_counts,
            "production_measure_counts": prod_counts,
            "control_mmr": [
                {"system": s, "measure": m, "skip": skip}
                for s, m, skip in control_mmr
            ],
            "production_mmr": [
                {"system": s, "measure": m, "skip": skip}
                for s, m, skip in prod_mmr
            ],
        }
        if not row["topology_equal"]:
            topology_changed.append(row)
        if not row["mmr_equal"]:
            mmr_changed.append(row)
        if not row["number_values_equal"]:
            number_changed.append(row)
        if (
            not row["topology_equal"]
            or not row["mmr_equal"]
            or not row["number_values_equal"]
            or start_delta != 0
            or next_delta != 0
        ):
            changed.append(row)

    target = next(
        row for row in changed
        if row["score"] == "Shostakovich-Sym5-Va" and row["page"] == "page_021"
    )

    independent_changes = [
        row for row in changed
        if not (
            row["score"] == "Shostakovich-Sym5-Va"
            and row["page"] in {"page_021", "page_022", "page_024", "page_025"}
        )
    ]

    report = {
        "schema_version": "issue372.corrected_current_control_vs_production.v1",
        "contract": {
            "detector_rerun": False,
            "control_barline_source": str(x4_run_root / "control" / "aggregate_probe_output"),
            "mmr_page_frame": "score-local page_number/score_index",
            "production_source": str(args.production_report.resolve()),
        },
        "summary": {
            "page_count": len(control),
            "topology_changed_page_count": len(topology_changed),
            "mmr_changed_page_count": len(mmr_changed),
            "number_value_changed_page_count": len(number_changed),
            "any_changed_page_count": len(changed),
            "independent_changed_page_count": len(independent_changes),
        },
        "page021": target,
        "changed_pages": changed,
        "independent_changed_pages": independent_changes,
        "variant": {
            "current_control": {
                "barline_count": total,
                "mmr_override_count": sum(len(row["mmr_overrides"]) for row in control.values()),
            }
        },
    }
    report_path = output_root / "corrected_current_control_vs_production.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("=== Issue #372 corrected current-control vs production ===")
    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
    print("\n=== page_021 ===")
    print(json.dumps(target, indent=2, ensure_ascii=False))
    print("\n=== changed pages ===")
    for row in changed:
        print(
            f"{row['score']}/{row['page']} "
            f"topology_equal={row['topology_equal']} "
            f"mmr_equal={row['mmr_equal']} "
            f"start_delta={row['start_delta']} next_delta={row['next_delta']}"
        )
    print(f"\nOUTPUT={report_path}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production-report", type=Path, required=True)
    parser.add_argument("--x4-run-root", type=Path, required=True)
    parser.add_argument("--issue43-repo-root", type=Path, required=True)
    parser.add_argument("--image-root", type=Path, required=True)
    parser.add_argument(
        "--mmr-model",
        type=Path,
        default=ROOT / "tools/mmr_training/models/mmr_classifier_best.pth",
    )
    parser.add_argument("--mmr-threshold", type=float, default=0.5)
    parser.add_argument("--mmr-rescue-threshold", type=float, default=0.1)
    parser.add_argument("--output-root", type=Path, required=True)
    run(parser.parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
