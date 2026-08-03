#!/usr/bin/env python3
"""Run one Issue #255 control or public-baseline detector variant."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import platform
import sys
from pathlib import Path
from typing import Any, Mapping

from src.pipeline.core.config import load_yaml
from src.pipeline.core.run_ids import build_probe_run_id
from src.pipeline.detection import run_detection_step
from src.pipeline.detection.hybrid import HybridDetector

ROOT = Path(__file__).resolve().parents[2]
CANONICAL_CONFIG = ROOT / "configs/dense_full_pipeline.yaml"
FRESH_CONTRACT = {
    "mode": "fresh_upstream",
    "fresh_upstream_authoritative": True,
    "override_keys": [],
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    path = path.resolve()
    if not path.is_file():
        return {"path": str(path), "exists": False}
    return {
        "path": str(path),
        "exists": True,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _probe_page_dir(
    *, image: Path, sr_image: Path, probe_root: Path, detection: Mapping[str, Any]
) -> Path:
    effective = (
        sr_image
        if bool(detection.get("enable_sr", True))
        and not bool(detection.get("probe_use_original_images", False))
        and sr_image.is_file()
        else image
    )
    configured_score = detection.get("probe_score_name")
    score_name = str(configured_score) if configured_score else None
    return probe_root / build_probe_run_id(effective, score_name=score_name)


def _artifact_paths(
    *, image: Path, run_dir: Path, hybrid: Path, probe: Path, detection: Mapping[str, Any]
) -> dict[str, Path | None]:
    stem = image.stem
    sr = hybrid / "sr" / "batch" / stem
    baseline = hybrid / "baseline" / "batch" / stem
    probe_image = sr / f"{stem}.png"
    probe_page = _probe_page_dir(
        image=image,
        sr_image=probe_image,
        probe_root=probe,
        detection=detection,
    )
    accepted = probe_page / "pipeline2_no_peak_filtered_cnn.json"
    clef_candidates = (
        sr / f"{stem}_clef_mask.png",
        sr / f"{stem}_clefs_keys_mask.png",
        sr / f"{stem}_proxy_debug_2_clefs.png",
        sr / f"{stem}_debug_2_clefs.png",
    )
    clef = next((path for path in clef_candidates if path.is_file()), None)
    return {
        "image": image,
        "input_contract": run_dir / "intermediate/detector_input_contract.json",
        "fresh_baseline": baseline / f"{stem}_detections.json",
        "current_sr": sr / f"{stem}_detections.json",
        "current_omr": hybrid / "omr_sr" / stem / "predictions.json",
        "hybrid": hybrid / "hybrid_results" / f"{stem}_hybrid.json",
        "probe_image": probe_image,
        "staff_mask": sr / f"{stem}_staff_mask.png",
        "clef_mask": clef,
        "cnn_candidates": probe_page / "pipeline2_no_peak_candidates.json",
        "cnn_scored": probe_page / "pipeline2_no_peak_scored.json",
        "cnn_accepted": accepted,
        "final_barlines": accepted,
    }


def _load_handoff(path: Path, image: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or payload.get("status") != "completed":
        raise ValueError("Public baseline handoff is incomplete")
    if payload.get("freshly_generated") is not True:
        raise ValueError("Public baseline handoff was not freshly generated")
    if payload.get("historical_artifact_used_as_runtime_input") is not False:
        raise ValueError("Historical runtime input is forbidden")
    if payload.get("source_image_sha256") != _sha256(image):
        raise ValueError("Public baseline handoff image hash mismatch")
    detection_path = Path(str(payload["detection_path"])).resolve()
    if not detection_path.is_file():
        raise FileNotFoundError(detection_path)
    if payload.get("detection_sha256") != _sha256(detection_path):
        raise ValueError("Public baseline handoff detection hash mismatch")
    return dict(payload)


def _install_public_baseline_skip_override(handoff: Mapping[str, Any]) -> Path:
    """Skip only the pre-generated public baseline despite connector-mask guard.

    The production guard intentionally reruns HOMR outputs that predate the connector
    artifact contract. This detector-only A/B must retain the freshly generated public
    baseline detections while current SR/OMR/probe/CNN stages still execute. The
    override is process-local and applies only to the exact baseline directory from
    the validated handoff.
    """

    detection_path = Path(str(handoff["detection_path"])).resolve()
    baseline_root = detection_path.parents[2]
    guarded_check = HybridDetector._all_stems_exist
    plain_check = getattr(guarded_check, "__wrapped__", None)
    if plain_check is None:
        raise RuntimeError("HOMR skip-existing guard wrapper was not installed")

    def check_with_public_baseline(
        self: HybridDetector,
        base_dir: Path,
        stems_to_check: list[str],
        glob_pattern: str,
    ) -> bool:
        if Path(base_dir).resolve() == baseline_root:
            return bool(plain_check(self, base_dir, stems_to_check, glob_pattern))
        return bool(guarded_check(self, base_dir, stems_to_check, glob_pattern))

    HybridDetector._all_stems_exist = check_with_public_baseline
    return baseline_root


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    image = args.image.resolve()
    if not image.is_file():
        raise FileNotFoundError(image)
    if image.parent.name != args.score or image.stem != args.page:
        raise ValueError("Image path must preserve score and page names")

    canonical = load_yaml(CANONICAL_CONFIG)
    if not isinstance(canonical, Mapping) or not isinstance(canonical.get("detection"), Mapping):
        raise ValueError("Canonical config lacks detection settings")
    config = copy.deepcopy(dict(canonical))
    config.setdefault("inputs", {}).setdefault("pdf_to_images", {})
    config.setdefault("run", {})
    config["inputs"]["pdf_to_images"].update(
        {"output_dir": str(image.parent), "image_glob": image.name}
    )
    output_root = args.output_root.resolve()
    run_dir = output_root / args.run_id
    if run_dir.exists() and any(run_dir.iterdir()):
        raise FileExistsError(run_dir)
    config["run"].update({"run_id": args.run_id, "output_root": str(output_root)})
    filter_kwargs = config["detection"].setdefault("candidate_filter_kwargs", {})
    filter_kwargs["rescue_low_paper_verticals"] = False

    handoff = None
    public_baseline_root = None
    if args.variant == "public_baseline":
        if args.baseline_handoff is None:
            raise ValueError("public_baseline requires --baseline-handoff")
        handoff = _load_handoff(args.baseline_handoff.resolve(), image)
        public_baseline_root = _install_public_baseline_skip_override(handoff)
        # The fresh public baseline is already present in this unique run directory.
        # SR, OMR, consensus, probe and CNN outputs do not exist and still execute.
        config["detection"]["probe_skip_existing"] = True

    run_dir.mkdir(parents=True, exist_ok=True)
    effective_path = run_dir / "issue255_public_baseline_ab_effective_config.json"
    effective_path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    result = run_detection_step(
        config, [image], [args.page], args.run_id, run_dir, dry_run=False
    )
    contract = result.get("detector_input_contract")
    if not isinstance(contract, Mapping) or any(
        contract.get(key) != value for key, value in FRESH_CONTRACT.items()
    ):
        raise RuntimeError(f"Fresh detector contract mismatch: {contract}")

    detection = config["detection"]
    artifact_paths = _artifact_paths(
        image=image,
        run_dir=run_dir,
        hybrid=Path(result["hybrid_output_dir"]),
        probe=Path(result["probe_output_dir"]),
        detection=detection,
    )
    artifacts = {name: _artifact(path) for name, path in artifact_paths.items()}
    missing = [
        name
        for name, record in artifacts.items()
        if name != "clef_mask"
        and (not isinstance(record, Mapping) or record.get("exists") is not True)
    ]
    if missing:
        raise RuntimeError(f"Missing artifacts: {missing}")

    if handoff is not None:
        baseline_record = artifacts["fresh_baseline"]
        if not isinstance(baseline_record, Mapping):
            raise RuntimeError("Public baseline artifact record is missing")
        expected_hash = str(handoff["detection_sha256"])
        actual_hash = str(baseline_record.get("sha256"))
        if actual_hash != expected_hash:
            raise RuntimeError(
                "Public baseline was overwritten during current downstream execution: "
                f"expected={expected_hash} actual={actual_hash}"
            )

    report = {
        "schema_version": "issue255.public_baseline_ab_run.v1",
        "status": "completed",
        "variant": args.variant,
        "score": args.score,
        "page": args.page,
        "run_id": args.run_id,
        "run_dir": str(run_dir),
        "detector_input_contract": dict(contract),
        "execution_only_overrides": {
            "candidate_filter_kwargs.rescue_low_paper_verticals": False,
            "probe_skip_existing": args.variant == "public_baseline",
            "baseline_connector_guard_bypass": args.variant == "public_baseline",
            "baseline_connector_guard_bypass_root": (
                str(public_baseline_root) if public_baseline_root is not None else None
            ),
        },
        "baseline_profile_handoff": handoff,
        "coordinate_space": {
            "original": "input_image_pixels",
            "probe": "sr_image_pixels"
            if detection.get("enable_sr", True)
            else "input_image_pixels",
            "sr_scale": int(detection.get("sr_scale", 2)),
            "cnn_output": "input_image_pixels",
        },
        "runtime": {"python": sys.version, "platform": platform.platform()},
        "artifacts": artifacts,
    }
    report_path = run_dir / "issue255_public_baseline_ab_run_contract.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=("control", "public_baseline"), required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--score", required=True)
    parser.add_argument("--page", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--baseline-handoff", type=Path)
    args = parser.parse_args()
    try:
        report = build_report(args)
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps({"status": report["status"], "run_dir": report["run_dir"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
