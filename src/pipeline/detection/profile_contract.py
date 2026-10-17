"""Validate pinned profile metadata shared by maintained and historical execution."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def load_profile_manifest(name: str, path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Invalid HOMR profile: {path}")
    if payload.get("schema_version") != "pipeline.homr_profile.v1":
        raise ValueError(f"Unsupported HOMR profile schema: {payload.get('schema_version')}")
    if payload.get("name") != name:
        raise ValueError(
            f"HOMR profile name mismatch: expected={name} actual={payload.get('name')}"
        )
    if payload.get("historical_detector_artifact_runtime_input") is not False:
        raise ValueError("HOMR profile must not permit historical detector artifacts")
    runtime = payload.get("runtime")
    if not isinstance(runtime, Mapping):
        raise ValueError("HOMR profile lacks runtime settings")
    for key in (
        "python",
        "homr_source",
        "pdfscore_source",
        "homr_commit_marker",
        "pdfscore_commit_marker",
        "compat_entrypoint",
    ):
        if not isinstance(runtime.get(key), str) or not runtime.get(key):
            raise ValueError(f"HOMR profile runtime lacks {key}")
    return dict(payload)


def _required_commit(profile: Mapping[str, Any], section: str) -> str:
    value = profile.get(section)
    if not isinstance(value, Mapping) or not isinstance(value.get("commit"), str):
        raise ValueError(f"HOMR profile lacks pinned commit: {section}")
    return str(value["commit"])


def validate_profile_runtime(profile: Mapping[str, Any]) -> None:
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
        raise FileNotFoundError("HOMR profile runtime is incomplete: " + ", ".join(missing))

    expected_homr = _required_commit(profile, "homr")
    expected_pdfscore = _required_commit(profile, "pdfscore_evaluator")
    actual_homr = homr_marker.read_text(encoding="utf-8").strip()
    actual_pdfscore = pdfscore_marker.read_text(encoding="utf-8").strip()
    if actual_homr != expected_homr:
        raise RuntimeError(
            f"HOMR profile commit mismatch: expected={expected_homr} actual={actual_homr}"
        )
    if actual_pdfscore != expected_pdfscore:
        raise RuntimeError(
            "PDFScore evaluator profile commit mismatch: "
            f"expected={expected_pdfscore} actual={actual_pdfscore}"
        )
