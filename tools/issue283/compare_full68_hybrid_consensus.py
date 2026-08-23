"""Compare retained vs optimized current-HOMR impact on hybrid consensus.

This is a CPU-only diagnostic for Issue #283. The two-HOMR detector keeps
pinned-original HOMR and current OMR fixed, and uses current x4 HOMR only as a
support source for pinned baseline boxes. Therefore current-HOMR bbox jitter can
only affect downstream detection when it changes which pinned boxes survive the
IoU consensus threshold.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.common import barline_iou
from src.pipeline.steps.hybrid_consensus import (
    apply_hybrid_consensus_filter,
    load_json_boxes,
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _validation_path(raw: Any, validation_root: Path) -> Path:
    path = Path(str(raw))
    if path.exists():
        return path.resolve()
    try:
        relative = path.relative_to("/issue283-output")
    except ValueError:
        return path.resolve()
    return (validation_root / relative).resolve()


def _hybrid_score_root(baseline_result: Path) -> Path:
    current_support = next(
        (parent for parent in baseline_result.parents if parent.name == "current_support"),
        None,
    )
    if current_support is None:
        raise ValueError(f"Cannot locate current_support ancestor: {baseline_result}")
    return current_support.parent


def _max_iou(box: tuple[int, int, int, int], references: list[tuple[int, int, int, int]]) -> float:
    return max((barline_iou(box, ref) for ref in references), default=0.0)


def _decision_delta(
    box: tuple[int, int, int, int],
    *,
    old_sr: list[tuple[int, int, int, int]],
    new_sr: list[tuple[int, int, int, int]],
    omr: list[tuple[int, int, int, int]],
) -> dict[str, Any]:
    return {
        "baseline_box": list(box),
        "old_sr_max_iou": _max_iou(box, old_sr),
        "new_sr_max_iou": _max_iou(box, new_sr),
        "omr_max_iou": _max_iou(box, omr),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    validation_root = args.validation_root.resolve()
    output = (args.output or validation_root / "hybrid_consensus_comparison.json").resolve()
    page_results = _load_json(validation_root / "page_results.json")
    preflight = _load_json(validation_root / "preflight.json")
    preflight_by_key = {(row["score"], row["page"]): row for row in preflight}

    rows: list[dict[str, Any]] = []
    consensus_changed: list[str] = []
    current_detection_changed = 0

    for page_result in page_results:
        score = str(page_result["score"])
        page = str(page_result["page"])
        key = (score, page)
        artifact = page_result["artifact_comparison"]["current_sr_detection"]
        detection_exact = bool(artifact["equal"])
        if detection_exact:
            rows.append(
                {
                    "score": score,
                    "page": page,
                    "current_detection_exact": True,
                    "hybrid_consensus_exact": True,
                    "reason": "current detection is byte-identical",
                }
            )
            continue

        current_detection_changed += 1
        entry = preflight_by_key[key]
        baseline_result = Path(str(entry["baseline_result"])).resolve()
        baseline_payload = _load_json(baseline_result)
        old_sr_path = Path(str(baseline_payload["current_sr_detection"])).resolve()

        score_root = _hybrid_score_root(baseline_result)
        baseline_path = score_root / "baseline" / "batch" / page / f"{page}_detections.json"
        omr_path = baseline_result.parent / "omr_sr" / page / "predictions.json"
        retained_hybrid_path = score_root / "hybrid_results" / f"{page}_hybrid.json"

        replay_result_path = validation_root / "pages" / score / page / "replay" / "result.json"
        replay_payload = _load_json(replay_result_path)
        new_sr_path = _validation_path(replay_payload["current_sr_detection"], validation_root)

        required = (
            baseline_path,
            old_sr_path,
            new_sr_path,
            omr_path,
            retained_hybrid_path,
        )
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise FileNotFoundError("Missing consensus inputs: " + ", ".join(missing))

        baseline_boxes = load_json_boxes(baseline_path)
        old_sr_boxes = load_json_boxes(old_sr_path)
        new_sr_boxes = load_json_boxes(new_sr_path)
        omr_boxes = load_json_boxes(omr_path)
        retained_hybrid = load_json_boxes(retained_hybrid_path)
        recomputed = apply_hybrid_consensus_filter(
            baseline_boxes=baseline_boxes,
            sr_boxes=new_sr_boxes,
            omr_boxes=omr_boxes,
        )
        recomputed_boxes = [tuple(box) for box in recomputed]
        exact = recomputed_boxes == retained_hybrid

        retained_set = set(retained_hybrid)
        recomputed_set = set(recomputed_boxes)
        removed = sorted(retained_set - recomputed_set)
        added = sorted(recomputed_set - retained_set)
        page_id = f"{score}/{page}"
        if not exact:
            consensus_changed.append(page_id)

        rows.append(
            {
                "score": score,
                "page": page,
                "current_detection_exact": False,
                "old_current_detection_count": len(old_sr_boxes),
                "new_current_detection_count": len(new_sr_boxes),
                "retained_hybrid_count": len(retained_hybrid),
                "recomputed_hybrid_count": len(recomputed_boxes),
                "hybrid_consensus_exact": exact,
                "removed_baseline_boxes": [
                    _decision_delta(box, old_sr=old_sr_boxes, new_sr=new_sr_boxes, omr=omr_boxes)
                    for box in removed
                ],
                "added_baseline_boxes": [
                    _decision_delta(box, old_sr=old_sr_boxes, new_sr=new_sr_boxes, omr=omr_boxes)
                    for box in added
                ],
            }
        )

    summary = {
        "schema_version": "issue283.full68_hybrid_consensus_comparison.v1",
        "pages": len(rows),
        "current_detection_changed_pages": current_detection_changed,
        "hybrid_consensus_changed_pages": len(consensus_changed),
        "hybrid_consensus_exact_pages": len(rows) - len(consensus_changed),
        "changed_pages": consensus_changed,
        "rows": rows,
    }
    _write_json(output, summary)
    print(json.dumps({key: value for key, value in summary.items() if key != "rows"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
