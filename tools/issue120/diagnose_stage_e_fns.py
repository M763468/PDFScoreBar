#!/usr/bin/env python3
"""Diagnose remaining Issue #141 Stage E false negatives.

The regular Stage E evaluator writes page-level counts only. This diagnostic
script reloads the same manifest/GT/prediction artifacts and emits per-FN box
information, including where each GT is or is not represented across raw dense
candidates, filtered dense candidates, regenerated probe-rescue candidates,
pipeline candidate input, and final CNN predictions.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.common.barline_evaluation import (  # noqa: E402
    barline_iou,
    barline_vertical_overlap,
    center_distance_x,
    greedy_barline_match,
    is_barline_match,
)
from tools.issue120.eval_stage_e_from_manifest import (  # noqa: E402
    SCORES,
    boxes_from_candidates,
    boxes_from_gt,
    boxes_from_scored,
)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def page_map_from_manifest(manifest: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for item in manifest.get("pages", []):
        if not isinstance(item, dict):
            continue
        stem = Path(str(item.get("image_path", ""))).stem
        idx = stem.rfind("_page_")
        if idx < 0:
            continue
        score = stem[:idx]
        page = f"page_{stem[idx + len('_page_') :]}"
        out[(score, page)] = item
    return out


def safe_boxes(path: Path, kind: str, score_threshold: float) -> list[tuple[int, int, int, int]]:
    if not path.exists():
        return []
    payload = load_json(path)
    if kind == "gt":
        return boxes_from_gt(payload)
    if kind == "scored":
        return boxes_from_scored(payload, score_threshold=score_threshold)
    return boxes_from_candidates(payload)


def match_flags(
    boxes: Iterable[tuple[int, int, int, int]],
    gt: tuple[int, int, int, int],
    *,
    rule_name: str,
    vov_threshold: float,
    xdist_threshold: float,
) -> bool:
    return any(
        is_barline_match(
            box,
            gt,
            rule_name=rule_name,
            vov_threshold=vov_threshold,
            xdist_threshold=xdist_threshold,
        )
        for box in boxes
    )


def nearest_box(
    boxes: list[tuple[int, int, int, int]],
    gt: tuple[int, int, int, int],
) -> dict[str, Any] | None:
    if not boxes:
        return None
    ranked = []
    for idx, box in enumerate(boxes):
        vov = barline_vertical_overlap(box, gt)
        xdist = center_distance_x(box, gt)
        iou = barline_iou(box, gt)
        ranked.append(((vov, -xdist, iou), idx, box, vov, xdist, iou))
    ranked.sort(reverse=True)
    _, idx, box, vov, xdist, iou = ranked[0]
    return {
        "index": idx,
        "box": list(box),
        "vov": vov,
        "xdist": xdist,
        "iou": iou,
    }


def first_existing(*paths: Path) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]


def stage_paths(args: argparse.Namespace, score: str, page: str) -> dict[str, Path]:
    recon = args.reconstruction_root
    probe_rescue = first_existing(
        recon / "probe_rescue_candidates" / f"eval2_{score}_{page}" / "pipeline2_no_peak_candidates.json",
        recon / "issue53_probe_rescue_candidates" / f"eval2_{score}_{page}" / "pipeline2_no_peak_candidates.json",
    )
    return {
        "dense_raw": recon / "probe_candidates_from_inventory" / score / page / "pipeline2_no_peak_candidates.json",
        "dense_filtered": recon / "probe_candidates_filtered" / score / page / "pipeline2_no_peak_candidates.json",
        "probe_rescue": probe_rescue,
    }


def diagnose(args: argparse.Namespace) -> dict[str, Any]:
    manifest = load_json(args.manifest)
    if not isinstance(manifest, dict):
        raise ValueError("Manifest must be a JSON object")
    pmap = page_map_from_manifest(manifest)

    pages: list[dict[str, Any]] = []
    totals = {"fn": 0, "fn_pages": 0}

    for score, page_list in SCORES.items():
        for page in page_list:
            pdata = pmap.get((score, page))
            if pdata is None:
                continue
            gt_path = args.gt_root / score / page / "boxes_sorted.json"
            scored_path = Path(str(pdata.get("barlines_json", "")))
            pipeline_candidates_path = scored_path.parent / "pipeline2_no_peak_candidates.json"
            if not gt_path.exists() or not scored_path.exists():
                continue

            gts = safe_boxes(gt_path, "gt", args.score_threshold)
            preds = safe_boxes(scored_path, "scored", args.score_threshold)
            pipeline_candidates = safe_boxes(
                pipeline_candidates_path, "candidate", args.score_threshold
            )
            extra_paths = stage_paths(args, score, page)
            dense_raw = safe_boxes(extra_paths["dense_raw"], "candidate", args.score_threshold)
            dense_filtered = safe_boxes(
                extra_paths["dense_filtered"], "candidate", args.score_threshold
            )
            probe_rescue = safe_boxes(extra_paths["probe_rescue"], "candidate", args.score_threshold)

            result = greedy_barline_match(
                preds,
                gts,
                rule_name=args.rule_name,
                vov_threshold=args.vov_threshold,
                xdist_threshold=args.xdist_threshold,
            )
            if not result.false_negative_indices:
                continue

            totals["fn"] += len(result.false_negative_indices)
            totals["fn_pages"] += 1
            fn_details = []
            for gt_idx in result.false_negative_indices:
                gt = gts[gt_idx]
                source_boxes = {
                    "dense_raw": dense_raw,
                    "dense_filtered": dense_filtered,
                    "probe_rescue": probe_rescue,
                    "pipeline_candidates": pipeline_candidates,
                    "final_predictions": preds,
                }
                presence = {}
                nearest = {}
                for name, boxes in source_boxes.items():
                    presence[name] = match_flags(
                        boxes,
                        gt,
                        rule_name=args.rule_name,
                        vov_threshold=args.vov_threshold,
                        xdist_threshold=args.xdist_threshold,
                    )
                    nearest[name] = nearest_box(boxes, gt)
                fn_details.append(
                    {
                        "gt_index": gt_idx,
                        "gt_box": list(gt),
                        "presence": presence,
                        "nearest": nearest,
                    }
                )

            pages.append(
                {
                    "score": score,
                    "page": page,
                    "gt": len(gts),
                    "pred": len(preds),
                    "tp": len(result.matches),
                    "fp": len(result.false_positive_indices),
                    "fn": len(result.false_negative_indices),
                    "soft_matches": len(result.soft_matches),
                    "paths": {
                        "gt": str(gt_path),
                        "scored": str(scored_path),
                        "pipeline_candidates": str(pipeline_candidates_path),
                        **{k: str(v) for k, v in extra_paths.items()},
                    },
                    "candidate_counts": {
                        "dense_raw": len(dense_raw),
                        "dense_filtered": len(dense_filtered),
                        "probe_rescue": len(probe_rescue),
                        "pipeline_candidates": len(pipeline_candidates),
                        "final_predictions": len(preds),
                    },
                    "false_negatives": fn_details,
                }
            )

    return {
        "schema_version": "issue141.stage_e_fn_diagnostics.v1",
        "manifest": str(args.manifest),
        "reconstruction_root": str(args.reconstruction_root),
        "rule_name": args.rule_name,
        "vov_threshold": args.vov_threshold,
        "xdist_threshold": args.xdist_threshold,
        "score_threshold": args.score_threshold,
        "totals": totals,
        "pages": pages,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("logs/issue120_e2e_recovery/stage_e_full_pipeline/manifest.json"),
    )
    parser.add_argument("--gt-root", type=Path, default=Path("data/evaluation2/annotations"))
    parser.add_argument(
        "--reconstruction-root",
        type=Path,
        default=Path(
            "logs/issue120_e2e_recovery/stage_e_full_pipeline/dense_candidate_reconstruction"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "logs/issue120_e2e_recovery/stage_e_full_pipeline/eval_detector/fn_diagnostics.json"
        ),
    )
    parser.add_argument("--score-threshold", type=float, default=0.1)
    parser.add_argument("--rule-name", default="center_anchor")
    parser.add_argument("--vov-threshold", type=float, default=0.5)
    parser.add_argument("--xdist-threshold", type=float, default=12.0)
    args = parser.parse_args()

    payload = diagnose(args)
    write_json(args.output, payload)
    print(f"Wrote: {args.output}")
    print(json.dumps(payload["totals"], indent=2))


if __name__ == "__main__":
    main()
