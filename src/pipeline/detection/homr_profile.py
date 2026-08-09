"""Pinned HOMR runtime support for reproducible detector profiles."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.pipeline.core.subprocess_utils import run_with_logging

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROFILE_DIR = PROJECT_ROOT / "configs" / "detector_profiles"
SUPPORTED_PROFILES = {"stage_e_verified": PROFILE_DIR / "stage_e_verified_homr.json"}


def load_homr_profile(name: str) -> dict[str, Any]:
    path = SUPPORTED_PROFILES.get(name)
    if path is None:
        raise ValueError(f"Unsupported HOMR profile: {name}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Invalid HOMR profile: {path}")
    if payload.get("schema_version") != "pipeline.homr_profile.v1":
        raise ValueError(f"Unsupported HOMR profile schema: {payload.get('schema_version')}")
    if payload.get("name") != name:
        raise ValueError(f"HOMR profile name mismatch: expected={name} actual={payload.get('name')}")
    if payload.get("historical_detector_artifact_runtime_input") is not False:
        raise ValueError("HOMR profile must not permit historical detector artifacts")
    runtime = payload.get("runtime")
    if not isinstance(runtime, Mapping):
        raise ValueError("HOMR profile lacks runtime settings")
    for key in ("python", "homr_source", "pdfscore_source", "compat_entrypoint"):
        if not isinstance(runtime.get(key), str) or not runtime.get(key):
            raise ValueError(f"HOMR profile runtime lacks {key}")
    return dict(payload)


def build_profile_environment(profile: Mapping[str, Any]) -> dict[str, str]:
    runtime = profile["runtime"]
    assert isinstance(runtime, Mapping)
    homr_source = str(runtime["homr_source"])
    pdfscore_source = str(runtime["pdfscore_source"])
    existing = os.environ.get("PYTHONPATH", "")
    entries = [homr_source, pdfscore_source, f"{pdfscore_source}/src", str(PROJECT_ROOT)]
    if existing:
        entries.append(existing)
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(entries)
    env.setdefault("HOME", "/tmp")
    return env


def build_profile_command(
    profile: Mapping[str, Any],
    *,
    images: Sequence[Path],
    output_root: Path,
    precomputed_sr: Path | None = None,
) -> list[str]:
    if not images:
        raise ValueError("HOMR profile run requires at least one image")
    if precomputed_sr is not None and len(images) != 1:
        raise ValueError("Pre-computed SR profile runs support exactly one image")
    runtime = profile["runtime"]
    assert isinstance(runtime, Mapping)
    command = [
        str(runtime["python"]),
        str(runtime["compat_entrypoint"]),
        "--images",
        *(str(path) for path in images),
        "--output-root",
        str(output_root),
        "--force-run-id",
        "batch",
        "--enable-segnet-cache",
    ]
    if precomputed_sr is not None:
        command.extend(["--pre-computed-sr", str(precomputed_sr)])
    return command


def validate_profile_runtime(profile: Mapping[str, Any]) -> None:
    runtime = profile["runtime"]
    assert isinstance(runtime, Mapping)
    python = Path(str(runtime["python"]))
    homr_source = Path(str(runtime["homr_source"]))
    pdfscore_source = Path(str(runtime["pdfscore_source"]))
    compat = Path(str(runtime["compat_entrypoint"]))
    missing = [
        str(path)
        for path in (python, homr_source / "homr", pdfscore_source / "src", compat)
        if not path.exists()
    ]
    if missing:
        raise FileNotFoundError("HOMR profile runtime is incomplete: " + ", ".join(missing))


def run_homr_profile(
    profile_name: str,
    *,
    images: Sequence[Path],
    output_root: Path,
    precomputed_sr: Mapping[Path, Path] | None = None,
) -> dict[str, Any]:
    profile = load_homr_profile(profile_name)
    validate_profile_runtime(profile)
    output_root.mkdir(parents=True, exist_ok=True)
    env = build_profile_environment(profile)

    if precomputed_sr is None:
        command = build_profile_command(profile, images=images, output_root=output_root)
        run_with_logging(command, env=env, check=True)
        commands = [command]
    else:
        commands = []
        for image in images:
            sr_image = precomputed_sr.get(image)
            if sr_image is None:
                raise ValueError(f"Missing pre-computed SR image for {image}")
            if not sr_image.is_file():
                raise FileNotFoundError(sr_image)
            command = build_profile_command(
                profile,
                images=[image],
                output_root=output_root,
                precomputed_sr=sr_image,
            )
            run_with_logging(command, env=env, check=True)
            commands.append(command)

    return {
        "profile": profile_name,
        "manifest": str(SUPPORTED_PROFILES[profile_name]),
        "historical_detector_artifact_runtime_input": False,
        "commands": commands,
    }
