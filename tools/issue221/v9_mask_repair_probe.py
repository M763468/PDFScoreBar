#!/usr/bin/env python3
"""Temporary #221 v9 mask-and-repair diagnostic.

This script is intentionally experimental. It does not change production code.
It scans ignored local logs for residual MMR digit crops, applies several
white-mask + black-dilation repair variants, and writes review artifacts.

Expected local use:

    PYTHONPATH=. python3 tools/issue221/v9_mask_repair_probe.py \
      --input-root logs/issue221_component_ocr \
      --output-dir logs/issue221_component_ocr/v9_mask_repair_probe

The final zip is written to:

    logs/issue221_component_ocr/issue221_mask_repair_probe_v9_pack.zip
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from collections import Counter, deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

try:
    import numpy as np
except Exception as exc:  # pragma: no cover - local diagnostic guard
    raise SystemExit(f"numpy is required for this diagnostic: {exc}") from exc

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception as exc:  # pragma: no cover - local diagnostic guard
    raise SystemExit(f"Pillow is required for this diagnostic: {exc}") from exc


@dataclass(frozen=True)
class Target:
    page_key: str
    key: tuple[int, int, int]
    expected_num: int
    path_terms: tuple[str, ...]
    preferred_terms: tuple[str, ...]


@dataclass
class ImageRecord:
    sample_id: str
    path: str
    group: str
    page_key: str | None
    expected_num: int | None
    score: int
    width: int
    height: int
    source_kind: str


@dataclass
class VariantRow:
    sample_id: str
    group: str
    page_key: str | None
    expected_num: int | None
    source_path: str
    variant: str
    variant_path: str
    horizontal_mask_pixels: int
    vertical_mask_pixels: int
    edge_mask_pixels: int
    mask_total_pixels: int
    ink_ratio_before: float
    ink_ratio_after_mask: float
    ink_ratio_after_repair: float
    components_before: int
    components_after_mask: int
    components_after_repair: int
    bbox_before: str
    bbox_after_repair: str
    ocr_text: str | None
    parsed_num: int | None
    is_exact: bool | None
    is_wrong: bool | None
    is_risky_global: bool
    notes: str


TARGETS = (
    Target(
        page_key="page_001",
        key=(0, 2, 2),
        expected_num=4,
        path_terms=("page_001",),
        preferred_terms=("sys2_m2", "s2_m2", "system2", "measure2", "stave0"),
    ),
    Target(
        page_key="page_004",
        key=(3, 2, 2),
        expected_num=3,
        path_terms=("page_004",),
        preferred_terms=("sys2_m2", "s2_m2", "system2", "measure2", "stave0"),
    ),
    Target(
        page_key="page_009",
        key=(8, 0, 0),
        expected_num=3,
        path_terms=("page_009",),
        preferred_terms=("sys0_m0", "s0_m0", "system0", "measure0", "stave0"),
    ),
)

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
BANNED_PATH_PARTS = (
    "annotated",
    "overview",
    "group_overview",
    "template",
    "debug",
    "montage",
    "contact",
    "overlay",
    "panel",
    "review_pack",
    "mask_repair_probe",
)
TARGET_LIKE_TERMS = (
    "crop",
    "component",
    "band",
    "union",
    "digit",
    "candidate",
    "s0_m0",
    "s2_m2",
    "sys0_m0",
    "sys2_m2",
)


VARIANTS = (
    "baseline_binary",
    "mask_horizontal_dilate1",
    "mask_horizontal_dilate2",
    "mask_vertical_dilate1",
    "mask_edge_components_dilate1",
    "mask_horizontal_vertical_dilate1",
    "mask_horizontal_edge_dilate1",
    "mask_horizontal_vertical_edge_dilate1",
    "mask_horizontal_vertical_edge_dilate2",
)


RISKY_DIGITS = {2, 3, 4}


def norm_text(value: str) -> str:
    return value.replace("\\", "/").lower()


def safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
    return value.strip("_")[:180]


def is_banned(path: Path) -> bool:
    text = norm_text(str(path))
    return any(part in text for part in BANNED_PATH_PARTS)


def is_target_like(path: Path) -> bool:
    text = norm_text(str(path))
    return any(term in text for term in TARGET_LIKE_TERMS)


def find_images(root: Path) -> list[Path]:
    if not root.exists():
        return []
    result: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        if is_banned(path):
            continue
        if not is_target_like(path):
            continue
        result.append(path)
    return sorted(result)


def score_for_target(path: Path, target: Target) -> int:
    text = norm_text(str(path))
    if not all(term in text for term in target.path_terms):
        return 0
    score = 10
    for term in target.preferred_terms:
        if term in text:
            score += 5
    for term in ("crop", "component", "band", "union", "digit", "candidate"):
        if term in text:
            score += 2
    return score


def open_grayscale(path: Path) -> Image.Image | None:
    try:
        return Image.open(path).convert("L")
    except Exception:
        return None


def maybe_resize_for_processing(gray: Image.Image, max_side: int = 512) -> Image.Image:
    width, height = gray.size
    side = max(width, height)
    if side <= max_side:
        return gray
    scale = max_side / float(side)
    new_size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    return gray.resize(new_size, Image.Resampling.LANCZOS)


def to_foreground(gray: Image.Image) -> np.ndarray:
    arr = np.asarray(gray, dtype=np.uint8)
    # Robust threshold: prefer dark ink on light background.
    threshold = int(np.clip(np.percentile(arr, 35), 30, 220))
    # If threshold is too low because crop is mostly white, use a safer fixed value.
    threshold = max(threshold, 160)
    foreground = arr < threshold
    # Remove one-pixel border noise from scanned crop edges.
    if foreground.shape[0] > 4 and foreground.shape[1] > 4:
        foreground[0, :] = False
        foreground[-1, :] = False
        foreground[:, 0] = False
        foreground[:, -1] = False
    return foreground


def bool_to_image(foreground: np.ndarray) -> Image.Image:
    arr = np.where(foreground, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode="L")


def dilate(mask: np.ndarray, iterations: int = 1) -> np.ndarray:
    result = mask.copy()
    for _ in range(iterations):
        padded = np.pad(result, 1, mode="constant", constant_values=False)
        out = np.zeros_like(result)
        for dy in range(3):
            for dx in range(3):
                out |= padded[dy : dy + result.shape[0], dx : dx + result.shape[1]]
        result = out
    return result


def erode(mask: np.ndarray, iterations: int = 1) -> np.ndarray:
    result = mask.copy()
    for _ in range(iterations):
        padded = np.pad(result, 1, mode="constant", constant_values=False)
        out = np.ones_like(result)
        for dy in range(3):
            for dx in range(3):
                out &= padded[dy : dy + result.shape[0], dx : dx + result.shape[1]]
        result = out
    return result


def horizontal_run_mask(foreground: np.ndarray) -> np.ndarray:
    height, width = foreground.shape
    min_run = max(8, int(round(width * 0.24)))
    result = np.zeros_like(foreground)
    for y in range(height):
        row = foreground[y]
        start: int | None = None
        for x in range(width + 1):
            active = bool(row[x]) if x < width else False
            if active and start is None:
                start = x
            elif not active and start is not None:
                run_len = x - start
                if run_len >= min_run:
                    result[y, start:x] = True
                start = None
    # Staff line masks should cover antialiasing just above/below the line.
    return dilate(result, 1)


def vertical_run_mask(foreground: np.ndarray) -> np.ndarray:
    height, width = foreground.shape
    min_run = max(8, int(round(height * 0.35)))
    result = np.zeros_like(foreground)
    for x in range(width):
        col = foreground[:, x]
        start: int | None = None
        for y in range(height + 1):
            active = bool(col[y]) if y < height else False
            if active and start is None:
                start = y
            elif not active and start is not None:
                run_len = y - start
                if run_len >= min_run:
                    result[start:y, x] = True
                start = None
    return dilate(result, 1)


def connected_components(mask: np.ndarray, max_components: int = 10000) -> list[dict[str, int]]:
    height, width = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    comps: list[dict[str, int]] = []
    ys, xs = np.nonzero(mask)
    starts = list(zip(ys.tolist(), xs.tolist(), strict=False))
    for sy, sx in starts:
        if seen[sy, sx] or not mask[sy, sx]:
            continue
        q: deque[tuple[int, int]] = deque([(sy, sx)])
        seen[sy, sx] = True
        area = 0
        min_y = max_y = sy
        min_x = max_x = sx
        while q:
            y, x = q.popleft()
            area += 1
            min_y = min(min_y, y)
            max_y = max(max_y, y)
            min_x = min(min_x, x)
            max_x = max(max_x, x)
            for ny in (y - 1, y, y + 1):
                if ny < 0 or ny >= height:
                    continue
                for nx in (x - 1, x, x + 1):
                    if nx < 0 or nx >= width or (ny == y and nx == x):
                        continue
                    if not seen[ny, nx] and mask[ny, nx]:
                        seen[ny, nx] = True
                        q.append((ny, nx))
        comps.append(
            {
                "area": area,
                "min_x": min_x,
                "min_y": min_y,
                "max_x": max_x,
                "max_y": max_y,
                "width": max_x - min_x + 1,
                "height": max_y - min_y + 1,
            }
        )
        if len(comps) >= max_components:
            break
    return comps


def edge_component_mask(foreground: np.ndarray) -> np.ndarray:
    height, width = foreground.shape
    edge_x = max(3, int(round(width * 0.08)))
    edge_y = max(3, int(round(height * 0.08)))
    min_area = max(3, int(round(width * height * 0.002)))
    result = np.zeros_like(foreground)
    comps = connected_components(foreground)
    for comp in comps:
        touches_edge = (
            comp["min_x"] <= edge_x
            or comp["max_x"] >= width - 1 - edge_x
            or comp["min_y"] <= edge_y
            or comp["max_y"] >= height - 1 - edge_y
        )
        # Do not remove huge central components by this mask; it is meant for
        # boxed/neighboring edge marks and vertical edge artifacts.
        too_large = comp["area"] > width * height * 0.35
        if touches_edge and comp["area"] >= min_area and not too_large:
            result[comp["min_y"] : comp["max_y"] + 1, comp["min_x"] : comp["max_x"] + 1] |= foreground[
                comp["min_y"] : comp["max_y"] + 1, comp["min_x"] : comp["max_x"] + 1
            ]
    return result


def bbox_string(foreground: np.ndarray) -> str:
    ys, xs = np.nonzero(foreground)
    if len(xs) == 0:
        return ""
    return f"{int(xs.min())},{int(ys.min())},{int(xs.max())},{int(ys.max())}"


def ink_ratio(foreground: np.ndarray) -> float:
    return float(np.count_nonzero(foreground)) / float(max(1, foreground.size))


def parse_num(text: str | None) -> int | None:
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def has_tesseract() -> bool:
    if shutil.which("tesseract") is None:
        return False
    try:
        import pytesseract  # noqa: F401
    except Exception:
        return False
    return True


def run_tesseract(image_path: Path) -> str | None:
    if not has_tesseract():
        return None
    try:
        import pytesseract

        text = pytesseract.image_to_string(
            Image.open(image_path),
            config="--psm 10 -c tessedit_char_whitelist=0123456789",
        )
    except Exception as exc:  # pragma: no cover - diagnostic only
        return f"ERROR:{type(exc).__name__}:{exc}"
    return text.strip()


def apply_variant(foreground: np.ndarray, variant: str) -> tuple[np.ndarray, dict[str, int | str]]:
    horizontal = horizontal_run_mask(foreground)
    vertical = vertical_run_mask(foreground)
    edge = edge_component_mask(foreground)

    mask = np.zeros_like(foreground)
    dilate_iters = 0

    if variant == "baseline_binary":
        pass
    elif variant == "mask_horizontal_dilate1":
        mask |= horizontal
        dilate_iters = 1
    elif variant == "mask_horizontal_dilate2":
        mask |= horizontal
        dilate_iters = 2
    elif variant == "mask_vertical_dilate1":
        mask |= vertical
        dilate_iters = 1
    elif variant == "mask_edge_components_dilate1":
        mask |= edge
        dilate_iters = 1
    elif variant == "mask_horizontal_vertical_dilate1":
        mask |= horizontal | vertical
        dilate_iters = 1
    elif variant == "mask_horizontal_edge_dilate1":
        mask |= horizontal | edge
        dilate_iters = 1
    elif variant == "mask_horizontal_vertical_edge_dilate1":
        mask |= horizontal | vertical | edge
        dilate_iters = 1
    elif variant == "mask_horizontal_vertical_edge_dilate2":
        mask |= horizontal | vertical | edge
        dilate_iters = 2
    else:
        raise ValueError(f"unknown variant: {variant}")

    after_mask = foreground & ~mask
    after_repair = dilate(after_mask, dilate_iters) if dilate_iters else after_mask
    info = {
        "horizontal_mask_pixels": int(np.count_nonzero(horizontal)),
        "vertical_mask_pixels": int(np.count_nonzero(vertical)),
        "edge_mask_pixels": int(np.count_nonzero(edge)),
        "mask_total_pixels": int(np.count_nonzero(mask)),
        "dilate_iters": dilate_iters,
    }
    return after_repair, info


def make_overlay(gray: Image.Image, foreground: np.ndarray, mask: np.ndarray | None = None) -> Image.Image:
    rgb = gray.convert("RGB")
    arr = np.asarray(rgb).copy()
    if mask is not None:
        arr[mask] = np.array([255, 0, 0], dtype=np.uint8)
    # Lightly tint foreground pixels blue if no explicit mask was passed.
    if mask is None:
        arr[foreground] = np.array([0, 0, 0], dtype=np.uint8)
    return Image.fromarray(arr)


def make_panel(title: str, source: Image.Image, variants: list[tuple[str, Image.Image, str]]) -> Image.Image:
    thumb_w = 180
    thumb_h = 140
    margin = 12
    label_h = 44
    cols = 3
    rows = int(math.ceil((len(variants) + 1) / cols))
    panel_w = cols * thumb_w + (cols + 1) * margin
    panel_h = rows * (thumb_h + label_h) + (rows + 1) * margin + 30
    panel = Image.new("RGB", (panel_w, panel_h), "white")
    draw = ImageDraw.Draw(panel)
    draw.text((margin, 6), title, fill="black")

    all_items = [("source", source.convert("RGB"), "")] + variants
    for idx, (name, image, note) in enumerate(all_items):
        row = idx // cols
        col = idx % cols
        x = margin + col * (thumb_w + margin)
        y = margin + 30 + row * (thumb_h + label_h + margin)
        img = image.convert("RGB")
        img.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        panel.paste(img, (x, y))
        draw.rectangle([x, y, x + img.width - 1, y + img.height - 1], outline="gray")
        draw.text((x, y + thumb_h + 4), name[:30], fill="black")
        if note:
            draw.text((x, y + thumb_h + 20), note[:32], fill="black")
    return panel


def write_csv(path: Path, rows: Iterable[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def select_records(paths: list[Path], max_target_images: int, max_global_images: int) -> list[ImageRecord]:
    records: list[ImageRecord] = []
    used: set[Path] = set()
    for target in TARGETS:
        candidates: list[tuple[int, Path]] = []
        for path in paths:
            score = score_for_target(path, target)
            if score > 0:
                candidates.append((score, path))
        candidates.sort(key=lambda item: (-item[0], len(str(item[1])), str(item[1])))
        for idx, (score, path) in enumerate(candidates[:max_target_images]):
            gray = open_grayscale(path)
            if gray is None:
                continue
            used.add(path)
            source_kind = "target_preferred" if score >= 20 else "target_page_match"
            records.append(
                ImageRecord(
                    sample_id=f"{target.page_key}_residual_{idx:03d}",
                    path=str(path),
                    group="residual",
                    page_key=target.page_key,
                    expected_num=target.expected_num,
                    score=score,
                    width=gray.width,
                    height=gray.height,
                    source_kind=source_kind,
                )
            )
    global_candidates = [p for p in paths if p not in used]
    # Deterministic spread over paths rather than random sampling.
    selected_global: list[Path] = []
    if global_candidates:
        step = max(1, len(global_candidates) // max_global_images)
        selected_global = global_candidates[::step][:max_global_images]
    for idx, path in enumerate(selected_global):
        gray = open_grayscale(path)
        if gray is None:
            continue
        page_match = re.search(r"page_\d{3}", norm_text(str(path)))
        records.append(
            ImageRecord(
                sample_id=f"global_{idx:03d}",
                path=str(path),
                group="global",
                page_key=page_match.group(0) if page_match else None,
                expected_num=None,
                score=0,
                width=gray.width,
                height=gray.height,
                source_kind="global_target_like_sample",
            )
        )
    return records


def process_record(
    record: ImageRecord,
    output_dir: Path,
    do_ocr: bool,
) -> tuple[list[VariantRow], Path | None]:
    gray_orig = open_grayscale(Path(record.path))
    if gray_orig is None:
        return [], None
    gray = maybe_resize_for_processing(gray_orig)
    foreground = to_foreground(gray)
    variant_rows: list[VariantRow] = []
    panel_items: list[tuple[str, Image.Image, str]] = []

    variant_base_dir = output_dir / "variant_images" / record.group / safe_name(record.sample_id)
    variant_base_dir.mkdir(parents=True, exist_ok=True)

    for variant in VARIANTS:
        repaired, info = apply_variant(foreground, variant)
        variant_img = bool_to_image(repaired)
        variant_path = variant_base_dir / f"{safe_name(variant)}.png"
        variant_img.save(variant_path)
        ocr_text = run_tesseract(variant_path) if do_ocr else None
        parsed = parse_num(ocr_text)
        is_exact: bool | None = None
        is_wrong: bool | None = None
        if record.expected_num is not None and parsed is not None:
            is_exact = parsed == record.expected_num
            is_wrong = parsed != record.expected_num
        is_risky_global = record.group == "global" and parsed in RISKY_DIGITS
        row = VariantRow(
            sample_id=record.sample_id,
            group=record.group,
            page_key=record.page_key,
            expected_num=record.expected_num,
            source_path=record.path,
            variant=variant,
            variant_path=str(variant_path),
            horizontal_mask_pixels=int(info["horizontal_mask_pixels"]),
            vertical_mask_pixels=int(info["vertical_mask_pixels"]),
            edge_mask_pixels=int(info["edge_mask_pixels"]),
            mask_total_pixels=int(info["mask_total_pixels"]),
            ink_ratio_before=ink_ratio(foreground),
            ink_ratio_after_mask=ink_ratio(foreground & ~(horizontal_run_mask(foreground) | vertical_run_mask(foreground) | edge_component_mask(foreground))),
            ink_ratio_after_repair=ink_ratio(repaired),
            components_before=len(connected_components(foreground)),
            components_after_mask=len(connected_components(foreground & ~(horizontal_run_mask(foreground) | vertical_run_mask(foreground) | edge_component_mask(foreground)))),
            components_after_repair=len(connected_components(repaired)),
            bbox_before=bbox_string(foreground),
            bbox_after_repair=bbox_string(repaired),
            ocr_text=ocr_text,
            parsed_num=parsed,
            is_exact=is_exact,
            is_wrong=is_wrong,
            is_risky_global=is_risky_global,
            notes="",
        )
        variant_rows.append(row)
        if record.group == "residual":
            note_parts = []
            if parsed is not None:
                note_parts.append(f"ocr={parsed}")
            if is_exact:
                note_parts.append("exact")
            if is_wrong:
                note_parts.append("wrong")
            panel_items.append((variant, variant_img.convert("RGB"), ", ".join(note_parts)))

    panel_path: Path | None = None
    if record.group == "residual":
        panel_dir = output_dir / "review_pack"
        panel_dir.mkdir(parents=True, exist_ok=True)
        title = f"{record.sample_id} expected={record.expected_num} source={Path(record.path).name}"
        panel = make_panel(title, gray.convert("RGB"), panel_items[:8])
        panel_path = panel_dir / f"{safe_name(record.sample_id)}_mask_repair_panel.png"
        panel.save(panel_path)
    return variant_rows, panel_path


def write_markdown_summary(output_dir: Path, summary: dict[str, object]) -> None:
    lines: list[str] = []
    lines.append("# Issue #221 v9 mask-and-repair preprocessing probe")
    lines.append("")
    lines.append("This is a temporary diagnostic. No production code is changed.")
    lines.append("")
    lines.append("## Inventory")
    inv = summary.get("inventory", {})
    for key, value in inv.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    lines.append("## Residual results by target")
    for target in summary.get("residual_targets", []):
        lines.append("")
        lines.append(f"### {target.get('page_key')} expected={target.get('expected_num')}")
        lines.append(f"- selected_images: `{target.get('selected_images')}`")
        lines.append(f"- exact_rows: `{target.get('exact_rows')}`")
        lines.append(f"- wrong_rows: `{target.get('wrong_rows')}`")
        lines.append(f"- parsed_counts: `{target.get('parsed_counts')}`")
        lines.append(f"- best_variants: `{target.get('best_variants')}`")
    lines.append("")
    lines.append("## Global risk proxy")
    risk = summary.get("global_risk", {})
    for key, value in risk.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    lines.append("## Interpretation guide")
    lines.append("")
    lines.append("A useful result is not merely an OCR exact hit. The important question is whether a mask variant improves residual readability without producing wrong residual outputs or risky global digit outputs.")
    lines.append("")
    lines.append("If horizontal masking helps but edge/vertical masking harms, split follow-up work by element type rather than bundling all masks together.")
    (output_dir / "decision.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def zip_output(output_dir: Path, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(output_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(output_dir.parent))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", default="logs/issue221_component_ocr", help="Root containing prior ignored #221 logs")
    parser.add_argument("--output-dir", default="logs/issue221_component_ocr/v9_mask_repair_probe")
    parser.add_argument("--max-target-images", type=int, default=40)
    parser.add_argument("--max-global-images", type=int, default=120)
    parser.add_argument("--skip-ocr", action="store_true", help="Do not run optional Tesseract OCR")
    args = parser.parse_args()

    started = time.time()
    input_root = Path(args.input_root)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    terminal_dir = output_dir / "terminal_logs"
    terminal_dir.mkdir(parents=True, exist_ok=True)

    paths = find_images(input_root)
    records = select_records(paths, args.max_target_images, args.max_global_images)
    do_ocr = (not args.skip_ocr) and has_tesseract()

    inventory = {
        "input_root": str(input_root),
        "output_dir": str(output_dir),
        "scanned_images": len(paths),
        "selected_records": len(records),
        "selected_residual_records": sum(1 for r in records if r.group == "residual"),
        "selected_global_records": sum(1 for r in records if r.group == "global"),
        "variants": list(VARIANTS),
        "tesseract_ocr_enabled": do_ocr,
        "python": sys.version,
        "cwd": os.getcwd(),
    }
    (output_dir / "input_inventory.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=False), encoding="utf-8")
    write_csv(
        output_dir / "selected_manifest.csv",
        [asdict(r) for r in records],
        [
            "sample_id",
            "path",
            "group",
            "page_key",
            "expected_num",
            "score",
            "width",
            "height",
            "source_kind",
        ],
    )

    all_rows: list[VariantRow] = []
    panel_paths: list[str] = []
    for record in records:
        rows, panel_path = process_record(record, output_dir, do_ocr=do_ocr)
        all_rows.extend(rows)
        if panel_path:
            panel_paths.append(str(panel_path))

    fieldnames = list(VariantRow.__dataclass_fields__.keys())
    write_csv(output_dir / "variant_rows.csv", [asdict(row) for row in all_rows], fieldnames)

    by_target: list[dict[str, object]] = []
    for target in TARGETS:
        rows = [r for r in all_rows if r.page_key == target.page_key and r.group == "residual"]
        parsed_counts = Counter(str(r.parsed_num) for r in rows if r.parsed_num is not None)
        exact_by_variant = Counter(r.variant for r in rows if r.is_exact)
        wrong_by_variant = Counter(r.variant for r in rows if r.is_wrong)
        by_target.append(
            {
                "page_key": target.page_key,
                "key": list(target.key),
                "expected_num": target.expected_num,
                "selected_images": len({r.sample_id for r in rows}),
                "rows": len(rows),
                "exact_rows": sum(1 for r in rows if r.is_exact),
                "wrong_rows": sum(1 for r in rows if r.is_wrong),
                "parsed_counts": dict(parsed_counts),
                "best_variants": [name for name, _ in exact_by_variant.most_common(5)],
                "wrong_by_variant": dict(wrong_by_variant),
            }
        )

    global_rows = [r for r in all_rows if r.group == "global"]
    global_risky = [r for r in global_rows if r.is_risky_global]
    risk = {
        "global_records": len({r.sample_id for r in global_rows}),
        "global_rows": len(global_rows),
        "global_parsed_rows": sum(1 for r in global_rows if r.parsed_num is not None),
        "global_risky_rows": len(global_risky),
        "global_risky_counts": dict(Counter(str(r.parsed_num) for r in global_risky)),
        "global_risky_by_variant": dict(Counter(r.variant for r in global_risky)),
    }

    candidate_variants: list[dict[str, object]] = []
    for variant in VARIANTS:
        rows_v = [r for r in all_rows if r.variant == variant]
        residual_v = [r for r in rows_v if r.group == "residual"]
        global_v = [r for r in rows_v if r.group == "global"]
        exact_targets = sorted({r.page_key for r in residual_v if r.is_exact})
        wrong_count = sum(1 for r in residual_v if r.is_wrong)
        risky_count = sum(1 for r in global_v if r.is_risky_global)
        candidate_variants.append(
            {
                "variant": variant,
                "recovered_pages": exact_targets,
                "recovered_count": len(exact_targets),
                "residual_exact_rows": sum(1 for r in residual_v if r.is_exact),
                "residual_wrong_rows": wrong_count,
                "global_risky_rows": risky_count,
                "candidate_like": bool(exact_targets and wrong_count == 0 and risky_count == 0),
            }
        )

    summary = {
        "experiment": "v9_mask_repair_preprocess_probe",
        "production_code_changed": False,
        "production_candidate": False,
        "inventory": inventory,
        "residual_targets": by_target,
        "global_risk": risk,
        "candidate_variants": candidate_variants,
        "review_panels": panel_paths,
        "elapsed_sec": round(time.time() - started, 3),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown_summary(output_dir, summary)

    zip_path = output_dir.parent / "issue221_mask_repair_probe_v9_pack.zip"
    zip_output(output_dir, zip_path)

    terminal_summary = {
        "zip_path": str(zip_path),
        "summary_path": str(output_dir / "summary.json"),
        "records": len(records),
        "rows": len(all_rows),
        "tesseract_ocr_enabled": do_ocr,
    }
    (terminal_dir / "run_summary.json").write_text(json.dumps(terminal_summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(terminal_summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
