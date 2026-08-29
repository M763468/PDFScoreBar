#!/usr/bin/env python3
"""Temporary retained-artifact diagnostic for Issue #284 Stage E FN regressions.

Read-only: no pipeline execution, GPU inference, model loading, or artifact
mutation. The file is intentionally temporary and must be removed before PR.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.common.barline_evaluation import (  # noqa: E402
    barline_iou,
    barline_vertical_overlap,
    center_distance_x,
    greedy_barline_match,
    is_barline_match,
)
from tools.issue120.eval_full68_from_intermediates import (  # noqa: E402
    SCORES,
    boxes_from_candidates,
    boxes_from_gt,
    boxes_from_scored,
)

SCORE_THRESHOLD = 0.1
RULE_NAME = "center_anchor"
VOV_THRESHOLD = 0.5
XDIST_THRESHOLD = 12.0
ACCEPTED = {
    "gt": 3580,
    "pred": 3600,
    "tp": 3579,
    "fp": 1,
    "fn": 1,
    "fn_det": 0,
    "fn_cnn": 1,
}
CURRENT = {
    "gt": 3580,
    "pred": 3599,
    "tp": 3574,
    "fp": 1,
    "fn": 6,
    "fn_det": 0,
    "fn_cnn": 6,
}
STAGE_ORDER = (
    "dense_raw",
    "dense_filtered",
    "probe_rescue_candidates",
    "pipeline_candidates",
    "scored_records",
    "final_predictions",
)
BOX_KEYS = ("bbox", "box", "barline_location")
SCORE_KEYS = ("score", "cnn_score", "probability", "confidence")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_box(box: Iterable[Any]) -> tuple[int, int, int, int]:
    values = list(box)
    return tuple(int(round(float(v))) for v in values[:4])  # type: ignore[return-value]


def matches_gt(
    boxes: Iterable[tuple[int, int, int, int]],
    gt: tuple[int, int, int, int],
) -> bool:
    return any(
        is_barline_match(
            box,
            gt,
            rule_name=RULE_NAME,
            vov_threshold=VOV_THRESHOLD,
            xdist_threshold=XDIST_THRESHOLD,
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


def final_path_rank(path: Path) -> tuple[int, int, str]:
    text = str(path)
    score = 0
    if path.name == "pipeline2_no_peak_scored.json":
        score += 100
    if "probe_rescue_candidates" in text:
        score += 20
    if "dense_candidate_reconstruction" in text:
        score += 10
    if "dense_full_pipeline_route" in text:
        score += 5
    # Prefer the more specific/shorter path when the semantic rank ties.
    return (score, -len(path.parts), str(path))


def discover_page_artifacts(root: Path) -> dict[tuple[str, str], dict[str, Any]]:
    if not root.is_dir():
        raise FileNotFoundError(root)

    finals = list(root.rglob("pipeline2_no_peak_scored.json"))
    if not finals:
        finals = list(root.rglob("pipeline2_no_peak_filtered_cnn.json"))
    if not finals:
        raise FileNotFoundError(
            f"No final Stage E detector JSON found under {root}. "
            "Expected pipeline2_no_peak_scored.json."
        )

    out: dict[tuple[str, str], dict[str, Any]] = {}
    for score, pages in SCORES.items():
        for page in pages:
            token = f"eval2_{score}_{page}"
            matches = [
                path
                for path in finals
                if token in str(path) or (score in str(path) and page in str(path))
            ]
            if not matches:
                continue
            ranked = sorted(matches, key=final_path_rank, reverse=True)
            final_path = ranked[0]
            out[(score, page)] = {
                "final": final_path,
                "candidates": final_path.parent / "pipeline2_no_peak_candidates.json",
                "alternatives": [str(path) for path in ranked[1:]],
            }
    return out


def ancestor_named(path: Path, name: str) -> Path | None:
    for parent in (path.parent, *path.parents):
        if parent.name == name:
            return parent
    return None


def reconstruction_paths(final_path: Path, score: str, page: str) -> dict[str, Path | None]:
    recon = ancestor_named(final_path, "dense_candidate_reconstruction")
    if recon is None:
        return {
            "dense_raw": None,
            "dense_filtered": None,
            "probe_rescue_candidates": final_path.parent / "pipeline2_no_peak_candidates.json",
        }
    dense_raw = (
        recon
        / "probe_candidates_from_inventory"
        / score
        / page
        / "pipeline2_no_peak_candidates.json"
    )
    dense_filtered = (
        recon
        / "probe_candidates_filtered"
        / score
        / page
        / "pipeline2_no_peak_candidates.json"
    )
    return {
        "dense_raw": dense_raw if dense_raw.is_file() else None,
        "dense_filtered": dense_filtered if dense_filtered.is_file() else None,
        "probe_rescue_candidates": final_path.parent / "pipeline2_no_peak_candidates.json",
    }


def safe_candidate_boxes(path: Path | None) -> list[tuple[int, int, int, int]]:
    if path is None or not path.is_file():
        return []
    return boxes_from_candidates(load_json(path))


def safe_scored_boxes(path: Path | None, *, threshold: float) -> list[tuple[int, int, int, int]]:
    if path is None or not path.is_file():
        return []
    return boxes_from_scored(load_json(path), score_threshold=threshold)


def snapshot(
    path: Path | None,
    gt: tuple[int, int, int, int],
    *,
    kind: str,
) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {
            "available": False,
            "path": None if path is None else str(path),
            "count": None,
            "present": None,
            "nearest": None,
        }
    boxes = (
        safe_scored_boxes(path, threshold=SCORE_THRESHOLD)
        if kind == "scored"
        else safe_candidate_boxes(path)
    )
    return {
        "available": True,
        "path": str(path),
        "count": len(boxes),
        "present": matches_gt(boxes, gt),
        "nearest": nearest_box(boxes, gt),
    }


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def extract_box_records(obj: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    def visit(value: Any, node_path: str) -> None:
        if isinstance(value, dict):
            found_box = False
            for key in BOX_KEYS:
                box = value.get(key)
                if (
                    isinstance(box, (list, tuple))
                    and len(box) >= 4
                    and all(is_number(v) for v in box[:4])
                ):
                    score_key = next(
                        (candidate for candidate in SCORE_KEYS if is_number(value.get(candidate))),
                        None,
                    )
                    records.append(
                        {
                            "box": list(normalize_box(box)),
                            "node_path": node_path,
                            "score_key": score_key,
                            "score": float(value[score_key]) if score_key else None,
                        }
                    )
                    found_box = True
                    break
            for key, child in value.items():
                if found_box and key in BOX_KEYS:
                    continue
                if isinstance(child, (dict, list)):
                    visit(child, f"{node_path}.{key}")
            return

        if isinstance(value, list):
            if len(value) >= 4 and all(is_number(v) for v in value[:4]):
                records.append(
                    {
                        "box": list(normalize_box(value)),
                        "node_path": node_path,
                        "score_key": None,
                        "score": None,
                    }
                )
                return
            for idx, child in enumerate(value):
                if isinstance(child, (dict, list)):
                    visit(child, f"{node_path}[{idx}]")

    visit(obj, "$")
    return records


def nearest_record(
    records: list[dict[str, Any]],
    gt: tuple[int, int, int, int],
) -> dict[str, Any] | None:
    if not records:
        return None
    boxes = [normalize_box(record["box"]) for record in records]
    nearest = nearest_box(boxes, gt)
    if nearest is None:
        return None
    record = records[int(nearest["index"])]
    return {
        **nearest,
        "node_path": record["node_path"],
        "score_key": record["score_key"],
        "score": record["score"],
    }


def scored_record_snapshot(
    path: Path,
    gt: tuple[int, int, int, int],
) -> dict[str, Any]:
    if not path.is_file():
        return {
            "available": False,
            "path": str(path),
            "record_count": None,
            "present_any_score": None,
            "nearest": None,
        }
    records = extract_box_records(load_json(path))
    boxes = [normalize_box(record["box"]) for record in records]
    return {
        "available": True,
        "path": str(path),
        "record_count": len(records),
        "present_any_score": matches_gt(boxes, gt),
        "nearest": nearest_record(records, gt),
    }


def inspect_sibling_jsons(
    page_dir: Path,
    gt: tuple[int, int, int, int],
    *,
    max_json_bytes: int,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for path in sorted(page_dir.glob("*.json")):
        size = path.stat().st_size
        if size > max_json_bytes:
            result[path.name] = {"path": str(path), "size_bytes": size, "skipped": "too_large"}
            continue
        try:
            records = extract_box_records(load_json(path))
        except (OSError, ValueError, TypeError) as exc:
            result[path.name] = {
                "path": str(path),
                "size_bytes": size,
                "skipped": type(exc).__name__,
            }
            continue
        if not records:
            continue
        boxes = [normalize_box(record["box"]) for record in records]
        result[path.name] = {
            "path": str(path),
            "size_bytes": size,
            "box_record_count": len(records),
            "present": matches_gt(boxes, gt),
            "nearest": nearest_record(records, gt),
        }
    return result


def evaluate_run(root: Path) -> dict[str, Any]:
    artifacts = discover_page_artifacts(root)
    expected_pages = sum(len(pages) for pages in SCORES.values())
    missing: list[dict[str, str]] = []
    totals = {key: 0 for key in ACCEPTED}
    pages: dict[tuple[str, str], dict[str, Any]] = {}

    for score, page_list in SCORES.items():
        for page in page_list:
            key = (score, page)
            paths = artifacts.get(key)
            if paths is None:
                missing.append({"score": score, "page": page, "reason": "final_artifact_not_found"})
                continue
            gt_path = PROJECT_ROOT / "data/evaluation2/annotations" / score / page / "boxes_sorted.json"
            final_path = paths["final"]
            candidates_path = paths["candidates"]
            if not gt_path.is_file():
                missing.append({"score": score, "page": page, "reason": f"missing_gt:{gt_path}"})
                continue
            if not candidates_path.is_file():
                missing.append(
                    {"score": score, "page": page, "reason": f"missing_candidates:{candidates_path}"}
                )
                continue

            gt = boxes_from_gt(load_json(gt_path))
            pred = boxes_from_scored(load_json(final_path), score_threshold=SCORE_THRESHOLD)
            candidates = boxes_from_candidates(load_json(candidates_path))
            matched = greedy_barline_match(
                pred,
                gt,
                rule_name=RULE_NAME,
                vov_threshold=VOV_THRESHOLD,
                xdist_threshold=XDIST_THRESHOLD,
            )
            fn_det = 0
            fn_cnn = 0
            for gt_idx in matched.false_negative_indices:
                if matches_gt(candidates, gt[gt_idx]):
                    fn_cnn += 1
                else:
                    fn_det += 1

            row = {
                "gt": len(gt),
                "pred": len(pred),
                "tp": len(matched.matches),
                "fp": len(matched.false_positive_indices),
                "fn": len(matched.false_negative_indices),
                "fn_det": fn_det,
                "fn_cnn": fn_cnn,
            }
            for metric in totals:
                totals[metric] += row[metric]
            pages[key] = {
                "gt": gt,
                "pred": pred,
                "candidates": candidates,
                "matched": matched,
                "final_path": final_path,
                "candidates_path": candidates_path,
                "reconstruction": reconstruction_paths(final_path, score, page),
                "alternatives": paths["alternatives"],
                "metrics": row,
            }

    return {
        "root": str(root),
        "metrics": totals,
        "page_count": len(pages),
        "expected_page_count": expected_pages,
        "missing": missing,
        "_pages": pages,
    }


def contract_check(metrics: dict[str, int], expected: dict[str, int]) -> dict[str, Any]:
    mismatches = {
        key: {"expected": value, "actual": metrics.get(key)}
        for key, value in expected.items()
        if metrics.get(key) != value
    }
    return {"matched": not mismatches, "mismatches": mismatches}


def stage_snapshots(
    page_data: dict[str, Any],
    gt: tuple[int, int, int, int],
) -> dict[str, Any]:
    recon = page_data["reconstruction"]
    return {
        "dense_raw": snapshot(recon["dense_raw"], gt, kind="candidate"),
        "dense_filtered": snapshot(recon["dense_filtered"], gt, kind="candidate"),
        "probe_rescue_candidates": snapshot(
            recon["probe_rescue_candidates"], gt, kind="candidate"
        ),
        "pipeline_candidates": snapshot(page_data["candidates_path"], gt, kind="candidate"),
        "scored_records": scored_record_snapshot(page_data["final_path"], gt),
        "final_predictions": snapshot(page_data["final_path"], gt, kind="scored"),
    }


def first_known_divergence(
    accepted: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, str] | None:
    for stage in STAGE_ORDER:
        a = accepted[stage]
        c = current[stage]
        if not a.get("available") or not c.get("available"):
            continue
        if stage == "scored_records":
            if a.get("present_any_score") != c.get("present_any_score"):
                return {"stage": stage, "reason": "any_score_presence"}
            a_nearest = (a.get("nearest") or {}).get("box")
            c_nearest = (c.get("nearest") or {}).get("box")
            a_score = (a.get("nearest") or {}).get("score")
            c_score = (c.get("nearest") or {}).get("score")
            if a_nearest != c_nearest:
                return {"stage": stage, "reason": "nearest_geometry"}
            if a_score != c_score:
                return {"stage": stage, "reason": "nearest_score"}
            continue

        if a.get("present") != c.get("present"):
            return {"stage": stage, "reason": "match_presence"}
        a_nearest = (a.get("nearest") or {}).get("box")
        c_nearest = (c.get("nearest") or {}).get("box")
        if a.get("present") and c.get("present") and a_nearest != c_nearest:
            return {"stage": stage, "reason": "nearest_matching_geometry"}
    return None


def public_run(run: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in run.items() if key != "_pages"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accepted-root", type=Path, required=True)
    parser.add_argument("--current-root", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("logs/issue284/issue284_fn_regression_diagnostics.json"),
    )
    parser.add_argument("--max-json-bytes", type=int, default=25_000_000)
    args = parser.parse_args()

    accepted = evaluate_run(args.accepted_root.resolve())
    current = evaluate_run(args.current_root.resolve())

    accepted_pages = accepted["_pages"]
    current_pages = current["_pages"]
    items: list[dict[str, Any]] = []

    for score, page_list in SCORES.items():
        for page in page_list:
            key = (score, page)
            apage = accepted_pages.get(key)
            cpage = current_pages.get(key)
            if apage is None or cpage is None:
                continue
            accepted_fn = set(apage["matched"].false_negative_indices)
            for gt_idx in cpage["matched"].false_negative_indices:
                gt = cpage["gt"][gt_idx]
                accepted_gt = apage["gt"][gt_idx] if gt_idx < len(apage["gt"]) else None
                gt_consistent = accepted_gt == gt
                classification = (
                    "accepted_residual"
                    if gt_consistent and gt_idx in accepted_fn
                    else "regression"
                )
                astages = stage_snapshots(apage, gt)
                cstages = stage_snapshots(cpage, gt)
                items.append(
                    {
                        "classification": classification,
                        "score": score,
                        "page": page,
                        "gt_index": gt_idx,
                        "gt_box": list(gt),
                        "accepted_gt_box": list(accepted_gt) if accepted_gt is not None else None,
                        "gt_consistent": gt_consistent,
                        "first_known_divergence": first_known_divergence(astages, cstages),
                        "accepted_stages": astages,
                        "current_stages": cstages,
                        "accepted_sibling_jsons": inspect_sibling_jsons(
                            apage["final_path"].parent,
                            gt,
                            max_json_bytes=args.max_json_bytes,
                        ),
                        "current_sibling_jsons": inspect_sibling_jsons(
                            cpage["final_path"].parent,
                            gt,
                            max_json_bytes=args.max_json_bytes,
                        ),
                        "accepted_alternative_final_paths": apage["alternatives"],
                        "current_alternative_final_paths": cpage["alternatives"],
                    }
                )

    classification = {
        "current_fn": len(items),
        "accepted_residual": sum(i["classification"] == "accepted_residual" for i in items),
        "regression": sum(i["classification"] == "regression" for i in items),
    }
    payload = {
        "schema_version": "issue284.stage_e_fn_regression_diagnostics.v1",
        "read_only": True,
        "evaluation_contract": {
            "score_threshold": SCORE_THRESHOLD,
            "rule_name": RULE_NAME,
            "vov_threshold": VOV_THRESHOLD,
            "xdist_threshold": XDIST_THRESHOLD,
        },
        "accepted": public_run(accepted),
        "current": public_run(current),
        "contract_checks": {
            "accepted": contract_check(accepted["metrics"], ACCEPTED),
            "current": contract_check(current["metrics"], CURRENT),
        },
        "classification_counts": classification,
        "false_negatives": items,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    compact = {
        "accepted_metrics": accepted["metrics"],
        "current_metrics": current["metrics"],
        "accepted_contract_matched": payload["contract_checks"]["accepted"]["matched"],
        "current_contract_matched": payload["contract_checks"]["current"]["matched"],
        "classification_counts": classification,
        "accepted_missing": len(accepted["missing"]),
        "current_missing": len(current["missing"]),
        "output": str(args.output),
    }
    print(json.dumps(compact, indent=2, ensure_ascii=False))

    if accepted["missing"] or current["missing"]:
        return 2
    if classification != {"current_fn": 6, "accepted_residual": 1, "regression": 5}:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
