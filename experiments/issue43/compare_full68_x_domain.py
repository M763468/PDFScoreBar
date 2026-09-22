#!/usr/bin/env python3
"""Issue #43 full-68 A/B using retained current-production upstream inventories.

The expensive maintained-HOMR/SR upstream is generated once per score unless an
upstream manifest is supplied. Both probe X-domain variants are then reconstructed
score-by-score from the exact same inventories, scored with the current production
CNN contract, aggregated, and evaluated with the canonical evaluation2 detector
evaluator.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import time
from argparse import Namespace
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
CANONICAL_CONFIG = ROOT / "configs/dense_full_pipeline.yaml"
DEFAULT_OUTPUT_ROOT = ROOT / "logs/issue43/full68_x_domain_ab"
EXPECTED_PAGES = 68
UPSTREAM_MANIFEST_SCHEMA = "issue43.probe_x_domain_upstream_manifest.v1"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_commit() -> str:
    value = os.environ.get("ISSUE43_SOURCE_COMMIT", "").strip()
    if len(value) != 40 or any(ch not in "0123456789abcdefABCDEF" for ch in value):
        raise RuntimeError(
            "ISSUE43_SOURCE_COMMIT must contain the 40-character host Git commit. "
            "Use experiments/issue43/run_full68_x_domain_ab.sh to launch the harness."
        )
    return value.lower()


def _canonical_images() -> list[Path]:
    from tools.issue120 import eval_full68_from_intermediates as full68_eval

    images = [
        ROOT / "data/evaluation2/images" / score / f"{page}.png"
        for score, pages in full68_eval.SCORES.items()
        for page in pages
    ]
    if len(images) != EXPECTED_PAGES:
        raise RuntimeError(
            f"Canonical evaluation2 manifest drifted: expected={EXPECTED_PAGES} actual={len(images)}"
        )
    missing = [str(path) for path in images if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing canonical evaluation2 images:\n" + "\n".join(missing))
    return images


def _group_images_by_score(images: Sequence[Path]) -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = {}
    for image in images:
        groups.setdefault(image.parent.name, []).append(image)
    return groups


def _expected_page_keys(images: Sequence[Path]) -> set[tuple[str, str]]:
    return {(image.parent.name, image.stem) for image in images}


def _validate_inventory(path: Path, *, images: Sequence[Path]) -> dict[str, Any]:
    payload = _load_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Inventory must be a JSON object: {path}")
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError(f"Inventory lacks records list: {path}")
    if len(records) != len(images):
        raise ValueError(
            f"Inventory page count mismatch: expected={len(images)} actual={len(records)} path={path}"
        )

    expected = _expected_page_keys(images)
    actual: set[tuple[str, str]] = set()
    for record in records:
        if not isinstance(record, Mapping):
            raise ValueError(f"Inventory record is not an object: {record!r}")
        key = (str(record.get("score")), str(record.get("page")))
        if key in actual:
            raise ValueError(f"Duplicate inventory page: {key[0]}/{key[1]}")
        actual.add(key)
        for field in ("image", "hybrid_predictions", "staff_mask", "clef_mask"):
            raw = record.get(field)
            if not raw or not Path(str(raw)).is_file():
                raise FileNotFoundError(f"Inventory {key[0]}/{key[1]} missing {field}: {raw}")

    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(f"Inventory page set mismatch: missing={missing} extra={extra}")
    return payload


def _load_canonical_config(path: Path) -> dict[str, Any]:
    from src.pipeline.core.config import load_yaml

    config = load_yaml(path)
    if not isinstance(config, dict):
        raise ValueError(f"Config must be a mapping: {path}")
    detection = config.get("detection")
    if not isinstance(detection, dict):
        raise ValueError(f"Config lacks detection mapping: {path}")
    if detection.get("detector_route") != "dense_full_pipeline":
        raise ValueError("Issue #43 full68 A/B requires detector_route=dense_full_pipeline")
    if detection.get("homr_profile") != "maintained_original":
        raise ValueError(
            "Issue #43 full68 A/B requires current production homr_profile=maintained_original; "
            f"got {detection.get('homr_profile')!r}"
        )
    if detection.get("cnn_apply_nms") is not False:
        raise ValueError("Issue #43 full68 A/B requires production cnn_apply_nms=false")
    return config


def _generate_current_upstream_manifest(
    *,
    config: Mapping[str, Any],
    image_groups: Mapping[str, Sequence[Path]],
    run_root: Path,
    run_tag: str,
) -> tuple[Path, list[dict[str, Any]]]:
    from src.pipeline.detection import run_detection_step

    production_runs: list[dict[str, Any]] = []
    manifest_groups: list[dict[str, Any]] = []
    hybrid_root = run_root / "upstream_hybrid"

    for score, score_images in image_groups.items():
        score_config = copy.deepcopy(dict(config))
        detection = score_config["detection"]
        assert isinstance(detection, dict)
        detection["scan_x_domain_mode"] = "full_width"
        detection.pop("scan_x_domain_pad", None)
        detection.pop("scan_x_domain_pad_unit_ratio", None)
        detection["probe_scan_collect_stats"] = True
        detection["hybrid_output_root"] = str(hybrid_root)

        score_run_id = f"{run_tag}__upstream__{score}"
        score_run_root = run_root / "upstream_production_runs" / score
        started = time.perf_counter()
        result = run_detection_step(
            score_config,
            list(score_images),
            [image.stem for image in score_images],
            score_run_id,
            score_run_root,
            dry_run=False,
        )
        elapsed = time.perf_counter() - started

        if result.get("detector_route") != "dense_full_pipeline":
            raise RuntimeError(f"Unexpected detector route for {score}: {result}")
        if result.get("homr_profile") != "maintained_original":
            raise RuntimeError(f"Unexpected HOMR profile for {score}: {result}")

        inventory = (
            score_run_root / "intermediate" / "dense_full_pipeline_inputs" / "inventory.json"
        )
        _validate_inventory(inventory, images=score_images)
        production_runs.append(
            {
                "score": score,
                "page_count": len(score_images),
                "run_id": score_run_id,
                "run_root": str(score_run_root),
                "hybrid_output_dir": str(result["hybrid_output_dir"]),
                "probe_output_dir": str(result["probe_output_dir"]),
                "elapsed_seconds": elapsed,
                "inventory": str(inventory),
                "inventory_sha256": _sha256(inventory),
            }
        )
        manifest_groups.append(
            {
                "score": score,
                "page_count": len(score_images),
                "inventory": str(inventory),
                "inventory_sha256": _sha256(inventory),
            }
        )

    manifest_path = run_root / "retained_upstream_manifest.json"
    _write_json(
        manifest_path,
        {
            "schema_version": UPSTREAM_MANIFEST_SCHEMA,
            "source_commit": _source_commit(),
            "groups": manifest_groups,
        },
    )
    return manifest_path, production_runs


def _validate_upstream_manifest(
    path: Path,
    *,
    image_groups: Mapping[str, Sequence[Path]],
) -> list[dict[str, Any]]:
    payload = _load_json(path)
    if not isinstance(payload, Mapping):
        raise ValueError(f"Upstream manifest must be an object: {path}")
    if payload.get("schema_version") != UPSTREAM_MANIFEST_SCHEMA:
        raise ValueError(f"Unsupported upstream manifest schema: {payload.get('schema_version')!r}")
    groups = payload.get("groups")
    if not isinstance(groups, list):
        raise ValueError(f"Upstream manifest lacks groups list: {path}")

    by_score: dict[str, dict[str, Any]] = {}
    for group in groups:
        if not isinstance(group, Mapping):
            raise ValueError(f"Invalid upstream group: {group!r}")
        score = str(group.get("score"))
        if score in by_score:
            raise ValueError(f"Duplicate upstream score group: {score}")
        by_score[score] = dict(group)

    if set(by_score) != set(image_groups):
        raise ValueError(
            "Upstream manifest score set mismatch: "
            f"expected={sorted(image_groups)} actual={sorted(by_score)}"
        )

    validated: list[dict[str, Any]] = []
    for score, score_images in image_groups.items():
        group = by_score[score]
        inventory = Path(str(group.get("inventory")))
        if not inventory.is_file():
            raise FileNotFoundError(inventory)
        _validate_inventory(inventory, images=score_images)
        expected_sha = group.get("inventory_sha256")
        actual_sha = _sha256(inventory)
        if expected_sha and str(expected_sha) != actual_sha:
            raise RuntimeError(
                f"Retained inventory digest changed for {score}: "
                f"expected={expected_sha} actual={actual_sha}"
            )
        validated.append(
            {
                "score": score,
                "page_count": len(score_images),
                "inventory": str(inventory),
                "inventory_sha256": actual_sha,
            }
        )
    return validated


def _resolve_production_cnn(config: Mapping[str, Any]) -> tuple[Path, float]:
    from src.pipeline.detection.restored_orchestrator import _resolve_verified_cnn_artifact

    detection = config["detection"]
    assert isinstance(detection, Mapping)
    manifest = detection.get("cnn_model_manifest")
    threshold = detection.get("cnn_threshold")
    if not manifest or threshold is None:
        raise ValueError("Canonical config must define cnn_model_manifest and cnn_threshold")
    model_path = _resolve_verified_cnn_artifact(
        str(manifest),
        cnn_threshold=float(threshold),
    )
    return model_path, float(threshold)


def _evaluation_args(
    *,
    results_dir: Path,
    output_dir: Path,
    score_threshold: float,
) -> Namespace:
    from tools.issue120 import eval_full68_from_intermediates as full68_eval

    return Namespace(
        results_dir=str(results_dir),
        gt_root=str(ROOT / "data/evaluation2/annotations"),
        output_dir=str(output_dir),
        scored_file="pipeline2_no_peak_filtered_cnn.json",
        candidates_file="pipeline2_no_peak_candidates.json",
        score_threshold=score_threshold,
        rule_name="center_anchor",
        vov_threshold=0.5,
        staff_units_json=str(ROOT / "data/evaluation2/staff_units.json"),
        image_root=str(ROOT / "data/evaluation2/images"),
        xdist_unit_ratio=full68_eval.CENTER_ANCHOR_XDIST_UNIT_RATIO,
        legacy_fixed_12px=False,
        allow_partial=False,
        measure_summary_json=None,
    )


def _sum_generation_stats(groups: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    full_width_columns = sum(int(group.get("full_width_columns", 0)) for group in groups)
    eligible_domain_columns = sum(int(group.get("eligible_domain_columns", 0)) for group in groups)
    projected_columns = sum(int(group.get("projected_columns", 0)) for group in groups)
    return {
        "probe_elapsed_seconds_total": sum(
            float(group.get("probe_elapsed_seconds_total", 0.0)) for group in groups
        ),
        "full_width_columns": full_width_columns,
        "eligible_domain_columns": eligible_domain_columns,
        "projected_columns": projected_columns,
        "eligible_width_ratio": (
            eligible_domain_columns / float(full_width_columns) if full_width_columns else 1.0
        ),
        "projected_width_ratio": (
            projected_columns / float(full_width_columns) if full_width_columns else 1.0
        ),
    }


def _sum_rescue_stats(groups: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    full_width_columns = sum(int(group.get("full_width_columns", 0)) for group in groups)
    eligible_domain_columns = sum(int(group.get("eligible_domain_columns", 0)) for group in groups)
    projected_columns = sum(int(group.get("projected_columns", 0)) for group in groups)
    full_width_domain_count = 0
    band_count = 0
    raw_peak_count = 0
    selected_peak_count = 0
    candidate_count = 0

    for group in groups:
        for page in group.get("pages", []):
            if not isinstance(page, Mapping):
                continue
            stats = page.get("detector_stats")
            if not isinstance(stats, Mapping):
                continue
            full_width_domain_count += int(stats.get("full_width_domain_count", 0))
            band_count += int(stats.get("band_count", 0))
            raw_peak_count += int(stats.get("raw_peak_count", 0))
            selected_peak_count += int(stats.get("selected_peak_count", 0))
            candidate_count += int(stats.get("candidate_count", 0))

    return {
        "total_detect_elapsed_seconds": sum(
            float(group.get("total_detect_elapsed_seconds", 0.0)) for group in groups
        ),
        "full_width_columns": full_width_columns,
        "eligible_domain_columns": eligible_domain_columns,
        "projected_columns": projected_columns,
        "eligible_width_ratio": (
            eligible_domain_columns / float(full_width_columns) if full_width_columns else 1.0
        ),
        "projected_width_ratio": (
            projected_columns / float(full_width_columns) if full_width_columns else 1.0
        ),
        "full_width_domain_count": full_width_domain_count,
        "band_count": band_count,
        "raw_peak_count": raw_peak_count,
        "selected_peak_count": selected_peak_count,
        "candidate_count": candidate_count,
    }


def _copy_tree(source: Path, destination: Path) -> None:
    if source.exists():
        shutil.copytree(source, destination, dirs_exist_ok=True)


def _run_downstream_variant(
    *,
    name: str,
    config: Mapping[str, Any],
    image_groups: Mapping[str, Sequence[Path]],
    upstream_groups: Sequence[Mapping[str, Any]],
    exclude: Path,
    variant_root: Path,
    probe_x_domain_kwargs: Mapping[str, Any],
    model_path: Path,
    score_threshold: float,
) -> dict[str, Any]:
    from src.pipeline.detector_routes.dense_full_pipeline import (
        reconstruct_dense_full_pipeline_route,
    )
    from src.pipeline.steps.cnn_scoring import run_cnn_scoring_batch
    from tools.issue120 import eval_full68_from_intermediates as full68_eval

    upstream_by_score = {str(group["score"]): group for group in upstream_groups}
    aggregate_raw = variant_root / "aggregate_raw_candidates"
    aggregate_filtered = variant_root / "aggregate_filtered_candidates"
    aggregate_probe = variant_root / "aggregate_probe_output"

    group_reports: list[dict[str, Any]] = []
    generation_stats: list[Mapping[str, Any]] = []
    rescue_stats: list[Mapping[str, Any]] = []
    total_started = time.perf_counter()

    detection = config["detection"]
    assert isinstance(detection, Mapping)

    for score, score_images in image_groups.items():
        upstream = upstream_by_score[score]
        inventory = Path(str(upstream["inventory"]))
        score_root = variant_root / "groups" / score

        reconstruction_started = time.perf_counter()
        route = reconstruct_dense_full_pipeline_route(
            inventory=inventory,
            exclude=exclude,
            route_root=score_root / "route",
            expected_pages=len(score_images),
            probe_x_domain_kwargs=dict(probe_x_domain_kwargs),
            collect_probe_stats=True,
        )
        reconstruction_elapsed = time.perf_counter() - reconstruction_started

        scoring_started = time.perf_counter()
        scored = run_cnn_scoring_batch(
            probe_output_root=route.probe_rescue_root,
            images=score_images,
            model_path=model_path,
            threshold=score_threshold,
            score_name=score,
            batch_size=int(detection.get("cnn_batch_size", 64)),
            bands_from=route.filtered_root,
            staff_vov_threshold=float(detection.get("staff_vov_threshold", 0.5)),
            crop_recenter_on_bbox_ink=bool(detection.get("crop_recenter_on_bbox_ink", False)),
            crop_recenter_max_shift_unit_ratio=float(
                detection.get("crop_recenter_max_shift_unit_ratio", 0.35)
            ),
            input_image_scale=1.0,
            apply_nms_enabled=False,
        )
        scoring_elapsed = time.perf_counter() - scoring_started
        if scored != len(score_images):
            raise RuntimeError(
                f"{name}/{score}: CNN scoring processed {scored}/{len(score_images)} pages"
            )

        dense_root = score_root / "route" / "dense_candidate_reconstruction"
        group_generation = _load_json(dense_root / "probe_generation_summary.json")
        group_rescue = _load_json(
            dense_root / "probe_rescue_candidates" / "probe_scan_stats_summary.json"
        )
        generation_stats.append(group_generation)
        rescue_stats.append(group_rescue)

        _copy_tree(dense_root / "probe_candidates_from_inventory", aggregate_raw)
        _copy_tree(dense_root / "probe_candidates_filtered", aggregate_filtered)
        _copy_tree(route.probe_rescue_root, aggregate_probe)

        group_reports.append(
            {
                "score": score,
                "page_count": len(score_images),
                "inventory": str(inventory),
                "route_root": str(score_root / "route"),
                "probe_rescue_root": str(route.probe_rescue_root),
                "reconstruction_seconds": reconstruction_elapsed,
                "cnn_scoring_seconds": scoring_elapsed,
                "generation_stats": group_generation,
                "rescue_stats": group_rescue,
                "execution_summary": route.execution_summary,
            }
        )

    evaluation_started = time.perf_counter()
    evaluation = full68_eval.evaluate(
        _evaluation_args(
            results_dir=aggregate_probe,
            output_dir=variant_root / "eval",
            score_threshold=score_threshold,
        )
    )
    evaluation_elapsed = time.perf_counter() - evaluation_started

    return {
        "name": name,
        "probe_x_domain_kwargs": dict(probe_x_domain_kwargs),
        "raw_candidates_root": str(aggregate_raw),
        "filtered_candidates_root": str(aggregate_filtered),
        "probe_rescue_root": str(aggregate_probe),
        "detector_summary": asdict(evaluation.detector_summary),
        "timing": {
            "reconstruction_seconds": sum(
                float(group["reconstruction_seconds"]) for group in group_reports
            ),
            "cnn_scoring_seconds": sum(
                float(group["cnn_scoring_seconds"]) for group in group_reports
            ),
            "evaluation_seconds": evaluation_elapsed,
            "total_downstream_seconds": time.perf_counter() - total_started,
        },
        "generation_stats": _sum_generation_stats(generation_stats),
        "rescue_stats": _sum_rescue_stats(rescue_stats),
        "groups": group_reports,
    }


def _normalize_box(item: Any) -> tuple[int, int, int, int] | None:
    if isinstance(item, list) and len(item) == 4:
        return tuple(int(round(float(value))) for value in item)
    if isinstance(item, Mapping):
        box = (
            item.get("barline_location")
            or item.get("orig_bbox")
            or item.get("pred_bbox")
            or item.get("bbox")
        )
        if isinstance(box, list) and len(box) == 4:
            return tuple(int(round(float(value))) for value in box)
    return None


def _box_set(path: Path) -> set[tuple[int, int, int, int]]:
    payload = _load_json(path)
    if isinstance(payload, Mapping):
        payload = payload.get("predictions", payload.get("boxes", payload))
    if not isinstance(payload, list):
        raise ValueError(f"Box payload must be a list: {path}")
    boxes = {_normalize_box(item) for item in payload}
    return {box for box in boxes if box is not None}


def _box_files(root: Path, filename: str) -> dict[str, Path]:
    return {str(path.relative_to(root)): path for path in sorted(root.rglob(filename))}


def _compare_box_roots(
    *,
    full_width_root: Path,
    staff_mask_root: Path,
    filename: str,
) -> dict[str, Any]:
    left_files = _box_files(full_width_root, filename)
    right_files = _box_files(staff_mask_root, filename)
    all_keys = sorted(set(left_files) | set(right_files))

    full_total = 0
    staff_total = 0
    removed_total = 0
    added_total = 0
    changes: list[dict[str, Any]] = []

    for key in all_keys:
        left = _box_set(left_files[key]) if key in left_files else set()
        right = _box_set(right_files[key]) if key in right_files else set()
        removed = sorted(left - right)
        added = sorted(right - left)
        full_total += len(left)
        staff_total += len(right)
        removed_total += len(removed)
        added_total += len(added)
        if removed or added or key not in left_files or key not in right_files:
            changes.append(
                {
                    "path": key,
                    "full_width_count": len(left),
                    "staff_mask_count": len(right),
                    "removed_count": len(removed),
                    "added_count": len(added),
                    "removed_boxes": removed,
                    "added_boxes": added,
                }
            )

    return {
        "file_count_full_width": len(left_files),
        "file_count_staff_mask": len(right_files),
        "full_width_total": full_total,
        "staff_mask_total": staff_total,
        "removed_total": removed_total,
        "added_total": added_total,
        "changed_files": len(changes),
        "changes": changes,
    }


def _accuracy_not_worse(
    full_width: Mapping[str, Any],
    staff_mask: Mapping[str, Any],
) -> bool:
    return (
        int(staff_mask["tp"]) >= int(full_width["tp"])
        and int(staff_mask["fp"]) <= int(full_width["fp"])
        and int(staff_mask["fn"]) <= int(full_width["fn"])
    )


def _build_comparison(
    full_width: Mapping[str, Any],
    staff_mask: Mapping[str, Any],
) -> dict[str, Any]:
    stage_roots = {
        "raw_candidates": (
            Path(str(full_width["raw_candidates_root"])),
            Path(str(staff_mask["raw_candidates_root"])),
            "pipeline2_no_peak_candidates.json",
        ),
        "filtered_candidates": (
            Path(str(full_width["filtered_candidates_root"])),
            Path(str(staff_mask["filtered_candidates_root"])),
            "pipeline2_no_peak_candidates.json",
        ),
        "probe_rescue_candidates": (
            Path(str(full_width["probe_rescue_root"])),
            Path(str(staff_mask["probe_rescue_root"])),
            "pipeline2_no_peak_candidates.json",
        ),
        "final_detector_boxes": (
            Path(str(full_width["probe_rescue_root"])),
            Path(str(staff_mask["probe_rescue_root"])),
            "pipeline2_no_peak_filtered_cnn.json",
        ),
    }
    stages = {
        stage_name: _compare_box_roots(
            full_width_root=roots[0],
            staff_mask_root=roots[1],
            filename=roots[2],
        )
        for stage_name, roots in stage_roots.items()
    }

    full_summary = full_width["detector_summary"]
    staff_summary = staff_mask["detector_summary"]
    assert isinstance(full_summary, Mapping)
    assert isinstance(staff_summary, Mapping)

    generation = staff_mask["generation_stats"]
    rescue = staff_mask["rescue_stats"]
    assert isinstance(generation, Mapping)
    assert isinstance(rescue, Mapping)

    full_columns = int(generation.get("full_width_columns", 0))
    projected_columns = int(generation.get("projected_columns", 0))
    projected_ratio = projected_columns / float(full_columns) if full_columns else 1.0

    return {
        "detector_summary_equal": dict(full_summary) == dict(staff_summary),
        "accuracy_not_worse": _accuracy_not_worse(full_summary, staff_summary),
        "stages": stages,
        "projection_reduction": {
            "full_width_columns": full_columns,
            "staff_mask_projected_columns": projected_columns,
            "projected_width_ratio": projected_ratio,
            "projected_width_reduction_ratio": 1.0 - projected_ratio,
            "rescue_projected_width_ratio": rescue.get("projected_width_ratio"),
            "rescue_full_width_domain_count": rescue.get("full_width_domain_count"),
            "rescue_band_count": rescue.get("band_count"),
        },
        "candidate_reduction_observed": any(
            stages[stage_name]["removed_total"] > stages[stage_name]["added_total"]
            for stage_name in (
                "raw_candidates",
                "filtered_candidates",
                "probe_rescue_candidates",
            )
        ),
        "final_detector_boxes_equal": stages["final_detector_boxes"]["changed_files"] == 0,
    }


def run(args: argparse.Namespace) -> Path:
    config_path = args.config.resolve()
    config = _load_canonical_config(config_path)
    images = _canonical_images()
    image_groups = _group_images_by_score(images)

    output_root = args.output_root.resolve()
    run_root = output_root / args.run_tag
    if run_root.exists() and any(run_root.iterdir()):
        raise FileExistsError(run_root)
    run_root.mkdir(parents=True, exist_ok=True)

    provenance: dict[str, Any] = {
        "schema_version": "issue43.probe_x_domain_full68_ab.v2",
        "source_commit": _git_head(),
        "config": str(config_path),
        "config_sha256": _sha256(config_path),
        "homr_profile": config["detection"]["homr_profile"],
        "detector_route": config["detection"]["detector_route"],
        "page_count": len(images),
        "score_count": len(image_groups),
        "same_upstream_inventory_for_both_variants": True,
        "score_isolated_downstream_reconstruction": True,
    }

    if args.upstream_manifest is None:
        manifest_path, production_runs = _generate_current_upstream_manifest(
            config=config,
            image_groups=image_groups,
            run_root=run_root,
            run_tag=args.run_tag,
        )
        provenance["upstream_mode"] = "fresh_current_production_once_per_score"
        provenance["production_runs"] = production_runs
    else:
        manifest_path = args.upstream_manifest.resolve()
        provenance["upstream_mode"] = "retained_upstream_manifest"
        provenance["production_runs"] = []

    upstream_groups = _validate_upstream_manifest(
        manifest_path,
        image_groups=image_groups,
    )
    provenance["upstream_manifest"] = str(manifest_path)
    provenance["upstream_manifest_sha256"] = _sha256(manifest_path)
    provenance["upstream_groups"] = upstream_groups

    exclude = run_root / "exclude.json"
    _write_json(exclude, {"excluded_pages": []})

    model_path, score_threshold = _resolve_production_cnn(config)
    provenance["cnn_model"] = str(model_path)
    provenance["cnn_model_sha256"] = _sha256(model_path)
    provenance["cnn_threshold"] = score_threshold

    full_width = _run_downstream_variant(
        name="full_width",
        config=config,
        image_groups=image_groups,
        upstream_groups=upstream_groups,
        exclude=exclude,
        variant_root=run_root / "full_width",
        probe_x_domain_kwargs={"scan_x_domain_mode": "full_width"},
        model_path=model_path,
        score_threshold=score_threshold,
    )
    staff_mask = _run_downstream_variant(
        name="staff_mask",
        config=config,
        image_groups=image_groups,
        upstream_groups=upstream_groups,
        exclude=exclude,
        variant_root=run_root / "staff_mask",
        probe_x_domain_kwargs={
            "scan_x_domain_mode": "staff_mask",
            "scan_x_domain_pad_unit_ratio": args.staff_mask_pad_unit_ratio,
        },
        model_path=model_path,
        score_threshold=score_threshold,
    )

    comparison = _build_comparison(full_width, staff_mask)
    report = {
        "provenance": provenance,
        "variants": {
            "full_width": full_width,
            "staff_mask": staff_mask,
        },
        "comparison": comparison,
    }
    report_path = run_root / "issue43_full68_x_domain_ab_report.json"
    _write_json(report_path, report)

    print(
        json.dumps(
            {
                "status": "completed",
                "report": str(report_path),
                "detector_summary_equal": comparison["detector_summary_equal"],
                "accuracy_not_worse": comparison["accuracy_not_worse"],
                "final_detector_boxes_equal": comparison["final_detector_boxes_equal"],
                "candidate_reduction_observed": comparison["candidate_reduction_observed"],
                "projected_width_ratio": comparison["projection_reduction"][
                    "projected_width_ratio"
                ],
            },
            indent=2,
        )
    )
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-tag", required=True)
    parser.add_argument("--config", type=Path, default=CANONICAL_CONFIG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--upstream-manifest",
        type=Path,
        help=(
            "Reuse a retained Issue #43 current-production per-score upstream manifest "
            "and skip the expensive HOMR/SR upstream generation."
        ),
    )
    parser.add_argument(
        "--staff-mask-pad-unit-ratio",
        type=float,
        default=1.0,
    )
    args = parser.parse_args()
    try:
        run(args)
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
                ensure_ascii=False,
            )
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
