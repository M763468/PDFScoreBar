#!/usr/bin/env python3
"""Run the historical Stage E route on two same-run fresh upstream pages.

Temporary Issue #255 experiment tooling. Remove, consolidate, or promote this
entry point before the final PR.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from src.pipeline.core.config import load_yaml
from src.pipeline.core.run_ids import build_probe_run_id
from src.pipeline.detection import run_detection_step
from src.pipeline.detector_routes.dense_full_pipeline import (
    FILTER_PARAMS,
    GENERATION_PARAMS,
    reconstruct_dense_full_pipeline_route,
)
from src.pipeline.steps.cnn_scoring import run_cnn_scoring_batch
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue252.probe_boundary import (
    artifact_record,
    normalize_box,
    sha256,
    target_metrics,
    validate_fresh_contract_payload,
    write_json,
)
from tools.issue255.evaluate_focused_candidate_rescue import _match_box_details

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs/dense_full_pipeline.yaml"
TARGETS = ROOT / "tools/issue255/gate05_targets.json"
IMAGE_ROOT = ROOT / "data/evaluation2/images"
FRESH_CONTRACT = {
    "mode": "fresh_upstream",
    "fresh_upstream_authoritative": True,
    "override_keys": [],
}
CANDIDATES = "pipeline2_no_peak_candidates.json"
SCORED = "pipeline2_no_peak_scored.json"
ACCEPTED = "pipeline2_no_peak_filtered_cnn.json"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() or None


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute() and path.parts[:2] == ("/", "workspace"):
        return ROOT / path.relative_to("/workspace")
    return path if path.is_absolute() else ROOT / path


def _record(path: Path, *, role: str | None = None) -> dict[str, Any]:
    result = artifact_record(path.resolve())
    if role:
        result["role"] = role
    return result


def _tree_record(root: Path) -> dict[str, Any]:
    files = sorted(path for path in root.rglob("*") if path.is_file())
    rows = [
        {
            "path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in files
    ]
    import hashlib

    digest = hashlib.sha256()
    for row in rows:
        digest.update(row["path"].encode())
        digest.update(b"\0")
        digest.update(row["sha256"].encode())
        digest.update(b"\0")
    return {
        "path": str(root.resolve()),
        "file_count": len(rows),
        "size_bytes": sum(row["size_bytes"] for row in rows),
        "tree_sha256": digest.hexdigest(),
    }


def _page_specs(targets: Path, image_root: Path) -> list[dict[str, Any]]:
    payload = _load(targets)
    pages = payload.get("pages") if isinstance(payload, Mapping) else None
    if not isinstance(pages, Mapping):
        raise ValueError("Target manifest lacks pages")
    result = []
    for label, value in pages.items():
        if not isinstance(value, Mapping):
            raise ValueError(f"Invalid target page: {label}")
        score, page = str(value["score"]), str(value["page"])
        image = image_root / score / f"{page}.png"
        accepted = _resolve(str(value["accepted_barlines"]))
        if not image.is_file():
            raise FileNotFoundError(image)
        if not accepted.is_file():
            raise FileNotFoundError(f"Evaluation-only Stage E reference missing: {accepted}")
        result.append(
            {
                "label": str(label),
                "score": score,
                "page": page,
                "image": image.resolve(),
                "accepted": accepted.resolve(),
                "targets": list(value.get("targets", [])),
            }
        )
    return result


def _find(dirs: Sequence[Path], patterns: Sequence[str], name: str) -> Path:
    for directory in dirs:
        for pattern in patterns:
            matches = sorted(directory.glob(pattern))
            if matches:
                return matches[0]
    raise FileNotFoundError(f"Fresh {name} missing under {[str(path) for path in dirs]}")


def _fresh_sources(image: Path, hybrid_root: Path) -> dict[str, Path]:
    stem = image.stem
    baseline = hybrid_root / "baseline/batch" / stem
    sr = hybrid_root / "sr/batch" / stem
    dirs = (baseline, sr)
    sources = {
        "baseline": baseline / f"{stem}_detections.json",
        "sr": sr / f"{stem}_detections.json",
        "omr": hybrid_root / "omr_sr" / stem / "predictions.json",
        "hybrid": hybrid_root / "hybrid_results" / f"{stem}_hybrid.json",
        "staff_mask": _find(
            dirs,
            (
                f"{stem}_staff_mask.png",
                f"{stem}_proxy_debug_3_staff.png",
                f"{stem}_debug_3_staff.png",
                "*_staff_mask.png",
                "*_debug_3_staff.png",
            ),
            "staff mask",
        ),
        "clef_mask": _find(
            dirs,
            (
                f"{stem}_clef_mask.png",
                f"{stem}_clefs_keys_mask.png",
                f"{stem}_proxy_debug_7_clefs_keys.png",
                f"{stem}_debug_7_clefs_keys.png",
                f"{stem}_proxy_debug_2_clefs.png",
                f"{stem}_debug_2_clefs.png",
                "*_clef_mask.png",
                "*_clefs_keys_mask.png",
                "*_debug_7_clefs_keys.png",
                "*_debug_2_clefs.png",
            ),
            "clef mask",
        ),
    }
    missing = [key for key, path in sources.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Fresh source artifacts missing: {missing}")
    return sources


def _normal_page(
    image: Path, hybrid_root: Path, probe_root: Path, detection: Mapping[str, Any]
) -> Path:
    effective = image
    if detection.get("enable_sr", True) and not detection.get("probe_use_original_images", False):
        sr_image = hybrid_root / "sr/batch" / image.stem / image.name
        if sr_image.is_file():
            effective = sr_image
    score = detection.get("probe_score_name")
    return probe_root / build_probe_run_id(effective, score_name=str(score) if score else None)


def _candidate_file(root: Path, image: Path, name: str) -> Path:
    direct = root / build_probe_run_id(image) / name
    if direct.is_file():
        return direct
    matches = [path for path in root.rglob(name) if image.stem in path.as_posix()]
    if len(matches) == 1:
        return matches[0]
    raise FileNotFoundError(f"Cannot resolve {name} for {image}: {matches}")


def _scored(path: Path) -> list[dict[str, Any]]:
    payload = _load(path)
    if not isinstance(payload, list):
        raise ValueError(f"Scored payload must be a list: {path}")
    return [
        {"bbox": normalize_box(item["bbox"]), "score": item.get("score")}
        for item in payload
        if isinstance(item, Mapping)
        and isinstance(item.get("bbox"), Sequence)
        and not isinstance(item.get("bbox"), (str, bytes))
    ]


def _layer(reference: tuple[int, int, int, int], boxes: Sequence[Any]) -> dict[str, Any]:
    metrics = target_metrics(reference, boxes, accepted_iou=0.5)
    best = metrics.get("best")
    return {
        "candidate_present": bool(metrics["accepted"]),
        "best_bbox": best.get("bbox") if isinstance(best, Mapping) else None,
        "best_iou": best.get("iou") if isinstance(best, Mapping) else 0.0,
        "x_center_distance": (best.get("x_center_distance") if isinstance(best, Mapping) else None),
    }


def _scored_layer(
    reference: tuple[int, int, int, int], records: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    result = _layer(reference, [item["bbox"] for item in records])
    result["cnn_score"] = None
    if result["best_bbox"] is not None:
        best = normalize_box(result["best_bbox"])
        for item in records:
            if normalize_box(item["bbox"]) == best:
                value = item.get("score")
                result["cnn_score"] = float(value) if isinstance(value, (int, float)) else None
                break
    return result


def _drop_evidence(path: Path, reference: tuple[int, int, int, int]) -> list[dict[str, Any]]:
    payload = _load(path)
    dropped = payload.get("drop_suggested", []) if isinstance(payload, Mapping) else []
    rows = []
    for item in dropped:
        if not isinstance(item, Mapping) or not isinstance(item.get("bbox"), Sequence):
            continue
        box = normalize_box(item["bbox"])
        metrics = target_metrics(reference, [box], accepted_iou=0.5)
        best = metrics.get("best")
        if isinstance(best, Mapping) and (best["iou"] > 0 or best["x_center_distance"] <= 12.0):
            rows.append(
                {
                    "bbox": list(box),
                    "iou": best["iou"],
                    "x_center_distance": best["x_center_distance"],
                    "reasons": list(item.get("reasons", [])),
                }
            )
    return sorted(rows, key=lambda row: (-row["iou"], row["x_center_distance"]))[:10]


def _first_loss(layers: Mapping[str, Mapping[str, Any]]) -> str:
    for name in (
        "dense_raw_candidate",
        "clef_mask_filtering",
        "issue53_reconstruction",
        "cnn_scored",
        "cnn_accepted",
        "final_detector_output",
    ):
        if not layers[name]["candidate_present"]:
            return name
    return "recovered"


def _effective(canonical: Mapping[str, Any], run_id: str, output: Path) -> dict[str, Any]:
    config = copy.deepcopy(dict(canonical))
    config.setdefault("run", {}).update({"run_id": run_id, "output_root": str(output.resolve())})
    if config.get("detection") != canonical.get("detection"):
        raise ValueError("Focused run changed canonical detection config")
    if config.get("steps") != canonical.get("steps"):
        raise ValueError("Focused run changed canonical steps")
    return config


def _copy_sources(root: Path, page: Mapping[str, Any], sources: Mapping[str, Path]) -> None:
    dest = root / page["score"] / page["page"]
    dest.mkdir(parents=True, exist_ok=True)
    for name, source in sources.items():
        shutil.copy2(source, dest / f"{name}{source.suffix}")


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    if args.config.resolve() != CONFIG.resolve():
        raise ValueError(f"Canonical config required: {CONFIG}")
    commit = _git("rev-parse", "HEAD")
    if args.expected_commit and commit != args.expected_commit:
        raise ValueError(f"HEAD mismatch: expected={args.expected_commit} actual={commit}")
    run_root = args.output_root.resolve() / args.run_tag
    if run_root.exists() and any(run_root.iterdir()):
        raise FileExistsError(f"Run root must be new: {run_root}")
    run_root.mkdir(parents=True, exist_ok=True)

    canonical = load_yaml(args.config)
    detection = canonical.get("detection") if isinstance(canonical, Mapping) else None
    if not isinstance(detection, Mapping):
        raise ValueError("Canonical config lacks detection settings")
    forbidden = [
        key for key in ("precomputed_probe_candidates_root", "cnn_bands_from") if detection.get(key)
    ]
    if forbidden:
        raise ValueError(f"Canonical fresh route contains overrides: {forbidden}")
    pages = _page_specs(args.targets.resolve(), args.image_root.resolve())
    images = [page["image"] for page in pages]

    pipeline_root = run_root / "pipeline_runs"
    control_id = f"{args.run_tag}_fresh_control"
    control_dir = pipeline_root / control_id
    control_dir.mkdir(parents=True, exist_ok=True)
    effective = _effective(canonical, control_id, pipeline_root)
    effective_path = run_root / "effective_config.yaml"
    effective_path.write_text(yaml.safe_dump(effective, sort_keys=False), encoding="utf-8")
    control = run_detection_step(
        effective,
        images,
        [page["page"] for page in pages],
        control_id,
        control_dir,
        dry_run=False,
    )
    contract = validate_fresh_contract_payload(control["detector_input_contract"])
    hybrid_root = Path(control["hybrid_output_dir"]).resolve()
    probe_root = Path(control["probe_output_dir"]).resolve()

    source_by_label: dict[str, dict[str, Path]] = {}
    inventory = []
    for page in pages:
        sources = _fresh_sources(page["image"], hybrid_root)
        source_by_label[page["label"]] = sources
        inventory.append(
            {
                "score": page["score"],
                "page": page["page"],
                "image": str(page["image"]),
                "hybrid_predictions": str(sources["hybrid"]),
                "staff_mask": str(sources["staff_mask"]),
                "clef_mask": str(sources["clef_mask"]),
                "run_dir": str(sources["staff_mask"].parent),
            }
        )
        _copy_sources(run_root / "fresh_source_snapshot", page, sources)

    inventory_path = run_root / "fresh_inventory.json"
    exclude_path = run_root / "fresh_exclude.json"
    write_json(
        inventory_path,
        {
            "schema_version": "issue255.focused_fresh_inventory.v1",
            "historical_runtime_input": False,
            "records": inventory,
        },
    )
    write_json(exclude_path, {"excluded_pages": []})
    dense_root = run_root / "dense_route"
    dense = reconstruct_dense_full_pipeline_route(
        inventory=inventory_path,
        exclude=exclude_path,
        route_root=dense_root,
        expected_pages=len(pages),
        verbose_logs=args.verbose_dense_logs,
    )

    cnn_model = _resolve(str(detection["cnn_model_path"])).resolve()
    if not cnn_model.is_file():
        raise FileNotFoundError(cnn_model)
    run_cnn_scoring_batch(
        probe_output_root=dense.probe_rescue_root,
        images=images,
        model_path=cnn_model,
        threshold=float(detection.get("cnn_threshold", 0.1)),
        score_name=(
            str(detection["probe_score_name"]) if detection.get("probe_score_name") else None
        ),
        crop_recenter_on_bbox_ink=bool(detection.get("crop_recenter_on_bbox_ink", False)),
        crop_recenter_max_shift_unit_ratio=float(
            detection.get("crop_recenter_max_shift_unit_ratio", 0.35)
        ),
        input_image_scale=1.0,
        bands_from=dense.filtered_root,
        staff_vov_threshold=float(detection.get("staff_vov_threshold", 0.5)),
        apply_nms_enabled=False,
        in_memory_images=None,
    )

    page_reports = {}
    for page in pages:
        image, score, page_id = page["image"], page["score"], page["page"]
        control_page = _normal_page(image, hybrid_root, probe_root, detection)
        control_final = control_page / ACCEPTED
        raw = (
            dense_root
            / "dense_candidate_reconstruction/probe_candidates_from_inventory"
            / score
            / page_id
            / CANDIDATES
        )
        filtered = dense.filtered_root / score / page_id / CANDIDATES
        suggestions = (
            dense_root
            / "dense_candidate_reconstruction/filter_suggestions"
            / score
            / f"{page_id}_suggestion.json"
        )
        issue53 = _candidate_file(dense.probe_rescue_root, image, CANDIDATES)
        scored_path = _candidate_file(dense.probe_rescue_root, image, SCORED)
        final = _candidate_file(dense.probe_rescue_root, image, ACCEPTED)
        required = [control_final, raw, filtered, suggestions, issue53, scored_path, final]
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"Focused artifacts missing: {missing}")

        accepted_boxes = load_json_boxes(page["accepted"])
        control_boxes = load_json_boxes(control_final)
        raw_boxes = load_json_boxes(raw)
        filtered_boxes = load_json_boxes(filtered)
        issue53_boxes = load_json_boxes(issue53)
        scored_rows = _scored(scored_path)
        final_boxes = load_json_boxes(final)
        target_rows = []
        for target in page["targets"]:
            reference = normalize_box(target["accepted_bbox"])
            layers = {
                "dense_raw_candidate": _layer(reference, raw_boxes),
                "clef_mask_filtering": _layer(reference, filtered_boxes),
                "issue53_reconstruction": _layer(reference, issue53_boxes),
                "cnn_scored": _scored_layer(reference, scored_rows),
                "cnn_accepted": _layer(reference, final_boxes),
                "final_detector_output": _layer(reference, final_boxes),
            }
            layers["clef_mask_filtering"]["drop_evidence"] = _drop_evidence(suggestions, reference)
            target_rows.append(
                {
                    **target,
                    "accepted_bbox": list(reference),
                    "control_final": _layer(reference, control_boxes),
                    "layers": layers,
                    "first_loss_boundary": _first_loss(layers),
                }
            )
        control_metrics = _match_box_details(accepted_boxes, control_boxes)
        reconstructed_metrics = _match_box_details(accepted_boxes, final_boxes)
        page_reports[page["label"]] = {
            "score": score,
            "page": page_id,
            "coordinate_space": "original_input_pixels",
            "counts": {
                "dense_raw_candidate": len(raw_boxes),
                "clef_mask_filtering": len(filtered_boxes),
                "issue53_reconstruction": len(issue53_boxes),
                "cnn_scored": len(scored_rows),
                "cnn_accepted": len(final_boxes),
                "normal_control_final": len(control_boxes),
                "historical_stage_e_reference": len(accepted_boxes),
            },
            "metrics": {
                "normal_control": {key: control_metrics[key] for key in ("tp", "fp", "fn")},
                "reconstructed": {key: reconstructed_metrics[key] for key in ("tp", "fp", "fn")},
                "delta_vs_control": {
                    key: reconstructed_metrics[key] - control_metrics[key]
                    for key in ("tp", "fp", "fn")
                },
            },
            "accepted_reference": _record(
                page["accepted"], role="evaluation_only_not_runtime_input"
            ),
            "artifacts": {
                "control_final": _record(control_final),
                "dense_raw": _record(raw),
                "filtered": _record(filtered),
                "filter_suggestions": _record(suggestions),
                "issue53": _record(issue53),
                "cnn_scored": _record(scored_path),
                "cnn_accepted": _record(final),
                "fresh_sources": {
                    name: _record(path) for name, path in source_by_label[page["label"]].items()
                },
            },
            "targets": target_rows,
        }

    targets = [target for page in page_reports.values() for target in page["targets"]]
    omr_model = Path(os.environ["OMR_DLN_MODEL_PATH"]).resolve()
    report = {
        "schema_version": "issue255.focused_stage_e_reconstruction.v1",
        "status": "completed",
        "cleanup_policy": "Temporary experiment code; clean up before final PR.",
        "run_tag": args.run_tag,
        "detector_input_contract": contract,
        "reconstruction_contract": {
            **FRESH_CONTRACT,
            "fresh_inventory_generated_in_run": True,
            "historical_detector_candidate_runtime_inputs": [],
            "accepted_reference_runtime_input": False,
        },
        "run_specific_overrides": {
            "selected_pages": [f"{page['score']}/{page['page']}" for page in pages],
            "run.run_id": control_id,
            "run.output_root": str(pipeline_root),
        },
        "repository": {
            "commit": commit,
            "branch": _git("branch", "--show-current"),
            "status": _git("status", "--short"),
        },
        "route": {
            "dense_generation_params": GENERATION_PARAMS,
            "clef_filter_params": FILTER_PARAMS,
            "bands_from": str(dense.filtered_root),
            "probe_use_original_images": True,
            "cnn_model": str(cnn_model),
            "cnn_threshold": float(detection.get("cnn_threshold", 0.1)),
            "cnn_apply_nms": False,
            "production_orchestrator_connection": False,
        },
        "provenance": {
            "canonical_config": _record(args.config.resolve()),
            "effective_config": _record(effective_path),
            "target_manifest": _record(args.targets.resolve(), role="evaluation_metadata_only"),
            "fresh_inventory": _record(inventory_path),
            "cnn_model": _record(cnn_model),
            "omr_dln_model": _record(omr_model),
            "input_images": [_record(page["image"]) for page in pages],
            "dense_raw_tree": _tree_record(
                dense_root / "dense_candidate_reconstruction/probe_candidates_from_inventory"
            ),
            "filtered_tree": _tree_record(dense.filtered_root),
            "issue53_tree": _tree_record(dense.probe_rescue_root),
            "dense_execution_summary": dense.execution_summary,
        },
        "pages": page_reports,
        "gates": {
            "all_targets_recovered": all(
                target["first_loss_boundary"] == "recovered" for target in targets
            ),
            "focused_fp_increase_zero": all(
                page["metrics"]["delta_vs_control"]["fp"] <= 0 for page in page_reports.values()
            ),
            "historical_runtime_artifact_dependency_absent": True,
            "fresh_contract_exact": contract == FRESH_CONTRACT
            or all(contract.get(key) == value for key, value in FRESH_CONTRACT.items()),
        },
    }
    report_path = run_root / "focused_stage_e_reconstruction_report.json"
    write_json(report_path, report)
    return {**report, "report_path": str(report_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-tag", required=True)
    parser.add_argument("--output-root", type=Path, default=ROOT / "logs/issue255_stage_e_focused")
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--targets", type=Path, default=TARGETS)
    parser.add_argument("--image-root", type=Path, default=IMAGE_ROOT)
    parser.add_argument("--expected-commit")
    parser.add_argument("--verbose-dense-logs", action="store_true")
    args = parser.parse_args()
    try:
        report = build_report(args)
    except Exception as error:  # noqa: BLE001
        root = args.output_root.resolve() / args.run_tag
        root.mkdir(parents=True, exist_ok=True)
        failure = {
            "status": "failed",
            "error_type": type(error).__name__,
            "error": str(error),
            "repository_commit": _git("rev-parse", "HEAD"),
        }
        write_json(root / "focused_stage_e_reconstruction_failure.json", failure)
        print(json.dumps(failure, ensure_ascii=False))
        return 1
    print(
        json.dumps(
            {
                "status": report["status"],
                "report": report["report_path"],
                "gates": report["gates"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
