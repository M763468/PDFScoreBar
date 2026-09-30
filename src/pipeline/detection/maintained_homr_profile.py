"""Production-only dispatch for the maintained original-page HOMR baseline."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROFILE_PATH = PROJECT_ROOT / "configs" / "detector_profiles" / "maintained_original_homr.json"
PROFILE_NAME = "maintained_original"


def load_maintained_homr_profile() -> dict[str, Any]:
    payload = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Invalid maintained HOMR profile: {PROFILE_PATH}")
    if payload.get("schema_version") != "pipeline.homr_profile.v1":
        raise ValueError(f"Unsupported HOMR profile schema: {payload.get('schema_version')}")
    if payload.get("name") != PROFILE_NAME:
        raise ValueError(
            f"HOMR profile name mismatch: expected={PROFILE_NAME} actual={payload.get('name')}"
        )
    if payload.get("historical_detector_artifact_runtime_input") is not False:
        raise ValueError("Maintained HOMR profile must not permit historical detector artifacts")
    runtime = payload.get("runtime")
    if not isinstance(runtime, Mapping):
        raise ValueError("Maintained HOMR profile lacks runtime settings")
    for key in (
        "python",
        "homr_source",
        "pdfscore_source",
        "homr_commit_marker",
        "pdfscore_commit_marker",
        "compat_entrypoint",
    ):
        if not isinstance(runtime.get(key), str) or not runtime.get(key):
            raise ValueError(f"Maintained HOMR runtime lacks {key}")
    return dict(payload)


def _required_commit(profile: Mapping[str, Any], section: str) -> str:
    value = profile.get(section)
    if not isinstance(value, Mapping) or not isinstance(value.get("commit"), str):
        raise ValueError(f"Maintained HOMR profile lacks pinned commit: {section}")
    return str(value["commit"])


def validate_maintained_homr_runtime(profile: Mapping[str, Any]) -> None:
    runtime = profile["runtime"]
    assert isinstance(runtime, Mapping)
    python = Path(str(runtime["python"]))
    homr_source = Path(str(runtime["homr_source"]))
    pdfscore_source = Path(str(runtime["pdfscore_source"]))
    homr_marker = Path(str(runtime["homr_commit_marker"]))
    pdfscore_marker = Path(str(runtime["pdfscore_commit_marker"]))
    compat = Path(str(runtime["compat_entrypoint"]))
    required_paths = (
        python,
        homr_source / "homr",
        pdfscore_source / "src",
        homr_marker,
        pdfscore_marker,
        compat,
    )
    missing = [str(path) for path in required_paths if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Maintained HOMR runtime is incomplete: " + ", ".join(missing)
        )

    expected_homr = _required_commit(profile, "homr")
    expected_pdfscore = _required_commit(profile, "pdfscore_evaluator")
    actual_homr = homr_marker.read_text(encoding="utf-8").strip()
    actual_pdfscore = pdfscore_marker.read_text(encoding="utf-8").strip()
    if actual_homr != expected_homr:
        raise RuntimeError(
            f"Maintained HOMR commit mismatch: expected={expected_homr} actual={actual_homr}"
        )
    if actual_pdfscore != expected_pdfscore:
        raise RuntimeError(
            "Maintained PDFScore runtime marker mismatch: "
            f"expected={expected_pdfscore} actual={actual_pdfscore}"
        )


def run_maintained_homr_profile(
    *,
    images: Sequence[Path],
    output_root: Path,
) -> dict[str, Any]:
    """Run one original-page maintained HOMR baseline worker."""
    if len(images) != 1:
        raise ValueError("The maintained original profile runs one page per worker")

    profile = load_maintained_homr_profile()
    validate_maintained_homr_runtime(profile)
    output_root.mkdir(parents=True, exist_ok=True)

    from .maintained_homr_worker import run as run_maintained_homr

    image = Path(images[0]).resolve()
    result_path = output_root / "batch" / image.stem / "worker_result.json"
    payload = run_maintained_homr(image, output_root, result_path)
    command = [
        str(profile["runtime"]["python"]),
        "-m",
        "src.pipeline.detection.maintained_homr_worker",
        "--image",
        str(image),
        "--output-root",
        str(output_root),
        "--result",
        str(result_path),
    ]
    return {
        "profile": PROFILE_NAME,
        "manifest": str(PROFILE_PATH),
        "historical_detector_artifact_runtime_input": False,
        "commands": [command],
        "worker": payload,
    }
