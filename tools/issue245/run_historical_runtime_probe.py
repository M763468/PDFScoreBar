#!/usr/bin/env python3
"""Run current evaluator code with the preserved historical SR/HOMR runtime.

The caller must start this tool inside a snapshot of the existing ``sr_eval_gpu``
container and mount the Issue #245 worktree at ``/workspace``. This isolates the
runtime/HOMR package from evaluator-source changes while keeping the canonical
input and comparison contract fixed.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import inspect
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

from tools.issue245.homr_route_analysis import compare_record_sets, load_prediction_records
from tools.issue245.run_canonical_historical_probe import (
    DEFAULT_HISTORICAL_ROOT,
    DEFAULT_IMAGE,
    EXPECTED_CANONICAL_SHA256,
    discover_historical_detection,
    resolve_inside_repo,
)
from tools.issue245.run_focused_homr_probe import (
    IMPORT_CHECKS,
    PROVENANCE_ENV_KEYS,
    detection_path,
    image_summary,
    import_provenance,
    mask_path,
    mask_summary,
    package_versions,
    runtime_provider_summary,
    sha256_file,
    write_json,
)

DEFAULT_OUTPUT_ROOT = Path(
    "logs/issue245_focused_homr_probe/"
    "canonical_va_prokofiev_symphony1_page001/historical_runtime_probe/run"
)
DEFAULT_RUN_ID = "issue245_historical_runtime_baseline"
MODEL_SUFFIXES = {".bin", ".onnx", ".pt", ".pth", ".safetensors"}
MODEL_NAME_HINTS = (
    "decoder_pytorch_model",
    "encoder_pytorch_model",
    "homr",
    "segnet",
    "tromr",
)


def run_logged(command: list[str], log_path: Path, *, cwd: Path) -> dict[str, Any]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as stream:
        stream.write("command: " + " ".join(command) + "\n\n")
        stream.flush()
        completed = subprocess.run(
            command,
            cwd=cwd,
            stdout=stream,
            stderr=subprocess.STDOUT,
            check=False,
            text=True,
        )
        stream.write(f"\nexit_status={completed.returncode}\n")
    return {
        "command": command,
        "returncode": completed.returncode,
        "log": str(log_path),
    }


def command_capture(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def distribution_record(name: str) -> dict[str, Any]:
    try:
        distribution = importlib.metadata.distribution(name)
    except importlib.metadata.PackageNotFoundError:
        return {"installed": False}

    direct_url_text = distribution.read_text("direct_url.json")
    direct_url: Any = None
    if direct_url_text:
        try:
            direct_url = json.loads(direct_url_text)
        except json.JSONDecodeError:
            direct_url = direct_url_text

    return {
        "installed": True,
        "name": distribution.metadata.get("Name"),
        "version": distribution.version,
        "location": str(distribution.locate_file("")),
        "direct_url": direct_url,
    }


def homr_api_record() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for module_name in ("homr", "homr.main", "homr.constants"):
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001 - this is provenance collection
            result[module_name] = {
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            continue

        module_path_value = getattr(module, "__file__", None)
        module_path = Path(module_path_value).resolve() if module_path_value else None
        record: dict[str, Any] = {
            "ok": True,
            "file": str(module_path) if module_path else None,
            "sha256": (
                sha256_file(module_path)
                if module_path is not None and module_path.is_file()
                else None
            ),
        }
        if module_name == "homr.main":
            for attribute in (
                "download_weights",
                "load_and_preprocess_predictions",
                "ProcessingConfig",
            ):
                value = getattr(module, attribute, None)
                if value is not None:
                    try:
                        record[f"{attribute}_signature"] = str(inspect.signature(value))
                    except (TypeError, ValueError):
                        record[f"{attribute}_signature"] = None
        result[module_name] = record
    return result


def runtime_provenance_without_git(repo_root: Path, images: list[Path]) -> dict[str, Any]:
    """Collect runtime provenance without invoking git inside the container."""
    imports = {name: import_provenance(name) for name in IMPORT_CHECKS}
    hybrid = imports.get("src.pipeline.detection.hybrid", {})
    hybrid_runtime: dict[str, Any] = {}
    if hybrid.get("ok"):
        try:
            module = importlib.import_module("src.pipeline.detection.hybrid")
            hybrid_runtime = {
                "_HOMR_AVAILABLE": getattr(module, "_HOMR_AVAILABLE", None),
                "selected_baseline_route": (
                    "in_process"
                    if getattr(module, "_HOMR_AVAILABLE", False)
                    else "evaluator_fallback"
                ),
            }
        except Exception as exc:  # noqa: BLE001 - provenance must capture failures
            hybrid_runtime = {"error_type": type(exc).__name__, "error": str(exc)}

    return {
        "schema_version": "issue245.historical_homr_runtime_provenance.v1",
        "git": {
            "available": False,
            "reason": "disabled in container; host metadata is supplied via environment",
        },
        "runtime": {
            "python_executable": sys.executable,
            "python_version": sys.version,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cwd": str(Path.cwd()),
            "repo_root": str(repo_root),
        },
        "environment": {key: os.environ.get(key) for key in PROVENANCE_ENV_KEYS},
        "packages": package_versions(),
        "providers": runtime_provider_summary(),
        "imports": imports,
        "hybrid_runtime": hybrid_runtime,
        "images": [image_summary(path) for path in images],
    }


def candidate_model_roots() -> list[Path]:
    values = [
        Path(sys.prefix),
        Path.home() / ".cache",
        Path("/opt/weights"),
        Path("/root/.cache"),
    ]
    roots: list[Path] = []
    for path in values:
        resolved = path.resolve()
        if resolved.is_dir() and resolved not in roots:
            roots.append(resolved)
    return roots


def iter_model_files(roots: Iterable[Path]) -> Iterable[Path]:
    seen: set[Path] = set()
    for root in roots:
        try:
            candidates = root.rglob("*")
            for path in candidates:
                if not path.is_file() or path.suffix.lower() not in MODEL_SUFFIXES:
                    continue
                lowered = str(path).lower()
                if not any(hint in lowered for hint in MODEL_NAME_HINTS):
                    continue
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                yield resolved
        except OSError:
            continue


def model_artifact_inventory(limit: int = 200) -> dict[str, Any]:
    roots = candidate_model_roots()
    records: list[dict[str, Any]] = []
    for path in iter_model_files(roots):
        if len(records) >= limit:
            break
        try:
            records.append(
                {
                    "path": str(path),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
        except OSError as exc:
            records.append({"path": str(path), "error": str(exc)})
    return {
        "roots": [str(path) for path in roots],
        "count": len(records),
        "limit": limit,
        "artifacts": records,
    }


def historical_mask_path(historical_detection: Path, suffix: str) -> Path:
    stem = historical_detection.name.removesuffix("_detections.json")
    return historical_detection.parent / f"{stem}_{suffix}.png"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument("--historical-root", type=Path, default=DEFAULT_HISTORICAL_ROOT)
    parser.add_argument("--historical-detection", type=Path)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    repo_root = Path.cwd().resolve()
    image = resolve_inside_repo(repo_root, args.image, label="--image")
    historical_root = resolve_inside_repo(
        repo_root, args.historical_root, label="--historical-root"
    )
    output_root = resolve_inside_repo(repo_root, args.output_root, label="--output-root")

    if not image.is_file():
        raise FileNotFoundError(image)
    image_sha256 = sha256_file(image)
    if image_sha256 != EXPECTED_CANONICAL_SHA256:
        raise RuntimeError(
            "Canonical image hash mismatch: "
            f"expected={EXPECTED_CANONICAL_SHA256} actual={image_sha256} path={image}"
        )

    if args.historical_detection is None:
        historical_detection = discover_historical_detection(historical_root)
    else:
        historical_detection = resolve_inside_repo(
            repo_root, args.historical_detection, label="--historical-detection"
        )
        if not historical_detection.is_file():
            raise FileNotFoundError(historical_detection)

    if output_root.exists():
        if not args.force:
            raise FileExistsError(f"Output exists; pass --force: {output_root}")
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    provenance = runtime_provenance_without_git(repo_root, [image])
    provenance["issue245_historical_runtime"] = {
        "container_name": os.environ.get("ISSUE245_SOURCE_CONTAINER"),
        "source_image_id": os.environ.get("ISSUE245_SOURCE_IMAGE_ID"),
        "snapshot_image_id": os.environ.get("ISSUE245_SNAPSHOT_IMAGE_ID"),
        "host_commit": os.environ.get("ISSUE245_HOST_COMMIT"),
        "host_branch": os.environ.get("ISSUE245_HOST_BRANCH"),
    }
    provenance["distributions"] = {
        name: distribution_record(name)
        for name in (
            "homr",
            "numpy",
            "onnxruntime",
            "onnxruntime-gpu",
            "opencv-python-headless",
            "torch",
            "torchvision",
        )
    }
    provenance["homr_api"] = homr_api_record()
    provenance["pip_freeze"] = command_capture([sys.executable, "-m", "pip", "freeze"])
    write_json(output_root / "historical_runtime_provenance.json", provenance)

    evaluator_root = output_root / "evaluator"
    command = [
        sys.executable,
        "tools/issue245/run_homr_evaluator_compat.py",
        "--images",
        str(image),
        "--output-root",
        str(evaluator_root),
        "--force-run-id",
        args.run_id,
        "--enable-segnet-cache",
    ]
    run = run_logged(command, output_root / "historical_runtime_evaluator.log", cwd=repo_root)

    model_inventory = model_artifact_inventory()
    write_json(output_root / "historical_runtime_model_artifacts.json", model_inventory)

    report: dict[str, Any] = {
        "schema_version": "issue245.historical_runtime_probe.v1",
        "purpose": (
            "Run current evaluator code in the preserved historical sr_eval_gpu "
            "runtime and compare baseline HOMR with the retained artifact."
        ),
        "status": "route_failed" if run["returncode"] else "pending_comparison",
        "production_default_changed": False,
        "historical_artifact_used_as_production_input": False,
        "input": {
            "path": str(image),
            "sha256": image_sha256,
            "expected_sha256": EXPECTED_CANONICAL_SHA256,
        },
        "historical_detection": str(historical_detection),
        "runtime_provenance": str(output_root / "historical_runtime_provenance.json"),
        "model_artifacts": str(output_root / "historical_runtime_model_artifacts.json"),
        "run": run,
    }

    if run["returncode"] == 0:
        generated_detection = detection_path(
            evaluator_root, args.run_id, image, in_process=False
        )
        if not generated_detection.is_file():
            report["status"] = "missing_detection_artifact"
            report["generated_detection"] = str(generated_detection)
        else:
            historical_records = load_prediction_records(historical_detection)
            generated_records = load_prediction_records(generated_detection)
            report["status"] = "compared"
            report["generated_detection"] = str(generated_detection)
            report["comparison"] = compare_record_sets(
                "historical",
                historical_records,
                "historical_runtime_current_evaluator",
                generated_records,
            )
            report["masks"] = {
                "historical_staff": mask_summary(
                    historical_mask_path(historical_detection, "staff_mask")
                ),
                "generated_staff": mask_summary(
                    mask_path(
                        evaluator_root,
                        args.run_id,
                        image,
                        "staff_mask",
                        in_process=False,
                    )
                ),
                "historical_notehead": mask_summary(
                    historical_mask_path(historical_detection, "notehead_mask")
                ),
                "generated_notehead": mask_summary(
                    mask_path(
                        evaluator_root,
                        args.run_id,
                        image,
                        "notehead_mask",
                        in_process=False,
                    )
                ),
            }

    report_path = output_root / "historical_runtime_probe_report.json"
    write_json(report_path, report)

    print("Issue #245 historical runtime HOMR probe")
    print(f"Status: {report['status']}")
    print(f"Evaluator exit: {run['returncode']}")
    if report.get("comparison"):
        comparison = report["comparison"]
        print(
            f"historical={comparison['left_summary']['count']} "
            f"generated={comparison['right_summary']['count']} "
            f"matched={comparison['matched_count']} "
            f"historical_only={comparison['left_only_summary']['count']} "
            f"generated_only={comparison['right_only_summary']['count']}"
        )
    print(f"Report: {report_path.relative_to(repo_root)}")
    if run["returncode"] != 0:
        return int(run["returncode"])
    return 0 if report["status"] == "compared" else 1


if __name__ == "__main__":
    raise SystemExit(main())
