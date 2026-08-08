#!/usr/bin/env python3
"""Replay historical Stage E from retained fresh public-baseline sources.

This temporary Issue #255 entry point does not run HOMR, SR HOMR, OMR-DLN, or
hybrid consensus. It consumes the already completed public-baseline A/B source
artifacts, rebuilds the Issue36 dense/filter/Issue53 route, and rescoring its
candidates with the canonical CNN and NMS disabled.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.pipeline.core.config import load_yaml
from src.pipeline.detector_routes.dense_full_pipeline import (
    FILTER_PARAMS,
    GENERATION_PARAMS,
    reconstruct_dense_full_pipeline_route,
)
from src.pipeline.steps.cnn_scoring import run_cnn_scoring_batch
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue252.probe_boundary import normalize_box, write_json
from tools.issue255.evaluate_focused_candidate_rescue import _match_box_details
from tools.issue255.run_focused_stage_e_reconstruction import (
    ACCEPTED,
    CANDIDATES,
    CONFIG,
    IMAGE_ROOT,
    ROOT,
    SCORED,
    TARGETS,
    _candidate_file,
    _drop_evidence,
    _first_loss,
    _git,
    _layer,
    _page_specs,
    _record,
    _scored,
    _scored_layer,
    _tree_record,
)

FRESH_CONTRACT = {
    "mode": "fresh_upstream",
    "fresh_upstream_authoritative": True,
    "override_keys": [],
}
STAFF_PATTERNS = (
    "{stem}_proxy_debug_3_staff.png",
    "{stem}_debug_3_staff.png",
    "{stem}_staff_mask.png",
)
CLEF_PATTERNS = (
    "{stem}_proxy_debug_7_clefs_keys.png",
    "{stem}_debug_7_clefs_keys.png",
    "{stem}_clefs_keys_mask.png",
    "{stem}_clef_mask.png",
    "{stem}_proxy_debug_2_clefs.png",
    "{stem}_debug_2_clefs.png",
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fresh_contract_matches(value: Any) -> bool:
    return isinstance(value, Mapping) and all(
        value.get(key) == expected for key, expected in FRESH_CONTRACT.items()
    )


def _resolve_repo_artifact(value: str | Path, root: Path = ROOT) -> Path:
    path = Path(value)
    if path.exists():
        return path.resolve()
    if path.is_absolute() and path.parts[:2] == ("/", "workspace"):
        return (root / path.relative_to("/workspace")).resolve()

    parts = path.parts
    indices = [index for index, part in enumerate(parts) if part == root.name]
    if indices:
        return (root / Path(*parts[indices[-1] + 1 :])).resolve()

    for marker in ("logs", "data", "configs", "tools", "external"):
        if marker in parts:
            index = parts.index(marker)
            return (root / Path(*parts[index:])).resolve()
    return path.resolve()


def _contract_artifact(contract: Mapping[str, Any], name: str) -> Path:
    artifacts = contract.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError("Public run contract lacks artifacts")
    record = artifacts.get(name)
    if not isinstance(record, Mapping) or not isinstance(record.get("path"), str):
        raise ValueError(f"Public run contract lacks artifact path: {name}")
    return _resolve_repo_artifact(record["path"])


def _find_historical_mask(
    directories: Sequence[Path],
    patterns: Sequence[str],
    *,
    stem: str,
    name: str,
) -> Path:
    for pattern in patterns:
        formatted = pattern.format(stem=stem)
        for directory in directories:
            candidate = directory / formatted
            if candidate.is_file():
                return candidate.resolve()
    raise FileNotFoundError(
        f"Historical-compatible {name} missing for {stem} under "
        f"{[str(path) for path in directories]}"
    )


def _validate_public_run(
    run: Mapping[str, Any],
    page: Mapping[str, Any],
) -> dict[str, Any]:
    contract = run.get("contract")
    if not isinstance(contract, Mapping) or contract.get("status") != "completed":
        raise ValueError(f"Incomplete public run: {run.get('label')}")
    if contract.get("variant") != "public_baseline":
        raise ValueError(f"Expected public-baseline run: {run.get('label')}")
    fresh = contract.get("detector_input_contract")
    if not _fresh_contract_matches(fresh):
        raise ValueError(f"Fresh contract mismatch: {run.get('label')}")

    handoff = contract.get("baseline_profile_handoff")
    if not isinstance(handoff, Mapping) or handoff.get("status") != "completed":
        raise ValueError(f"Incomplete baseline handoff: {run.get('label')}")
    if handoff.get("freshly_generated") is not True:
        raise ValueError(f"Baseline was not freshly generated: {run.get('label')}")
    if handoff.get("historical_artifact_used_as_runtime_input") is not False:
        raise ValueError(f"Historical runtime input detected: {run.get('label')}")

    score = str(run.get("score"))
    page_id = str(run.get("page"))
    if score != page["score"] or page_id != page["page"]:
        raise ValueError(
            f"Public run page mismatch: {score}/{page_id} != {page['score']}/{page['page']}"
        )

    image = _contract_artifact(contract, "image")
    baseline = _contract_artifact(contract, "fresh_baseline")
    sr = _contract_artifact(contract, "current_sr")
    omr = _contract_artifact(contract, "current_omr")
    hybrid = _contract_artifact(contract, "hybrid")
    public_final = _contract_artifact(contract, "cnn_accepted")
    required = (image, baseline, sr, omr, hybrid, public_final)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Public Stage E source artifacts missing: {missing}")

    expected_hash = str(handoff.get("detection_sha256"))
    actual_hash = _sha256(baseline)
    if actual_hash != expected_hash:
        raise ValueError(
            f"Public baseline hash mismatch: expected={expected_hash} actual={actual_hash}"
        )

    directories = (baseline.parent, sr.parent)
    staff = _find_historical_mask(
        directories,
        STAFF_PATTERNS,
        stem=page_id,
        name="staff mask",
    )
    clef = _find_historical_mask(
        directories,
        CLEF_PATTERNS,
        stem=page_id,
        name="clef mask",
    )
    return {
        "label": str(run.get("label")),
        "run_id": str(run.get("run_id")),
        "score": score,
        "page": page_id,
        "image": image,
        "baseline": baseline,
        "sr": sr,
        "omr": omr,
        "hybrid": hybrid,
        "staff_mask": staff,
        "clef_mask": clef,
        "public_final": public_final,
        "fresh_contract": dict(fresh),
        "handoff": dict(handoff),
    }


def _load_public_sources(
    batch_path: Path,
    pages: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    payload = _load(batch_path)
    if not isinstance(payload, Mapping) or payload.get("status") != "completed":
        raise ValueError("Public-baseline batch is incomplete")
    if payload.get("variant") != "public_baseline":
        raise ValueError("Expected public-baseline batch")
    runs = payload.get("runs")
    if not isinstance(runs, list) or len(runs) != len(pages):
        raise ValueError("Public-baseline batch page count mismatch")

    by_label = {str(run.get("label")): run for run in runs if isinstance(run, Mapping)}
    sources = {}
    for page in pages:
        label = str(page["label"])
        run = by_label.get(label)
        if not isinstance(run, Mapping):
            raise ValueError(f"Public-baseline batch lacks page: {label}")
        sources[label] = _validate_public_run(run, page)
    return sources


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
    public = _load_public_sources(args.public_batch.resolve(), pages)
    images = [page["image"] for page in pages]

    inventory = []
    for page in pages:
        source = public[page["label"]]
        if source["image"].resolve() != page["image"].resolve():
            raise ValueError(f"Source image mismatch for {page['label']}")
        inventory.append(
            {
                "score": page["score"],
                "page": page["page"],
                "image": str(page["image"]),
                "hybrid_predictions": str(source["hybrid"]),
                "staff_mask": str(source["staff_mask"]),
                "clef_mask": str(source["clef_mask"]),
                "run_dir": str(source["baseline"].parent),
            }
        )

    inventory_path = run_root / "public_baseline_fresh_inventory.json"
    exclude_path = run_root / "fresh_exclude.json"
    write_json(
        inventory_path,
        {
            "schema_version": "issue255.public_baseline_stage_e_inventory.v1",
            "historical_runtime_input": False,
            "source_batch": str(args.public_batch.resolve()),
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

    cnn_model = _resolve_repo_artifact(str(detection["cnn_model_path"]))
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
        label = page["label"]
        score = page["score"]
        page_id = page["page"]
        image = page["image"]
        source = public[label]
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
        required = (
            page["accepted"],
            source["public_final"],
            raw,
            filtered,
            suggestions,
            issue53,
            scored_path,
            final,
        )
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"Stage E replay artifacts missing: {missing}")

        accepted_boxes = load_json_boxes(page["accepted"])
        public_boxes = load_json_boxes(source["public_final"])
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
            layers["clef_mask_filtering"]["drop_evidence"] = _drop_evidence(
                suggestions,
                reference,
            )
            target_rows.append(
                {
                    **target,
                    "accepted_bbox": list(reference),
                    "public_pipeline_final": _layer(reference, public_boxes),
                    "layers": layers,
                    "first_loss_boundary": _first_loss(layers),
                }
            )

        public_metrics = _match_box_details(accepted_boxes, public_boxes)
        reconstructed_metrics = _match_box_details(accepted_boxes, final_boxes)
        page_reports[label] = {
            "score": score,
            "page": page_id,
            "coordinate_space": "original_input_pixels",
            "counts": {
                "dense_raw_candidate": len(raw_boxes),
                "clef_mask_filtering": len(filtered_boxes),
                "issue53_reconstruction": len(issue53_boxes),
                "cnn_scored": len(scored_rows),
                "cnn_accepted": len(final_boxes),
                "public_pipeline_final": len(public_boxes),
                "historical_stage_e_reference": len(accepted_boxes),
            },
            "metrics": {
                "public_pipeline": {key: public_metrics[key] for key in ("tp", "fp", "fn")},
                "reconstructed": {key: reconstructed_metrics[key] for key in ("tp", "fp", "fn")},
                "delta_vs_public_pipeline": {
                    key: reconstructed_metrics[key] - public_metrics[key]
                    for key in ("tp", "fp", "fn")
                },
            },
            "accepted_reference": _record(
                page["accepted"],
                role="evaluation_only_not_runtime_input",
            ),
            "source_contract": {
                "run_id": source["run_id"],
                "fresh_contract": source["fresh_contract"],
                "public_baseline_handoff": source["handoff"],
            },
            "artifacts": {
                "image": _record(image),
                "public_baseline": _record(source["baseline"]),
                "current_sr": _record(source["sr"]),
                "current_omr": _record(source["omr"]),
                "public_hybrid": _record(source["hybrid"]),
                "staff_mask": _record(source["staff_mask"]),
                "clef_mask": _record(source["clef_mask"]),
                "public_pipeline_final": _record(source["public_final"]),
                "dense_raw": _record(raw),
                "filtered": _record(filtered),
                "filter_suggestions": _record(suggestions),
                "issue53": _record(issue53),
                "cnn_scored": _record(scored_path),
                "cnn_accepted": _record(final),
            },
            "targets": target_rows,
        }

    targets = [target for page in page_reports.values() for target in page["targets"]]
    report = {
        "schema_version": "issue255.public_baseline_stage_e_reconstruction.v1",
        "status": "completed",
        "analysis_only": True,
        "restoration_scope_only": True,
        "cleanup_policy": "Temporary experiment code; clean up before final PR.",
        "run_tag": args.run_tag,
        "source_batch": _record(args.public_batch.resolve()),
        "reconstruction_contract": {
            **FRESH_CONTRACT,
            "fresh_public_baseline_generated_before_replay": True,
            "upstream_inference_repeated": False,
            "fresh_inventory_generated_for_replay": True,
            "historical_detector_candidate_runtime_inputs": [],
            "accepted_reference_runtime_input": False,
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
            "target_manifest": _record(
                args.targets.resolve(),
                role="evaluation_metadata_only",
            ),
            "fresh_inventory": _record(inventory_path),
            "cnn_model": _record(cnn_model),
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
                page["metrics"]["delta_vs_public_pipeline"]["fp"] <= 0
                for page in page_reports.values()
            ),
            "public_baselines_preserved": all(
                _sha256(source["baseline"]) == str(source["handoff"]["detection_sha256"])
                for source in public.values()
            ),
            "fresh_contract_exact": all(
                _fresh_contract_matches(source["fresh_contract"]) for source in public.values()
            ),
            "historical_runtime_artifact_dependency_absent": True,
            "upstream_gpu_rerun_performed": False,
        },
        "new_recovery_direction_introduced": False,
    }
    report_path = run_root / "public_baseline_stage_e_reconstruction_report.json"
    write_json(report_path, report)
    return {**report, "report_path": str(report_path)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-tag", required=True)
    parser.add_argument("--public-batch", type=Path, required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "logs/issue255_stage_e_public_baseline",
    )
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--targets", type=Path, default=TARGETS)
    parser.add_argument("--image-root", type=Path, default=IMAGE_ROOT)
    parser.add_argument("--expected-commit")
    parser.add_argument("--verbose-dense-logs", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args)
    print(
        json.dumps(
            {
                "status": report["status"],
                "gates": report["gates"],
                "report": report["report_path"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
