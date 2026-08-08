#!/usr/bin/env python3
"""Generate the Issue #255 restored fresh upstream route for canonical full-68.

This is an experiment runner, not a production-default change. For every canonical
page it freshly generates the verified public-profile baseline, generates SR at x4
with the current pipeline, runs the verified public HOMR profile on that fresh x4
image, reuses the freshly generated current OMR result, and recomputes consensus.
Historical detector artifacts are never runtime inputs.

The run is page-resumable. Completed page reports are hash-validated before they
are reused with ``--resume``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from src.pipeline.steps.hybrid_consensus import (
    apply_hybrid_consensus_filter,
    load_json_boxes,
)
from tools.issue255.full68_restoration import canonical_pages, page_key
from tools.issue255.run_public_baseline_ab import (
    EXPECTED_BRANCH,
    HOMR_PROFILE_COMMIT,
    ISSUE245_TOOLING_COMMIT,
    PDFSCORE_PROFILE_COMMIT,
    PUBLIC_IMAGE,
    ROOT,
    _container_path,
    _copy_model_into_container,
    _ensure_commit,
    _extract_snapshot,
    _find_omr_model,
    _git,
    _prepare_public_image,
    _require_executable,
    _run,
    _sha256,
    _validate_profile,
    _write_git_file,
    _write_handoff,
)
from tools.issue255.run_public_baseline_stage_e_reconstruction import (
    CLEF_PATTERNS,
    STAFF_PATTERNS,
    _find_historical_mask,
    _fresh_contract_matches,
    _resolve_repo_artifact,
)

DEFAULT_OUTPUT_ROOT = ROOT / "logs/issue255_full68_restoration"
WORKER = ROOT / "tools/issue255/run_public_baseline_sr_scale_variant.py"
CANONICAL_CONFIG = ROOT / "configs/dense_full_pipeline.yaml"
SR_SCALE = 4
REQUIRED_PAGE_ARTIFACTS = (
    "image",
    "fresh_baseline",
    "fresh_sr_x4_image",
    "public_profile_sr",
    "current_omr",
    "restored_hybrid",
    "staff_mask",
    "clef_mask",
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact(path: Path) -> dict[str, Any]:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
    }


def _artifact_from_contract(contract: Mapping[str, Any], name: str) -> Path:
    artifacts = contract.get("artifacts")
    row = artifacts.get(name) if isinstance(artifacts, Mapping) else None
    value = row.get("path") if isinstance(row, Mapping) else None
    if not isinstance(value, str):
        raise ValueError(f"Variant contract lacks artifact: {name}")
    path = _resolve_repo_artifact(value)
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _artifact_record_valid(value: Any) -> bool:
    if not isinstance(value, Mapping) or not isinstance(value.get("path"), str):
        return False
    path = _resolve_repo_artifact(str(value["path"]))
    if not path.is_file():
        return False
    expected = value.get("sha256")
    return isinstance(expected, str) and _sha256(path) == expected


def _page_report_valid(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        payload = _load(path)
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(payload, Mapping) or payload.get("status") != "completed":
        return False
    if payload.get("historical_artifact_used_as_runtime_input") is not False:
        return False
    if not _fresh_contract_matches(payload.get("detector_input_contract")):
        return False
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, Mapping):
        return False
    return all(_artifact_record_valid(artifacts.get(name)) for name in REQUIRED_PAGE_ARTIFACTS)


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


def _write_run_manifest(
    path: Path,
    pages: list[dict[str, Any]],
    *,
    repository_commit: str,
    resume: bool,
) -> None:
    expected = {
        "schema_version": "issue255.full68_restored_upstream_manifest.v1",
        "repository_commit": repository_commit,
        "sr_scale": SR_SCALE,
        "canonical_page_count": 68,
        "selected_pages": [str(page["key"]) for page in pages],
    }
    if path.is_file():
        existing = _load(path)
        if existing != expected:
            raise ValueError("Existing run manifest does not match requested commit/page selection")
        return
    if resume:
        raise FileNotFoundError(f"--resume requested but run manifest is missing: {path}")
    path.write_text(
        json.dumps(expected, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_runtime_provenance(
    path: Path,
    *,
    repository_commit: str,
    container: str,
    omr_model: Path,
) -> dict[str, Any]:
    profile = _validate_profile()
    public_image_id = _run(
        ("docker", "image", "inspect", "--format", "{{.Id}}", PUBLIC_IMAGE),
        capture=True,
    ).stdout.strip()
    production_image = _run(
        ("docker", "inspect", "--format", "{{.Config.Image}}", container),
        capture=True,
    ).stdout.strip()
    payload = {
        "schema_version": "issue255.full68_restored_upstream_provenance.v1",
        "repository_commit": repository_commit,
        "public_homr_profile": profile,
        "public_homr_profile_commit": HOMR_PROFILE_COMMIT,
        "public_homr_image": PUBLIC_IMAGE,
        "public_homr_image_id": public_image_id,
        "production_container": container,
        "production_container_image": production_image,
        "omr_model": _artifact(omr_model),
        "sr_scale": SR_SCALE,
        "historical_artifact_used_as_runtime_input": False,
    }
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return payload


def _cleanup_page_outputs(
    *,
    page_root: Path,
    variant_run_dir: Path,
    hybrid_run_dir: Path,
) -> None:
    for path in (page_root, variant_run_dir, hybrid_run_dir):
        if path.exists():
            shutil.rmtree(path)


def _run_page(
    *,
    page_spec: Mapping[str, Any],
    args: argparse.Namespace,
    run_root: Path,
    hybrid_root: Path,
    compat: Path,
    snapshot: Path,
    provenance_path: Path,
    container_model: str,
    uid_gid: str,
) -> dict[str, Any]:
    score = str(page_spec["score"])
    page = str(page_spec["page"])
    image = Path(page_spec["image"]).resolve()
    key = page_key(score, page)
    if not image.is_file():
        raise FileNotFoundError(image)

    run_id = f"issue255_full68_restore_{score}_{page}_{args.run_tag}"
    page_root = run_root / "pages" / score / page
    page_report_path = page_root / "page_report.json"
    if args.resume and _page_report_valid(page_report_path):
        return dict(_load(page_report_path))

    variant_run_dir = run_root / "variant_runs" / run_id
    hybrid_run_dir = hybrid_root / run_id
    _cleanup_page_outputs(
        page_root=page_root,
        variant_run_dir=variant_run_dir,
        hybrid_run_dir=hybrid_run_dir,
    )
    page_root.mkdir(parents=True)

    baseline_root = hybrid_run_dir / "baseline"
    baseline_root.mkdir(parents=True)
    public_env = "PYTHONPATH=/opt/issue255_public_homr:/historical:/historical/src:/workspace"
    _run(
        (
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
            public_env,
            PUBLIC_IMAGE,
            "/opt/venv_pipeline/bin/python",
            _container_path(compat),
            "--images",
            _container_path(image),
            "--output-root",
            _container_path(baseline_root),
            "--force-run-id",
            "batch",
            "--enable-segnet-cache",
        ),
        log=page_root / "public_baseline.log",
    )
    baseline_page = baseline_root / "batch" / page
    baseline_detection = baseline_page / f"{page}_detections.json"
    if not baseline_detection.is_file():
        raise FileNotFoundError(baseline_detection)

    handoff_path = page_root / "baseline_handoff.json"
    _write_handoff(
        image=image,
        detection=baseline_detection,
        provenance=provenance_path,
        output=handoff_path,
    )

    worker_command = (
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
        "YOLO_CONFIG_DIR=/tmp/issue255_full68_restore_ultralytics",
        "-e",
        f"OMR_DLN_MODEL_PATH={container_model}",
        args.container,
        args.container_python,
        _container_path(WORKER),
        "--sr-scale",
        str(SR_SCALE),
        "--image",
        _container_path(image),
        "--score",
        score,
        "--page",
        page,
        "--run-id",
        run_id,
        "--output-root",
        _container_path(run_root / "variant_runs"),
        "--baseline-handoff",
        _container_path(handoff_path),
    )
    _run(worker_command, log=page_root / "current_x4_variant.log")
    contract_path = variant_run_dir / "issue255_public_baseline_ab_run_contract.json"
    contract = _load(contract_path)
    if not isinstance(contract, Mapping) or contract.get("status") != "completed":
        raise ValueError(f"Incomplete x4 variant contract: {key}")
    fresh_contract = contract.get("detector_input_contract")
    if not _fresh_contract_matches(fresh_contract):
        raise ValueError(f"Fresh detector contract mismatch: {key}")
    if contract.get("sr_scale_override") != SR_SCALE:
        raise ValueError(f"SR scale override missing from variant contract: {key}")

    sr_x4_image = _artifact_from_contract(contract, "probe_image")
    current_omr = _artifact_from_contract(contract, "current_omr")

    public_sr_root = page_root / "public_profile_sr"
    public_sr_root.mkdir(parents=True)
    _run(
        (
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
            public_env,
            PUBLIC_IMAGE,
            "/opt/venv_pipeline/bin/python",
            _container_path(compat),
            "--images",
            _container_path(image),
            "--pre-computed-sr",
            _container_path(sr_x4_image),
            "--output-root",
            _container_path(public_sr_root),
            "--force-run-id",
            "batch",
            "--enable-segnet-cache",
        ),
        log=page_root / "public_profile_sr.log",
    )
    public_sr = public_sr_root / "batch" / page / f"{page}_detections.json"
    if not public_sr.is_file():
        raise FileNotFoundError(public_sr)

    baseline_boxes = load_json_boxes(baseline_detection)
    sr_boxes = load_json_boxes(public_sr)
    omr_boxes = load_json_boxes(current_omr)
    restored_hybrid = apply_hybrid_consensus_filter(
        baseline_boxes=baseline_boxes,
        sr_boxes=sr_boxes,
        omr_boxes=omr_boxes,
        iou_thresh=0.5,
    )
    restored_hybrid_path = page_root / "restored_hybrid.json"
    restored_hybrid_path.write_text(
        json.dumps(restored_hybrid, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    staff_mask = _find_historical_mask(
        (baseline_page,),
        STAFF_PATTERNS,
        stem=page,
        name="staff mask",
    )
    clef_mask = _find_historical_mask(
        (baseline_page,),
        CLEF_PATTERNS,
        stem=page,
        name="clef mask",
    )

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

    report = {
        "schema_version": "issue255.full68_restored_upstream_page.v1",
        "status": "completed",
        "key": key,
        "score": score,
        "page": page,
        "run_id": run_id,
        "detector_input_contract": dict(fresh_contract),
        "execution_only_overrides": {
            "detection.sr_scale": SR_SCALE,
            "historical_detector_artifacts": False,
        },
        "historical_artifact_used_as_runtime_input": False,
        "component_counts": {
            "fresh_baseline": len(baseline_boxes),
            "public_profile_sr": len(sr_boxes),
            "current_omr": len(omr_boxes),
            "restored_hybrid": len(restored_hybrid),
        },
        "artifacts": {
            "image": _artifact(image),
            "fresh_baseline": _artifact(baseline_detection),
            "fresh_sr_x4_image": _artifact(sr_x4_image),
            "public_profile_sr": _artifact(public_sr),
            "current_omr": _artifact(current_omr),
            "restored_hybrid": _artifact(restored_hybrid_path),
            "staff_mask": _artifact(staff_mask),
            "clef_mask": _artifact(clef_mask),
            "variant_contract": _artifact(contract_path),
            "baseline_handoff": _artifact(handoff_path),
        },
    }
    page_report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report


def run(args: argparse.Namespace) -> Path:
    for command in ("docker", "git", "tar"):
        _require_executable(command)
    if _git("branch", "--show-current") != EXPECTED_BRANCH:
        raise RuntimeError(f"Expected branch {EXPECTED_BRANCH}")
    if _git("status", "--short", "--untracked-files=no"):
        raise RuntimeError("Tracked working tree must be clean before authoritative replay")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", args.run_tag):
        raise ValueError("--run-tag contains unsupported characters")
    if not WORKER.is_file():
        raise FileNotFoundError(WORKER)

    pages = canonical_pages()
    if args.page_limit is not None:
        if args.page_limit <= 0 or args.page_limit > 68:
            raise ValueError("--page-limit must be between 1 and 68")
        pages = pages[: args.page_limit]

    run_root = args.output_root.expanduser().resolve() / args.run_tag
    if run_root.exists() and not args.resume:
        raise FileExistsError(run_root)
    run_root.mkdir(parents=True, exist_ok=True)
    for directory in ("pages", "profile", "tooling", "variant_runs"):
        (run_root / directory).mkdir(exist_ok=True)

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
    _write_run_manifest(
        run_root / "run_manifest.json",
        pages,
        repository_commit=head,
        resume=args.resume,
    )

    _ensure_commit(ISSUE245_TOOLING_COMMIT)
    _ensure_commit(PDFSCORE_PROFILE_COMMIT)
    compat = run_root / "tooling/run_homr_evaluator_compat.py"
    if not compat.is_file():
        _write_git_file(
            ISSUE245_TOOLING_COMMIT,
            "tools/issue245/run_homr_evaluator_compat.py",
            compat,
        )
    snapshot = run_root / "profile/pdfscore_source_snapshot"
    if not snapshot.is_dir():
        _extract_snapshot(PDFSCORE_PROFILE_COMMIT, snapshot)
    _prepare_public_image(
        container=args.container,
        rebuild=args.rebuild_public_image,
        output_root=run_root,
    )

    config = yaml.safe_load(CANONICAL_CONFIG.read_text(encoding="utf-8"))
    detection = config.get("detection") if isinstance(config, Mapping) else None
    if not isinstance(detection, Mapping):
        raise ValueError("Canonical config lacks detection settings")
    hybrid_root = (ROOT / str(detection["hybrid_output_root"])).resolve()
    hybrid_root.relative_to(ROOT)

    model = _find_omr_model(args.omr_model)
    container_model, copied_directory = _copy_model_into_container(args.container, model)
    provenance_path = run_root / "profile/runtime_provenance.json"
    provenance = _write_runtime_provenance(
        provenance_path,
        repository_commit=head,
        container=args.container,
        omr_model=model,
    )
    uid_gid = f"{os.getuid()}:{os.getgid()}"

    page_reports: dict[str, Any] = {}
    try:
        for index, page_spec in enumerate(pages, start=1):
            key = str(page_spec["key"])
            print(f"[{index}/{len(pages)}] {key}", flush=True)
            page_reports[key] = _run_page(
                page_spec=page_spec,
                args=args,
                run_root=run_root,
                hybrid_root=hybrid_root,
                compat=compat,
                snapshot=snapshot,
                provenance_path=provenance_path,
                container_model=container_model,
                uid_gid=uid_gid,
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

    authoritative = len(pages) == 68 and args.page_limit is None
    report = {
        "schema_version": "issue255.full68_restored_upstream.v1",
        "status": "completed",
        "analysis_only": True,
        "restoration_scope_only": True,
        "run_tag": args.run_tag,
        "repository_commit": head,
        "canonical_config": _artifact(CANONICAL_CONFIG),
        "authoritative_full68": authoritative,
        "canonical_page_count": 68,
        "selected_page_count": len(pages),
        "sr_scale": SR_SCALE,
        "public_homr_profile_commit": HOMR_PROFILE_COMMIT,
        "historical_artifact_used_as_runtime_input": False,
        "runtime_provenance": provenance,
        "pages": page_reports,
        "summary": {
            "fresh_contract_required_fields_match": all(
                _fresh_contract_matches(page["detector_input_contract"])
                for page in page_reports.values()
            ),
            "completed_page_count": len(page_reports),
            "baseline_count": sum(
                int(page["component_counts"]["fresh_baseline"]) for page in page_reports.values()
            ),
            "public_profile_sr_count": sum(
                int(page["component_counts"]["public_profile_sr"]) for page in page_reports.values()
            ),
            "current_omr_count": sum(
                int(page["component_counts"]["current_omr"]) for page in page_reports.values()
            ),
            "restored_hybrid_count": sum(
                int(page["component_counts"]["restored_hybrid"]) for page in page_reports.values()
            ),
        },
    }
    report_path = run_root / "full68_restored_upstream_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-tag", required=True)
    parser.add_argument(
        "--container",
        default=os.environ.get("ISSUE255_CONTAINER", "pdfscore_pipeline_gpu"),
    )
    parser.add_argument("--container-python", default="/opt/venv_pipeline/bin/python")
    parser.add_argument("--omr-model", type=Path)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--rebuild-public-image", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--page-limit", type=int)
    args = parser.parse_args()
    try:
        report = run(args)
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
    print(
        json.dumps(
            {"status": "completed", "report": str(report)},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
