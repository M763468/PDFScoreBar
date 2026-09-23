#!/usr/bin/env python3
"""Score retained Issue #372 singleton probe seeds with the verified CNN.

Diagnostic only. No detector regeneration is performed and no production rule
is changed. The script reuses the exact retained current images, verified CNN
checkpoint, threshold, and crop/recenter settings recorded by the Issue #372
counterfactual.

The purpose is to test whether CNN evidence can distinguish singleton rows whose
probe expansion is useful from rows such as Shostakovich-Sym5-Va/page_021 that
only amplify false candidates.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Mapping

import cv2
import numpy as np
import torch
from PIL import Image
from torchvision import transforms

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.issue372.run_retained_x4_gap_counterfactual import (
    _host_path,
    _load_config,
)
from experiments.issue372.diagnose_page021_row_source_attribution import (
    _load_inventory_record,
)
from src.pipeline.steps.cnn_scoring import (
    GPUNormalize,
    IMG_SIZE,
    MEAN,
    STD,
    _center_crop,
    _compute_bbox_ink_center_x,
    _crop_size_from_bbox,
    _load_model,
)
from src.pipeline.utils.images import load_image


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _score_box(
    img: np.ndarray,
    box: list[int],
    *,
    model: torch.nn.Module,
    gpu_norm: GPUNormalize,
    device: torch.device,
    recenter: bool,
    recenter_max_shift: float,
) -> tuple[float, int, int]:
    x1, y1, x2, y2 = box
    cx = int((x1 + x2) / 2)
    cy = int((y1 + y2) / 2)
    original_cx = cx

    if recenter:
        adjusted = _compute_bbox_ink_center_x(
            img,
            box,
            max_shift_unit_ratio=recenter_max_shift,
        )
        if adjusted is not None:
            cx = adjusted

    cw, ch = _crop_size_from_bbox(box)
    crop = _center_crop(img, cx, cy, cw, ch)
    resize_filter = (
        Image.Resampling.BILINEAR if hasattr(Image, "Resampling") else Image.BILINEAR
    )
    tensor = transforms.ToTensor()(
        Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)).resize(
            (IMG_SIZE[1], IMG_SIZE[0]),
            resize_filter,
        )
    )
    batch = gpu_norm(tensor.unsqueeze(0).to(device))
    with torch.no_grad():
        score = float(torch.sigmoid(model(batch)).cpu().numpy().flatten()[0])
    return score, original_cx, cx


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [float(row["cnn_score"]) for row in rows]
    return {
        "rows": len(rows),
        "score_min": min(scores) if scores else None,
        "score_median": statistics.median(scores) if scores else None,
        "score_max": max(scores) if scores else None,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    competing_report = args.competing_report.resolve()
    x4_run = args.x4_run_root.resolve()
    issue43_root = args.issue43_repo_root.resolve()
    output = args.output.resolve()

    competing = _load_json(competing_report)
    if competing.get("schema_version") != "issue372.probe_seed_competing_row.v1":
        raise ValueError(
            f"Unexpected competing report schema: {competing.get('schema_version')!r}"
        )

    counterfactual_path = x4_run / "counterfactual_report.json"
    counterfactual = _load_json(counterfactual_path)
    contract = counterfactual.get("contract")
    if not isinstance(contract, Mapping):
        raise ValueError(f"Counterfactual report lacks contract: {counterfactual_path}")

    model_path = Path(str(contract["cnn_model"]))
    if not model_path.is_file():
        raise FileNotFoundError(model_path)

    config_path = Path(str(contract["config"]))
    if not config_path.is_file():
        raise FileNotFoundError(config_path)
    config = _load_config(config_path)
    detection = config["detection"]
    assert isinstance(detection, Mapping)

    threshold = float(contract["cnn_threshold"])
    recenter = bool(detection.get("crop_recenter_on_bbox_ink", False))
    recenter_max_shift = float(
        detection.get("crop_recenter_max_shift_unit_ratio", 0.35)
    )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = _load_model(model_path, device)
    gpu_norm = GPUNormalize(MEAN, STD).to(device)

    singleton_rows = [
        *competing.get("true_singletons", []),
        *competing.get("false_singletons", []),
    ]

    inventory_cache: dict[str, Mapping[str, Any]] = {}
    image_cache: dict[tuple[str, str], np.ndarray] = {}
    scored: list[dict[str, Any]] = []

    for row in singleton_rows:
        score_name = str(row["score"])
        page = str(row["page"])
        members = row.get("members")
        if not isinstance(members, list) or len(members) != 1:
            raise ValueError(f"Expected singleton member: {score_name}/{page}")
        box = [int(v) for v in members[0]["bbox"]]

        if score_name not in inventory_cache:
            inventory_path = x4_run / "inventories" / "control" / f"{score_name}.json"
            inventory_cache[score_name] = _load_json(inventory_path)

        # Use the same helper semantics as the prior Issue #372 retained diagnostics.
        inventory_path = x4_run / "inventories" / "control" / f"{score_name}.json"
        record = _load_inventory_record(inventory_path, page=page)
        image_path = _host_path(str(record["image"]), issue43_root)
        if not image_path.is_file():
            raise FileNotFoundError(image_path)

        key = (score_name, page)
        if key not in image_cache:
            image_cache[key] = load_image(image_path, None)
        img = image_cache[key]

        cnn_score, original_cx, crop_cx = _score_box(
            img,
            box,
            model=model,
            gpu_norm=gpu_norm,
            device=device,
            recenter=recenter,
            recenter_max_shift=recenter_max_shift,
        )

        nearest = row.get("nearest_multi")
        competing_nearby = bool(
            nearest is not None
            and float(nearest["overlap_px"]) > 0.0
            and float(nearest["center_gap"]) <= 100.0
        )
        expansion_gt = int(row["generated_distinct_gt_count"])

        scored.append(
            {
                **row,
                "image": str(image_path),
                "cnn_score": cnn_score,
                "cnn_positive_at_production_threshold": cnn_score >= threshold,
                "crop_original_cx": original_cx,
                "crop_cx": crop_cx,
                "crop_recenter_shift": crop_cx - original_cx,
                "competing_nearby_gap100": competing_nearby,
                "expansion_useful": expansion_gt > 0,
            }
        )

    useful = [row for row in scored if row["expansion_useful"]]
    useless = [row for row in scored if not row["expansion_useful"]]
    competing_nearby = [row for row in scored if row["competing_nearby_gap100"]]
    competing_useful = [row for row in competing_nearby if row["expansion_useful"]]
    competing_useless = [row for row in competing_nearby if not row["expansion_useful"]]

    target = [
        row
        for row in scored
        if row["score"] == "Shostakovich-Sym5-Va"
        and row["page"] == "page_021"
        and row["members"][0]["bbox"] == [976, 753, 982, 845]
    ]
    if len(target) != 1:
        raise RuntimeError(f"Expected one page_021 target row, got {len(target)}")

    def gate_eval(rows: list[dict[str, Any]]) -> dict[str, int]:
        rejected = [
            row for row in rows if float(row["cnn_score"]) < threshold
        ]
        return {
            "rows": len(rows),
            "cnn_negative_rows": len(rejected),
            "cnn_negative_useful_rows": sum(row["expansion_useful"] for row in rejected),
            "lost_distinct_gt_if_negative_rows_not_expanded": sum(
                int(row["generated_distinct_gt_count"]) for row in rejected
            ),
            "generated_candidates_removed_from_useless_rows": sum(
                int(row["generated_count"])
                for row in rejected
                if not row["expansion_useful"]
            ),
        }

    result = {
        "schema_version": "issue372.singleton_seed_cnn_score.v1",
        "contract": {
            "diagnostic_only": True,
            "detector_regeneration": False,
            "model_path": str(model_path),
            "cnn_threshold": threshold,
            "device": str(device),
            "crop_recenter_on_bbox_ink": recenter,
            "crop_recenter_max_shift_unit_ratio": recenter_max_shift,
            "competing_nearby_definition": "nearest multi row overlap_px>0 and center_gap<=100",
        },
        "summary": {
            "all": _summary(scored),
            "expansion_useful": _summary(useful),
            "expansion_useless": _summary(useless),
            "competing_nearby": _summary(competing_nearby),
            "competing_nearby_useful": _summary(competing_useful),
            "competing_nearby_useless": _summary(competing_useless),
            "production_threshold_gate_all": gate_eval(scored),
            "production_threshold_gate_competing_nearby": gate_eval(competing_nearby),
        },
        "page021_target": target[0],
        "rows": sorted(
            scored,
            key=lambda row: (
                float(row["cnn_score"]),
                str(row["score"]),
                str(row["page"]),
            ),
        ),
    }

    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("=== Issue #372 singleton seed CNN diagnostic ===")
    print(f"device={device}")
    print(f"threshold={threshold:.9f}")
    print(f"recenter={recenter} max_shift={recenter_max_shift}")
    print()
    for key, value in result["summary"].items():
        print(f"{key}: {json.dumps(value, ensure_ascii=False)}")

    print("\n=== page_021 target ===")
    target_row = target[0]
    print(
        f"score={target_row['cnn_score']:.9f} "
        f"positive={target_row['cnn_positive_at_production_threshold']} "
        f"generated={target_row['generated_count']} "
        f"generated_gt={target_row['generated_distinct_gt_count']} "
        f"gap={target_row['nearest_multi']['center_gap'] if target_row['nearest_multi'] else None}"
    )

    print("\n=== competing rows (gap<=100, overlapping) ===")
    for row in sorted(
        competing_nearby,
        key=lambda item: (
            float(item["cnn_score"]),
            str(item["score"]),
            str(item["page"]),
        ),
    ):
        nearest = row["nearest_multi"]
        print(
            f"{row['score']}/{row['page']} "
            f"seed_gt={row['row_gt_class']} expansion_gt={row['generated_distinct_gt_count']} "
            f"generated={row['generated_count']} score={row['cnn_score']:.9f} "
            f"cnn_pos={row['cnn_positive_at_production_threshold']} "
            f"gap={nearest['center_gap']:.1f} viou={nearest['vertical_iou']:.3f} "
            f"seed={row['members'][0]['bbox']}"
        )

    print(f"\nOUTPUT={output}")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--competing-report", type=Path, required=True)
    parser.add_argument("--x4-run-root", type=Path, required=True)
    parser.add_argument("--issue43-repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    run(parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
