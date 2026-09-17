#!/usr/bin/env python3
"""Diagnostic-only staff-view audit for Issue #332.

This module deliberately does not train a model or define a training view.  It
reuses the canonical source manifest and the existing staff-relative checkpoint
to compare crop context, expose staff logits, and create visual audit sheets.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Iterable, Sequence

import cv2
import numpy as np
import torch
from PIL import Image, ImageDraw
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


def _bbox(raw: Sequence[float]) -> tuple[float, float, float, float]:
    values = tuple(float(value) for value in raw)
    if len(values) != 4 or not all(math.isfinite(value) for value in values):
        raise ValueError(f"invalid bbox: {raw!r}")
    if values[2] <= values[0] or values[3] <= values[1]:
        raise ValueError(f"bbox must have positive area: {raw!r}")
    return values


def staff_band_full_width_rois(
    sample: dict[str, Any],
    measure_bbox: Sequence[float] | None = None,
) -> tuple[tuple[float, float, float, float], ...]:
    """Diagnostic proposed view: full measure width clipped to each staff band."""
    mx1, _my1, mx2, _my2 = _bbox(measure_bbox or sample["bbox"])
    return tuple((mx1, sy1, mx2, sy2) for _sx1, sy1, _sx2, sy2 in source_staff_bboxes(sample))


def _resolve_image(sample: dict[str, Any], manifest_path: Path) -> tuple[Path, np.ndarray]:
    path = Path(str(sample["image_path"]))
    if not path.is_absolute():
        path = (manifest_path.parent / path).resolve()
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(path)
    return path, image


def _crop_views(
    sample: dict[str, Any], image: np.ndarray
) -> list[tuple[str, int, tuple[float, float, float, float], np.ndarray]]:
    measure = _bbox(sample["bbox"])
    full_margin = (measure[0] - 20, measure[1] - 20, measure[2] + 20, measure[3] + 20)
    views: list[tuple[str, int, tuple[float, float, float, float], np.ndarray]] = []
    core = staff_relative_roi_bboxes(sample, measure)
    band = staff_band_full_width_rois(sample, measure)
    staff_count = len(core)
    for staff_index in range(staff_count):
        for name, roi in (
            ("full-measure+20px", full_margin),
            ("measure-no-margin", measure),
            ("staff-core-center-3h", core[staff_index]),
            ("staff-band-full-width", band[staff_index]),
        ):
            views.append((name, staff_index, roi, crop_source_bbox(image, roi)))
    return views


def _tile(crop: np.ndarray, title: str, *, width: int = 280, height: int = 220) -> Image.Image:
    rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    image = Image.fromarray(rgb)
    image.thumbnail((width - 8, height - 34), Image.Resampling.LANCZOS)
    tile = Image.new("RGB", (width, height), "white")
    tile.paste(image, ((width - image.width) // 2, 28 + (height - 28 - image.height) // 2))
    draw = ImageDraw.Draw(tile)
    draw.text((4, 4), title[:52], fill="black")
    return tile


def _contact_sheet(
    rows: Iterable[Sequence[tuple[np.ndarray, str]]], output: Path, *, columns: int
) -> None:
    materialized = [list(row) for row in rows]
    if not materialized:
        return
    tile_width, tile_height = 280, 220
    row_width = max(len(row) for row in materialized)
    row_width = max(row_width, columns)
    canvas = Image.new(
        "RGB",
        (row_width * tile_width, len(materialized) * tile_height),
        "#dddddd",
    )
    for row_index, row in enumerate(materialized):
        for col_index, (crop, title) in enumerate(row):
            canvas.paste(
                _tile(crop, title, width=tile_width, height=tile_height),
                (col_index * tile_width, row_index * tile_height),
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)


def _load_samples(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    samples = payload.get("samples", [])
    if not isinstance(samples, list) or not samples:
        raise ValueError(f"manifest has no samples: {path}")
    return [dict(sample) for sample in samples]


def _load_model(model_path: Path, device: torch.device) -> StaffRelativeResNet18:
    model = StaffRelativeResNet18(weights=None)
    state_dict = torch.load(model_path, map_location=device, weights_only=True)
    model.load_state_dict(state_dict)
    model.to(device)
    model.eval()
    return model


def _staff_logits(
    model: StaffRelativeResNet18,
    sample: dict[str, Any],
    image: np.ndarray,
    device: torch.device,
) -> dict[str, Any]:
    crops = []
    rois = staff_relative_roi_bboxes(sample)
    for roi in rois:
        crop = crop_source_bbox(image, roi)
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        crops.append(DIRECT_TRANSFORM(Image.fromarray(rgb)))
    staff_images = torch.stack(crops).to(device)
    with torch.inference_mode():
        logits = model.encoder(staff_images).reshape(-1).detach().cpu()
    probabilities = torch.sigmoid(logits)
    selected = int(torch.argmax(logits).item())
    return {
        "sample_id": sample["sample_id"],
        "label": int(sample["label"]),
        "staff_count": len(rois),
        "staff_rois": [list(roi) for roi in rois],
        "staff_logits": [float(value) for value in logits],
        "staff_probabilities": [float(value) for value in probabilities],
        "max_staff_index": selected,
        "max_logit": float(logits[selected]),
        "max_probability": float(probabilities[selected]),
    }


def _ink_retention(sample: dict[str, Any], image: np.ndarray) -> list[dict[str, Any]]:
    """Reproduce the conservative retention audit used by the ROI artifact."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    measure = _bbox(sample["bbox"])
    records = []
    for staff_index, roi in enumerate(staff_relative_roi_bboxes(sample, measure)):
        _x1, y1, _x2, y2 = roi
        height = max(1, int(round(y2 - y1)))
        band_roi = staff_band_full_width_rois(sample, measure)[staff_index]
        band = crop_source_bbox(gray, band_roi)
        core = crop_source_bbox(gray, roi)
        kernel_width = max(1, int(round(0.5 * height)))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_width, 1))

        def residual_count(array: np.ndarray) -> int:
            binary = (array < 160).astype(np.uint8)
            horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
            return int(np.count_nonzero(binary & (horizontal == 0)))

        denominator = residual_count(band)
        numerator = residual_count(core)
        records.append(
            {
                "sample_id": sample["sample_id"],
                "score_id": sample["score_id"],
                "page_id": sample["page_id"],
                "label": int(sample["label"]),
                "staff_index": staff_index,
                "retained_residual": numerator / denominator if denominator else 1.0,
                "band_residual_pixels": denominator,
                "core_residual_pixels": numerator,
                "core_roi": list(roi),
                "band_roi": list(band_roi),
            }
        )
    return records


def _make_view_sheet(
    samples: Sequence[dict[str, Any]], manifest_path: Path, output: Path, title_prefix: str
) -> None:
    rows = []
    for sample in samples:
        _path, image = _resolve_image(sample, manifest_path)
        views = _crop_views(sample, image)
        grouped: dict[int, list[tuple[np.ndarray, str]]] = {}
        for name, staff_index, _roi, crop in views:
            grouped.setdefault(staff_index, []).append((crop, f"s{staff_index} {name}"))
        rows.extend(grouped[index] for index in sorted(grouped))
    _contact_sheet(rows, output, columns=4)


def run(args: argparse.Namespace) -> dict[str, Any]:
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    test_samples = _load_samples(args.test_manifest)
    controls = _load_samples(args.controls_manifest)
    test_by_id = {sample["sample_id"]: sample for sample in test_samples}
    device = torch.device(args.device)
    model = _load_model(args.model, device)

    target_ids = [
        "Sibelius-Violin_Concerto-Viola::page_036::s0::m9",
        "Va_Prokofiev_Symphony1::page_046::s12::m9",
    ]
    targets = [test_by_id[sample_id] for sample_id in target_ids]
    for sample, name in zip(targets, ("sibelius_page036_s0m9", "prokofiev1_page046_s12m9")):
        _make_view_sheet(
            [sample],
            args.test_manifest,
            output / f"{name}_views.png",
            sample["sample_id"],
        )

    control_staff = []
    for sample in controls:
        _path, image = _resolve_image(sample, args.controls_manifest)
        control_staff.append(_staff_logits(model, sample, image, device))
    target_staff = []
    for sample in targets:
        _path, image = _resolve_image(sample, args.test_manifest)
        target_staff.append(_staff_logits(model, sample, image, device))

    benchmark = json.loads(args.benchmark.read_text(encoding="utf-8"))
    native_rows = [
        row
        for row in benchmark["rows"]
        if row["variant"] == "native" and float(row["dpi_scale"]) == 1.0 and row["label"] == 0
    ]
    top_negative_rows = sorted(
        native_rows, key=lambda row: float(row["probability"]), reverse=True
    )[:20]
    top_samples = [test_by_id[row["sample_id"]] for row in top_negative_rows]
    top_rows = []
    for rank, (row, sample) in enumerate(zip(top_negative_rows, top_samples), 1):
        _path, image = _resolve_image(sample, args.test_manifest)
        views = _crop_views(sample, image)
        row_tiles = []
        for name, staff_index, _roi, crop in views:
            if name not in ("full-measure+20px", "staff-core-center-3h"):
                continue
            row_tiles.append(
                (
                    crop,
                    f"#{rank} p={row['probability']:.3f} s{staff_index} {name}",
                )
            )
        top_rows.append(row_tiles)
    _contact_sheet(top_rows, output / "top20_negative_views.png", columns=2)

    positive_samples = [
        sample for sample in _load_samples(args.source_manifest) if int(sample["label"]) == 1
    ]
    retention_records = []
    for sample in positive_samples:
        _path, image = _resolve_image(sample, args.source_manifest)
        retention_records.extend(_ink_retention(sample, image))
    retention_records.sort(key=lambda record: record["retained_residual"])
    low_records = retention_records[:20]
    low_samples_by_id = {sample["sample_id"]: sample for sample in positive_samples}
    low_rows = []
    for record in low_records:
        sample = low_samples_by_id[record["sample_id"]]
        _path, image = _resolve_image(sample, args.source_manifest)
        core = crop_source_bbox(image, record["core_roi"])
        band = crop_source_bbox(image, record["band_roi"])
        low_rows.append(
            [
                (core, f"{record['retained_residual']:.3f} core {record['sample_id'][-16:]}"),
                (band, f"{record['retained_residual']:.3f} band {record['sample_id'][-16:]}"),
            ]
        )
    _contact_sheet(low_rows, output / "low_retention_positive_core_vs_band.png", columns=2)

    result = {
        "provenance": {
            "model": str(args.model.resolve()),
            "test_manifest": str(args.test_manifest.resolve()),
            "controls_manifest": str(args.controls_manifest.resolve()),
            "source_manifest": str(args.source_manifest.resolve()),
            "benchmark": str(args.benchmark.resolve()),
            "diagnostic_only": True,
            "staff_bbox_caveat": (
                "measure translate-y perturbation does not move the staff ROI; future acceptance "
                "must independently perturb source staff bbox by +/-1/2/4px"
            ),
        },
        "target_staff_logits": target_staff,
        "control_staff_logits": control_staff,
        "top20_negative_native": [
            {
                "sample_id": row["sample_id"],
                "score_id": row["score_id"],
                "page_id": row["page_id"],
                "probability": row["probability"],
                "label": row["label"],
            }
            for row in top_negative_rows
        ],
        "low_retention_positive_staff_views": low_records,
        "artifacts": {
            "target_contact_sheets": [
                str((output / "sibelius_page036_s0m9_views.png").resolve()),
                str((output / "prokofiev1_page046_s12m9_views.png").resolve()),
            ],
            "top20_negative_contact_sheet": str((output / "top20_negative_views.png").resolve()),
            "low_retention_contact_sheet": str(
                (output / "low_retention_positive_core_vs_band.png").resolve()
            ),
        },
    }
    (output / "staff_failure_diagnosis.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-manifest", type=Path, required=True)
    parser.add_argument("--controls-manifest", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    return parser


if __name__ == "__main__":
    arguments = build_parser().parse_args()
    result = run(arguments)
    print(json.dumps({"artifacts": result["artifacts"]}, indent=2))
