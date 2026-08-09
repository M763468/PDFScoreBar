#!/usr/bin/env python3
"""Run the production detector route and verify canonical evaluation2 detector contracts."""

from __future__ import annotations

import argparse
import json
from argparse import Namespace
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.pipeline.core.config import load_yaml
from src.pipeline.detection import run_detection_step
from tools.issue120 import eval_full68_from_intermediates as full68_eval

ROOT = Path(__file__).resolve().parents[2]
CANONICAL_CONFIG = ROOT / "configs/dense_full_pipeline.yaml"
DEFAULT_OUTPUT_ROOT = ROOT / "logs/verification/detector_full68"
DEFAULT_GT_ROOT = ROOT / "data/evaluation2/annotations"
FOCUSED_STAGE_E_PAGES = (
    "Va_Prokofiev_Symphony1/page_004",
    "Shostakovich-Sym5-Va/page_014",
)
FOCUSED_STAGE_E_EXPECTED = {
    "gt": 174,
    "pred": 174,
    "tp": 174,
    "fp": 0,
    "fn": 0,
    "fn_det": 0,
    "fn_cnn": 0,
}


def _canonical_images() -> list[Path]:
    images = [
        ROOT / "data/evaluation2/images" / score / f"{page}.png"
        for score, pages in full68_eval.SCORES.items()
        for page in pages
    ]
    if len(images) != 68:
        raise RuntimeError(f"Canonical evaluation2 manifest drifted: {len(images)} pages")
    missing = [str(path) for path in images if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing canonical evaluation2 images:\n" + "\n".join(missing))
    return images


def _page_selector(image: Path) -> str:
    return f"{image.parent.name}/{image.stem}"


def _select_images(
    images: Sequence[Path],
    *,
    pages: Sequence[str] | None,
    page_limit: int | None,
) -> list[Path]:
    if pages and page_limit is not None:
        raise ValueError("--page and --page-limit cannot be used together")
    if pages:
        canonical = {_page_selector(image): image for image in images}
        selected: list[Path] = []
        seen: set[str] = set()
        for selector in pages:
            if selector in seen:
                raise ValueError(f"Duplicate --page selector: {selector}")
            seen.add(selector)
            image = canonical.get(selector)
            if image is None:
                raise ValueError(f"Page is not in the canonical evaluation2 manifest: {selector}")
            selected.append(image)
        return selected
    if page_limit is not None:
        if page_limit <= 0 or page_limit > len(images):
            raise ValueError(f"--page-limit must be between 1 and {len(images)}")
        return list(images[:page_limit])
    return list(images)


def _evaluation_args(
    *,
    results_dir: Path,
    gt_root: Path,
    output_dir: Path,
    score_threshold: float,
    allow_partial: bool,
) -> Namespace:
    return Namespace(
        results_dir=str(results_dir),
        gt_root=str(gt_root),
        output_dir=str(output_dir),
        scored_file="pipeline2_no_peak_scored.json",
        candidates_file="pipeline2_no_peak_candidates.json",
        score_threshold=score_threshold,
        rule_name="center_anchor",
        vov_threshold=0.5,
        xdist_threshold=12.0,
        allow_partial=allow_partial,
        measure_summary_json=None,
    )


def _expected_metrics(config: Mapping[str, Any]) -> dict[str, Any]:
    detection = config.get("detection")
    if not isinstance(detection, Mapping):
        raise ValueError("Canonical config lacks detection settings")
    profile_name = detection.get("homr_profile")
    if profile_name != "stage_e_verified":
        raise ValueError(f"Canonical config does not select stage_e_verified: {profile_name}")
    profile_path = ROOT / "configs/detector_profiles/stage_e_verified_homr.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    expected = profile.get("verified_stage_e_full68")
    if not isinstance(expected, Mapping):
        raise ValueError("Stage E HOMR profile lacks verified full-68 metrics")
    return {key: expected[key] for key in ("gt", "pred", "tp", "fp", "fn", "fn_det", "fn_cnn")}


def _metric_mismatches(
    summary: Mapping[str, Any], expected: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    return {
        key: {"expected": expected_value, "actual": summary.get(key)}
        for key, expected_value in expected.items()
        if summary.get(key) != expected_value
    }


def run(args: argparse.Namespace) -> Path:
    config_path = args.config.resolve()
    if config_path != CANONICAL_CONFIG.resolve():
        raise ValueError(f"Canonical detector config required: {CANONICAL_CONFIG}")
    config = load_yaml(config_path)
    if not isinstance(config, Mapping):
        raise ValueError("Canonical config is not a mapping")
    images = _select_images(
        _canonical_images(),
        pages=getattr(args, "page", None),
        page_limit=args.page_limit,
    )

    output_root = args.output_root.resolve()
    run_root = output_root / args.run_tag
    if run_root.exists() and any(run_root.iterdir()):
        raise FileExistsError(run_root)
    run_root.mkdir(parents=True, exist_ok=True)
    page_ids = [image.stem for image in images]
    result = run_detection_step(
        dict(config),
        images,
        page_ids,
        args.run_tag,
        run_root,
        dry_run=False,
    )
    contract = result.get("detector_input_contract")
    if not isinstance(contract, Mapping):
        raise ValueError("Detector result lacks input contract")
    if contract.get("mode") != "fresh_upstream":
        raise ValueError(f"Detector route is not fresh upstream: {contract}")
    if contract.get("fresh_upstream_authoritative") is not True:
        raise ValueError(f"Detector fresh-upstream contract failed: {contract}")
    if contract.get("override_keys") != []:
        raise ValueError(f"Detector route contains candidate overrides: {contract}")

    selected_pages = [_page_selector(image) for image in images]
    authoritative_full68 = len(images) == 68 and not getattr(args, "page", None)
    report: dict[str, Any] = {
        "schema_version": "verification.detector_full68.v1",
        "status": "completed",
        "run_tag": args.run_tag,
        "config": str(config_path),
        "page_count": len(images),
        "selected_pages": selected_pages,
        "authoritative_full68": authoritative_full68,
        "historical_detector_artifact_runtime_input": False,
        "detector_input_contract": dict(contract),
        "detector_route": result.get("detector_route"),
        "homr_profile": result.get("homr_profile"),
        "hybrid_output_dir": str(result["hybrid_output_dir"]),
        "probe_output_dir": str(result["probe_output_dir"]),
    }

    detection = config["detection"]
    assert isinstance(detection, Mapping)
    eval_output = run_root / "eval_detector"
    evaluation = full68_eval.evaluate(
        _evaluation_args(
            results_dir=Path(result["probe_output_dir"]),
            gt_root=args.gt_root.resolve(),
            output_dir=eval_output,
            score_threshold=float(detection.get("cnn_threshold", 0.1)),
            allow_partial=not authoritative_full68,
        )
    )
    summary = asdict(evaluation.detector_summary)
    report.update(
        {
            "detector_summary": summary,
            "evaluation_contract": str(eval_output / "evaluation_contract.json"),
            "detector_metrics": str(eval_output / "detector_metrics.json"),
            "detector_page_metrics": str(eval_output / "detector_page_metrics.csv"),
        }
    )

    if authoritative_full68:
        expected = _expected_metrics(config)
        mismatches = _metric_mismatches(summary, expected)
        report.update(
            {
                "expected_detector_metrics": expected,
                "metric_mismatches": mismatches,
                "historical_detector_target_met": not mismatches,
                "verification_scope": "full68",
            }
        )
    elif set(selected_pages) == set(FOCUSED_STAGE_E_PAGES) and len(selected_pages) == 2:
        mismatches = _metric_mismatches(summary, FOCUSED_STAGE_E_EXPECTED)
        report.update(
            {
                "expected_detector_metrics": dict(FOCUSED_STAGE_E_EXPECTED),
                "metric_mismatches": mismatches,
                "historical_detector_target_met": not mismatches,
                "verification_scope": "focused_stage_e_two_page",
            }
        )
    else:
        report.update(
            {
                "historical_detector_target_met": None,
                "verification_scope": "partial_smoke",
                "note": "Partial detector run; no historical target is defined for this page set.",
            }
        )

    report_path = run_root / "detector_full68_verification_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-tag", required=True)
    parser.add_argument("--config", type=Path, default=CANONICAL_CONFIG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--gt-root", type=Path, default=DEFAULT_GT_ROOT)
    parser.add_argument(
        "--page",
        action="append",
        help="Canonical page selector SCORE/page_NNN. Repeat to run a focused subset.",
    )
    parser.add_argument("--page-limit", type=int)
    args = parser.parse_args()
    try:
        report = run(args)
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps({"status": "completed", "report": str(report)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
