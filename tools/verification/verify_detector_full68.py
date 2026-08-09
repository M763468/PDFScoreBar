#!/usr/bin/env python3
"""Run the production detector route and verify the canonical evaluation2 full-68 contract."""

from __future__ import annotations

import argparse
import json
from argparse import Namespace
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

from src.pipeline.core.config import load_yaml
from src.pipeline.detection import run_detection_step
from tools.issue120 import eval_full68_from_intermediates as full68_eval

ROOT = Path(__file__).resolve().parents[2]
CANONICAL_CONFIG = ROOT / "configs/dense_full_pipeline.yaml"
DEFAULT_OUTPUT_ROOT = ROOT / "logs/verification/detector_full68"
DEFAULT_GT_ROOT = ROOT / "data/evaluation2/annotations"


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


def _evaluation_args(
    *, results_dir: Path, gt_root: Path, output_dir: Path, score_threshold: float
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
        allow_partial=False,
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


def run(args: argparse.Namespace) -> Path:
    config_path = args.config.resolve()
    if config_path != CANONICAL_CONFIG.resolve():
        raise ValueError(f"Canonical detector config required: {CANONICAL_CONFIG}")
    config = load_yaml(config_path)
    if not isinstance(config, Mapping):
        raise ValueError("Canonical config is not a mapping")
    images = _canonical_images()
    if args.page_limit is not None:
        if args.page_limit <= 0 or args.page_limit > 68:
            raise ValueError("--page-limit must be between 1 and 68")
        images = images[: args.page_limit]

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

    report: dict[str, Any] = {
        "schema_version": "verification.detector_full68.v1",
        "status": "completed",
        "run_tag": args.run_tag,
        "config": str(config_path),
        "page_count": len(images),
        "authoritative_full68": len(images) == 68,
        "historical_detector_artifact_runtime_input": False,
        "detector_input_contract": dict(contract),
        "detector_route": result.get("detector_route"),
        "homr_profile": result.get("homr_profile"),
        "hybrid_output_dir": str(result["hybrid_output_dir"]),
        "probe_output_dir": str(result["probe_output_dir"]),
    }

    if len(images) == 68:
        detection = config["detection"]
        assert isinstance(detection, Mapping)
        eval_output = run_root / "eval_detector"
        evaluation = full68_eval.evaluate(
            _evaluation_args(
                results_dir=Path(result["probe_output_dir"]),
                gt_root=args.gt_root.resolve(),
                output_dir=eval_output,
                score_threshold=float(detection.get("cnn_threshold", 0.1)),
            )
        )
        summary = asdict(evaluation.detector_summary)
        expected = _expected_metrics(config)
        mismatches = {
            key: {"expected": expected_value, "actual": summary.get(key)}
            for key, expected_value in expected.items()
            if summary.get(key) != expected_value
        }
        report.update(
            {
                "detector_summary": summary,
                "expected_detector_metrics": expected,
                "metric_mismatches": mismatches,
                "historical_detector_target_met": not mismatches,
                "evaluation_contract": str(eval_output / "evaluation_contract.json"),
                "detector_metrics": str(eval_output / "detector_metrics.json"),
                "detector_page_metrics": str(eval_output / "detector_page_metrics.csv"),
            }
        )
    else:
        report["historical_detector_target_met"] = None
        report["note"] = "Partial smoke run; full-68 metrics were not evaluated."

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
