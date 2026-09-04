#!/usr/bin/env python3
"""Run B/latest HOMR detector-material smoke checks in the production container."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from tools.issue294 import run_downstream_candidate_matrix_host as matrix_host
from tools.issue294 import run_same_original_ab_host as base

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SMOKE_ROOT = PROJECT_ROOT / "temp/issue294_detector_smoke"


def _image_for_page(page: str) -> Path:
    image = PROJECT_ROOT / "data/evaluation2/images" / base.SCORE / f"page_{page}.png"
    if not image.is_file():
        raise FileNotFoundError(image)
    return image


def _load_result(path: Path, *, label: str, commit: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("status") != "completed":
        raise RuntimeError(f"{label} detector smoke incomplete: {payload!r}")

    homr = payload.get("homr")
    if not isinstance(homr, dict) or homr.get("commit") != commit:
        raise RuntimeError(
            f"{label} detector smoke commit mismatch: expected={commit} "
            f"actual={homr.get('commit') if isinstance(homr, dict) else None}"
        )

    runtime = payload.get("runtime")
    if not isinstance(runtime, dict) or runtime.get("cuda") is not True:
        raise RuntimeError(f"{label} detector smoke did not use CUDA runtime: {runtime!r}")

    sessions = payload.get("onnx_sessions")
    if not isinstance(sessions, list) or not sessions:
        raise RuntimeError(f"{label} detector smoke recorded no ONNX sessions")
    if not any(
        isinstance(session, dict)
        and "CUDAExecutionProvider" in session.get("active_providers", [])
        for session in sessions
    ):
        raise RuntimeError(f"{label} detector smoke has no active CUDA ONNX session: {sessions!r}")

    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        raise RuntimeError(f"{label} detector smoke artifacts missing")
    for key in ("detections", "staff_mask", "notehead_mask", "clef_mask"):
        artifact = Path(str(artifacts.get(key, "")))
        if not artifact.is_file():
            raise FileNotFoundError(f"{label} {key}: {artifact}")

    checks = payload.get("coordinate_checks")
    if not isinstance(checks, dict):
        raise RuntimeError(f"{label} coordinate checks missing")
    original_shape = checks.get("original_shape_wh")
    for key in ("staff_mask_shape_wh", "notehead_mask_shape_wh", "clef_mask_shape_wh"):
        if checks.get(key) != original_shape:
            raise RuntimeError(
                f"{label} coordinate shape mismatch: original={original_shape} "
                f"{key}={checks.get(key)}"
            )
    return payload


def _run_one(
    *,
    label: str,
    image: Path,
    source: Path,
    commit: str,
    root: Path,
) -> dict[str, Any]:
    output_root = root / label
    result_path = root / f"{label}_result.json"
    container_source = base.container_path(source)
    command = [
        "docker",
        "exec",
        "-w",
        str(base.CONTAINER_ROOT),
        "-e",
        f"PYTHONPATH={container_source}:{base.CONTAINER_ROOT}",
        base.CONTAINER,
        base.PIPELINE_PYTHON,
        "tools/issue294/run_latest_homr_detector_original.py",
        "--image",
        str(base.container_path(image)),
        "--homr-source",
        str(container_source),
        "--homr-commit",
        commit,
        "--output-root",
        str(base.container_path(output_root)),
        "--result",
        str(base.container_path(result_path)),
    ]
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    (root / f"{label}.log").write_text(completed.stdout or "", encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(
            f"{label} detector smoke failed ({completed.returncode}):\n{completed.stdout}"
        )
    return _load_result(result_path, label=label, commit=commit)


def run(run_tag: str, page: str, latest_commit: str) -> dict[str, Any]:
    checkout = matrix_host._require_issue294_checkout()
    base.require_container()
    if page not in base.ALLOWED_PAGES:
        raise ValueError(f"Unsupported representative page: {page}")

    resolved_latest = matrix_host._resolve_latest_commit(latest_commit)
    b_source, c_source, b_preflight, c_preflight = matrix_host._prepare_candidates(resolved_latest)
    image = _image_for_page(page)

    root = SMOKE_ROOT / run_tag
    if root.exists():
        raise FileExistsError(root)
    root.mkdir(parents=True, exist_ok=False)
    try:
        b_result = _run_one(
            label="B_b377",
            image=image,
            source=b_source,
            commit=matrix_host.B_COMMIT,
            root=root,
        )
        c_result = _run_one(
            label="C_latest",
            image=image,
            source=c_source,
            commit=resolved_latest,
            root=root,
        )
        report = {
            "schema_version": "issue294.detector_material_smoke_host.v1",
            "status": "completed",
            "checkout": checkout,
            "page": page,
            "image": str(image.relative_to(PROJECT_ROOT)),
            "B_homr_commit": matrix_host.B_COMMIT,
            "B_preflight": b_preflight,
            "B_result": b_result,
            "C_homr_commit": resolved_latest,
            "C_preflight": c_preflight,
            "C_result": c_result,
            "gates": {
                "B_detector_material_runtime": True,
                "C_detector_material_runtime": True,
                "both_cuda": True,
                "both_coordinate_shapes_match_original": True,
            },
        }
        report_path = root / "report.json"
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    finally:
        base._restore_host_ownership(root)
        base._restore_host_ownership(b_source)
        if c_source != b_source:
            base._restore_host_ownership(c_source)

    return {
        "status": "completed",
        "report": str(report_path),
        "page": page,
        "B_homr_commit": matrix_host.B_COMMIT,
        "latest_homr_commit": resolved_latest,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=f"Required checkout: git switch {matrix_host.ISSUE294_BRANCH}",
    )
    parser.add_argument("--run-tag", required=True)
    parser.add_argument("--page", choices=sorted(base.ALLOWED_PAGES), default="013")
    parser.add_argument("--latest-homr-commit", required=True)
    args = parser.parse_args()
    try:
        result = run(args.run_tag, args.page, args.latest_homr_commit)
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
