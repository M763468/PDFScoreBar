#!/usr/bin/env python3
"""Run one canonical fresh detector page and write an authoritative artifact contract."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

import yaml

from src.pipeline.core.config import load_yaml
from src.pipeline.core.run_ids import build_probe_run_id
from src.pipeline.detection import run_detection_step

ROOT = Path(__file__).resolve().parents[2]
CANONICAL_CONFIG = ROOT / "configs" / "dense_full_pipeline.yaml"
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
        "mtime_ns": path.stat().st_mtime_ns,
        "sha256": _sha256(path),
    }


def _git(*args: str, root: Path = ROOT) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() or None


def build_effective_config(
    canonical: Mapping[str, Any], *, image: Path, run_id: str, output_root: Path
) -> dict[str, Any]:
    config = copy.deepcopy(dict(canonical))
    config.setdefault("inputs", {}).setdefault("pdf_to_images", {})
    config.setdefault("run", {})
    config["inputs"]["pdf_to_images"].update(
        {"output_dir": str(image.parent.resolve()), "image_glob": image.name}
    )
    config["run"].update({"run_id": run_id, "output_root": str(output_root.resolve())})
    if config.get("detection") != canonical.get("detection"):
        raise ValueError("Focused run changed canonical detection settings")
    if config.get("steps") != canonical.get("steps"):
        raise ValueError("Focused run changed canonical pipeline steps")
    return config


def _probe_page_dir(
    *,
    image: Path,
    sr_image: Path,
    probe_root: Path,
    detection: Mapping[str, Any],
) -> Path:
    """Resolve the page directory exactly as probe scan and CNN scoring do."""
    effective_image = (
        sr_image
        if bool(detection.get("enable_sr", True))
        and not bool(detection.get("probe_use_original_images", False))
        and sr_image.is_file()
        else image
    )
    configured_score = detection.get("probe_score_name")
    score_name = str(configured_score) if configured_score else None
    return probe_root / build_probe_run_id(effective_image, score_name=score_name)


def _paths(
    image: Path,
    run_dir: Path,
    hybrid: Path,
    probe: Path,
    detection: Mapping[str, Any],
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
        "input_contract": run_dir / "intermediate" / "detector_input_contract.json",
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


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    if args.config.resolve() != CANONICAL_CONFIG.resolve():
        raise ValueError(f"Canonical config required: {CANONICAL_CONFIG}")
    image = args.image.resolve()
    if not image.is_file():
        raise FileNotFoundError(image)
    if image.parent.name != args.score or image.stem != args.page:
        raise ValueError("Image path must preserve the requested score and page names")

    canonical = load_yaml(args.config)
    if not isinstance(canonical, Mapping) or not isinstance(canonical.get("detection"), Mapping):
        raise ValueError("Canonical config lacks detection settings")
    detection = canonical["detection"]
    forbidden = [
        key for key in ("precomputed_probe_candidates_root", "cnn_bands_from") if detection.get(key)
    ]
    if forbidden:
        raise ValueError(f"Fresh run forbids detector source overrides: {forbidden}")

    output_root = args.output_root.resolve()
    run_dir = output_root / args.run_id
    if run_dir.exists() and any(run_dir.iterdir()):
        raise FileExistsError(f"Run directory must be new and empty: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)
    effective = build_effective_config(
        canonical, image=image, run_id=args.run_id, output_root=output_root
    )
    effective_path = run_dir / "issue255_focused_effective_config.yaml"
    effective_path.write_text(yaml.safe_dump(effective, sort_keys=False), encoding="utf-8")

    result = run_detection_step(
        effective, [image], [args.page], args.run_id, run_dir, dry_run=False
    )
    contract = result.get("detector_input_contract")
    if not isinstance(contract, Mapping) or any(
        contract.get(key) != value for key, value in FRESH_CONTRACT.items()
    ):
        raise RuntimeError(f"Fresh detector contract mismatch: {contract}")

    artifact_paths = _paths(
        image,
        run_dir,
        Path(result["hybrid_output_dir"]),
        Path(result["probe_output_dir"]),
        detection,
    )
    artifacts = {key: _artifact(path) for key, path in artifact_paths.items()}
    required = set(artifact_paths) - {"clef_mask"}
    missing = [key for key in required if artifacts[key]["exists"] is not True]
    if missing:
        raise RuntimeError(f"Focused detector run lacks artifacts: {missing}")

    report = {
        "schema_version": "issue255.focused_fresh_detector_run.v1",
        "status": "completed",
        "score": args.score,
        "page": args.page,
        "run_id": args.run_id,
        "run_dir": str(run_dir),
        "detector_input_contract": dict(contract),
        "canonical_config": _artifact(args.config),
        "effective_config": _artifact(effective_path),
        "effective_overrides": {
            "inputs.pdf_to_images.output_dir": str(image.parent),
            "inputs.pdf_to_images.image_glob": image.name,
            "run.run_id": args.run_id,
            "run.output_root": str(output_root),
        },
        "detection_config_changed": False,
        "pipeline_steps_changed": False,
        "repository": {
            "commit": _git("rev-parse", "HEAD"),
            "branch": _git("branch", "--show-current"),
            "status": _git("status", "--short"),
        },
        "runtime": {
            "python": sys.version,
            "executable": sys.executable,
            "platform": platform.platform(),
            "inside_container": Path("/.dockerenv").exists(),
            "omr_dln_model_path": os.environ.get("OMR_DLN_MODEL_PATH"),
        },
        "coordinate_space": {
            "original": "input_image_pixels",
            "probe": "sr_image_pixels"
            if detection.get("enable_sr", True)
            else "input_image_pixels",
            "sr_scale": int(detection.get("sr_scale", 2))
            if detection.get("enable_sr", True)
            else 1,
            "cnn_output": "input_image_pixels",
        },
        "commands": result.get("commands", []),
        "artifacts": artifacts,
    }
    report_path = run_dir / "issue255_focused_fresh_run_contract.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CANONICAL_CONFIG)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--score", required=True)
    parser.add_argument("--page", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = build_report(args)
    except Exception as error:  # noqa: BLE001
        failure = {
            "status": "failed",
            "error_type": type(error).__name__,
            "error": str(error),
        }
        root = args.output_root.resolve() / args.run_id
        root.mkdir(parents=True, exist_ok=True)
        (root / "issue255_focused_fresh_run_contract.json").write_text(
            json.dumps(failure, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(json.dumps(failure, ensure_ascii=False))
        return 1
    print(json.dumps({"status": report["status"], "run_dir": report["run_dir"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
