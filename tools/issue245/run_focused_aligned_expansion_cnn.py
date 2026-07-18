#!/usr/bin/env python3
"""Score Issue #245 aligned-expansion candidate variants with the production CNN."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable, Sequence

from src.common import barline_iou
from src.pipeline.core.run_ids import build_probe_run_id
from src.pipeline.steps.cnn_scoring import run_cnn_scoring_batch

Box = tuple[int, int, int, int]
DEFAULT_MODEL = Path(
    "logs/cnn_barline_classification/issue44_iter7_final_rescue_v1/cnn_classifier_best.pth"
)
DEFAULT_REPORT = Path(
    "logs/issue245_accuracy_first_stage_e/aligned_expansion_candidate_probe/"
    "aligned_expansion_candidate_probe_report.json"
)
DEFAULT_OUTPUT = Path("logs/issue245_accuracy_first_stage_e/aligned_expansion_cnn")


def _box(value: Sequence[Any]) -> Box:
    return tuple(int(round(float(item))) for item in value[:4])  # type: ignore[return-value]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _score_for_box(records: Iterable[dict[str, Any]], box: Box) -> float | None:
    for record in records:
        if _box(record["bbox"]) == box:
            return float(record["score"])
    return None


def _best_match(reference: Box, boxes: Iterable[Box]) -> dict[str, Any]:
    ranked = sorted(
        ((box, float(barline_iou(reference, box))) for box in boxes),
        key=lambda item: (-item[1], item[0]),
    )
    box, iou = ranked[0] if ranked else (None, 0.0)
    return {"bbox": list(box) if box is not None else None, "iou": iou, "accepted": iou > 0.5}


def _page_image(main_repo: Path, score: str, page: str) -> Path:
    return main_repo / "data" / "evaluation2" / "images" / score / f"{page}.png"


def _stage_variant(
    *, candidate_path: Path, output_root: Path, score: str, page: str, variant: str
) -> Path:
    run_dir = (
        output_root
        / score
        / page
        / variant
        / build_probe_run_id(_page_image(Path("."), score, page), score_name=score)
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "pipeline2_no_peak_candidates.json").write_text(
        candidate_path.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return run_dir


def _target_summary(
    *, target: dict[str, Any], scored: list[dict[str, Any]], threshold: float
) -> dict[str, Any]:
    reference = _box(target["reference"])
    boxes = [_box(item["bbox"]) for item in scored]
    match = _best_match(reference, boxes)
    box = _box(match["bbox"]) if match["bbox"] is not None else None
    score = _score_for_box(scored, box) if box is not None else None
    return {
        "reference": list(reference),
        "best_candidate": match["bbox"],
        "iou": match["iou"],
        "cnn_score": score,
        "accepted": bool(match["accepted"] and score is not None and score >= threshold),
    }


def build_report(
    *,
    main_repo: Path,
    candidate_report: Path,
    output_root: Path,
    model_path: Path,
    threshold: float,
) -> dict[str, Any]:
    probe_report = _load_json(candidate_report)
    variants = ("current_final", "aligned_trimmed_additive", "aligned_raw_additive")
    pages: list[dict[str, Any]] = []
    scored_by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = {}

    for page_record in probe_report["pages"]:
        score, page = str(page_record["score"]), str(page_record["page"])
        image = _page_image(main_repo, score, page)
        if not image.is_file():
            raise FileNotFoundError(image)
        mixed_hybrid = Path(page_record["mixed_hybrid"])
        for variant in variants:
            candidate_path = Path(page_record["variants"][variant]["output"])
            run_dir = _stage_variant(
                candidate_path=candidate_path,
                output_root=output_root,
                score=score,
                page=page,
                variant=variant,
            )
            processed = run_cnn_scoring_batch(
                probe_output_root=run_dir.parent,
                images=[image],
                model_path=model_path,
                threshold=threshold,
                score_name=score,
                bands_from=mixed_hybrid.parent.parent,
                crop_recenter_on_bbox_ink=True,
                apply_nms_enabled=False,
            )
            if processed != 1:
                raise RuntimeError(
                    f"CNN scoring processed {processed}/1 for {score}/{page}/{variant}"
                )
            scored_path = run_dir / "pipeline2_no_peak_scored.json"
            scored = _load_json(scored_path)
            if not isinstance(scored, list):
                raise ValueError(f"Invalid scored payload: {scored_path}")
            scored_by_key[(score, page, variant)] = scored
        pages.append({"score": score, "page": page, "mixed_hybrid": str(mixed_hybrid)})

    targets = []
    for target in probe_report["targets"]:
        score, page = str(target["score"]), str(target["page"])
        summaries = {
            variant: _target_summary(
                target=target,
                scored=scored_by_key[(score, page, variant)],
                threshold=threshold,
            )
            for variant in variants
        }
        targets.append({"score": score, "page": page, "variants": summaries})

    return {
        "schema_version": "issue245.focused_aligned_expansion_cnn.v1",
        "candidate_probe_report": str(candidate_report),
        "model_path": str(model_path),
        "threshold": threshold,
        "crop_recenter_on_bbox_ink": True,
        "cnn_apply_nms": False,
        "pages": pages,
        "targets": targets,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main-repo", type=Path, required=True)
    parser.add_argument("--candidate-report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--threshold", type=float, default=0.1)
    args = parser.parse_args()

    main_repo = args.main_repo.resolve()
    output_root = args.output_root.resolve()
    if output_root.exists():
        raise FileExistsError(f"Output already exists: {output_root}")
    output_root.mkdir(parents=True)
    report = build_report(
        main_repo=main_repo,
        candidate_report=args.candidate_report.resolve(),
        output_root=output_root,
        model_path=(main_repo / args.model_path).resolve(),
        threshold=args.threshold,
    )
    report_path = output_root / "focused_aligned_expansion_cnn_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
