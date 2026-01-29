#!/usr/bin/env python3
"""
Visualize MMR FP/FN/Mismatch cases from a global eval run.

Reads mmr_eval_robust.csv and produces per-page overlays with error boxes.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Tuple

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class PageConfig:
    work: str
    page: str
    image: Path
    rest_gt: Path


def parse_work_page(name: str) -> Tuple[str, str] | None:
    if "_page_" not in name:
        return None
    work, page_num = name.rsplit("_page_", 1)
    return work, f"page_{page_num}"


def load_configs(config_paths: Iterable[Path]) -> Dict[Tuple[str, str], PageConfig]:
    mapping: Dict[Tuple[str, str], PageConfig] = {}
    for path in config_paths:
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        for page in data.get("pages", []):
            name = page.get("name", "")
            parsed = parse_work_page(name)
            if not parsed:
                continue
            work, page_key = parsed
            image = (REPO_ROOT / page["image"]).resolve()
            rest_gt = (REPO_ROOT / page["rest_gt"]).resolve()
            mapping[(work, page_key)] = PageConfig(
                work=work,
                page=page_key,
                image=image,
                rest_gt=rest_gt,
            )
    return mapping


def flatten_measures(numbering: dict) -> Tuple[list, Dict[Tuple[int, int], int]]:
    page = (numbering.get("pages") or [{}])[0]
    systems = page.get("systems") or []
    measures = []
    sys_meas_to_idx: Dict[Tuple[int, int], int] = {}
    idx = 0
    for sys_idx, system in enumerate(systems):
        for meas_idx, measure in enumerate(system.get("measures") or []):
            measures.append(measure)
            sys_meas_to_idx[(sys_idx, meas_idx)] = idx
            idx += 1
    return measures, sys_meas_to_idx


def load_rest_gt(path: Path) -> Dict[int, int]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    gt = {}
    overrides = data.get("overrides", data.get("rest_overrides", []))
    for item in overrides:
        idx = item.get("measure_index")
        if idx is None:
            idx = item.get("measure")
        if idx is None:
            continue
        count = item.get("rest_count")
        if count is None:
            count = item.get("count")
        if count is None and item.get("skip") is not None:
            count = item.get("skip") + 1
        if isinstance(idx, int) and isinstance(count, int) and count >= 2:
            gt[idx] = count
    return gt


def load_pred_overrides(path: Path, sys_meas_to_idx: Dict[Tuple[int, int], int]) -> Dict[int, int]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    overrides = data.get("measure_overrides", [])
    pred = {}
    for item in overrides:
        sys_idx = item.get("system")
        meas_idx = item.get("measure")
        if sys_idx is None or meas_idx is None:
            continue
        global_idx = sys_meas_to_idx.get((sys_idx, meas_idx))
        if global_idx is None:
            continue
        count = item.get("rest_count")
        if count is None and item.get("skip") is not None:
            count = item.get("skip") + 1
        if isinstance(count, int) and count >= 2:
            pred[global_idx] = count
    return pred


def draw_label(
    draw: ImageDraw.ImageDraw, x: int, y: int, text: str, color: Tuple[int, int, int]
) -> None:
    font = ImageFont.load_default()
    text_w, text_h = draw.textsize(text, font=font)
    pad = 2
    draw.rectangle([x, y - text_h - pad * 2, x + text_w + pad * 2, y], fill=(0, 0, 0))
    draw.text((x + pad, y - text_h - pad), text, fill=color, font=font)


def visualize_page(
    image_path: Path,
    measures: list,
    gt: Dict[int, int],
    pred: Dict[int, int],
    output_path: Path,
) -> None:
    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)

    for idx, measure in enumerate(measures):
        bbox = measure.get("bbox")
        if not bbox or len(bbox) != 4:
            continue
        x1, y1, x2, y2 = map(int, bbox)

        gt_count = gt.get(idx)
        pred_count = pred.get(idx)

        if gt_count is None and pred_count is None:
            continue

        if gt_count is not None and pred_count is None:
            color = (255, 0, 0)  # FN
            label = f"FN R{idx + 1} gt={gt_count}"
        elif gt_count is None and pred_count is not None:
            color = (255, 165, 0)  # FP
            label = f"FP R{idx + 1} pred={pred_count}"
        elif gt_count != pred_count:
            color = (128, 0, 128)  # Mismatch
            label = f"MM R{idx + 1} gt={gt_count} pred={pred_count}"
        else:
            # Correct prediction; skip to keep overlay focused.
            continue

        draw.rectangle([x1, y1, x2, y2], outline=color, width=3)
        draw_label(draw, x1 + 2, y1 + 2, label, color)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--configs",
        nargs="+",
        type=Path,
        default=[
            Path("data/evaluation2/rest_gt_config_all.json"),
            Path("data/evaluation2/rest_gt_config_expansion.json"),
            Path("data/evaluation2/rest_gt_config_missing.json"),
        ],
    )
    parser.add_argument("--only-work", type=str, default=None)
    parser.add_argument("--only-page", type=str, default=None)
    args = parser.parse_args()

    config_map = load_configs(args.configs)
    csv_path = args.eval_root / "mmr_eval_robust.csv"
    if not csv_path.exists():
        raise SystemExit(f"CSV not found: {csv_path}")

    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            work = row["Work"]
            page = row["Page"]
            if args.only_work and work != args.only_work:
                continue
            if args.only_page and page != args.only_page:
                continue

            gt = int(row["GT"])
            pipe_tp = int(row["Pipe_TP"])
            pipe_fp = int(row["Pipe_FP"])
            has_errors = (gt > pipe_tp) or (pipe_fp > 0)
            if not has_errors:
                continue

            cfg = config_map.get((work, page))
            if not cfg:
                print(f"[Warn] Config not found for {work} {page}")
                continue

            page_dir = args.eval_root / work / page
            overrides_path = page_dir / "overrides.json"
            numbering_path = page_dir / "numbering_final.json"
            if not numbering_path.exists():
                numbering_path = page_dir / "numbering_initial.json"

            if not overrides_path.exists():
                print(f"[Warn] Overrides not found: {overrides_path}")
                continue

            numbering = json.loads(numbering_path.read_text())
            measures, sys_meas_to_idx = flatten_measures(numbering)
            gt_map = load_rest_gt(cfg.rest_gt)
            pred_map = load_pred_overrides(overrides_path, sys_meas_to_idx)

            out_name = f"{work}_{page}_errors.png"
            visualize_page(
                cfg.image,
                measures,
                gt_map,
                pred_map,
                args.output_dir / work / out_name,
            )
            print(f"Wrote {args.output_dir / work / out_name}")


if __name__ == "__main__":
    main()
