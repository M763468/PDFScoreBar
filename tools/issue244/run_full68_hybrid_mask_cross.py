#!/usr/bin/env python3
"""Run the Issue #244 hybrid-prediction/staff-mask cross experiment.

The completed historical and current full-68 runs are reused. Only dense candidate
reconstruction and probe-rescue candidate generation are executed for the two
crossed inventories:

C: historical hybrid predictions + current staff masks
D: current hybrid predictions + historical staff masks
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.pipeline.detector_routes.dense_full_pipeline import (
    reconstruct_dense_full_pipeline_route,
)
from tools.issue244.compare_full68_route_artifacts import (
    CANDIDATES_FILE,
    CANONICAL_EXCLUDE,
    CANONICAL_INVENTORY,
    CURRENT_INVENTORY,
    CURRENT_ROUTE,
    HISTORICAL_ROOT,
    canonical_records,
    compare_box_files,
    current_records_by_canonical_key,
    find_artifact,
    resolve_path,
)

DEFAULT_OUTPUT_ROOT = Path("logs/issue244_full_regression/hybrid_mask_cross")
DEFAULT_REPORT = Path("logs/issue244_full_regression/full68_hybrid_mask_cross_report.json")
CROSS_VARIANT_LABELS = (
    "C_historical_pred_current_mask",
    "D_current_pred_historical_mask",
)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _cross_record(
    canonical: dict[str, Any],
    current: dict[str, Any],
    *,
    prediction_source: str,
    mask_source: str,
) -> dict[str, Any]:
    prediction_record = canonical if prediction_source == "historical" else current
    mask_record = canonical if mask_source == "historical" else current
    staff_mask = resolve_path(str(mask_record["staff_mask"]))

    record: dict[str, Any] = {
        "name": f"{canonical['score']}/{canonical['page']}",
        "score": canonical["score"],
        "page": canonical["page"],
        "image": str(resolve_path(str(canonical["image"]))),
        "hybrid_predictions": str(resolve_path(str(prediction_record["hybrid_predictions"]))),
        "staff_mask": str(staff_mask),
        "run_dir": str(staff_mask.parent),
    }
    clef_mask = mask_record.get("clef_mask")
    if clef_mask:
        resolved_clef = resolve_path(str(clef_mask))
        if resolved_clef.exists():
            record["clef_mask"] = str(resolved_clef)
    return record


def _build_cross_inventory(
    canonical: list[dict[str, Any]],
    current_by_key: dict[tuple[str, str], dict[str, Any]],
    *,
    prediction_source: str,
    mask_source: str,
    path: Path,
) -> Path:
    records = []
    for canonical_record in canonical:
        key = (str(canonical_record["score"]), str(canonical_record["page"]))
        records.append(
            _cross_record(
                canonical_record,
                current_by_key[key],
                prediction_source=prediction_source,
                mask_source=mask_source,
            )
        )
    _write_json(path, {"records": records})
    return path


def _variant_candidate_root(label: str, output_root: Path, layer: str) -> Path:
    if label == "A_historical":
        dense = HISTORICAL_ROOT / "dense_candidate_reconstruction"
    elif label == "B_current":
        dense = CURRENT_ROUTE / "dense_candidate_reconstruction"
    else:
        dense = output_root / label / "dense_candidate_reconstruction"
    return dense / layer


def _variant_page_identity(
    label: str,
    canonical: dict[str, Any],
    current: dict[str, Any],
) -> tuple[str, str]:
    if label == "B_current":
        return str(current["score"]), str(current["page"])
    return str(canonical["score"]), str(canonical["page"])


def _compare_variant_to_historical(
    *,
    label: str,
    layer: str,
    canonical: list[dict[str, Any]],
    current_by_key: dict[tuple[str, str], dict[str, Any]],
    output_root: Path,
) -> dict[str, Any]:
    historical_root = _variant_candidate_root("A_historical", output_root, layer)
    variant_root = _variant_candidate_root(label, output_root, layer)
    aggregate = {
        "historical": 0,
        "variant": 0,
        "tolerant_matches": 0,
        "historical_only": 0,
        "variant_only": 0,
        "exact_equal_pages": 0,
    }
    pages: dict[str, Any] = {}

    for canonical_record in canonical:
        key = (str(canonical_record["score"]), str(canonical_record["page"]))
        current_record = current_by_key[key]
        variant_score, variant_page = _variant_page_identity(
            label, canonical_record, current_record
        )
        historical_path = find_artifact(
            historical_root,
            key[0],
            key[1],
            CANDIDATES_FILE,
        )
        variant_path = find_artifact(
            variant_root,
            variant_score,
            variant_page,
            CANDIDATES_FILE,
        )
        comparison = compare_box_files(historical_path, variant_path)
        if comparison["historical_count"] is None:
            raise RuntimeError(
                f"Missing candidate artifact for {label} {layer} {key}: {comparison}"
            )
        aggregate["historical"] += int(comparison["historical_count"])
        aggregate["variant"] += int(comparison["current_count"])
        aggregate["tolerant_matches"] += int(comparison["tolerant_matches"])
        aggregate["historical_only"] += int(comparison["historical_only"])
        aggregate["variant_only"] += int(comparison["current_only"])
        if comparison["exact_equal"]:
            aggregate["exact_equal_pages"] += 1
        pages[f"{key[0]}/{key[1]}"] = comparison

    aggregate["symmetric_difference"] = aggregate["historical_only"] + aggregate["variant_only"]
    return {"aggregate": aggregate, "pages": pages}


def _diagnose(comparisons: dict[str, Any]) -> dict[str, Any]:
    diagnosis: dict[str, Any] = {}
    labels = ("B_current", *CROSS_VARIANT_LABELS)
    for layer in ("probe_candidates_filtered", "probe_rescue_candidates"):
        scores = {
            label: int(comparisons[label][layer]["aggregate"]["symmetric_difference"])
            for label in labels
        }
        best_cross = min(CROSS_VARIANT_LABELS, key=lambda label: scores[label])
        diagnosis[layer] = {
            "symmetric_difference_from_historical": scores,
            "closer_cross_variant": best_cross,
            "interpretation": (
                "current staff-mask selection is the larger contributor"
                if best_cross == "D_current_pred_historical_mask"
                else "current hybrid predictions are the larger contributor"
            ),
            "note": (
                "If both cross variants remain materially worse than A, both upstream "
                "artifacts contribute and neither can be treated as the sole cause."
            ),
        }
    return diagnosis


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--verbose-logs", action="store_true")
    args = parser.parse_args()

    canonical = canonical_records()
    current_by_key = current_records_by_canonical_key(canonical)
    args.output_root.mkdir(parents=True, exist_ok=True)

    variants = {
        "C_historical_pred_current_mask": ("historical", "current"),
        "D_current_pred_historical_mask": ("current", "historical"),
    }
    execution: dict[str, Any] = {}
    for label, (prediction_source, mask_source) in variants.items():
        route_root = args.output_root / label
        inventory_path = route_root / "cross_inventory.json"
        exclude_path = route_root / "cross_exclude.json"
        _build_cross_inventory(
            canonical,
            current_by_key,
            prediction_source=prediction_source,
            mask_source=mask_source,
            path=inventory_path,
        )
        _write_json(exclude_path, {"excluded_pages": []})
        artifacts = reconstruct_dense_full_pipeline_route(
            inventory=inventory_path,
            exclude=exclude_path,
            route_root=route_root,
            expected_pages=len(canonical),
            verbose_logs=args.verbose_logs,
        )
        execution[label] = artifacts.execution_summary

    comparisons: dict[str, Any] = {}
    for label in ("B_current", *CROSS_VARIANT_LABELS):
        comparisons[label] = {}
        for layer in (
            "probe_candidates_filtered",
            "probe_rescue_candidates",
        ):
            comparisons[label][layer] = _compare_variant_to_historical(
                label=label,
                layer=layer,
                canonical=canonical,
                current_by_key=current_by_key,
                output_root=args.output_root,
            )

    report = {
        "schema": "issue244.full68_hybrid_mask_cross.v1",
        "page_count": len(canonical),
        "sources": {
            "canonical_inventory": str(CANONICAL_INVENTORY),
            "canonical_exclude": str(CANONICAL_EXCLUDE),
            "current_inventory": str(CURRENT_INVENTORY),
            "historical_root": str(HISTORICAL_ROOT),
            "current_route": str(CURRENT_ROUTE),
        },
        "variants": {
            "A_historical": "historical predictions + historical staff masks",
            "B_current": "current predictions + current staff masks",
            "C_historical_pred_current_mask": ("historical predictions + current staff masks"),
            "D_current_pred_historical_mask": ("current predictions + historical staff masks"),
        },
        "execution": execution,
        "comparisons_to_A_historical": comparisons,
        "diagnosis": _diagnose(comparisons),
    }
    _write_json(args.report, report)

    print("Issue #244 hybrid prediction / staff mask cross experiment")
    print(f"Pages: {len(canonical)}")
    for layer in ("probe_candidates_filtered", "probe_rescue_candidates"):
        print(f"Layer: {layer}")
        for label in comparisons:
            aggregate = comparisons[label][layer]["aggregate"]
            print(
                f"  {label}: count={aggregate['variant']} "
                f"matches={aggregate['tolerant_matches']} "
                f"historical_only={aggregate['historical_only']} "
                f"variant_only={aggregate['variant_only']} "
                f"symmetric_difference={aggregate['symmetric_difference']}"
            )
        print(f"  diagnosis={report['diagnosis'][layer]}")
    print(f"Report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
