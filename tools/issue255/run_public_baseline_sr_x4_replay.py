#!/usr/bin/env python3
"""Replay the Issue #255 public baseline with explicit SR x4.

The runner reuses only the verified fresh public-baseline artifacts from the
prior A/B run, regenerates SR/OMR/consensus/probe/CNN with ``sr_scale=4``, and
compares the resulting SR and hybrid artifacts with retained historical
artifacts. Historical artifacts are analysis references only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import cv2
import yaml

from src.common import barline_iou
from src.pipeline.steps.hybrid_consensus import load_json_boxes
from tools.issue252.probe_boundary import normalize_box
from tools.issue255.inspect_stage_e_historical_upstream import (
    _inventory,
    _single_box_record,
)
from tools.issue255.run_public_baseline_ab import (
    PAGES,
    _container_path,
    _copy_model_into_container,
    _find_omr_model,
    _git,
    _require_executable,
    _run,
)
from tools.issue255.run_public_baseline_stage_e_reconstruction import (
    ROOT,
    _resolve_repo_artifact,
)

EXPECTED_BRANCH = "fix/issue255-fresh-detector-production-recovery"
DEFAULT_SOURCE_BATCH = (
    ROOT
    / "logs/issue255_public_baseline_ab/issue255_public_baseline_ab_02"
    / "issue255_public_baseline_batch_issue255_public_baseline_ab_02.json"
)
DEFAULT_HISTORICAL_COMPARISON = (
    ROOT
    / "logs/issue255_stage_e_focused/issue255_stage_e_focused_03"
    / "stage_e_historical_input_comparison.json"
)
DEFAULT_TARGET_REPORT = (
    ROOT
    / "logs/issue255_stage_e_public_baseline/issue255_public_stage_e_01"
    / "public_stage_e_consensus_counterfactual.json"
)
DEFAULT_OUTPUT_ROOT = ROOT / "logs/issue255_public_baseline_sr_x4"
WORKER = ROOT / "tools/issue255/run_public_baseline_sr_scale_variant.py"
ACCEPTED_IOU = 0.5


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
    }


def _boxes(path: Path) -> list[tuple[int, int, int, int]]:
    return [normalize_box(box) for box in load_json_boxes(path)]


def _box_comparison(
    actual: Sequence[Sequence[int | float]],
    reference: Sequence[Sequence[int | float]],
) -> dict[str, Any]:
    actual_set = {normalize_box(box) for box in actual}
    reference_set = {normalize_box(box) for box in reference}
    return {
        "actual_count": len(actual_set),
        "reference_count": len(reference_set),
        "exact_common_count": len(actual_set & reference_set),
        "actual_only_count": len(actual_set - reference_set),
        "reference_only_count": len(reference_set - actual_set),
        "exact_match": actual_set == reference_set,
    }


def _classification(
    *,
    sr_exact: bool,
    hybrid_exact: bool,
    image_shape_match: bool,
) -> str:
    if sr_exact and hybrid_exact:
        return "historical_sr_and_hybrid_reproduced"
    if hybrid_exact:
        return "historical_hybrid_reproduced_with_sr_set_difference"
    if image_shape_match:
        return "x4_image_geometry_restored_but_detection_or_hybrid_differs"
    return "x4_image_geometry_not_restored"


def _image_record(path: Path) -> dict[str, Any]:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise FileNotFoundError(f"Failed to read image: {path}")
    result = {
        **_record(path),
        "shape": [int(image.shape[0]), int(image.shape[1])],
        "mean": float(image.mean()),
        "stddev": float(image.std()),
    }
    del image
    return result


def _target_boxes(page: Mapping[str, Any]) -> dict[str, list[tuple[int, int, int, int]]]:
    payload = page.get("target_cluster_members")
    result = {"historical": [], "public": []}
    if not isinstance(payload, Mapping):
        return result
    for side in result:
        rows = payload.get(side)
        if not isinstance(rows, list):
            continue
        for row in rows:
            bbox = row.get("bbox") if isinstance(row, Mapping) else None
            if isinstance(bbox, Sequence) and not isinstance(bbox, (str, bytes)):
                result[side].append(normalize_box(bbox))
    return result


def _target_support(
    targets: Mapping[str, Sequence[tuple[int, int, int, int]]],
    sr_boxes: Sequence[tuple[int, int, int, int]],
    hybrid_boxes: Sequence[tuple[int, int, int, int]],
) -> dict[str, list[dict[str, Any]]]:
    hybrid_set = set(hybrid_boxes)
    result: dict[str, list[dict[str, Any]]] = {}
    for side, boxes in targets.items():
        result[side] = []
        for bbox in boxes:
            supported = any(barline_iou(bbox, candidate) > ACCEPTED_IOU for candidate in sr_boxes)
            result[side].append(
                {
                    "bbox": list(bbox),
                    "sr_supported": supported,
                    "included_in_hybrid": bbox in hybrid_set,
                }
            )
    return result


def _historical_paths(
    page: Mapping[str, Any],
    label: str,
) -> dict[str, Path]:
    record = page.get("historical_inventory_record")
    if not isinstance(record, Mapping):
        raise ValueError(f"Missing historical inventory record: {label}")
    run_dir_value = record.get("run_dir")
    if not isinstance(run_dir_value, (str, Path)):
        raise ValueError(f"Missing historical run directory: {label}")
    run_dir = _resolve_repo_artifact(run_dir_value)
    if not run_dir.is_dir():
        raise FileNotFoundError(run_dir)
    rows = _inventory(run_dir)
    result: dict[str, Path] = {}
    for stage in ("sr", "hybrid"):
        stage_record = _single_box_record(rows, stage)
        if stage_record is None:
            raise ValueError(f"Expected one historical {stage} artifact: {label}")
        path = _resolve_repo_artifact(str(stage_record["path"]))
        if not path.is_file():
            raise FileNotFoundError(path)
        result[stage] = path
    image = result["sr"].parent / f"{page['page']}.png"
    if not image.is_file():
        raise FileNotFoundError(image)
    result["image"] = image
    return result


def _source_runs(batch: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    runs = batch.get("runs")
    if not isinstance(runs, list):
        raise ValueError("Source public-baseline batch lacks runs")
    result = {}
    for run in runs:
        if isinstance(run, Mapping):
            result[str(run.get("label"))] = run
    return result


def _prepare_replayed_handoff(
    *,
    source_run: Mapping[str, Any],
    destination_baseline: Path,
    output: Path,
    sr_scale: int,
) -> dict[str, Any]:
    contract = source_run.get("contract")
    if not isinstance(contract, Mapping):
        raise ValueError("Source run lacks contract")
    handoff = contract.get("baseline_profile_handoff")
    if not isinstance(handoff, Mapping):
        raise ValueError("Source run lacks public-baseline handoff")
    source_detection_value = handoff.get("detection_path")
    if not isinstance(source_detection_value, (str, Path)):
        raise ValueError("Source handoff lacks detection path")
    source_detection = _resolve_repo_artifact(source_detection_value)
    source_baseline = source_detection.parents[2]
    if not source_baseline.is_dir():
        raise FileNotFoundError(source_baseline)
    if destination_baseline.parent.exists():
        raise FileExistsError(destination_baseline.parent)
    destination_baseline.parent.mkdir(parents=True)
    shutil.copytree(source_baseline, destination_baseline)
    relative_detection = source_detection.relative_to(source_baseline)
    destination_detection = destination_baseline / relative_detection
    if not destination_detection.is_file():
        raise FileNotFoundError(destination_detection)

    replay = dict(handoff)
    replay["detection_path"] = _container_path(destination_detection)
    replay["detection_sha256"] = _sha256(destination_detection)
    replay["replayed_public_baseline_source"] = str(source_detection)
    replay["replay_sr_scale"] = sr_scale
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(replay, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return replay


def _analyze(
    *,
    contracts: Mapping[str, Mapping[str, Any]],
    historical_comparison: Path,
    target_report: Path,
) -> dict[str, Any]:
    comparison = _load(historical_comparison)
    targets = _load(target_report)
    comparison_pages = comparison.get("pages")
    target_pages = targets.get("pages")
    if not isinstance(comparison_pages, Mapping) or not isinstance(target_pages, Mapping):
        raise ValueError("Analysis source reports lack page mappings")

    pages: dict[str, Any] = {}
    for label, contract in contracts.items():
        historical_page = comparison_pages.get(label)
        target_page = target_pages.get(label)
        if not isinstance(historical_page, Mapping) or not isinstance(target_page, Mapping):
            raise ValueError(f"Missing analysis source page: {label}")
        historical = _historical_paths(historical_page, label)
        artifacts = contract.get("artifacts")
        if not isinstance(artifacts, Mapping):
            raise ValueError(f"Replay contract lacks artifacts: {label}")

        def artifact_path(name: str) -> Path:
            record = artifacts.get(name)
            value = record.get("path") if isinstance(record, Mapping) else None
            if not isinstance(value, (str, Path)):
                raise ValueError(f"Replay artifact path missing: {label}.{name}")
            path = _resolve_repo_artifact(value)
            if not path.is_file():
                raise FileNotFoundError(path)
            return path

        replay_sr = artifact_path("current_sr")
        replay_hybrid = artifact_path("hybrid")
        replay_image = artifact_path("probe_image")
        historical_sr_boxes = _boxes(historical["sr"])
        historical_hybrid_boxes = _boxes(historical["hybrid"])
        replay_sr_boxes = _boxes(replay_sr)
        replay_hybrid_boxes = _boxes(replay_hybrid)
        sr_comparison = _box_comparison(replay_sr_boxes, historical_sr_boxes)
        hybrid_comparison = _box_comparison(
            replay_hybrid_boxes,
            historical_hybrid_boxes,
        )
        historical_image = _image_record(historical["image"])
        replay_image_record = _image_record(replay_image)
        shape_match = historical_image["shape"] == replay_image_record["shape"]
        pages[label] = {
            "score": historical_page.get("score"),
            "page": historical_page.get("page"),
            "classification": _classification(
                sr_exact=bool(sr_comparison["exact_match"]),
                hybrid_exact=bool(hybrid_comparison["exact_match"]),
                image_shape_match=shape_match,
            ),
            "sr_image_comparison": {
                "same_shape": shape_match,
                "byte_exact": historical_image["sha256"] == replay_image_record["sha256"],
                "historical": historical_image,
                "replay": replay_image_record,
            },
            "sr_detection_comparison": sr_comparison,
            "hybrid_comparison": hybrid_comparison,
            "target_support": _target_support(
                _target_boxes(target_page),
                replay_sr_boxes,
                replay_hybrid_boxes,
            ),
            "paths": {
                "historical_sr": str(historical["sr"]),
                "historical_hybrid": str(historical["hybrid"]),
                "replay_sr": str(replay_sr),
                "replay_hybrid": str(replay_hybrid),
            },
        }
    return pages


def run(args: argparse.Namespace) -> Path:
    for command in ("docker", "git"):
        _require_executable(command)
    if _git("branch", "--show-current") != EXPECTED_BRANCH:
        raise RuntimeError(f"Expected branch {EXPECTED_BRANCH}")
    if _git("status", "--short", "--untracked-files=no"):
        raise RuntimeError("Tracked working tree must be clean before replay")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", args.run_tag):
        raise ValueError("--run-tag contains unsupported characters")
    if not WORKER.is_file():
        raise FileNotFoundError(WORKER)

    source_batch = _load(args.source_public_batch.resolve())
    if not isinstance(source_batch, Mapping) or source_batch.get("status") != "completed":
        raise ValueError("Source public-baseline batch is incomplete")
    source_runs = _source_runs(source_batch)
    run_root = args.output_root.resolve() / args.run_tag
    if run_root.exists():
        raise FileExistsError(run_root)
    (run_root / "profile").mkdir(parents=True)
    (run_root / "runs").mkdir(parents=True)

    config = yaml.safe_load((ROOT / "configs/dense_full_pipeline.yaml").read_text(encoding="utf-8"))
    hybrid_root = (ROOT / config["detection"]["hybrid_output_root"]).resolve()
    running = _run(
        ("docker", "ps", "--format", "{{.Names}}"),
        capture=True,
    ).stdout.splitlines()
    if args.container not in running:
        raise RuntimeError(f"Production container is not running: {args.container}")
    head = _git("rev-parse", "HEAD")
    container_head = _run(
        (
            "docker",
            "exec",
            "-w",
            "/workspace",
            args.container,
            "git",
            "rev-parse",
            "HEAD",
        ),
        capture=True,
    ).stdout.strip()
    if container_head != head:
        raise RuntimeError(
            f"Container /workspace HEAD mismatch: host={head} container={container_head}"
        )

    model = _find_omr_model(args.omr_model)
    container_model, copied_directory = _copy_model_into_container(
        args.container,
        model,
    )
    uid_gid = f"{os.getuid()}:{os.getgid()}"
    contracts: dict[str, Mapping[str, Any]] = {}
    batch_rows = []
    try:
        for label, score, page, image in PAGES:
            source_run = source_runs.get(label)
            if not isinstance(source_run, Mapping):
                raise ValueError(f"Source batch lacks page: {label}")
            run_id = f"issue255_sr{args.sr_scale}_public_{label}_{page}_{args.run_tag}"
            handoff_path = run_root / "profile" / f"{run_id}_handoff.json"
            _prepare_replayed_handoff(
                source_run=source_run,
                destination_baseline=hybrid_root / run_id / "baseline",
                output=handoff_path,
                sr_scale=args.sr_scale,
            )
            command = (
                "docker",
                "exec",
                "--user",
                uid_gid,
                "-w",
                "/workspace",
                "-e",
                "PYTHONPATH=/workspace",
                "-e",
                "HOME=/tmp",
                "-e",
                "YOLO_CONFIG_DIR=/tmp/issue255_sr_x4_ultralytics",
                "-e",
                f"OMR_DLN_MODEL_PATH={container_model}",
                args.container,
                args.container_python,
                _container_path(WORKER),
                "--sr-scale",
                str(args.sr_scale),
                "--image",
                _container_path(image),
                "--score",
                score,
                "--page",
                page,
                "--run-id",
                run_id,
                "--output-root",
                _container_path(run_root / "runs"),
                "--baseline-handoff",
                _container_path(handoff_path),
            )
            _run(command, log=run_root / f"{run_id}.log")
            contract_path = (
                run_root / "runs" / run_id / "issue255_public_baseline_ab_run_contract.json"
            )
            contract = _load(contract_path)
            if not isinstance(contract, Mapping) or contract.get("status") != "completed":
                raise ValueError(f"Incomplete replay contract: {label}")
            contracts[label] = contract
            batch_rows.append(
                {
                    "label": label,
                    "score": score,
                    "page": page,
                    "run_id": run_id,
                    "contract_path": str(contract_path),
                    "contract": contract,
                }
            )
    finally:
        if copied_directory:
            subprocess.run(
                (
                    "docker",
                    "exec",
                    "--user",
                    "0:0",
                    args.container,
                    "rm",
                    "-rf",
                    copied_directory,
                ),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )

    batch_path = run_root / f"issue255_public_baseline_sr_x4_batch_{args.run_tag}.json"
    batch = {
        "schema_version": "issue255.public_baseline_sr_x4_batch.v1",
        "status": "completed",
        "analysis_only": True,
        "run_tag": args.run_tag,
        "sr_scale": args.sr_scale,
        "source_public_batch": str(args.source_public_batch.resolve()),
        "historical_artifact_used_as_runtime_input": False,
        "runs": batch_rows,
    }
    batch_path.write_text(
        json.dumps(batch, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    pages = _analyze(
        contracts=contracts,
        historical_comparison=args.historical_comparison.resolve(),
        target_report=args.target_report.resolve(),
    )
    report = {
        "schema_version": "issue255.public_baseline_sr_x4_replay.v1",
        "status": "completed",
        "analysis_only": True,
        "restoration_scope_only": True,
        "run_tag": args.run_tag,
        "sr_scale": args.sr_scale,
        "source_public_batch": _record(args.source_public_batch.resolve()),
        "source_historical_comparison": _record(args.historical_comparison.resolve()),
        "source_target_report": _record(args.target_report.resolve()),
        "historical_artifacts_used_for_analysis_only": True,
        "historical_artifact_used_as_runtime_input": False,
        "repository_commit": head,
        "batch": _record(batch_path),
        "pages": pages,
        "summary": {
            "all_sr_images_restore_x4_geometry": all(
                page["sr_image_comparison"]["same_shape"] for page in pages.values()
            ),
            "all_sr_detections_exact_historical": all(
                page["sr_detection_comparison"]["exact_match"] for page in pages.values()
            ),
            "all_hybrids_exact_historical": all(
                page["hybrid_comparison"]["exact_match"] for page in pages.values()
            ),
        },
    }
    report["next_stage_e_reconstruction_recommended"] = bool(
        report["summary"]["all_hybrids_exact_historical"]
    )
    report["next_gpu_run_required"] = False
    output = run_root / "public_baseline_sr_x4_replay_report.json"
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-tag", required=True)
    parser.add_argument("--sr-scale", type=int, choices=(4,), default=4)
    parser.add_argument("--source-public-batch", type=Path, default=DEFAULT_SOURCE_BATCH)
    parser.add_argument(
        "--historical-comparison",
        type=Path,
        default=DEFAULT_HISTORICAL_COMPARISON,
    )
    parser.add_argument("--target-report", type=Path, default=DEFAULT_TARGET_REPORT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--container",
        default=os.environ.get("ISSUE255_CONTAINER", "pdfscore_pipeline_gpu"),
    )
    parser.add_argument("--container-python", default="/opt/venv_pipeline/bin/python")
    parser.add_argument("--omr-model", type=Path)
    args = parser.parse_args()
    try:
        output = run(args)
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
    print(json.dumps({"status": "completed", "report": str(output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
