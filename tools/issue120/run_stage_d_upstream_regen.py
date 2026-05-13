#!/usr/bin/env python3
"""Regenerate Stage-D upstream HOMR/SR/OMR artifacts for Issue #120.

This tool runs the current upstream hybrid detector score-by-score and composes a
`bands_from` directory that can be passed to the Stage-C Issue53 probe-rescue
verifier.

Why score-by-score?
    The current HybridDetector writes some outputs by page stem, for example
    `page_001`.  The canonical Issue #120 full-68 set contains repeated stems
    across different scores, so a single all-score HybridDetector run can collide.
    Running one score at a time keeps the upstream output unambiguous.

The generated outputs are intentionally written under ignored `logs/` paths.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline.detection.hybrid import HybridDetector  # noqa: E402
from tools.issue120.eval_full68_from_intermediates import SCORES  # noqa: E402


SOURCE_NAMES = ("hybrid", "baseline", "sr", "omr_sr")


@dataclass(frozen=True)
class PageComposition:
    score: str
    page: str
    source_name: str | None
    source_path: str | None
    output_dir: str
    status: str
    box_count: int | None


@dataclass(frozen=True)
class ScoreRun:
    score: str
    run_id: str
    hybrid_output_dir: str
    image_count: int
    status: str


def slugify(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def load_json_boxes(path: Path) -> list[Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if isinstance(payload, dict) and isinstance(payload.get("predictions"), list):
        return payload["predictions"]
    if not isinstance(payload, list):
        return None
    return payload


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def score_images(image_root: Path, score: str) -> list[Path]:
    images: list[Path] = []
    missing: list[str] = []
    for page in SCORES[score]:
        path = image_root / score / f"{page}.png"
        if path.exists():
            images.append(path)
        else:
            missing.append(str(path))
    if missing:
        raise SystemExit("Missing Stage-D input images:\n" + "\n".join(missing))
    return images


def build_det_cfg(args: argparse.Namespace, hybrid_output_root: Path) -> dict[str, Any]:
    return {
        "hybrid_output_root": str(hybrid_output_root),
        "enable_sr": not args.disable_sr,
        "sr_scale": args.sr_scale,
        "sr_tile": args.sr_tile,
        "sr_tile_pad": args.sr_tile_pad,
        "sr_fp32": args.sr_fp32,
        "enable_debug": args.enable_debug,
        "enable_cache": args.enable_cache,
        "write_staff_positions": args.write_staff_positions,
        "barline_min_height_factor": args.barline_min_height_factor,
        "barline_max_width_factor": args.barline_max_width_factor,
    }


def run_hybrid_for_score(
    *,
    args: argparse.Namespace,
    score: str,
    hybrid_output_root: Path,
) -> ScoreRun:
    run_id = f"{args.run_id_prefix}_{slugify(score)}"
    hybrid_output_dir = hybrid_output_root / run_id
    images = score_images(args.image_root, score)

    if args.dry_run:
        return ScoreRun(
            score=score,
            run_id=run_id,
            hybrid_output_dir=str(hybrid_output_dir),
            image_count=len(images),
            status="dry_run",
        )

    if args.compose_only:
        return ScoreRun(
            score=score,
            run_id=run_id,
            hybrid_output_dir=str(hybrid_output_dir),
            image_count=len(images),
            status="compose_only",
        )

    detector = HybridDetector(
        det_cfg=build_det_cfg(args, hybrid_output_root),
        images=images,
        run_id=run_id,
        project_root=PROJECT_ROOT,
        dry_run=False,
        skip_existing=args.skip_existing,
    )
    detector.run()
    return ScoreRun(
        score=score,
        run_id=run_id,
        hybrid_output_dir=str(hybrid_output_dir),
        image_count=len(images),
        status="completed",
    )


def source_path_for(run_dir: Path, source_name: str, page: str) -> Path:
    source_paths = {
        "hybrid": run_dir / "hybrid_results" / f"{page}_hybrid.json",
        "baseline": run_dir / "baseline" / "batch" / page / f"{page}_detections.json",
        "sr": run_dir / "sr" / "batch" / page / f"{page}_detections.json",
        "omr_sr": run_dir / "omr_sr" / page / "predictions.json",
    }
    return source_paths[source_name]


def ordered_sources(compose_source: str) -> list[str]:
    if compose_source == "first_available":
        return ["hybrid", "baseline", "sr", "omr_sr"]
    return [compose_source]


def compose_bands_for_score(
    *,
    score: str,
    run_id: str,
    hybrid_output_root: Path,
    bands_output_dir: Path,
    compose_source: str,
) -> list[PageComposition]:
    run_dir = hybrid_output_root / run_id
    rows: list[PageComposition] = []
    for page in SCORES[score]:
        payload: list[Any] | None = None
        source_path: Path | None = None
        source_name: str | None = None
        for candidate_source_name in ordered_sources(compose_source):
            candidate = source_path_for(run_dir, candidate_source_name, page)
            payload = load_json_boxes(candidate)
            if payload is not None:
                source_path = candidate
                source_name = candidate_source_name
                break

        output_dir = bands_output_dir / score / page
        if payload is None or source_path is None:
            rows.append(
                PageComposition(
                    score=score,
                    page=page,
                    source_name=None,
                    source_path=None,
                    output_dir=str(output_dir),
                    status="missing_source",
                    box_count=None,
                )
            )
            continue

        # The Stage-C loader accepts either candidates or scored filenames and
        # only needs boxes for staff-band reconstruction.  Write both aliases so
        # the composed directory is robust to loader preference order.
        write_json(output_dir / "pipeline2_no_peak_candidates.json", payload)
        write_json(output_dir / "pipeline2_no_peak_scored.json", payload)
        rows.append(
            PageComposition(
                score=score,
                page=page,
                source_name=source_name,
                source_path=str(source_path),
                output_dir=str(output_dir),
                status="composed",
                box_count=len(payload),
            )
        )
    return rows


def run(args: argparse.Namespace) -> dict[str, Any]:
    scores = args.scores or sorted(SCORES.keys())
    unknown_scores = sorted(set(scores) - set(SCORES.keys()))
    if unknown_scores:
        raise SystemExit("Unknown score(s): " + ", ".join(unknown_scores))

    if args.clean_output and not args.dry_run:
        shutil.rmtree(args.output_root, ignore_errors=True)

    hybrid_output_root = args.output_root / "hybrid_runs"
    bands_output_dir = args.output_root / "bands_from_candidate"
    if args.compose_source != "hybrid":
        bands_output_dir = args.output_root / f"bands_from_candidate_{args.compose_source}"
    hybrid_output_root.mkdir(parents=True, exist_ok=True)
    bands_output_dir.mkdir(parents=True, exist_ok=True)

    score_runs: list[ScoreRun] = []
    compositions: list[PageComposition] = []

    for score in scores:
        score_run = run_hybrid_for_score(
            args=args,
            score=score,
            hybrid_output_root=hybrid_output_root,
        )
        score_runs.append(score_run)
        if not args.dry_run:
            compositions.extend(
                compose_bands_for_score(
                    score=score,
                    run_id=score_run.run_id,
                    hybrid_output_root=hybrid_output_root,
                    bands_output_dir=bands_output_dir,
                    compose_source=args.compose_source,
                )
            )

    composed_pages = sum(1 for row in compositions if row.status == "composed")
    missing_pages = sum(1 for row in compositions if row.status != "composed")
    by_source: dict[str, int] = {}
    for row in compositions:
        if row.source_name:
            by_source[row.source_name] = by_source.get(row.source_name, 0) + 1
    payload = {
        "schema_version": "issue120.stage_d_upstream_regen.v1",
        "mode": "stage_d_upstream_hybrid_regeneration",
        "output_root": str(args.output_root),
        "hybrid_output_root": str(hybrid_output_root),
        "bands_output_dir": str(bands_output_dir),
        "compose_source": args.compose_source,
        "scores": scores,
        "score_runs": [asdict(item) for item in score_runs],
        "compositions": [asdict(item) for item in compositions],
        "summary": {
            "expected_pages": sum(len(SCORES[score]) for score in scores),
            "composed_pages": composed_pages,
            "missing_pages": missing_pages,
            "disable_sr": args.disable_sr,
            "sr_scale": args.sr_scale,
            "by_source": by_source,
        },
    }
    provenance_name = "stage_d_upstream_regen_provenance.json"
    if args.compose_source != "hybrid":
        provenance_name = f"stage_d_upstream_regen_provenance_{args.compose_source}.json"
    write_json(args.output_root / provenance_name, payload)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-root", type=Path, default=Path("data/evaluation2/images"))
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("logs/issue120_e2e_recovery/stage_d_upstream_regen"),
    )
    parser.add_argument("--run-id-prefix", default="issue120_stage_d_upstream_regen")
    parser.add_argument("--scores", nargs="*", help="Optional subset of score names to process.")
    parser.add_argument("--compose-source", choices=["first_available", *SOURCE_NAMES], default="hybrid")
    parser.add_argument(
        "--compose-only",
        action="store_true",
        help="Do not rerun HOMR/SR/OMR; only rebuild bands_from_candidate from existing upstream outputs.",
    )
    parser.add_argument("--sr-scale", type=int, default=2)
    parser.add_argument("--sr-tile", type=int, default=-1)
    parser.add_argument("--sr-tile-pad", type=int, default=10)
    parser.add_argument("--sr-fp32", action="store_true")
    parser.add_argument("--disable-sr", action="store_true")
    parser.add_argument("--enable-debug", action="store_true")
    parser.add_argument("--enable-cache", action="store_true", default=True)
    parser.add_argument("--write-staff-positions", action="store_true")
    parser.add_argument("--barline-min-height-factor", type=float, default=1.0)
    parser.add_argument("--barline-max-width-factor", type=float, default=1.0)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--clean-output", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    payload = run(args)
    summary = payload["summary"]
    print("Issue #120 Stage-D upstream regeneration")
    print(f"Scores: {', '.join(payload['scores'])}")
    print(f"Compose source: {payload['compose_source']}")
    print(f"Expected pages: {summary['expected_pages']}")
    print(f"Composed pages: {summary['composed_pages']}")
    print(f"Missing pages: {summary['missing_pages']}")
    print(f"By source: {summary.get('by_source', {})}")
    print(f"Bands output: {payload['bands_output_dir']}")
    print(f"Wrote: {args.output_root}")


if __name__ == "__main__":
    main()
