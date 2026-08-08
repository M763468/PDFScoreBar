#!/usr/bin/env python3
"""Run the verified public HOMR profile on fresh Issue #255 SR x4 images.

This experiment isolates the remaining SR-route reconstruction gap. It reuses
fresh public-baseline and current OMR artifacts, applies the verified public
HOMR profile to the freshly generated x4 image via ``--pre-computed-sr``, and
recomputes hybrid consensus. Retained historical SR/hybrid artifacts are read
only for analysis and are never runtime detector inputs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.common import barline_iou
from src.pipeline.steps.hybrid_consensus import (
    apply_hybrid_consensus_filter,
    load_json_boxes,
)
from tools.issue255.run_public_baseline_ab import (
    EXPECTED_BRANCH,
    ISSUE245_TOOLING_COMMIT,
    PAGES,
    PDFSCORE_PROFILE_COMMIT,
    PUBLIC_IMAGE,
    ROOT,
    _container_path,
    _ensure_commit,
    _extract_snapshot,
    _git,
    _prepare_public_image,
    _require_executable,
    _run,
    _validate_profile,
    _write_git_file,
)
from tools.issue255.run_public_baseline_stage_e_reconstruction import (
    _resolve_repo_artifact,
)

DEFAULT_X4_REPORT = (
    ROOT
    / "logs/issue255_public_baseline_sr_x4/issue255_public_baseline_sr_x4_02"
    / "public_baseline_sr_x4_replay_report.json"
)
DEFAULT_OUTPUT_ROOT = ROOT / "logs/issue255_public_homr_on_sr_x4"
IOU_THRESHOLDS = (0.25, 0.5, 0.75)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _greedy_match_count(
    actual: Sequence[Sequence[int]],
    reference: Sequence[Sequence[int]],
    threshold: float,
) -> int:
    pairs: list[tuple[float, int, int]] = []
    for actual_index, actual_box in enumerate(actual):
        for reference_index, reference_box in enumerate(reference):
            score = float(barline_iou(actual_box, reference_box))
            if score > threshold:
                pairs.append((score, actual_index, reference_index))
    pairs.sort(reverse=True)
    used_actual: set[int] = set()
    used_reference: set[int] = set()
    matched = 0
    for _score, actual_index, reference_index in pairs:
        if actual_index in used_actual or reference_index in used_reference:
            continue
        used_actual.add(actual_index)
        used_reference.add(reference_index)
        matched += 1
    return matched


def _compare_boxes(
    actual: Sequence[Sequence[int]],
    reference: Sequence[Sequence[int]],
) -> dict[str, Any]:
    actual_set = {tuple(int(v) for v in box) for box in actual}
    reference_set = {tuple(int(v) for v in box) for box in reference}
    tolerant = {}
    for threshold in IOU_THRESHOLDS:
        matched = _greedy_match_count(actual, reference, threshold)
        tolerant[str(threshold)] = {
            "matched": matched,
            "actual_unmatched": len(actual) - matched,
            "reference_unmatched": len(reference) - matched,
        }
    return {
        "actual_count": len(actual),
        "reference_count": len(reference),
        "exact_common_count": len(actual_set & reference_set),
        "actual_only": [list(box) for box in sorted(actual_set - reference_set)],
        "reference_only": [list(box) for box in sorted(reference_set - actual_set)],
        "exact_match": actual_set == reference_set,
        "tolerant_iou": tolerant,
    }


def _artifact_from_contract(contract: Mapping[str, Any], name: str) -> Path:
    artifacts = contract.get("artifacts")
    row = artifacts.get(name) if isinstance(artifacts, Mapping) else None
    value = row.get("path") if isinstance(row, Mapping) else None
    if not isinstance(value, str):
        raise ValueError(f"Source public batch lacks artifact path: {name}")
    path = _resolve_repo_artifact(value)
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _source_runs(batch: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows = batch.get("runs")
    if not isinstance(rows, list):
        raise ValueError("Source public batch lacks runs")
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if isinstance(row, Mapping):
            result[str(row.get("label"))] = row
    return result


def _target_support(
    target_rows: Mapping[str, Any],
    sr_boxes: Sequence[Sequence[int]],
    hybrid_boxes: Sequence[Sequence[int]],
) -> dict[str, Any]:
    hybrid_set = {tuple(int(v) for v in box) for box in hybrid_boxes}
    result: dict[str, Any] = {}
    for side in ("historical", "public"):
        rows = target_rows.get(side)
        result[side] = []
        if not isinstance(rows, list):
            continue
        for row in rows:
            bbox = row.get("bbox") if isinstance(row, Mapping) else None
            if not isinstance(bbox, list) or len(bbox) != 4:
                continue
            normalized = tuple(int(v) for v in bbox)
            best_iou = max(
                (float(barline_iou(normalized, candidate)) for candidate in sr_boxes),
                default=0.0,
            )
            result[side].append(
                {
                    "bbox": list(normalized),
                    "best_sr_iou": best_iou,
                    "sr_supported_iou_gt_0_5": best_iou > 0.5,
                    "included_in_recomputed_hybrid": normalized in hybrid_set,
                }
            )
    return result


def _container_head(container: str) -> str:
    return _run(
        (
            "docker",
            "exec",
            "-w",
            "/workspace",
            "-e",
            "GIT_CONFIG_COUNT=1",
            "-e",
            "GIT_CONFIG_KEY_0=safe.directory",
            "-e",
            "GIT_CONFIG_VALUE_0=/workspace",
            container,
            "git",
            "rev-parse",
            "HEAD",
        ),
        capture=True,
    ).stdout.strip()


def run(args: argparse.Namespace) -> Path:
    for command in ("docker", "git", "tar"):
        _require_executable(command)
    if _git("branch", "--show-current") != EXPECTED_BRANCH:
        raise RuntimeError(f"Expected branch {EXPECTED_BRANCH}")
    if _git("status", "--short", "--untracked-files=no"):
        raise RuntimeError("Tracked working tree must be clean before public-profile replay")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", args.run_tag):
        raise ValueError("--run-tag contains unsupported characters")
    profile = _validate_profile()

    x4_report_path = args.x4_report.resolve()
    x4_report = _load(x4_report_path)
    if not isinstance(x4_report, Mapping) or x4_report.get("status") != "completed":
        raise ValueError("SR x4 replay report is incomplete")
    if x4_report.get("sr_scale") != 4:
        raise ValueError("Expected an SR x4 replay report")
    if x4_report.get("historical_artifact_used_as_runtime_input") is not False:
        raise ValueError("SR x4 replay used historical runtime input")
    x4_pages = x4_report.get("pages")
    if not isinstance(x4_pages, Mapping):
        raise ValueError("SR x4 replay report lacks pages")

    source_record = x4_report.get("source_public_batch")
    source_value = source_record.get("path") if isinstance(source_record, Mapping) else None
    if not isinstance(source_value, str):
        raise ValueError("SR x4 report lacks source public batch")
    source_batch_path = _resolve_repo_artifact(source_value)
    source_batch = _load(source_batch_path)
    if not isinstance(source_batch, Mapping) or source_batch.get("status") != "completed":
        raise ValueError("Source public batch is incomplete")
    source_runs = _source_runs(source_batch)

    output_root = args.output_root.resolve()
    run_root = output_root / args.run_tag
    if run_root.exists():
        raise FileExistsError(run_root)
    (run_root / "tooling").mkdir(parents=True)
    (run_root / "profile").mkdir(parents=True)
    (run_root / "runs").mkdir(parents=True)

    running = _run(
        ("docker", "ps", "--format", "{{.Names}}"),
        capture=True,
    ).stdout.splitlines()
    if args.container not in running:
        raise RuntimeError(f"Production container is not running: {args.container}")
    head = _git("rev-parse", "HEAD")
    container_head = _container_head(args.container)
    if container_head != head:
        raise RuntimeError(
            f"Container /workspace HEAD mismatch: host={head} container={container_head}"
        )

    _ensure_commit(ISSUE245_TOOLING_COMMIT)
    _ensure_commit(PDFSCORE_PROFILE_COMMIT)
    compat = run_root / "tooling/run_homr_evaluator_compat.py"
    _write_git_file(
        ISSUE245_TOOLING_COMMIT,
        "tools/issue245/run_homr_evaluator_compat.py",
        compat,
    )
    snapshot = run_root / "profile/pdfscore_source_snapshot"
    _extract_snapshot(PDFSCORE_PROFILE_COMMIT, snapshot)
    _prepare_public_image(
        container=args.container,
        rebuild=args.rebuild_public_image,
        output_root=run_root,
    )

    uid_gid = f"{os.getuid()}:{os.getgid()}"
    page_reports: dict[str, Any] = {}
    for label, score, page, original_image in PAGES:
        x4_page = x4_pages.get(label)
        source_run = source_runs.get(label)
        if not isinstance(x4_page, Mapping) or not isinstance(source_run, Mapping):
            raise ValueError(f"Missing page inputs: {label}")
        source_contract = source_run.get("contract")
        if not isinstance(source_contract, Mapping):
            raise ValueError(f"Source public run lacks contract: {label}")
        handoff = source_contract.get("baseline_profile_handoff")
        if not isinstance(handoff, Mapping):
            raise ValueError(f"Source public run lacks baseline handoff: {label}")
        if handoff.get("historical_artifact_used_as_runtime_input") is not False:
            raise ValueError(f"Historical runtime input in source public run: {label}")

        image_comparison = x4_page.get("sr_image_comparison")
        replay_image_row = (
            image_comparison.get("replay") if isinstance(image_comparison, Mapping) else None
        )
        replay_image_value = (
            replay_image_row.get("path") if isinstance(replay_image_row, Mapping) else None
        )
        if not isinstance(replay_image_value, str):
            raise ValueError(f"SR x4 image path missing: {label}")
        replay_x4_image = _resolve_repo_artifact(replay_image_value)
        if not replay_x4_image.is_file():
            raise FileNotFoundError(replay_x4_image)

        paths = x4_page.get("paths")
        historical_sr_value = paths.get("historical_sr") if isinstance(paths, Mapping) else None
        historical_hybrid_value = (
            paths.get("historical_hybrid") if isinstance(paths, Mapping) else None
        )
        if not isinstance(historical_sr_value, str) or not isinstance(historical_hybrid_value, str):
            raise ValueError(f"Historical analysis paths missing: {label}")
        historical_sr = _resolve_repo_artifact(historical_sr_value)
        historical_hybrid = _resolve_repo_artifact(historical_hybrid_value)
        if not historical_sr.is_file() or not historical_hybrid.is_file():
            raise FileNotFoundError(f"Historical analysis artifact missing: {label}")

        fresh_baseline = _artifact_from_contract(source_contract, "fresh_baseline")
        fresh_omr = _artifact_from_contract(source_contract, "current_omr")
        page_root = run_root / "runs" / label
        public_sr_root = page_root / "public_profile_sr"
        public_sr_root.mkdir(parents=True)
        command = (
            "docker",
            "run",
            "--rm",
            "--gpus",
            "all",
            "-v",
            f"{ROOT}:/workspace",
            "-v",
            f"{snapshot}:/historical:ro",
            "-w",
            "/workspace",
            "-e",
            "HOME=/tmp",
            "-e",
            ("PYTHONPATH=/opt/issue255_public_homr:/historical:/historical/src:/workspace"),
            PUBLIC_IMAGE,
            "/opt/venv_pipeline/bin/python",
            _container_path(compat),
            "--images",
            _container_path(original_image),
            "--pre-computed-sr",
            _container_path(replay_x4_image),
            "--output-root",
            _container_path(public_sr_root),
            "--force-run-id",
            "batch",
            "--enable-segnet-cache",
        )
        _run(command, log=page_root / "public_profile_sr.log")
        _run(
            (
                "docker",
                "exec",
                "--user",
                "0:0",
                args.container,
                "chown",
                "-R",
                uid_gid,
                _container_path(page_root),
            )
        )

        public_sr = public_sr_root / "batch" / page / f"{page}_detections.json"
        if not public_sr.is_file():
            raise FileNotFoundError(public_sr)
        baseline_boxes = load_json_boxes(fresh_baseline)
        public_sr_boxes = load_json_boxes(public_sr)
        omr_boxes = load_json_boxes(fresh_omr)
        recomputed_hybrid = apply_hybrid_consensus_filter(
            baseline_boxes=baseline_boxes,
            sr_boxes=public_sr_boxes,
            omr_boxes=omr_boxes,
            iou_thresh=0.5,
        )
        recomputed_hybrid_path = page_root / "public_profile_sr_hybrid.json"
        recomputed_hybrid_path.write_text(
            json.dumps(recomputed_hybrid, indent=2) + "\n",
            encoding="utf-8",
        )

        historical_sr_boxes = load_json_boxes(historical_sr)
        historical_hybrid_boxes = load_json_boxes(historical_hybrid)
        targets = x4_page.get("target_support")
        page_reports[label] = {
            "score": score,
            "page": page,
            "runtime_inputs": {
                "original_image": str(original_image.resolve()),
                "fresh_sr_x4_image": str(replay_x4_image),
                "fresh_public_baseline": str(fresh_baseline),
                "fresh_current_omr": str(fresh_omr),
                "public_homr_profile_image": PUBLIC_IMAGE,
            },
            "analysis_references": {
                "historical_sr": str(historical_sr),
                "historical_hybrid": str(historical_hybrid),
            },
            "public_profile_sr": str(public_sr),
            "recomputed_hybrid": str(recomputed_hybrid_path),
            "sr_comparison": _compare_boxes(
                public_sr_boxes,
                historical_sr_boxes,
            ),
            "hybrid_comparison": _compare_boxes(
                recomputed_hybrid,
                historical_hybrid_boxes,
            ),
            "target_support": _target_support(
                targets if isinstance(targets, Mapping) else {},
                public_sr_boxes,
                recomputed_hybrid,
            ),
        }

    report = {
        "schema_version": "issue255.public_homr_on_sr_x4.v1",
        "status": "completed",
        "analysis_only": True,
        "restoration_scope_only": True,
        "run_tag": args.run_tag,
        "repository_commit": head,
        "source_x4_report": str(x4_report_path),
        "source_public_batch": str(source_batch_path),
        "public_homr_profile": profile,
        "historical_artifacts_used_for_analysis_only": True,
        "historical_artifact_used_as_runtime_input": False,
        "pages": page_reports,
        "summary": {
            "all_public_profile_sr_exact_historical": all(
                page["sr_comparison"]["exact_match"] for page in page_reports.values()
            ),
            "all_recomputed_hybrids_exact_historical": all(
                page["hybrid_comparison"]["exact_match"] for page in page_reports.values()
            ),
            "all_recomputed_hybrids_iou_0_5_cover_historical": all(
                page["hybrid_comparison"]["tolerant_iou"]["0.5"]["reference_unmatched"] == 0
                and page["hybrid_comparison"]["tolerant_iou"]["0.5"]["actual_unmatched"] == 0
                for page in page_reports.values()
            ),
        },
    }
    report["next_stage_e_reconstruction_recommended"] = bool(
        report["summary"]["all_recomputed_hybrids_exact_historical"]
    )
    report["next_if_not_exact"] = (
        "quantify_sr_x4_pixel_difference_and_historical_homr_source_gap"
        if not report["next_stage_e_reconstruction_recommended"]
        else None
    )
    output = run_root / "public_homr_on_sr_x4_report.json"
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-tag", required=True)
    parser.add_argument("--x4-report", type=Path, default=DEFAULT_X4_REPORT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--container",
        default=os.environ.get("ISSUE255_CONTAINER", "pdfscore_pipeline_gpu"),
    )
    parser.add_argument("--rebuild-public-image", action="store_true")
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
