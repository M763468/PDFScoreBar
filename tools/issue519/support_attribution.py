#!/usr/bin/env python3
"""Issue #519: attribute retained hybrid-consensus support to x4 HOMR vs OMR-DLN.

Read-only analysis of a retained full68 run.  For every canonical page it reloads the
retained baseline HOMR, current x4 HOMR and OMR-DLN source files with the production
loader/consensus implementation and:

* verifies that recomputed consensus equals the retained ``*_hybrid.json`` (harness check);
* recomputes the consensus with OMR-DLN support removed (``omr_boxes=[]``);
* classifies every baseline box as supported by SR only, OMR only, both, or neither.

No production code path, threshold or model is changed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.common import barline_iou  # noqa: E402
from src.pipeline.steps.hybrid_consensus import (  # noqa: E402
    apply_hybrid_consensus_filter,
    load_json_boxes,
)
from tools.issue120.eval_full68_from_intermediates import SCORES  # noqa: E402

IOU = 0.5  # production default of apply_hybrid_consensus_filter


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def page_sources(run_root: Path, score: str, page: str) -> dict[str, Path]:
    hybrid = next((run_root / score / "hybrid_output").iterdir())
    support = json.loads(
        (hybrid / "current_support" / score / page / "result.json").read_text()
    )
    return {
        "baseline": hybrid / "baseline" / "batch" / page / f"{page}_detections.json",
        "sr": Path(str(support["current_sr_detection"])),
        "omr": Path(str(support["current_omr"])),
        "hybrid": hybrid / "hybrid_results" / f"{page}_hybrid.json",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True,
                        help="checkout that holds retained logs (paths are relative to it)")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    totals = {"pages": 0, "baseline": 0, "hybrid": 0, "hybrid_no_omr": 0,
              "sr_only": 0, "omr_only": 0, "both": 0, "neither": 0,
              "omr_boxes": 0, "harness_mismatch_pages": 0}
    pages = []
    for score, page_list in SCORES.items():
        for page in page_list:
            src = page_sources(args.run_root, score, page)
            src = {k: (v if v.is_absolute() else args.artifact_root / v) for k, v in src.items()}
            strict = True  # maintained_original profile uses strict loading
            base = load_json_boxes(src["baseline"], strict=strict)
            sr = load_json_boxes(src["sr"], strict=strict)
            omr = load_json_boxes(src["omr"], strict=strict)
            retained = json.loads(src["hybrid"].read_text())
            recomputed = apply_hybrid_consensus_filter(
                baseline_boxes=base, sr_boxes=sr, omr_boxes=omr)
            no_omr = apply_hybrid_consensus_filter(
                baseline_boxes=base, sr_boxes=sr, omr_boxes=[])
            classes = []
            for box in base:
                s = any(barline_iou(box, r) > IOU for r in sr)
                o = any(barline_iou(box, r) > IOU for r in omr)
                cls = "both" if s and o else "sr_only" if s else "omr_only" if o else "neither"
                classes.append(cls)
                totals[cls] += 1
            match = recomputed == retained
            totals["pages"] += 1
            totals["baseline"] += len(base)
            totals["hybrid"] += len(recomputed)
            totals["hybrid_no_omr"] += len(no_omr)
            totals["omr_boxes"] += len(omr)
            totals["harness_mismatch_pages"] += 0 if match else 1
            pages.append({
                "score": score, "page": page,
                "baseline": len(base), "sr": len(sr), "omr": len(omr),
                "hybrid_retained": len(retained), "hybrid_recomputed_match": match,
                "hybrid_no_omr": len(no_omr),
                "omr_only_boxes": [list(b) for b, c in zip(base, classes) if c == "omr_only"],
                "input_sha256": {k: sha(v) for k, v in src.items()},
            })
    report = {
        "schema_version": "issue519.support_attribution.v1",
        "run_root": str(args.run_root), "iou_threshold": IOU,
        "totals": totals, "pages": pages,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(totals, indent=1))
    omr_pages = [(p["score"], p["page"], len(p["omr_only_boxes"]))
                 for p in pages if p["omr_only_boxes"]]
    print("pages_with_omr_only_support", len(omr_pages))
    for row in omr_pages:
        print(*row)
    return 0 if totals["harness_mismatch_pages"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
