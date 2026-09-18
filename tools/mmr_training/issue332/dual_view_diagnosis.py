#!/usr/bin/env python3
"""Diagnostic comparison of full-measure and staff-relative checkpoints.

This is evaluation-only.  It does not train a model or change the primary
split.  It aligns existing geometry benchmark rows, computes the diagnostic
minimum-probability conjunction, and measures independent source-staff-bbox
sensitivity for the staff-relative checkpoint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Sequence

import cv2
import numpy as np
import torch
from PIL import Image
from torchvision import transforms

from tools.mmr_training.issue332.staff_model import StaffRelativeResNet18
from tools.mmr_training.issue332.staff_view import (
    crop_source_bbox,
    source_staff_bboxes,
    staff_relative_roi_bboxes,
)

DIRECT_TRANSFORM = transforms.Compose(
    [
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ]
)
DELTAS = (1, 2, 4)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _key(row: dict[str, Any]) -> tuple[str, str, float, str]:
    return (
        str(row["sample_id"]),
        str(row["variant"]),
        float(row["dpi_scale"]),
        str(row["resize_mode"]),
    )


def _native_rows(path: Path) -> list[dict[str, Any]]:
    payload = _load_json(path)
    return [
        row
        for row in payload["rows"]
        if row["variant"] == "native"
        and float(row["dpi_scale"]) == 1.0
        and row["resize_mode"] == "direct"
    ]


def _all_aligned(
    full_path: Path, staff_path: Path, *, threshold: float = 0.5
) -> list[dict[str, Any]]:
    full = _load_json(full_path)["rows"]
    staff = _load_json(staff_path)["rows"]
    full_by_key = {_key(row): row for row in full}
    staff_by_key = {_key(row): row for row in staff}
    if set(full_by_key) != set(staff_by_key):
        missing_full = sorted(set(staff_by_key) - set(full_by_key))[:5]
        missing_staff = sorted(set(full_by_key) - set(staff_by_key))[:5]
        raise ValueError(
            f"benchmark rows do not align: full_missing={missing_full}, staff_missing={missing_staff}"
        )
    result = []
    for key in sorted(full_by_key):
        full_row = full_by_key[key]
        staff_row = staff_by_key[key]
        if int(full_row["label"]) != int(staff_row["label"]):
            raise ValueError(f"label mismatch for {key}")
        full_probability = float(full_row["probability"])
        staff_probability = float(staff_row["probability"])
        conjunction = min(full_probability, staff_probability)
        result.append(
            {
                "sample_id": full_row["sample_id"],
                "score_id": full_row["score_id"],
                "page_id": full_row["page_id"],
                "label": int(full_row["label"]),
                "variant": full_row["variant"],
                "dpi_scale": float(full_row["dpi_scale"]),
                "resize_mode": full_row["resize_mode"],
                "full_probability": full_probability,
                "staff_probability": staff_probability,
                "conjunction_probability": conjunction,
                "full_positive": full_probability >= threshold,
                "staff_positive": staff_probability >= threshold,
                "conjunction_positive": conjunction >= threshold,
            }
        )
    return result


def _metrics(rows: Sequence[dict[str, Any]], probability_key: str) -> dict[str, Any]:
    tp = fp = tn = fn = 0
    for row in rows:
        actual = int(row["label"])
        predicted = int(float(row[probability_key]) >= 0.5)
        if actual and predicted:
            tp += 1
        elif not actual and predicted:
            fp += 1
        elif not actual and not predicted:
            tn += 1
        else:
            fn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "samples": len(rows),
        "positives": sum(int(row["label"]) == 1 for row in rows),
        "negatives": sum(int(row["label"]) == 0 for row in rows),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "confusion_matrix": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
    }


def _native(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row["variant"] == "native"
        and float(row["dpi_scale"]) == 1.0
        and row["resize_mode"] == "direct"
    ]


def _by_score(rows: Sequence[dict[str, Any]], probability_key: str) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["score_id"]), []).append(row)
    return {score: _metrics(items, probability_key) for score, items in sorted(grouped.items())}


def _crossings(
    rows: Sequence[dict[str, Any]], probability_key: str, *, threshold: float
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["sample_id"]), []).append(row)
    native = {}
    directions = {"positive_to_negative": set(), "negative_to_positive": set()}
    for sample_id, items in grouped.items():
        native_rows = [
            row
            for row in items
            if row["variant"] == "native"
            and float(row["dpi_scale"]) == 1.0
            and row["resize_mode"] == "direct"
        ]
        if len(native_rows) != 1:
            raise ValueError(f"expected one native row for {sample_id}, got {len(native_rows)}")
        native_decision = float(native_rows[0][probability_key]) >= threshold
        native[sample_id] = float(native_rows[0][probability_key])
        for row in items:
            decision = float(row[probability_key]) >= threshold
            if decision == native_decision:
                continue
            if native_decision:
                directions["positive_to_negative"].add(sample_id)
            else:
                directions["negative_to_positive"].add(sample_id)
    crossing_samples = set(directions["positive_to_negative"]) | set(
        directions["negative_to_positive"]
    )
    return {
        "threshold": threshold,
        "unique_crossing_samples": sorted(crossing_samples),
        "unique_crossing_count": len(crossing_samples),
        "positive_to_negative": sorted(directions["positive_to_negative"]),
        "negative_to_positive": sorted(directions["negative_to_positive"]),
        "positive_to_negative_count": len(directions["positive_to_negative"]),
        "negative_to_positive_count": len(directions["negative_to_positive"]),
    }


def _probability_envelope(rows: Sequence[dict[str, Any]], probability_key: str) -> dict[str, float]:
    grouped: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        item = grouped.setdefault(str(row["sample_id"]), {"all": [], "native": []})
        probability = float(row[probability_key])
        item["all"].append(probability)
        if (
            row["variant"] == "native"
            and float(row["dpi_scale"]) == 1.0
            and row["resize_mode"] == "direct"
        ):
            item["native"].append(probability)
    ranges = []
    deltas = []
    for item in grouped.values():
        if len(item["native"]) != 1:
            raise ValueError("expected exactly one native probability per sample")
        native = item["native"][0]
        ranges.append(max(item["all"]) - min(item["all"]))
        deltas.append(max(abs(value - native) for value in item["all"]))
    return {
        "max_probability_range": max(ranges) if ranges else 0.0,
        "mean_probability_range": float(np.mean(ranges)) if ranges else 0.0,
        "max_abs_delta_from_native": max(deltas) if deltas else 0.0,
        "mean_abs_delta_from_native": float(np.mean(deltas)) if deltas else 0.0,
    }


def _view_summary(rows: Sequence[dict[str, Any]], probability_key: str) -> dict[str, Any]:
    native = _native(rows)
    return {
        "native": _metrics(native, probability_key),
        "per_score_native": _by_score(native, probability_key),
        "geometry": {
            "main": _crossings(rows, probability_key, threshold=0.5),
            "rescue": _crossings(rows, probability_key, threshold=0.1),
            "probability_envelope": _probability_envelope(rows, probability_key),
        },
    }


def _error_complementarity(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    native = _native(rows)
    categories = {
        "full_only_wrong": [],
        "staff_only_wrong": [],
        "both_wrong": [],
        "conjunction_resolves_error": [],
        "conjunction_new_positive_fn": [],
    }
    for row in native:
        actual = int(row["label"])
        full_wrong = bool(row["full_positive"]) != bool(actual)
        staff_wrong = bool(row["staff_positive"]) != bool(actual)
        conjunction_wrong = bool(row["conjunction_positive"]) != bool(actual)
        if full_wrong and not staff_wrong:
            categories["full_only_wrong"].append(row["sample_id"])
        if staff_wrong and not full_wrong:
            categories["staff_only_wrong"].append(row["sample_id"])
        if full_wrong and staff_wrong:
            categories["both_wrong"].append(row["sample_id"])
        if (full_wrong or staff_wrong) and not conjunction_wrong:
            categories["conjunction_resolves_error"].append(row["sample_id"])
        if actual == 1 and conjunction_wrong and not full_wrong and not staff_wrong:
            categories["conjunction_new_positive_fn"].append(row["sample_id"])
    return {key: sorted(set(value)) for key, value in categories.items()}


def _load_model(model_path: Path, device: torch.device) -> StaffRelativeResNet18:
    model = StaffRelativeResNet18(weights=None)
    model.load_state_dict(torch.load(model_path, map_location=device, weights_only=True))
    model.to(device)
    model.eval()
    return model


def _staff_bbox_variants(
    staves: Sequence[Sequence[float]], deltas: Iterable[int] = DELTAS
) -> list[tuple[str, list[list[float]]]]:
    base = [[float(value) for value in staff] for staff in staves]
    result = [("native", base)]
    for delta in deltas:
        for sign, suffix in ((-int(delta), "minus"), (int(delta), "plus")):
            for family in ("translate_y", "top", "bottom", "height"):
                modified = [staff[:] for staff in base]
                for staff in modified:
                    if family == "translate_y":
                        staff[1] += sign
                        staff[3] += sign
                    elif family == "top":
                        staff[1] += sign
                    elif family == "bottom":
                        staff[3] += sign
                    elif family == "height":
                        staff[1] -= sign
                        staff[3] += sign
                    if staff[3] <= staff[1]:
                        raise ValueError(f"invalid staff bbox after {family} {sign}: {staff}")
                result.append((f"staff_{family}_{suffix}_{delta}px", modified))
    return result


def _resolve_image(sample: dict[str, Any], manifest_path: Path) -> np.ndarray:
    path = Path(str(sample["image_path"]))
    if not path.is_absolute():
        path = (manifest_path.parent / path).resolve()
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(path)
    return image


def _staff_bbox_sensitivity(
    samples: Sequence[dict[str, Any]],
    manifest_path: Path,
    model: StaffRelativeResNet18,
    device: torch.device,
) -> list[dict[str, Any]]:
    rows = []
    for index, sample in enumerate(samples):
        image = _resolve_image(sample, manifest_path)
        variants = _staff_bbox_variants(source_staff_bboxes(sample))
        tensors = []
        slices = []
        for variant_name, staff_bboxes in variants:
            variant_sample = dict(sample)
            variant_sample["_staff_bboxes"] = staff_bboxes
            start = len(tensors)
            for roi in staff_relative_roi_bboxes(variant_sample):
                crop = crop_source_bbox(image, roi)
                rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                tensors.append(DIRECT_TRANSFORM(Image.fromarray(rgb)))
            slices.append((variant_name, start, len(tensors), len(staff_bboxes)))
        batch = torch.stack(tensors).to(device)
        with torch.inference_mode():
            logits = model.encoder(batch).reshape(-1).detach().cpu()
        for variant_name, start, end, staff_count in slices:
            variant_logits = logits[start:end]
            max_index = int(torch.argmax(variant_logits).item())
            rows.append(
                {
                    "sample_id": sample["sample_id"],
                    "score_id": sample["score_id"],
                    "page_id": sample["page_id"],
                    "label": int(sample["label"]),
                    "variant": variant_name,
                    "staff_count": staff_count,
                    "max_staff_index": max_index,
                    "probability": float(torch.sigmoid(variant_logits[max_index])),
                }
            )
        if (index + 1) % 100 == 0:
            print(f"staff-bbox sensitivity: {index + 1}/{len(samples)} samples")
    return rows


def _sensitivity_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by_variant: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_variant.setdefault(row["variant"], []).append(row)
    result = {}
    for variant, items in sorted(by_variant.items()):
        metrics = _metrics(
            [{**row, "probability": row["probability"]} for row in items],
            "probability",
        )
        result[variant] = metrics
    return result


def _top_negative_comparison(
    rows: Sequence[dict[str, Any]], count: int = 20
) -> list[dict[str, Any]]:
    native = [row for row in _native(rows) if int(row["label"]) == 0]
    native.sort(key=lambda row: float(row["full_probability"]), reverse=True)
    return [
        {
            "rank": index,
            "sample_id": row["sample_id"],
            "score_id": row["score_id"],
            "page_id": row["page_id"],
            "full_probability": row["full_probability"],
            "staff_probability": row["staff_probability"],
            "conjunction_probability": row["conjunction_probability"],
        }
        for index, row in enumerate(native[:count], 1)
    ]


def run(args: argparse.Namespace) -> dict[str, Any]:
    primary = _all_aligned(args.full_primary, args.staff_primary)
    controls = _all_aligned(args.full_controls, args.staff_controls)
    model = _load_model(args.staff_model, torch.device(args.device))
    sensitivity_primary = _staff_bbox_sensitivity(
        _load_json(args.primary_manifest)["samples"],
        args.primary_manifest,
        model,
        torch.device(args.device),
    )
    sensitivity_controls = _staff_bbox_sensitivity(
        _load_json(args.controls_manifest)["samples"],
        args.controls_manifest,
        model,
        torch.device(args.device),
    )
    output = {
        "provenance": {
            "diagnostic_only": True,
            "full_primary_artifact": str(args.full_primary.resolve()),
            "staff_primary_artifact": str(args.staff_primary.resolve()),
            "full_controls_artifact": str(args.full_controls.resolve()),
            "staff_controls_artifact": str(args.staff_controls.resolve()),
            "staff_model": str(args.staff_model.resolve()),
            "staff_model_sha256": sha256_file(args.staff_model),
            "primary_manifest": str(args.primary_manifest.resolve()),
            "controls_manifest": str(args.controls_manifest.resolve()),
            "staff_bbox_source": "canonical source numbering system['staves'][*]['bbox']",
            "measure_geometry_perturbation_staff_caveat": (
                "measure translate-y changes keep source staff bbox fixed; this is not complete "
                "staff-geometry robustness"
            ),
            "staff_bbox_sensitivity_contract": {
                "translate_y": "y1'=y1+d, y2'=y2+d",
                "top": "y1'=y1+d, y2'=y2",
                "bottom": "y1'=y1, y2'=y2+d",
                "height": "y1'=y1-d, y2'=y2+d",
                "deltas_px": list(DELTAS),
                "x_coordinates": "unchanged",
                "measure_bbox": "unchanged",
                "historical_geometry": "not used",
            },
        },
        "primary": {
            "full_measure": _view_summary(primary, "full_probability"),
            "staff_core": _view_summary(primary, "staff_probability"),
            "conjunction_min": _view_summary(primary, "conjunction_probability"),
            "error_complementarity": _error_complementarity(primary),
            "top20_negative_comparison": _top_negative_comparison(primary),
            "aligned_rows": primary,
        },
        "controls": {
            "full_measure": _view_summary(controls, "full_probability"),
            "staff_core": _view_summary(controls, "staff_probability"),
            "conjunction_min": _view_summary(controls, "conjunction_probability"),
            "aligned_rows": controls,
        },
        "staff_bbox_sensitivity": {
            "primary": {
                "summary": _sensitivity_summary(sensitivity_primary),
                "rows": sensitivity_primary,
            },
            "controls": {
                "summary": _sensitivity_summary(sensitivity_controls),
                "rows": sensitivity_controls,
            },
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-primary", type=Path, required=True)
    parser.add_argument("--staff-primary", type=Path, required=True)
    parser.add_argument("--full-controls", type=Path, required=True)
    parser.add_argument("--staff-controls", type=Path, required=True)
    parser.add_argument("--primary-manifest", type=Path, required=True)
    parser.add_argument("--controls-manifest", type=Path, required=True)
    parser.add_argument("--staff-model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    return parser


if __name__ == "__main__":
    arguments = build_parser().parse_args()
    result = run(arguments)
    print(
        json.dumps(
            {
                "primary": {
                    key: value for key, value in result["primary"].items() if key != "aligned_rows"
                },
                "controls": {
                    key: value for key, value in result["controls"].items() if key != "aligned_rows"
                },
            },
            indent=2,
        )
    )
