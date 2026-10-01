"""Run only the pinned maintained HOMR profile on original-page input."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .profile_contract import load_profile_manifest, validate_profile_runtime

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROFILE_PATH = PROJECT_ROOT / "configs/detector_profiles/maintained_original_homr.json"


def run_homr_profile(
    profile_name: str,
    *,
    images: Sequence[Path],
    output_root: Path,
    precomputed_sr: Mapping[Path, Path] | None = None,
) -> dict[str, Any]:
    if profile_name != "maintained_original":
        raise ValueError(f"Unsupported maintained HOMR profile: {profile_name}")
    profile = load_profile_manifest(profile_name, PROFILE_PATH)
    validate_profile_runtime(profile)
    output_root.mkdir(parents=True, exist_ok=True)
    if precomputed_sr is not None:
        raise ValueError("The maintained original profile does not consume precomputed SR")
    if len(images) != 1:
        raise ValueError("The maintained original profile runs one page per worker")
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
        "profile": profile_name,
        "manifest": str(PROFILE_PATH),
        "historical_detector_artifact_runtime_input": False,
        "commands": [command],
        "worker": payload,
    }
