#!/usr/bin/env python3
"""Build a host-resolved current full-68 inventory from Issue #244 cross inventories.

Cross C preserves the current staff mask while replaying historical hybrid predictions.
Cross D preserves the current hybrid predictions while replaying the historical staff mask.
Combining C staff-mask fields with D hybrid fields reconstructs the current upstream
inventory needed by the Issue #245 mixed-route experiment without another GPU run.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

DEFAULT_MAIN_REPO = Path("/home/masaki_muramatsu/ws_PDFScoreBar")
DEFAULT_CURRENT_MASK_INVENTORY = Path(
    "logs/issue244_full_regression/hybrid_mask_cross/"
    "C_historical_pred_current_mask/cross_inventory.json"
)
DEFAULT_CURRENT_PRED_INVENTORY = Path(
    "logs/issue244_full_regression/hybrid_mask_cross/"
    "D_current_pred_historical_mask/cross_inventory.json"
)
DEFAULT_OUTPUT = Path("logs/issue245_current_source_inventory.json")
DEFAULT_NORMALIZED_ROOT = Path("logs/issue245_current_source_layers")
EXPECTED_PAGES = 68


def resolve_host_path(main_repo: Path, raw: str | Path) -> Path:
    """Resolve repository-relative and /workspace container paths on the host."""
    path = Path(raw)
    if path.is_absolute():
        try:
            relative = path.relative_to("/workspace")
        except ValueError:
            return path
        return main_repo / relative
    return main_repo / path


def load_inventory(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise ValueError(f"Inventory records must be a list: {path}")
    return payload


def records_by_key(payload: dict[str, Any], source: Path) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for record in payload["records"]:
        if not isinstance(record, dict):
            continue
        score = record.get("score")
        page = record.get("page")
        if not isinstance(score, str) or not isinstance(page, str):
            raise ValueError(f"Inventory record is missing score/page: {source}")
        key = (score, page)
        if key in result:
            raise RuntimeError(f"Duplicate inventory record: {score}/{page} in {source}")
        result[key] = record
    return result


def normalize_record_paths(main_repo: Path, record: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    for key, value in list(normalized.items()):
        if not isinstance(value, str):
            continue
        if key.endswith("_path") or key in {
            "image",
            "staff_mask",
            "hybrid_predictions",
            "baseline_predictions",
            "sr_predictions",
            "omr_predictions",
        }:
            normalized[key] = str(resolve_host_path(main_repo, value))
    return normalized


def _normalized_token(value: str | Path) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


def _matches_page(path: Path, run_root: Path, score: str, page: str) -> bool:
    try:
        relative = path.relative_to(run_root)
    except ValueError:
        relative = path
    return _normalized_token(f"{score}_{page}") in _normalized_token(relative)


def _choose_unique(layer: str, candidates: list[Path], *, score: str, page: str) -> Path:
    unique = sorted({path.resolve() for path in candidates if path.is_file()})
    if len(unique) != 1:
        raise FileNotFoundError(
            f"Expected one current {layer} artifact for {score}/{page}, found {len(unique)}: "
            + ", ".join(str(path) for path in unique[:20])
        )
    return unique[0]


def resolve_current_layers(current_hybrid: Path, score: str, page: str) -> dict[str, Path]:
    """Resolve score-qualified current baseline/SR/OMR artifacts from one run root."""
    if not current_hybrid.is_file():
        raise FileNotFoundError(f"Current hybrid prediction is missing: {current_hybrid}")
    if current_hybrid.parent.name != "hybrid_results":
        raise RuntimeError(f"Unexpected current hybrid layout: {current_hybrid}")

    run_root = current_hybrid.parent.parent
    stem = f"{score}_{page}"
    direct = {
        "baseline": [
            run_root / "baseline" / "batch" / stem / f"{stem}_detections.json",
            run_root / "baseline" / stem / stem / f"{stem}_detections.json",
            run_root / "baseline" / stem / f"{stem}_detections.json",
        ],
        "sr": [
            run_root / "sr" / "batch" / stem / f"{stem}_detections.json",
            run_root / "sr" / stem / stem / f"{stem}_detections.json",
            run_root / "sr" / stem / f"{stem}_detections.json",
        ],
        "omr": [
            run_root / "omr_sr" / stem / "predictions.json",
            run_root / "omr_sr" / "batch" / stem / "predictions.json",
        ],
    }

    json_files = list(run_root.rglob("*.json"))
    fallback = {
        "baseline": [
            path
            for path in json_files
            if "baseline" in path.parts
            and path.name.endswith("_detections.json")
            and _matches_page(path, run_root, score, page)
        ],
        "sr": [
            path
            for path in json_files
            if "sr" in path.parts
            and "omr_sr" not in path.parts
            and path.name.endswith("_detections.json")
            and _matches_page(path, run_root, score, page)
        ],
        "omr": [
            path
            for path in json_files
            if "omr_sr" in path.parts
            and path.name == "predictions.json"
            and _matches_page(path, run_root, score, page)
        ],
    }

    resolved: dict[str, Path] = {"hybrid": current_hybrid.resolve()}
    for layer in ("baseline", "sr", "omr"):
        existing_direct = [path for path in direct[layer] if path.is_file()]
        candidates = existing_direct if existing_direct else fallback[layer]
        resolved[layer] = _choose_unique(layer, candidates, score=score, page=page)
    return resolved


def _replace_with_symlink(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        destination.unlink()
    destination.symlink_to(source.resolve())


def materialize_normalized_layers(
    *,
    normalized_root: Path,
    score: str,
    page: str,
    source_layers: dict[str, Path],
) -> dict[str, Path]:
    """Expose one page through the page-only layout expected by the mixed-route validator."""
    page_root = normalized_root / score / page
    destinations = {
        "baseline": page_root / "baseline" / "batch" / page / f"{page}_detections.json",
        "sr": page_root / "sr" / "batch" / page / f"{page}_detections.json",
        "omr": page_root / "omr_sr" / page / "predictions.json",
        "hybrid": page_root / "hybrid_results" / f"{page}_hybrid.json",
    }
    for layer, destination in destinations.items():
        _replace_with_symlink(source_layers[layer], destination)
    return destinations


def build_current_inventory(
    *,
    main_repo: Path,
    current_mask_inventory: Path,
    current_prediction_inventory: Path,
    normalized_root: Path,
) -> dict[str, Any]:
    mask_payload = load_inventory(current_mask_inventory)
    pred_payload = load_inventory(current_prediction_inventory)
    mask_records = records_by_key(mask_payload, current_mask_inventory)
    pred_records = records_by_key(pred_payload, current_prediction_inventory)

    if set(mask_records) != set(pred_records):
        missing_mask = sorted(set(pred_records) - set(mask_records))
        missing_pred = sorted(set(mask_records) - set(pred_records))
        raise RuntimeError(
            "Cross inventories do not contain the same page keys: "
            f"missing_mask={missing_mask[:10]} missing_prediction={missing_pred[:10]}"
        )
    if len(mask_records) != EXPECTED_PAGES:
        raise RuntimeError(
            f"Expected {EXPECTED_PAGES} cross-inventory pages, found {len(mask_records)}"
        )

    shutil.rmtree(normalized_root, ignore_errors=True)
    normalized_root.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    source_manifest: list[dict[str, Any]] = []
    for key in sorted(mask_records):
        score, page = key
        mask_record = normalize_record_paths(main_repo, mask_records[key])
        pred_record = normalize_record_paths(main_repo, pred_records[key])

        current_staff_mask = mask_record.get("staff_mask")
        current_hybrid = pred_record.get("hybrid_predictions")
        if not isinstance(current_staff_mask, str) or not current_staff_mask:
            raise ValueError(f"Current-mask record is missing staff_mask: {key}")
        if not isinstance(current_hybrid, str) or not current_hybrid:
            raise ValueError(f"Current-prediction record is missing hybrid_predictions: {key}")
        if not Path(current_staff_mask).is_file():
            raise FileNotFoundError(f"Current staff mask is missing: {current_staff_mask}")

        source_layers = resolve_current_layers(Path(current_hybrid), score, page)
        normalized_layers = materialize_normalized_layers(
            normalized_root=normalized_root,
            score=score,
            page=page,
            source_layers=source_layers,
        )

        merged = mask_record
        merged["hybrid_predictions"] = str(normalized_layers["hybrid"])
        merged["staff_mask"] = current_staff_mask
        merged["issue245_source_cross_current_mask"] = str(current_mask_inventory)
        merged["issue245_source_cross_current_prediction"] = str(current_prediction_inventory)
        records.append(merged)
        source_manifest.append(
            {
                "score": score,
                "page": page,
                "source_layers": {name: str(path) for name, path in source_layers.items()},
                "normalized_layers": {
                    name: str(path) for name, path in normalized_layers.items()
                },
                "current_staff_mask": current_staff_mask,
            }
        )

    return {
        "schema_version": "issue245.current_source_inventory_from_cross.v2",
        "source_current_mask_inventory": str(current_mask_inventory),
        "source_current_prediction_inventory": str(current_prediction_inventory),
        "normalized_source_root": str(normalized_root),
        "source_manifest": source_manifest,
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--main-repo-root",
        type=Path,
        default=Path(os.environ.get("ISSUE245_MAIN_REPO_ROOT", DEFAULT_MAIN_REPO)),
    )
    parser.add_argument(
        "--current-mask-inventory", type=Path, default=DEFAULT_CURRENT_MASK_INVENTORY
    )
    parser.add_argument(
        "--current-prediction-inventory",
        type=Path,
        default=DEFAULT_CURRENT_PRED_INVENTORY,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--normalized-root", type=Path, default=DEFAULT_NORMALIZED_ROOT)
    args = parser.parse_args()

    main_repo = args.main_repo_root.expanduser().resolve()
    mask_inventory = resolve_host_path(main_repo, args.current_mask_inventory)
    prediction_inventory = resolve_host_path(main_repo, args.current_prediction_inventory)
    output = resolve_host_path(main_repo, args.output)
    normalized_root = resolve_host_path(main_repo, args.normalized_root)

    payload = build_current_inventory(
        main_repo=main_repo,
        current_mask_inventory=mask_inventory,
        current_prediction_inventory=prediction_inventory,
        normalized_root=normalized_root,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
