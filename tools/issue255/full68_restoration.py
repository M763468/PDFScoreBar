"""Shared contracts for the Issue #255 full-68 historical-route restoration experiment."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tools.issue120.eval_full68_from_intermediates import SCORES
from tools.issue255.run_public_baseline_stage_e_reconstruction import (
    FRESH_CONTRACT,
    ROOT,
    _fresh_contract_matches,
    _resolve_repo_artifact,
)

EXPECTED_CURRENT_GT_METRICS: dict[str, int | float] = {
    "page_count": 68,
    "expected_page_count": 68,
    "gt": 3580,
    "pred": 3600,
    "tp": 3579,
    "fp": 1,
    "fn": 1,
    "fn_det": 0,
    "fn_cnn": 1,
}


def page_key(score: str, page: str) -> str:
    return f"{score}/{page}"


def canonical_pages(root: Path = ROOT) -> list[dict[str, Any]]:
    pages = []
    for score, page_ids in SCORES.items():
        for page in page_ids:
            pages.append(
                {
                    "key": page_key(score, page),
                    "score": score,
                    "page": page,
                    "image": root / "data/evaluation2/images" / score / f"{page}.png",
                }
            )
    if len(pages) != 68:
        raise RuntimeError(f"Canonical full-68 manifest drifted: {len(pages)} pages")
    return pages


def artifact_path(record: Mapping[str, Any], name: str) -> Path:
    value = record.get("path")
    if not isinstance(value, str):
        raise ValueError(f"Artifact record lacks path: {name}")
    path = _resolve_repo_artifact(value)
    if not path.is_file():
        raise FileNotFoundError(f"Artifact missing for {name}: {path}")
    return path


def validate_upstream_report(report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    if report.get("status") != "completed":
        raise ValueError("Full-68 upstream report is incomplete")
    if report.get("authoritative_full68") is not True:
        raise ValueError("Full-68 upstream report is not authoritative")
    if report.get("historical_artifact_used_as_runtime_input") is not False:
        raise ValueError("Historical runtime artifact dependency is forbidden")
    pages = report.get("pages")
    if not isinstance(pages, Mapping) or len(pages) != 68:
        raise ValueError("Full-68 upstream report must contain exactly 68 pages")

    validated: dict[str, Mapping[str, Any]] = {}
    for expected in canonical_pages():
        key = str(expected["key"])
        row = pages.get(key)
        if not isinstance(row, Mapping) or row.get("status") != "completed":
            raise ValueError(f"Missing completed upstream page: {key}")
        if row.get("score") != expected["score"] or row.get("page") != expected["page"]:
            raise ValueError(f"Upstream page identity mismatch: {key}")
        if row.get("historical_artifact_used_as_runtime_input") is not False:
            raise ValueError(f"Historical runtime artifact dependency on page: {key}")
        contract = row.get("detector_input_contract")
        if not _fresh_contract_matches(contract):
            raise ValueError(f"Fresh contract mismatch on page: {key}")
        artifacts = row.get("artifacts")
        if not isinstance(artifacts, Mapping):
            raise ValueError(f"Upstream page lacks artifacts: {key}")
        for name in (
            "image",
            "fresh_baseline",
            "fresh_sr_x4_image",
            "public_profile_sr",
            "current_omr",
            "restored_hybrid",
            "staff_mask",
            "clef_mask",
        ):
            artifact = artifacts.get(name)
            if not isinstance(artifact, Mapping):
                raise ValueError(f"Upstream page lacks artifact record: {key}.{name}")
            artifact_path(artifact, f"{key}.{name}")
        validated[key] = row
    return validated


def inventory_from_upstream_report(report: Mapping[str, Any]) -> list[dict[str, str]]:
    pages = validate_upstream_report(report)
    inventory = []
    for expected in canonical_pages():
        key = str(expected["key"])
        row = pages[key]
        artifacts = row["artifacts"]
        assert isinstance(artifacts, Mapping)
        baseline = artifact_path(artifacts["fresh_baseline"], f"{key}.fresh_baseline")
        inventory.append(
            {
                "score": str(expected["score"]),
                "page": str(expected["page"]),
                "image": str(artifact_path(artifacts["image"], f"{key}.image")),
                "hybrid_predictions": str(
                    artifact_path(artifacts["restored_hybrid"], f"{key}.restored_hybrid")
                ),
                "staff_mask": str(artifact_path(artifacts["staff_mask"], f"{key}.staff_mask")),
                "clef_mask": str(artifact_path(artifacts["clef_mask"], f"{key}.clef_mask")),
                "run_dir": str(baseline.parent),
            }
        )
    return inventory


def metric_mismatches(summary: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    mismatches: dict[str, dict[str, Any]] = {}
    for key, expected in EXPECTED_CURRENT_GT_METRICS.items():
        actual = summary.get(key)
        matches = actual == expected
        if isinstance(expected, float) and isinstance(actual, (int, float)):
            matches = abs(float(actual) - expected) <= 1e-12
        if not matches:
            mismatches[key] = {"expected": expected, "actual": actual}
    return mismatches


__all__ = [
    "EXPECTED_CURRENT_GT_METRICS",
    "FRESH_CONTRACT",
    "artifact_path",
    "canonical_pages",
    "inventory_from_upstream_report",
    "metric_mismatches",
    "page_key",
    "validate_upstream_report",
]
