#!/usr/bin/env python3
"""Write a compact Issue #255 downstream path-resolution diagnostic report.

The report is intentionally small enough to upload directly in a review session.
It does not run detector, HOMR, SR, MMR, or numbering inference.
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping

from src.common.connector_artifacts import (
    connector_mask_paths_for_numbering,
    describe_connector_artifacts,
)
from src.pipeline.core.config import load_yaml
from src.pipeline.detection import resolve_paths_from_detection

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DETECTOR_REPORT = (
    ROOT
    / "logs/verification/detector_full68"
    / "issue255_production_restore_full68_top_level_worker_01"
    / "detector_full68_verification_report.json"
)
DEFAULT_OUTPUT = ROOT / "logs/verification/issue255_downstream_path_diagnostic.json"
FOCUSED_SELECTORS = (
    "Shostakovich-Sym5-Va/page_013",
    "Shostakovich-Sym5-Va/page_014",
    "Va_Prokofiev_Symphony1/page_004",
)
EXPECTED_BRANCH = "fix/issue255-production-detector-restoration"


def _resolve_artifact_path(raw: str | Path) -> Path:
    path = Path(raw)
    if path.exists():
        return path.resolve()
    if path.is_absolute() and "workspace" in path.parts:
        index = path.parts.index("workspace")
        candidate = ROOT.joinpath(*path.parts[index + 1 :])
        if candidate.exists():
            return candidate.resolve()
    candidate = ROOT / path
    if candidate.exists():
        return candidate.resolve()
    raise FileNotFoundError(path)


def _rel(path: Path | str | None) -> str | None:
    if path is None:
        return None
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def _runs_by_score(report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for item in report.get("production_runs", []):
        if isinstance(item, Mapping) and isinstance(item.get("score"), str):
            result[str(item["score"])] = item
    return result


def _diagnose_page(
    *,
    selector: str,
    detector_run: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    score, page_id = selector.split("/", 1)
    image = ROOT / "data/evaluation2/images" / score / f"{page_id}.png"
    probe_root = _resolve_artifact_path(str(detector_run["probe_output_dir"]))
    hybrid_root = _resolve_artifact_path(str(detector_run["hybrid_output_dir"]))

    resolved = resolve_paths_from_detection(
        dict(config), probe_root, hybrid_root, [page_id], [image]
    )[0]
    staff_mask = _resolve_artifact_path(resolved["staff_mask"])
    connector_paths = connector_mask_paths_for_numbering(staff_mask)
    connector_description = describe_connector_artifacts(staff_mask)

    staff_is_debug = staff_mask.name.endswith("_debug_3_staff.png")
    connector_is_semantic = connector_description.get("source") == "proxy_symbol_layers"

    return {
        "selector": selector,
        "staff_mask": _rel(staff_mask),
        "staff_mask_is_expected_debug_geometry": staff_is_debug,
        "connector_masks": (
            {key: _rel(path) for key, path in connector_paths.items()}
            if connector_paths is not None
            else None
        ),
        "connector_source": connector_description.get("source"),
        "connector_coordinate_space": connector_description.get("coordinate_space"),
        "passed": bool(staff_is_debug and connector_is_semantic),
    }


def _host_git_metadata() -> dict[str, Any]:
    branch = os.environ.get("ISSUE255_GIT_BRANCH") or None
    local_sha = os.environ.get("ISSUE255_GIT_LOCAL_SHA") or None
    remote_sha = os.environ.get("ISSUE255_GIT_REMOTE_SHA") or None
    dirty_raw = os.environ.get("ISSUE255_GIT_DIRTY")
    dirty = None if dirty_raw is None else dirty_raw == "1"
    commit_matches_remote = bool(local_sha and remote_sha and local_sha == remote_sha)
    return {
        "metadata_source": "host_environment",
        "branch": branch,
        "expected_branch": EXPECTED_BRANCH,
        "local_sha": local_sha,
        "remote_sha": remote_sha,
        "commit_matches_remote": commit_matches_remote,
        "dirty": dirty,
    }


def run(detector_report_path: Path, output_path: Path) -> Path:
    report = json.loads(detector_report_path.read_text(encoding="utf-8"))
    if not isinstance(report, Mapping):
        raise ValueError("Detector report is not a mapping")
    config = load_yaml(ROOT / "configs/dense_full_pipeline.yaml")
    if not isinstance(config, Mapping):
        raise ValueError("Canonical config is not a mapping")

    runs = _runs_by_score(report)
    pages: list[dict[str, Any]] = []
    for selector in FOCUSED_SELECTORS:
        score = selector.split("/", 1)[0]
        detector_run = runs.get(score)
        if detector_run is None:
            raise ValueError(f"Detector run not found for score: {score}")
        pages.append(_diagnose_page(selector=selector, detector_run=detector_run, config=config))

    git = _host_git_metadata()
    module_paths = {
        "resolver": _rel(inspect.getsourcefile(resolve_paths_from_detection)),
        "connector_artifacts": _rel(
            inspect.getsourcefile(connector_mask_paths_for_numbering)
        ),
    }

    git_ok = bool(
        git["branch"] == EXPECTED_BRANCH
        and git["commit_matches_remote"]
        and git["dirty"] is False
    )
    payload = {
        "schema_version": "verification.issue255_downstream_path_diagnostic.v2",
        "git": git,
        "runtime": {
            "python_executable": sys.executable,
            "module_paths": module_paths,
        },
        "detector_report": _rel(detector_report_path),
        "pages": pages,
        "passed": bool(git_ok and all(page["passed"] for page in pages)),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--detector-report", type=Path, default=DEFAULT_DETECTOR_REPORT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = run(args.detector_report.resolve(), args.output.resolve())
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
