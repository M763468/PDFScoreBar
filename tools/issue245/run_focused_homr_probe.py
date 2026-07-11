#!/usr/bin/env python3
"""Run a focused baseline-HOMR provenance and route A/B probe for Issue #245.

The tool intentionally stops at baseline HOMR. It does not change production
configuration, run dense reconstruction, score with the CNN, or execute MMR and
numbering. Generated files must remain under an ignored ``logs/`` path.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any, Iterable

DEFAULT_OUTPUT_ROOT = Path("logs/issue245_focused_homr_probe")
DEFAULT_RUN_ID = "issue245_focused_baseline"
PACKAGE_NAMES = (
    "homr",
    "numpy",
    "opencv-python-headless",
    "onnxruntime",
    "onnxruntime-gpu",
    "torch",
    "torchvision",
    "Pillow",
    "scipy",
    "rapidocr-onnxruntime",
)
IMPORT_CHECKS = (
    "homr.main",
    "homr.music_xml_generator",
    "src.common.preprocessing",
    "src.homr_eval_scripts.core.metrics",
    "src.homr_eval_scripts.core.predictor",
    "src.homr_eval_scripts.core.reporting",
    "src.homr_eval_scripts.core.utils",
    "src.pipeline.detection.hybrid",
)
PROVENANCE_ENV_KEYS = (
    "CUDA_VISIBLE_DEVICES",
    "NVIDIA_VISIBLE_DEVICES",
    "ORT_CUDA_UNAVAILABLE",
    "PIPELINE_PYTHON",
    "POETRY_DYNAMIC_VERSIONING_BYPASS",
    "PYTHONPATH",
    "PDFSCORE_HOMR_VERBOSE_INTERNAL_LOGS",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_command(command: list[str], *, cwd: Path | None = None) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=cwd,
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


def git_metadata(repo_root: Path) -> dict[str, Any]:
    git = shutil.which("git")
    if git is None:
        return {"available": False, "reason": "git executable not found"}
    head = run_command([git, "rev-parse", "HEAD"], cwd=repo_root)
    branch = run_command([git, "branch", "--show-current"], cwd=repo_root)
    status = run_command([git, "status", "--short"], cwd=repo_root)
    return {
        "available": True,
        "head": head["stdout"] or None,
        "branch": branch["stdout"] or None,
        "status_short": status["stdout"],
        "diagnostics": {"head": head, "branch": branch, "status": status},
    }


def package_versions() -> dict[str, Any]:
    versions: dict[str, Any] = {}
    for package_name in PACKAGE_NAMES:
        try:
            versions[package_name] = importlib.metadata.version(package_name)
        except importlib.metadata.PackageNotFoundError:
            versions[package_name] = None
    return versions


def import_provenance(module_name: str) -> dict[str, Any]:
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # noqa: BLE001 - provenance must capture any runtime failure
        return {
            "ok": False,
            "exception_type": type(exc).__name__,
            "exception": str(exc),
            "traceback": traceback.format_exc(),
        }

    module_file_value = getattr(module, "__file__", None)
    module_file = Path(module_file_value).resolve() if module_file_value else None
    return {
        "ok": True,
        "module_file": str(module_file) if module_file else None,
        "module_sha256": (
            sha256_file(module_file) if module_file is not None and module_file.is_file() else None
        ),
    }


def runtime_provider_summary() -> dict[str, Any]:
    result: dict[str, Any] = {}
    try:
        import onnxruntime as ort

        result["onnxruntime"] = {
            "version": getattr(ort, "__version__", None),
            "device": ort.get_device(),
            "available_providers": ort.get_available_providers(),
        }
    except Exception as exc:  # noqa: BLE001
        result["onnxruntime"] = {
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    try:
        import torch

        cuda_available = bool(torch.cuda.is_available())
        result["torch"] = {
            "version": getattr(torch, "__version__", None),
            "cuda_available": cuda_available,
            "cuda_version": getattr(torch.version, "cuda", None),
            "device_count": torch.cuda.device_count() if cuda_available else 0,
            "device_names": (
                [torch.cuda.get_device_name(index) for index in range(torch.cuda.device_count())]
                if cuda_available
                else []
            ),
        }
    except Exception as exc:  # noqa: BLE001
        result["torch"] = {"error_type": type(exc).__name__, "error": str(exc)}
    return result


def image_summary(path: Path) -> dict[str, Any]:
    record: dict[str, Any] = {
        "path": str(path),
        "exists": path.is_file(),
    }
    if not path.is_file():
        return record
    record.update({"size_bytes": path.stat().st_size, "sha256": sha256_file(path)})
    try:
        import cv2

        image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if image is None:
            record["opencv_read_error"] = "cv2.imread returned None"
        else:
            record.update(
                {
                    "shape": list(image.shape),
                    "dtype": str(image.dtype),
                    "channels": 1 if image.ndim == 2 else int(image.shape[2]),
                }
            )
    except Exception as exc:  # noqa: BLE001
        record["opencv_read_error"] = f"{type(exc).__name__}: {exc}"
    return record


def collect_provenance(repo_root: Path, images: list[Path]) -> dict[str, Any]:
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
        except Exception as exc:  # noqa: BLE001
            hybrid_runtime = {"error_type": type(exc).__name__, "error": str(exc)}

    return {
        "schema_version": "issue245.homr_runtime_provenance.v1",
        "git": git_metadata(repo_root),
        "runtime": {
            "python_executable": sys.executable,
            "python_version": sys.version,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cwd": str(Path.cwd()),
        },
        "environment": {key: os.environ.get(key) for key in PROVENANCE_ENV_KEYS},
        "packages": package_versions(),
        "providers": runtime_provider_summary(),
        "imports": imports,
        "hybrid_runtime": hybrid_runtime,
        "images": [image_summary(path) for path in images],
    }


def normalize_box(value: Any) -> tuple[int, int, int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        return None
    try:
        return tuple(int(round(float(item))) for item in value[:4])  # type: ignore[return-value]
    except (TypeError, ValueError):
        return None


def load_detection_boxes(path: Path) -> list[tuple[int, int, int, int]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    predictions = payload.get("predictions", []) if isinstance(payload, dict) else []
    boxes: list[tuple[int, int, int, int]] = []
    for item in predictions:
        if not isinstance(item, dict):
            continue
        box = normalize_box(item.get("orig_bbox") or item.get("pred_bbox"))
        if box is not None:
            boxes.append(box)
    return boxes


def vertical_overlap_ratio(
    left: tuple[int, int, int, int], right: tuple[int, int, int, int]
) -> float:
    overlap = max(0, min(left[3], right[3]) - max(left[1], right[1]))
    denominator = max(1, min(left[3] - left[1], right[3] - right[1]))
    return overlap / denominator


def tolerant_match_count(
    left: list[tuple[int, int, int, int]],
    right: list[tuple[int, int, int, int]],
    *,
    x_distance_threshold: float = 12.0,
    vertical_overlap_threshold: float = 0.5,
) -> int:
    candidates: list[tuple[float, int, int]] = []
    for left_index, left_box in enumerate(left):
        left_x = (left_box[0] + left_box[2]) / 2.0
        for right_index, right_box in enumerate(right):
            right_x = (right_box[0] + right_box[2]) / 2.0
            x_distance = abs(left_x - right_x)
            if (
                x_distance <= x_distance_threshold
                and vertical_overlap_ratio(left_box, right_box) >= vertical_overlap_threshold
            ):
                candidates.append((x_distance, left_index, right_index))

    matched_left: set[int] = set()
    matched_right: set[int] = set()
    for _, left_index, right_index in sorted(candidates):
        if left_index in matched_left or right_index in matched_right:
            continue
        matched_left.add(left_index)
        matched_right.add(right_index)
    return len(matched_left)


def mask_summary(path: Path) -> dict[str, Any]:
    record: dict[str, Any] = {"path": str(path), "exists": path.is_file()}
    if not path.is_file():
        return record
    record.update({"size_bytes": path.stat().st_size, "sha256": sha256_file(path)})
    try:
        import cv2
        import numpy as np

        mask = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if mask is None:
            record["read_error"] = "cv2.imread returned None"
        else:
            record.update(
                {
                    "shape": list(mask.shape),
                    "dtype": str(mask.dtype),
                    "nonzero_pixels": int(np.count_nonzero(mask)),
                    "max_value": int(mask.max()) if mask.size else None,
                }
            )
    except Exception as exc:  # noqa: BLE001
        record["read_error"] = f"{type(exc).__name__}: {exc}"
    return record


def detection_path(root: Path, run_id: str, image: Path, *, in_process: bool) -> Path:
    if in_process:
        return root / run_id / "baseline" / "batch" / image.stem / f"{image.stem}_detections.json"
    return root / run_id / image.stem / f"{image.stem}_detections.json"


def mask_path(
    root: Path, run_id: str, image: Path, suffix: str, *, in_process: bool
) -> Path:
    base = detection_path(root, run_id, image, in_process=in_process).parent
    return base / f"{image.stem}_{suffix}.png"


def run_in_process(repo_root: Path, images: list[Path], output_root: Path, run_id: str) -> int:
    from src.pipeline.detection.hybrid import HybridDetector

    detector = HybridDetector(
        det_cfg={
            "hybrid_output_root": str(output_root),
            "enable_sr": False,
            "enable_cache": False,
            "write_staff_positions": True,
            "enable_debug": False,
        },
        images=images,
        run_id=run_id,
        project_root=repo_root,
        dry_run=False,
        skip_existing=False,
    )
    baseline_root = output_root / run_id / "baseline"
    detector._run_homr_in_process(baseline_root, enable_sr=False)
    return 0


def run_child(command: list[str], log_path: Path, *, cwd: Path) -> dict[str, Any]:
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
    return {"command": command, "returncode": completed.returncode, "log": str(log_path)}


def compare_routes(
    images: list[Path],
    in_process_root: Path,
    evaluator_root: Path,
    run_id: str,
) -> dict[str, Any]:
    pages: dict[str, Any] = {}
    aggregate = {
        "in_process_count": 0,
        "evaluator_count": 0,
        "tolerant_matches": 0,
        "in_process_only": 0,
        "evaluator_only": 0,
    }
    for image in images:
        in_process_detection = detection_path(
            in_process_root, run_id, image, in_process=True
        )
        evaluator_detection = detection_path(
            evaluator_root, run_id, image, in_process=False
        )
        page: dict[str, Any] = {
            "image": image_summary(image),
            "in_process_detection": str(in_process_detection),
            "evaluator_detection": str(evaluator_detection),
            "in_process_staff_mask": mask_summary(
                mask_path(in_process_root, run_id, image, "staff_mask", in_process=True)
            ),
            "evaluator_staff_mask": mask_summary(
                mask_path(evaluator_root, run_id, image, "staff_mask", in_process=False)
            ),
        }
        if not in_process_detection.is_file() or not evaluator_detection.is_file():
            page["status"] = "missing_detection_artifact"
            pages[image.stem] = page
            continue

        in_process_boxes = load_detection_boxes(in_process_detection)
        evaluator_boxes = load_detection_boxes(evaluator_detection)
        matched = tolerant_match_count(in_process_boxes, evaluator_boxes)
        comparison = {
            "in_process_count": len(in_process_boxes),
            "evaluator_count": len(evaluator_boxes),
            "tolerant_matches": matched,
            "in_process_only": len(in_process_boxes) - matched,
            "evaluator_only": len(evaluator_boxes) - matched,
            "semantic_equal": matched == len(in_process_boxes) == len(evaluator_boxes),
        }
        page["status"] = "compared"
        page["comparison"] = comparison
        for key in aggregate:
            aggregate[key] += int(comparison[key])
        pages[image.stem] = page
    return {"aggregate": aggregate, "pages": pages}


def validate_images(values: Iterable[str]) -> list[Path]:
    images = [Path(value).resolve() for value in values]
    missing = [path for path in images if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing image(s): " + ", ".join(map(str, missing)))
    if not images:
        raise ValueError("At least one --image is required")
    return images


def run_probe(args: argparse.Namespace) -> int:
    repo_root = Path.cwd().resolve()
    images = validate_images(args.image)
    output_root = (repo_root / args.output_root).resolve()
    try:
        output_root.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError("--output-root must be inside the repository") from exc

    if output_root.exists():
        if not args.force:
            raise FileExistsError(f"Output exists; pass --force to replace it: {output_root}")
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    provenance = collect_provenance(repo_root, images)
    write_json(output_root / "runtime_provenance.json", provenance)

    in_process_root = output_root / "in_process"
    evaluator_root = output_root / "evaluator"
    child_script = Path(__file__).resolve()
    in_process_command = [
        sys.executable,
        str(child_script),
        "_run-in-process",
        "--output-root",
        str(in_process_root),
        "--run-id",
        args.run_id,
    ]
    for image in images:
        in_process_command.extend(["--image", str(image)])
    in_process_result = run_child(
        in_process_command, output_root / "in_process.log", cwd=repo_root
    )

    evaluator_command = [
        sys.executable,
        "src/homr_eval_scripts/homr_evaluator.py",
        "--images",
        *[str(image) for image in images],
        "--output-root",
        str(evaluator_root),
        "--force-run-id",
        args.run_id,
        "--enable-segnet-cache",
    ]
    evaluator_result = run_child(
        evaluator_command, output_root / "evaluator.log", cwd=repo_root
    )

    report = {
        "schema_version": "issue245.focused_homr_probe.v1",
        "purpose": (
            "Compare current in-process baseline HOMR with evaluator fallback "
            "on identical images."
        ),
        "production_default_changed": False,
        "runtime_provenance": str(output_root / "runtime_provenance.json"),
        "runs": {"in_process": in_process_result, "evaluator": evaluator_result},
        "comparison": compare_routes(
            images,
            in_process_root,
            evaluator_root,
            args.run_id,
        ),
    }
    write_json(output_root / "focused_homr_probe_report.json", report)

    print("Issue #245 focused HOMR probe")
    print(f"Output: {output_root.relative_to(repo_root)}")
    print(f"Selected route: {provenance['hybrid_runtime'].get('selected_baseline_route')}")
    print(f"In-process exit: {in_process_result['returncode']}")
    print(f"Evaluator exit: {evaluator_result['returncode']}")
    print("Comparison:", report["comparison"]["aggregate"])
    return 0 if in_process_result["returncode"] == evaluator_result["returncode"] == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    probe = subparsers.add_parser("probe", help="Run provenance capture and baseline route A/B.")
    probe.add_argument("--image", action="append", required=True)
    probe.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    probe.add_argument("--run-id", default=DEFAULT_RUN_ID)
    probe.add_argument("--force", action="store_true")

    inspect = subparsers.add_parser("inspect", help="Capture runtime provenance without inference.")
    inspect.add_argument("--image", action="append", default=[])
    inspect.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT / "runtime_provenance.json",
    )

    internal = subparsers.add_parser("_run-in-process", help=argparse.SUPPRESS)
    internal.add_argument("--image", action="append", required=True)
    internal.add_argument("--output-root", type=Path, required=True)
    internal.add_argument("--run-id", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    repo_root = Path.cwd().resolve()
    if args.command == "probe":
        return run_probe(args)
    if args.command == "inspect":
        images = [Path(value).resolve() for value in args.image]
        output = (repo_root / args.output).resolve()
        write_json(output, collect_provenance(repo_root, images))
        print(f"Wrote: {output}")
        return 0
    if args.command == "_run-in-process":
        images = validate_images(args.image)
        return run_in_process(repo_root, images, args.output_root, args.run_id)
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
