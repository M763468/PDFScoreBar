#!/usr/bin/env python3
"""Replay retained hybrid consensus for Issue #284 provenance diagnosis.

Read-only retained-artifact diagnostic. It loads the actual retained consensus
inputs, recomputes the current hybrid consensus rule, and compares that replay
with the saved hybrid output. Historical Issue #255 runs used verified/pinned
HOMR on the fresh x4 image (``<hybrid-run>/sr/...``) as the SR consensus input;
post-Issue-274 runs reuse ``current_support/current_homr`` instead. This script
selects the historical verified-SR artifact when it exists and otherwise falls
back to the current-support SR-HOMR path. Remove before PR.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.common import barline_iou  # noqa: E402
from src.common.barline_evaluation import (  # noqa: E402
    center_distance_x,
    is_barline_match,
)
from src.pipeline.steps.hybrid_consensus import (  # noqa: E402
    apply_hybrid_consensus_filter,
    load_json_boxes,
)

IOU_THRESHOLD = 0.5
VOV_THRESHOLD = 0.5
XDIST_THRESHOLD = 12.0


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def remap_path(raw: Any) -> Path | None:
    if not raw:
        return None
    path = Path(str(raw))
    if path.is_file():
        return path.resolve()
    text = str(path)
    if text == "/workspace":
        candidate = ROOT
    elif text.startswith("/workspace/"):
        candidate = ROOT / text[len("/workspace/") :]
    elif not path.is_absolute():
        candidate = ROOT / path
    else:
        candidate = path
    return candidate.resolve() if candidate.is_file() else candidate


def boxes(path: Path) -> list[tuple[int, int, int, int]]:
    return [tuple(int(v) for v in box) for box in load_json_boxes(path)]


def as_lists(values: Iterable[Sequence[int]]) -> list[list[int]]:
    return [[int(v) for v in box] for box in values]


def best_support(
    baseline: Sequence[int], support_boxes: list[tuple[int, int, int, int]]
) -> dict[str, Any]:
    if not support_boxes:
        return {"iou": None, "box": None, "passes_strict_gt_0_5": False}
    ranked = sorted(
        ((barline_iou(baseline, box), box) for box in support_boxes),
        key=lambda item: (item[0], item[1]),
        reverse=True,
    )
    iou, box = ranked[0]
    return {
        "iou": iou,
        "box": list(box),
        "passes_strict_gt_0_5": iou > IOU_THRESHOLD,
    }


def center_anchor_match(box: Sequence[int], gt: Sequence[int]) -> bool:
    return is_barline_match(
        box,
        gt,
        rule_name="center_anchor",
        vov_threshold=VOV_THRESHOLD,
        xdist_threshold=XDIST_THRESHOLD,
    )


def target_rows(
    *,
    gt: tuple[int, int, int, int],
    baseline: list[tuple[int, int, int, int]],
    sr: list[tuple[int, int, int, int]],
    omr: list[tuple[int, int, int, int]],
    saved: list[tuple[int, int, int, int]],
    replay: list[tuple[int, int, int, int]],
) -> list[dict[str, Any]]:
    saved_set = set(saved)
    replay_set = set(replay)
    relevant = [
        box
        for box in baseline
        if center_anchor_match(box, gt) or center_distance_x(box, gt) <= 20.0
    ]
    rows = []
    for box in relevant:
        sr_best = best_support(box, sr)
        omr_best = best_support(box, omr)
        rows.append(
            {
                "baseline_box": list(box),
                "center_anchor_matches_gt": center_anchor_match(box, gt),
                "in_saved_hybrid": box in saved_set,
                "in_replay_hybrid": box in replay_set,
                "best_sr_support": sr_best,
                "best_omr_support": omr_best,
                "replay_keep": bool(
                    sr_best["passes_strict_gt_0_5"] or omr_best["passes_strict_gt_0_5"]
                ),
            }
        )
    rows.sort(key=lambda row: (center_distance_x(row["baseline_box"], gt), row["baseline_box"]))
    return rows


def choose_sr_consensus_source(
    *,
    baseline: Path,
    saved_hybrid: Path,
    current_support_sr: Path | None,
) -> tuple[Path | None, str, Path | None]:
    page = baseline.parent.name
    historical_verified_sr = (
        saved_hybrid.parent.parent
        / "sr"
        / "batch"
        / page
        / f"{page}_detections.json"
    )
    if historical_verified_sr.is_file():
        return historical_verified_sr.resolve(), "verified_profile_on_fresh_x4", current_support_sr
    return current_support_sr, "current_support_sr_homr", historical_verified_sr


def inspect_run(run: dict[str, Any], gt: tuple[int, int, int, int]) -> dict[str, Any]:
    source = run.get("sources") or {}
    baseline = remap_path((source.get("baseline_homr") or {}).get("path"))
    current_support_sr = remap_path((source.get("current_sr_homr") or {}).get("path"))
    omr = remap_path((source.get("current_omr") or {}).get("path"))
    saved_hybrid = remap_path((source.get("hybrid_consensus") or {}).get("path"))
    if baseline is None or saved_hybrid is None:
        raise FileNotFoundError("baseline or saved hybrid path unavailable")

    sr, sr_source_kind, alternate_sr = choose_sr_consensus_source(
        baseline=baseline,
        saved_hybrid=saved_hybrid,
        current_support_sr=current_support_sr,
    )
    paths = {
        "baseline": baseline,
        "sr": sr,
        "omr": omr,
        "saved_hybrid": saved_hybrid,
    }
    missing = [name for name, path in paths.items() if path is None or not path.is_file()]
    if missing:
        raise FileNotFoundError("missing retained source(s): " + ", ".join(missing))

    baseline_boxes = boxes(paths["baseline"])  # type: ignore[arg-type]
    sr_boxes = boxes(paths["sr"])  # type: ignore[arg-type]
    omr_boxes = boxes(paths["omr"])  # type: ignore[arg-type]
    saved_boxes = boxes(paths["saved_hybrid"])  # type: ignore[arg-type]
    replay_boxes = [
        tuple(row)
        for row in apply_hybrid_consensus_filter(
            baseline_boxes=baseline_boxes,
            sr_boxes=sr_boxes,
            omr_boxes=omr_boxes,
            iou_thresh=IOU_THRESHOLD,
        )
    ]

    saved_set = set(saved_boxes)
    replay_set = set(replay_boxes)
    alternate_summary: dict[str, Any] | None = None
    if alternate_sr is not None and alternate_sr.is_file() and alternate_sr.resolve() != paths["sr"]:
        alternate_boxes = boxes(alternate_sr.resolve())
        alternate_replay = [
            tuple(row)
            for row in apply_hybrid_consensus_filter(
                baseline_boxes=baseline_boxes,
                sr_boxes=alternate_boxes,
                omr_boxes=omr_boxes,
                iou_thresh=IOU_THRESHOLD,
            )
        ]
        alternate_set = set(alternate_replay)
        alternate_summary = {
            "path": str(alternate_sr.resolve()),
            "sha256": sha256(alternate_sr.resolve()),
            "count": len(alternate_boxes),
            "replay_hybrid_count": len(alternate_replay),
            "saved_set_exact_equal": alternate_set == saved_set,
            "saved_only_count": len(saved_set - alternate_set),
            "replay_only_count": len(alternate_set - saved_set),
            "target_center_anchor_matches": as_lists(
                box for box in alternate_replay if center_anchor_match(box, gt)
            ),
        }

    return {
        "sr_source_kind": sr_source_kind,
        "paths": {name: str(path) for name, path in paths.items()},
        "sha256": {name: sha256(path) for name, path in paths.items() if path is not None},
        "counts": {
            "baseline": len(baseline_boxes),
            "sr": len(sr_boxes),
            "omr": len(omr_boxes),
            "saved_hybrid": len(saved_boxes),
            "replay_hybrid": len(replay_boxes),
        },
        "saved_vs_replay": {
            "list_exact_equal": saved_boxes == replay_boxes,
            "set_exact_equal": saved_set == replay_set,
            "saved_only_count": len(saved_set - replay_set),
            "replay_only_count": len(replay_set - saved_set),
            "saved_only_boxes": as_lists(sorted(saved_set - replay_set)),
            "replay_only_boxes": as_lists(sorted(replay_set - saved_set)),
        },
        "alternate_sr_source_replay": alternate_summary,
        "target": {
            "gt_box": list(gt),
            "saved_center_anchor_matches": as_lists(
                box for box in saved_boxes if center_anchor_match(box, gt)
            ),
            "replay_center_anchor_matches": as_lists(
                box for box in replay_boxes if center_anchor_match(box, gt)
            ),
            "baseline_support_rows": target_rows(
                gt=gt,
                baseline=baseline_boxes,
                sr=sr_boxes,
                omr=omr_boxes,
                saved=saved_boxes,
                replay=replay_boxes,
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-attribution-json", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("logs/issue284/issue284_hybrid_consensus_replay.json"),
    )
    args = parser.parse_args()

    source_report = load_json(args.source_attribution_json)
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for item in source_report.get("results", []):
        score = str(item.get("score"))
        page = str(item.get("page"))
        gt_index = item.get("gt_index")
        gt = tuple(int(v) for v in item.get("gt_box", []))
        if len(gt) != 4:
            errors.append({"score": score, "page": page, "error": "invalid gt_box"})
            continue
        try:
            accepted = inspect_run(item["accepted"], gt)  # type: ignore[arg-type]
            current = inspect_run(item["current"], gt)  # type: ignore[arg-type]
            results.append(
                {
                    "score": score,
                    "page": page,
                    "gt_index": gt_index,
                    "gt_box": list(gt),
                    "accepted": accepted,
                    "current": current,
                    "classification": {
                        "accepted_sr_source_kind": accepted["sr_source_kind"],
                        "current_sr_source_kind": current["sr_source_kind"],
                        "accepted_replay_matches_saved": accepted["saved_vs_replay"]["set_exact_equal"],
                        "current_replay_matches_saved": current["saved_vs_replay"]["set_exact_equal"],
                    },
                }
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(
                {
                    "score": score,
                    "page": page,
                    "gt_index": gt_index,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )

    unique_page_runs: dict[tuple[str, str], dict[str, Any]] = {}
    for row in results:
        key = (row["score"], row["page"])
        unique_page_runs[key] = dict(row["classification"])

    payload = {
        "schema_version": "issue284.hybrid_consensus_replay.v2",
        "read_only": True,
        "consensus_contract": {"iou_threshold": IOU_THRESHOLD, "comparison": "strict_gt"},
        "historical_source_rule": (
            "Prefer <hybrid-run>/sr/batch/<page>/<page>_detections.json when retained; "
            "otherwise use current_support/current_homr from source attribution."
        ),
        "result_count": len(results),
        "error_count": len(errors),
        "unique_page_runs": [
            {"score": score, "page": page, **classification}
            for (score, page), classification in sorted(unique_page_runs.items())
        ],
        "results": results,
        "errors": errors,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "result_count": len(results),
                "error_count": len(errors),
                "unique_page_runs": payload["unique_page_runs"],
                "targets": [
                    {
                        "score": row["score"],
                        "page": row["page"],
                        "gt_index": row["gt_index"],
                        **row["classification"],
                        "accepted_saved_only": row["accepted"]["saved_vs_replay"]["saved_only_count"],
                        "accepted_replay_only": row["accepted"]["saved_vs_replay"]["replay_only_count"],
                        "current_saved_only": row["current"]["saved_vs_replay"]["saved_only_count"],
                        "current_replay_only": row["current"]["saved_vs_replay"]["replay_only_count"],
                    }
                    for row in results
                ],
                "errors": errors,
                "output": str(args.output),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if results and not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
