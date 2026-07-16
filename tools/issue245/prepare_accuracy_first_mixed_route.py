#!/usr/bin/env python3
"""Build an accuracy-first mixed upstream inventory for Issue #245.

The experiment replaces only baseline HOMR with the verified fresh public-upstream
output. Current SR-side HOMR, OMR-DLN, and staff-mask inputs remain unchanged. The
current consensus implementation is then reapplied and compared with the accepted
historical hybrid geometry before any expensive dense/CNN evaluation is run.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Any

from src.pipeline.steps.hybrid_consensus import (
    apply_hybrid_consensus_filter,
    load_json_boxes,
)
from tools.issue120.eval_full68_from_intermediates import SCORES
from tools.issue245.run_pdfscore_evaluator_ref_probe import (
    compare_records,
    load_records,
    sha256_file,
)

DEFAULT_MAIN_REPO = Path("/home/masaki_muramatsu/ws_PDFScoreBar")
DEFAULT_LOGS_ROOT = Path("logs")
DEFAULT_HISTORICAL_INVENTORY = Path(
    "logs/issue36_prep/20260208_bench_inventory.json"
)
DEFAULT_RESTORED_BASELINE_REPORT = Path(
    "logs/issue245_fresh_upstream_full68_probe/"
    "fresh_upstream_full68_probe_report.json"
)
DEFAULT_OUTPUT_ROOT = Path("logs/issue245_accuracy_first_mixed_route")
EXPECTED_PAGES = 68
EXPECTED_CURRENT_TOTALS = {
    "baseline": 10229,
    "sr": 4635,
    "omr": 5984,
    "hybrid": 4064,
}
EXPECTED_HISTORICAL_TOTALS = {
    "baseline": 4381,
    "sr": 3356,
    "omr": 5820,
    "hybrid": 3312,
}


def canonical_keys() -> list[tuple[str, str]]:
    return [(score, page) for score, pages in SCORES.items() for page in pages]


def resolve_repo_path(main_repo: Path, raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else main_repo / path


def load_inventory(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise ValueError(f"Inventory records must be a list: {path}")
    return payload


def inventory_by_key(payload: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for record in payload["records"]:
        if not isinstance(record, dict):
            continue
        score = record.get("score")
        page = record.get("page")
        if not isinstance(score, str) or not isinstance(page, str):
            continue
        key = (score, page)
        if key in result:
            raise RuntimeError(f"Duplicate inventory record: {score}/{page}")
        result[key] = record
    return result


def layer_paths(main_repo: Path, record: dict[str, Any]) -> dict[str, Path]:
    raw_hybrid = record.get("hybrid_predictions")
    if not isinstance(raw_hybrid, str) or not raw_hybrid:
        raise ValueError("Inventory record is missing hybrid_predictions")
    hybrid = resolve_repo_path(main_repo, raw_hybrid)
    page = str(record["page"])

    roots: list[Path] = []
    if hybrid.parent.name == "hybrid_results":
        roots.append(hybrid.parent.parent)
    roots.extend([hybrid.parent, hybrid.parent.parent])

    seen: set[Path] = set()
    unique_roots: list[Path] = []
    for root in roots:
        resolved = root.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique_roots.append(root)

    for root in unique_roots:
        baseline_candidates = [
            root / "baseline" / "batch" / page / f"{page}_detections.json",
            root / "baseline" / page / page / f"{page}_detections.json",
            root / "baseline" / page / f"{page}_detections.json",
        ]
        sr_candidates = [
            root / "sr" / "batch" / page / f"{page}_detections.json",
            root / "sr" / page / page / f"{page}_detections.json",
            root / "sr" / page / f"{page}_detections.json",
        ]
        omr_candidates = [
            root / "omr_sr" / page / "predictions.json",
            root / "omr_sr" / "predictions.json",
        ]
        baseline = next((path for path in baseline_candidates if path.is_file()), None)
        sr = next((path for path in sr_candidates if path.is_file()), None)
        omr = next((path for path in omr_candidates if path.is_file()), None)
        if baseline and sr and omr and hybrid.is_file():
            return {"baseline": baseline, "sr": sr, "omr": omr, "hybrid": hybrid}

    raise FileNotFoundError(
        "Could not resolve baseline/SR/OMR siblings for current hybrid: " f"{hybrid}"
    )


def count_boxes(path: Path) -> int:
    return len(load_json_boxes(path))


def validate_inventory_sources(
    main_repo: Path,
    inventory_path: Path,
) -> dict[str, Any]:
    payload = load_inventory(inventory_path)
    by_key = inventory_by_key(payload)
    required = canonical_keys()
    missing = [f"{score}/{page}" for score, page in required if (score, page) not in by_key]
    if missing:
        raise RuntimeError(
            f"Inventory is missing {len(missing)} canonical pages: " + ", ".join(missing[:10])
        )

    totals = {"baseline": 0, "sr": 0, "omr": 0, "hybrid": 0}
    paths_by_key: dict[tuple[str, str], dict[str, Path]] = {}
    for key in required:
        paths = layer_paths(main_repo, by_key[key])
        paths_by_key[key] = paths
        for layer, path in paths.items():
            totals[layer] += count_boxes(path)

    return {
        "path": str(inventory_path),
        "payload": payload,
        "by_key": by_key,
        "paths_by_key": paths_by_key,
        "totals": totals,
        "canonical_pages": len(required),
    }


def looks_like_inventory(path: Path) -> bool:
    try:
        if not path.is_file() or path.stat().st_size > 50 * 1024 * 1024:
            return False
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            prefix = handle.read(256 * 1024)
        return '"records"' in prefix and '"hybrid_predictions"' in prefix
    except OSError:
        return False


def discover_current_inventory(main_repo: Path, logs_root: Path) -> dict[str, Any]:
    candidates = sorted(logs_root.rglob("*inventory*.json"))
    if not candidates:
        candidates = [path for path in logs_root.rglob("*.json") if looks_like_inventory(path)]

    inspected: list[dict[str, Any]] = []
    matched: list[dict[str, Any]] = []
    for path in candidates:
        if not looks_like_inventory(path):
            continue
        try:
            summary = validate_inventory_sources(main_repo, path)
            item = {
                "path": summary["path"],
                "canonical_pages": summary["canonical_pages"],
                "totals": summary["totals"],
            }
            inspected.append(item)
            if summary["totals"] == EXPECTED_CURRENT_TOTALS:
                matched.append(summary)
        except Exception as error:  # noqa: BLE001
            inspected.append(
                {
                    "path": str(path),
                    "status": "rejected",
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            )

    if len(matched) != 1:
        raise RuntimeError(
            "Expected exactly one current full-68 inventory with totals "
            f"{EXPECTED_CURRENT_TOTALS}, found {len(matched)}. "
            "Pass --current-inventory explicitly. Inspected candidates: "
            + json.dumps(inspected, ensure_ascii=False)
        )
    matched[0]["discovery"] = {"inspected": inspected, "matched_count": len(matched)}
    return matched[0]


def load_restored_baselines(
    main_repo: Path,
    report_path: Path,
) -> dict[tuple[str, str], Path]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("status") != "completed" or not report.get("all_semantic_equal"):
        raise RuntimeError(f"Restored baseline report is not a completed exact match: {report_path}")

    result: dict[tuple[str, str], Path] = {}
    for page in report.get("pages", []):
        if not isinstance(page, dict) or page.get("status") != "completed":
            continue
        image_rel = Path(str(page["image_rel"]))
        key = (image_rel.parent.name, image_rel.stem)
        candidate = resolve_repo_path(main_repo, str(page["candidate_detection"]))
        if not candidate.is_file():
            raise FileNotFoundError(f"Restored baseline detection is missing: {candidate}")
        result[key] = candidate

    missing = [key for key in canonical_keys() if key not in result]
    if missing:
        raise RuntimeError(f"Restored baseline report is missing {len(missing)} pages: {missing[:10]}")
    return result


def aggregate_comparisons(pages: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "pages": len(pages),
        "pages_semantic_equal": sum(
            bool(page["comparison"]["semantic_equal"]) for page in pages
        ),
        "pages_different": sum(
            not bool(page["comparison"]["semantic_equal"]) for page in pages
        ),
        "historical_count": sum(page["comparison"]["left"]["count"] for page in pages),
        "mixed_count": sum(page["comparison"]["right"]["count"] for page in pages),
        "matched_count": sum(page["comparison"]["matched_count"] for page in pages),
        "historical_only_count": sum(
            page["comparison"]["left_only"]["count"] for page in pages
        ),
        "mixed_only_count": sum(
            page["comparison"]["right_only"]["count"] for page in pages
        ),
        "differing_pages": [
            f"{page['score']}/{page['page']}"
            for page in pages
            if not page["comparison"]["semantic_equal"]
        ],
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--main-repo-root",
        type=Path,
        default=Path(os.environ.get("ISSUE245_MAIN_REPO_ROOT", DEFAULT_MAIN_REPO)),
    )
    parser.add_argument("--logs-root", type=Path, default=DEFAULT_LOGS_ROOT)
    parser.add_argument("--current-inventory", type=Path, default=None)
    parser.add_argument(
        "--historical-inventory", type=Path, default=DEFAULT_HISTORICAL_INVENTORY
    )
    parser.add_argument(
        "--restored-baseline-report", type=Path, default=DEFAULT_RESTORED_BASELINE_REPORT
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    main_repo = args.main_repo_root.expanduser().resolve()
    logs_root = resolve_repo_path(main_repo, args.logs_root)
    historical_inventory_path = resolve_repo_path(main_repo, args.historical_inventory)
    restored_report_path = resolve_repo_path(main_repo, args.restored_baseline_report)
    output_root = resolve_repo_path(main_repo, args.output_root)

    if output_root.exists():
        if not args.force:
            raise FileExistsError(f"Output exists; rerun with --force: {output_root}")
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    report_path = output_root / "accuracy_first_mixed_route_report.json"
    report: dict[str, Any] = {
        "schema_version": "issue245.accuracy_first_mixed_route.v1",
        "status": "running",
        "production_default_changed": False,
        "historical_artifact_used_as_production_input": False,
        "experiment": (
            "verified fresh baseline HOMR + current SR-side HOMR + current OMR-DLN "
            "+ current staff mask + current consensus"
        ),
        "expected_current_source_totals": EXPECTED_CURRENT_TOTALS,
        "expected_historical_source_totals": EXPECTED_HISTORICAL_TOTALS,
    }
    write_json(report_path, report)

    try:
        if args.current_inventory is None:
            current = discover_current_inventory(main_repo, logs_root)
        else:
            current_path = resolve_repo_path(main_repo, args.current_inventory)
            current = validate_inventory_sources(main_repo, current_path)
            if current["totals"] != EXPECTED_CURRENT_TOTALS:
                raise RuntimeError(
                    "Explicit current inventory totals do not match the #244 current source run: "
                    f"expected={EXPECTED_CURRENT_TOTALS} actual={current['totals']}"
                )

        historical = validate_inventory_sources(main_repo, historical_inventory_path)
        if historical["totals"] != EXPECTED_HISTORICAL_TOTALS:
            raise RuntimeError(
                "Historical inventory totals do not match the accepted source baseline: "
                f"expected={EXPECTED_HISTORICAL_TOTALS} actual={historical['totals']}"
            )
        restored = load_restored_baselines(main_repo, restored_report_path)

        mixed_records: list[dict[str, Any]] = []
        page_results: list[dict[str, Any]] = []
        mixed_root = output_root / "mixed_hybrid"
        for score, page in canonical_keys():
            key = (score, page)
            current_record = current["by_key"][key]
            current_paths = current["paths_by_key"][key]
            historical_paths = historical["paths_by_key"][key]
            baseline_path = restored[key]

            mixed_predictions = apply_hybrid_consensus_filter(
                baseline_boxes=load_json_boxes(baseline_path),
                sr_boxes=load_json_boxes(current_paths["sr"]),
                omr_boxes=load_json_boxes(current_paths["omr"]),
            )
            mixed_path = mixed_root / score / f"{page}_hybrid.json"
            write_json(mixed_path, mixed_predictions)

            record = dict(current_record)
            record["hybrid_predictions"] = str(mixed_path)
            mixed_records.append(record)

            comparison = compare_records(
                load_records(historical_paths["hybrid"]),
                load_records(mixed_path),
            )
            page_results.append(
                {
                    "score": score,
                    "page": page,
                    "fresh_baseline": str(baseline_path),
                    "current_sr": str(current_paths["sr"]),
                    "current_omr": str(current_paths["omr"]),
                    "current_staff_mask": str(
                        resolve_repo_path(main_repo, str(current_record["staff_mask"]))
                    ),
                    "historical_hybrid": str(historical_paths["hybrid"]),
                    "mixed_hybrid": str(mixed_path),
                    "mixed_hybrid_sha256": sha256_file(mixed_path),
                    "comparison": comparison,
                }
            )

        mixed_inventory = {
            "schema_version": "issue245.accuracy_first_mixed_inventory.v1",
            "source_current_inventory": current["path"],
            "source_historical_inventory": historical["path"],
            "restored_baseline_report": str(restored_report_path),
            "records": mixed_records,
        }
        mixed_inventory_path = output_root / "mixed_inventory.json"
        write_json(mixed_inventory_path, mixed_inventory)

        aggregate = aggregate_comparisons(page_results)
        page_001 = next(
            page
            for page in page_results
            if page["score"] == "Va_Prokofiev_Symphony1" and page["page"] == "page_001"
        )
        report.update(
            {
                "status": "completed",
                "current_inventory": {
                    "path": current["path"],
                    "totals": current["totals"],
                    "discovery": current.get("discovery"),
                },
                "historical_inventory": {
                    "path": historical["path"],
                    "totals": historical["totals"],
                },
                "restored_baseline_report": str(restored_report_path),
                "mixed_inventory": str(mixed_inventory_path),
                "aggregate_comparison_to_historical_hybrid": aggregate,
                "page_001_comparison_to_historical_hybrid": page_001,
                "pages": page_results,
                "next_gate": (
                    "Run Stage E dense/CNN evaluation with mixed_inventory only after reviewing "
                    "the source-level aggregate."
                ),
            }
        )
    except Exception as error:
        report.update(
            {
                "status": "failed",
                "error_type": type(error).__name__,
                "error": str(error),
            }
        )
    finally:
        write_json(report_path, report)

    print(f"Report: {report_path}")
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
