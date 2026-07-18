#!/usr/bin/env python3
"""Run the canonical Issue #120 full-68 detector route from fresh upstream artifacts.

The production HybridDetector uses page stems as part of its intermediate
layout.  Canonical full-68 pages repeat stems across scores, so this runner
executes one score at a time, then collects only the freshly generated probe
and CNN artifacts into the canonical evaluator layout.  It never reads a
historical detector or candidate artifact as an input.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from src.pipeline.core.config import load_yaml
from src.pipeline.core.run_ids import build_probe_run_id_from_parts
from tools.issue120.eval_full68_from_intermediates import SCORES, evaluate

DEFAULT_CONFIG = Path("configs/dense_full_pipeline.yaml")
DEFAULT_IMAGE_ROOT = Path("data/evaluation2/images")
DEFAULT_GT_ROOT = Path("data/evaluation2/annotations")


def slugify(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def selected_scores(scores: list[str] | None) -> list[str]:
    """Validate an optional score subset while preserving canonical order."""
    if scores is None:
        return list(SCORES)
    requested = set(scores)
    unknown = sorted(requested - set(SCORES))
    if unknown:
        raise ValueError("Unknown canonical score(s): " + ", ".join(unknown))
    return [score for score in SCORES if score in requested]


def score_images(image_root: Path, score: str) -> list[Path]:
    images = [image_root / score / f"{page}.png" for page in SCORES[score]]
    missing = [str(path) for path in images if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing canonical images:\n" + "\n".join(missing))
    return images


def _copy_page_artifacts(
    *,
    probe_output_root: Path,
    score: str,
    page: str,
    destination_root: Path,
) -> dict[str, str]:
    source_dir = probe_output_root / build_probe_run_id_from_parts(score, page)
    destination_dir = destination_root / score / page
    destination_dir.mkdir(parents=True, exist_ok=True)
    copied: dict[str, str] = {"score": score, "page": page}
    for filename in ("pipeline2_no_peak_candidates.json", "pipeline2_no_peak_scored.json"):
        source = source_dir / filename
        if not source.is_file():
            raise FileNotFoundError(f"Missing fresh {filename}: {source}")
        destination = destination_dir / filename
        shutil.copy2(source, destination)
        copied[f"{filename}_source"] = str(source)
        copied[f"{filename}_destination"] = str(destination)
    return copied


def _load_rescue_summary(probe_output_root: Path) -> dict[str, Any] | None:
    path = probe_output_root / "aligned_expansion_rescue_summary.json"
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.output_root.exists():
        raise FileExistsError(
            f"Refusing to reuse existing output root: {args.output_root}. "
            "Choose a new output directory so fresh artifact provenance remains unambiguous."
        )
    config = load_yaml(args.config)
    selected = selected_scores(args.scores)
    args.output_root.mkdir(parents=True)
    fresh_results_root = args.output_root / "stage_e_full_pipeline"
    fresh_results_root.mkdir()

    provenance: dict[str, Any] = {
        "schema_version": "issue245.fresh_stage_e_full68.v1",
        "status": "running",
        "config": str(args.config),
        "image_root": str(args.image_root),
        "gt_root": str(args.gt_root),
        "selected_scores": selected,
        "expected_pages": sum(len(SCORES[score]) for score in selected),
        "historical_detector_candidate_artifact_used": False,
        "fresh_route": "HOMR + SR + official OMR-DLN -> hybrid -> probe -> current CNN",
        "score_runs": [],
        "copied_page_artifacts": [],
        "rescue_summaries": [],
    }
    provenance_path = args.output_root / "fresh_stage_e_full68_provenance.json"

    # Import lazily so parser/unit tests remain host-lightweight.
    from src.pipeline.detection.orchestrator import DetectorOrchestrator

    for score in selected:
        score_config = copy.deepcopy(config)
        detection = score_config.setdefault("detection", {})
        if detection.get("precomputed_probe_candidates_root"):
            raise ValueError("Fresh runner rejects detection.precomputed_probe_candidates_root")
        detection["hybrid_output_root"] = str(args.output_root / "hybrid_runs")
        detection["probe_score_name"] = score
        run_id = f"issue245_fresh_{slugify(score)}"
        run_dir = args.output_root / "runs" / slugify(score)
        images = score_images(args.image_root, score)
        detector = DetectorOrchestrator(
            config=score_config,
            images=images,
            run_id=run_id,
            run_dir=run_dir,
            dry_run=False,
        )
        result = detector.run_detection()
        probe_output_root = Path(result["probe_output_dir"])
        copied = [
            _copy_page_artifacts(
                probe_output_root=probe_output_root,
                score=score,
                page=page,
                destination_root=fresh_results_root,
            )
            for page in SCORES[score]
        ]
        provenance["score_runs"].append(
            {
                "score": score,
                "run_id": run_id,
                "run_dir": str(run_dir),
                "hybrid_output_dir": str(result["hybrid_output_dir"]),
                "probe_output_dir": str(probe_output_root),
                "page_count": len(images),
            }
        )
        provenance["copied_page_artifacts"].extend(copied)
        summary = _load_rescue_summary(probe_output_root)
        if summary is not None:
            provenance["rescue_summaries"].append(summary)
        provenance_path.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")

    if len(selected) == len(SCORES):
        evaluation_root = args.output_root / "eval_detector"
        contract = evaluate(
            SimpleNamespace(
                results_dir=str(fresh_results_root),
                gt_root=str(args.gt_root),
                output_dir=str(evaluation_root),
                scored_file="pipeline2_no_peak_scored.json",
                candidates_file="pipeline2_no_peak_candidates.json",
                score_threshold=float(args.score_threshold),
                rule_name="center_anchor",
                vov_threshold=0.5,
                xdist_threshold=float(args.xdist_threshold),
                allow_partial=False,
                measure_summary_json=None,
            )
        )
        provenance["evaluation"] = {
            "output_dir": str(evaluation_root),
            "detector_summary": vars(contract.detector_summary),
        }
    provenance["status"] = "completed"
    provenance_path.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    return provenance


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--image-root", type=Path, default=DEFAULT_IMAGE_ROOT)
    parser.add_argument("--gt-root", type=Path, default=DEFAULT_GT_ROOT)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--scores", nargs="*", help="Optional canonical score subset for focused gates."
    )
    parser.add_argument("--score-threshold", type=float, default=0.1)
    parser.add_argument("--xdist-threshold", type=float, default=12.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    provenance = run(args)
    print(f"Fresh pages: {len(provenance['copied_page_artifacts'])}")
    print(f"Provenance: {args.output_root / 'fresh_stage_e_full68_provenance.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
