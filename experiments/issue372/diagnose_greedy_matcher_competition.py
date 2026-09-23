#!/usr/bin/env python3
"""Trace greedy matcher ownership for Issue #372 combined residual FNs.

Retained-only. No inference or candidate regeneration.

For each residual FN from diagnose_combined_residual_fns.py:
- list every final prediction that individually satisfies current-unit matching;
- show which GT each such prediction is actually assigned to by greedy matching;
- show rank metrics against the residual GT and assigned GT;
- compare the same GT's status in retained late-raw final output.

This distinguishes true detector loss from one-to-one matcher competition.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.common.barline_evaluation import (
    CENTER_ANCHOR_XDIST_UNIT_RATIO,
    barline_iou,
    barline_vertical_overlap,
    center_distance_x,
    get_barline_match_rank,
    greedy_barline_match,
    is_barline_match,
)
from src.common.barline_units import load_page_staff_units, require_page_staff_unit
from tools.issue120 import eval_full68_from_intermediates as full68_eval


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _norm(box: Sequence[Any]) -> tuple[int, int, int, int]:
    return tuple(int(round(float(v))) for v in box[:4])  # type: ignore[return-value]


def _find(root: Path, score: str, page: str, filename: str) -> Path:
    rec = full68_eval.PageRecord(score=score, page=page)
    path = full68_eval.find_page_file(root, rec, filename)
    if path is None or not path.is_file():
        raise FileNotFoundError(f"{score}/{page}: {filename} under {root}")
    return path


def _final(path: Path) -> list[tuple[int, int, int, int]]:
    return [_norm(box) for box in full68_eval.boxes_from_candidates(_load(path))]


def _gt(path: Path) -> list[tuple[int, int, int, int]]:
    return [_norm(box) for box in full68_eval.boxes_from_gt(_load(path))]


def _match(pred: Sequence[int], gt: Sequence[int], unit: float) -> bool:
    return is_barline_match(
        pred,
        gt,
        rule_name="center_anchor",
        vov_threshold=0.5,
        xdist_threshold=None,
        unit_size=unit,
        xdist_unit_ratio=CENTER_ANCHOR_XDIST_UNIT_RATIO,
    )


def _pair(pred: Sequence[int], gt: Sequence[int]) -> dict[str, Any]:
    return {
        "vov": barline_vertical_overlap(tuple(pred), tuple(gt)),
        "xdist": center_distance_x(tuple(pred), tuple(gt)),
        "iou": barline_iou(tuple(pred), tuple(gt)),
        "rank": list(get_barline_match_rank(tuple(pred), tuple(gt), "center_anchor")),
    }


def _trace_variant(
    preds: list[tuple[int, int, int, int]],
    gts: list[tuple[int, int, int, int]],
    *,
    unit: float,
    residual_gt_index: int,
) -> dict[str, Any]:
    result = greedy_barline_match(
        preds,
        gts,
        rule_name="center_anchor",
        vov_threshold=0.5,
        xdist_threshold=None,
        unit_size=unit,
        xdist_unit_ratio=CENTER_ANCHOR_XDIST_UNIT_RATIO,
    )
    ownership = {m.pred_index: m.gt_index for m in result.matches}
    gt_to_pred = {m.gt_index: m.pred_index for m in result.matches}

    residual = gts[residual_gt_index]
    compatible = []
    for p_idx, pred in enumerate(preds):
        if not _match(pred, residual, unit):
            continue
        assigned_gt_index = ownership.get(p_idx)
        assigned_gt = gts[assigned_gt_index] if assigned_gt_index is not None else None
        compatible.append(
            {
                "pred_index": p_idx,
                "pred_bbox": list(pred),
                "residual_pair": _pair(pred, residual),
                "assigned_gt_index": assigned_gt_index,
                "assigned_gt_bbox": list(assigned_gt) if assigned_gt is not None else None,
                "assigned_pair": _pair(pred, assigned_gt) if assigned_gt is not None else None,
            }
        )

    assigned_pred_idx = gt_to_pred.get(residual_gt_index)
    return {
        "is_fn": residual_gt_index in result.false_negative_indices,
        "assigned_pred_index": assigned_pred_idx,
        "assigned_pred_bbox": list(preds[assigned_pred_idx])
        if assigned_pred_idx is not None
        else None,
        "compatible_predictions": compatible,
        "hard_fp_count_page": len(result.false_positive_indices),
        "soft_count_page": len(result.soft_matches),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    residual_report = _load(args.residual_report.resolve())
    combined_report = _load(args.combined_report.resolve())
    late_report = _load(args.late_report.resolve())

    if not all(isinstance(x, Mapping) for x in (residual_report, combined_report, late_report)):
        raise ValueError("reports must be objects")

    combined_root = Path(str(combined_report["aggregate_probe"]))
    late_root = Path(str(late_report["late_raw_x4"]["aggregate_probe"]))
    gt_root = args.gt_root.resolve()
    units = load_page_staff_units(args.staff_units_json.resolve())

    traces = []
    for row in residual_report["residuals"]:
        score = str(row["score"])
        page = str(row["page"])
        gt_index = int(row["gt_index"])
        unit = float(require_page_staff_unit(units, score, page).unit_size)

        gts = _gt(gt_root / score / page / "boxes_sorted.json")
        combined = _final(
            _find(combined_root, score, page, "pipeline2_no_peak_filtered_cnn.json")
        )
        late = _final(
            _find(late_root, score, page, "pipeline2_no_peak_filtered_cnn.json")
        )

        traces.append(
            {
                "score": score,
                "page": page,
                "gt_index": gt_index,
                "gt_bbox": list(gts[gt_index]),
                "unit_size": unit,
                "xdist_limit": unit * CENTER_ANCHOR_XDIST_UNIT_RATIO,
                "combined": _trace_variant(
                    combined, gts, unit=unit, residual_gt_index=gt_index
                ),
                "late_raw": _trace_variant(
                    late, gts, unit=unit, residual_gt_index=gt_index
                ),
            }
        )

    report = {
        "schema_version": "issue372.greedy_matcher_competition.v1",
        "contract": {
            "retained_only": True,
            "matcher": "center_anchor current-unit greedy one-to-one",
        },
        "summary": {
            "residual_count": len(traces),
            "combined_residuals_with_compatible_final_prediction": sum(
                bool(t["combined"]["compatible_predictions"]) for t in traces
            ),
            "combined_residuals_where_compatible_pred_owned_by_other_gt": sum(
                any(
                    p["assigned_gt_index"] is not None
                    and p["assigned_gt_index"] != t["gt_index"]
                    for p in t["combined"]["compatible_predictions"]
                )
                for t in traces
            ),
            "late_raw_same_gt_fn_count": sum(t["late_raw"]["is_fn"] for t in traces),
        },
        "traces": traces,
    }

    out = args.output.resolve()
    if out.exists():
        raise FileExistsError(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("=== Issue #372 greedy matcher competition ===")
    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
    for t in traces:
        print(f"\n{t['score']}/{t['page']} gt#{t['gt_index']} {t['gt_bbox']}")
        print(
            f"  unit={t['unit_size']:.3f} xdist_limit={t['xdist_limit']:.3f} "
            f"combined_fn={t['combined']['is_fn']} late_fn={t['late_raw']['is_fn']}"
        )
        for p in t["combined"]["compatible_predictions"]:
            print(
                "  combined compatible "
                f"pred#{p['pred_index']}={p['pred_bbox']} "
                f"residual(vov={p['residual_pair']['vov']:.3f},"
                f"xdist={p['residual_pair']['xdist']:.3f}) "
                f"assigned_gt#{p['assigned_gt_index']}={p['assigned_gt_bbox']} "
                f"assigned(vov={p['assigned_pair']['vov']:.3f},"
                f"xdist={p['assigned_pair']['xdist']:.3f})"
                if p["assigned_pair"] is not None
                else "  combined compatible unassigned"
            )
        for p in t["late_raw"]["compatible_predictions"]:
            print(
                "  late compatible "
                f"pred#{p['pred_index']}={p['pred_bbox']} "
                f"assigned_gt#{p['assigned_gt_index']}={p['assigned_gt_bbox']}"
            )
    print(f"\nOUTPUT={out}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--residual-report", type=Path, required=True)
    parser.add_argument("--combined-report", type=Path, required=True)
    parser.add_argument("--late-report", type=Path, required=True)
    parser.add_argument("--gt-root", type=Path, required=True)
    parser.add_argument("--staff-units-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
