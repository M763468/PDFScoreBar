#!/usr/bin/env python3
"""Issue #522: Full68 x4 staff-piece support replayed from retained producer outputs.

``x4_staff_piece`` uses the production consensus (``apply_x4_staff_piece_consensus_filter``
with staff regions from the baseline staff mask) and x4-only staff-stroke seeding.
Production code, config, thresholds and models are used unchanged.  The retained
producer outputs come from the #409 fresh Full68 run (same images and runtime image as
#416); dense route, staff-stroke normalization and CUDA CNN scoring are regenerated.
Outputs are compared with the accepted #416 bytes (the OMR-DLN control/no_omr replays
that reproduce those bytes live in the evaluation-only #519 tools, PR #520).

Run inside the #409/#416 runtime image with the manager checkout at /workspace and this
worktree at /workspace/.worktrees/issue522.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from collections import Counter
from pathlib import Path

CODE = Path(__file__).resolve().parents[2]
ROOT = Path("/workspace")
sys.path.insert(0, str(CODE))
os.chdir(ROOT)

import cv2  # noqa: E402
import torch  # noqa: E402
import yaml  # noqa: E402

from src.common.barline_evaluation import greedy_barline_match  # noqa: E402
from src.measure_numbering.pipeline import MeasureNumberingPipeline  # noqa: E402
from src.measure_numbering.types import Score, score_to_dict  # noqa: E402
from src.pipeline.core import build_probe_run_id  # noqa: E402
from src.pipeline.detection.config import get_probe_x_domain_kwargs  # noqa: E402
from src.pipeline.detection.dense_orchestrator import DetectorOrchestrator  # noqa: E402
from src.pipeline.detector_routes.dense_full_pipeline import (  # noqa: E402
    reconstruct_dense_full_pipeline_route,
)
from src.pipeline.steps.hybrid_consensus import (  # noqa: E402
    apply_x4_staff_piece_consensus_filter,
    load_json_boxes,
)
from src.pipeline.steps.staff_strokes import prepare_staff_stroke_candidates  # noqa: E402
from tools.issue120 import eval_full68_from_intermediates as ev  # noqa: E402

SOURCE_RUN = ROOT / "logs/issue409/full68-numbering-20261009/candidate"
ACCEPTED_416 = ROOT / "logs/issue416/review-422-round3-20261016/candidate"
ACCEPTED_TOTALS = dict(gt=3567, pred=3681, tp=3560, fp=0, fn=7, soft=121)
ACCEPTED_MEASURES = 3287


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def link(path: Path, target: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(os.path.relpath(target, path.parent), target_is_directory=target.is_dir())


def staff_regions(score: str, page: str, retained: Path):
    """Staff regions through the production helpers used by ``ProfileHybridDetector.run``."""
    from src.pipeline.detection.profile_sources import _baseline_staff_mask
    from src.pipeline.steps.hybrid_consensus import staff_regions_from_mask

    image = ROOT / "data/evaluation2/images" / score / f"{page}.png"
    return staff_regions_from_mask(
        _baseline_staff_mask(retained / "baseline/batch" / page, page), image
    )


def build_variant_hybrid(variant: str, score: str, retained: Path, out: Path, pages) -> dict:
    """Materialize the hybrid_output tree the x4_staff_piece variant consumes."""
    link(out / "baseline", retained / "baseline")
    audit = {}
    for page in pages:
        support = read(retained / "current_support" / score / page / "result.json")
        base = load_json_boxes(retained / "baseline/batch" / page / f"{page}_detections.json")
        sr = load_json_boxes(Path(support["current_sr_detection"]))
        hybrid = apply_x4_staff_piece_consensus_filter(
            baseline_boxes=base, sr_boxes=sr, staves=staff_regions(score, page, retained)
        )
        # The production staff-stroke step reads only x4 support fields.
        support = {k: v for k, v in support.items() if "omr" not in k.lower() or "homr" in k}
        write(out / "hybrid_results" / f"{page}_hybrid.json", hybrid)
        write(out / "current_support" / score / page / "result.json", support)
        audit[page] = {"hybrid": len(hybrid)}
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=("x4_staff_piece",), required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists():
        raise SystemExit(f"refusing to reuse existing output {out}")

    assert torch.cuda.is_available(), "CUDA required; refusing CPU fallback"
    torch.set_num_threads(4)
    config = yaml.safe_load((CODE / "configs/dense_full_pipeline.yaml").read_text())
    det_cfg = config["detection"]
    model = Path(
        "/opt/pdfscore-assets/model-cache/barline_cnn/issue296-d27-v1/cnn_classifier_epoch_9.pth"
    )
    assert sha(model) == read(CODE / "models/barline_cnn/manifest.json")["sha256"]
    write(
        out / "provenance.json",
        dict(
            variant=args.variant,
            code_root=str(CODE),
            runner_sha256=sha(__file__),
            config_sha256=sha(CODE / "configs/dense_full_pipeline.yaml"),
            cnn_model_sha256=sha(model),
            cnn_threshold=det_cfg["cnn_threshold"],
            source_run=str(SOURCE_RUN),
            accepted_reference=str(ACCEPTED_416),
            device=torch.cuda.get_device_name(),
            torch=torch.__version__,
            cuda=torch.version.cuda,
            python=sys.version,
            image_id=os.environ.get("PDFSCORE_DOCKER_IMAGE_ID"),
            source_commit=os.environ.get("PDFSCORE_HOST_SOURCE_COMMIT"),
        ),
    )

    source = read(SOURCE_RUN / "variant_summary.json")
    units = ev.load_page_staff_units(ROOT / "data/evaluation2/staff_units.json")
    pipe = MeasureNumberingPipeline()
    rows = []
    hybrid_audit = {}
    for item in source["scores"]:
        name = item["score"]
        retained = ROOT / Path(item["hybrid_run"]).relative_to("/workspace")
        hybrid = out / "hybrid" / name
        hybrid_audit[name] = build_variant_hybrid(
            args.variant, name, retained, hybrid, item["pages"]
        )
        images = [Path("data/evaluation2/images") / name / f"{p}.png" for p in item["pages"]]
        detector = DetectorOrchestrator(
            config=config,
            images=images,
            run_id="issue519",
            run_dir=out / "runs" / name,
            dry_run=False,
        )
        detector.hybrid_output_dir = hybrid
        # Mirror DetectorOrchestrator._run_dense_route, snapshotting rescue output
        # before staff-stroke normalization so it can be compared with #409 bytes.
        inventory, exclude = detector._write_dense_inventory()
        route_root = detector.run_dir / "intermediate" / "dense_full_pipeline_route"
        route = reconstruct_dense_full_pipeline_route(
            inventory=inventory,
            exclude=exclude,
            route_root=route_root,
            expected_pages=len(images),
            probe_x_domain_kwargs=get_probe_x_domain_kwargs(det_cfg),
            collect_probe_stats=bool(det_cfg.get("probe_scan_collect_stats", False)),
        )
        shutil.copytree(route.probe_rescue_root, out / "rescue_before_strokes" / name)
        detector._dense_route = route
        detector._staff_stroke_units = prepare_staff_stroke_candidates(
            inventory=inventory, hybrid_root=hybrid, probe_root=route.probe_rescue_root
        )
        detector.probe_output_dir = route.probe_rescue_root
        detector._run_cnn_scoring()

        pipeline_run = ROOT / Path(item["pipeline_run"]).relative_to("/workspace")
        retained_rescue = (
            pipeline_run / "intermediate/dense_full_pipeline_route/"
            "dense_candidate_reconstruction/probe_rescue_candidates"
        )
        for record in read(inventory)["records"]:
            image = Path(record["image"])
            page = record["page"]
            rid = build_probe_run_id(image)
            folder = route.probe_rescue_root / rid
            predictions = read(folder / "pipeline2_no_peak_filtered_cnn.json")
            gt = ev.boxes_from_gt(
                read(ROOT / f"data/evaluation2/annotations/{name}/{page}/boxes_sorted.json")
            )
            match = greedy_barline_match(
                predictions,
                gt,
                rule_name="center_anchor",
                vov_threshold=0.5,
                unit_size=ev.require_page_staff_unit(units, name, page).unit_size,
                xdist_unit_ratio=0.5,
            )
            counts = dict(
                gt=len(gt),
                pred=len(predictions),
                tp=len(match.matches),
                fp=len(match.false_positive_indices),
                fn=len(match.false_negative_indices),
                soft=len(match.soft_matches),
            )
            pixels = cv2.imread(str(image))
            height, width = pixels.shape[:2]
            numbered = pipe.process_page(
                predictions,
                Path(record["staff_mask"]),
                (width, height),
                page_number=int(page[-3:]),
                image=pixels,
            )
            score = Score()
            score.pages.append(numbered)
            pipe.numberer.number_score(score)
            base = score_to_dict(score)
            accepted_pred = read(ACCEPTED_416 / name / page / "predictions.json")
            accepted_base = read(ACCEPTED_416 / name / page / "numbering_base.json")
            rescue_now = read(
                out / "rescue_before_strokes" / name / rid / "pipeline2_no_peak_candidates.json"
            )
            rescue_409 = read(
                retained_rescue / f"eval2_{name}_{page}" / "pipeline2_no_peak_candidates.json"
            )
            rows.append(
                dict(
                    score=name,
                    page=page,
                    metrics=counts,
                    fn_gt=[gt[i] for i in match.false_negative_indices],
                    fp_pred=[predictions[i] for i in match.false_positive_indices],
                    counts=[len(s["measures"]) for s in base["pages"][0]["systems"]],
                    predictions_equal_accepted=sorted(predictions) == sorted(accepted_pred),
                    numbering_base_equal_accepted=base == accepted_base,
                    rescue_equal_409=sorted(map(tuple, rescue_now))
                    == sorted(map(tuple, rescue_409)),
                    hybrid=hybrid_audit[name][page],
                )
            )
            write(out / "candidate" / name / page / "predictions.json", predictions)
            write(out / "candidate" / name / page / "numbering_base.json", base)
            print(
                args.variant,
                name,
                page,
                counts,
                "pred_eq" if rows[-1]["predictions_equal_accepted"] else "PRED_DIFF",
                "base_eq" if rows[-1]["numbering_base_equal_accepted"] else "BASE_DIFF",
                flush=True,
            )

    totals = Counter()
    for row in rows:
        totals.update(row["metrics"])
    measures = sum(sum(r["counts"]) for r in rows)
    summary = dict(
        variant=args.variant,
        pages=len(rows),
        totals=dict(totals),
        physical_measures=measures,
        pages_predictions_equal_accepted=sum(r["predictions_equal_accepted"] for r in rows),
        pages_numbering_base_equal_accepted=sum(r["numbering_base_equal_accepted"] for r in rows),
        pages_rescue_equal_409=sum(r["rescue_equal_409"] for r in rows),
        accepted_totals=ACCEPTED_TOTALS,
        accepted_measures=ACCEPTED_MEASURES,
    )
    write(out / "report.json", dict(summary=summary, pages=rows))
    print(json.dumps(summary, indent=1), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
