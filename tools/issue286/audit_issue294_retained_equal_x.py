#!/usr/bin/env python3
"""Audit Issue #286 from retained Issue #294 full68 candidate-C artifacts.

This is a read-only retained-artifact audit. It consumes the Issue #294
full68_host.json plus its child matrix reports, reconstructs the adopted
C_latest candidate-native Phase-A numbering input, and screens exact-x
representative policies. It does not run detector, HOMR, SR, OMR-DLN, CNN,
MMR, or OCR inference.
"""

from __future__ import annotations

import argparse
import copy
import importlib.metadata
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.measure_numbering.numbering import MeasureNumberer
from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.measure_numbering.types import Score
from src.pipeline.core.config import load_yaml
from src.pipeline.utils.images import load_image
from src.pipeline.utils.io import load_json
from tools.issue120.eval_full68_from_intermediates import SCORES
from tools.issue286.audit_current_full68_equal_x import (
    SELECTORS,
    apply_selector,
    inventory_ties,
)

CURRENT_CONFIG = PROJECT_ROOT / "configs/dense_full_pipeline.yaml"
CURRENT_HOMR_PROFILE = PROJECT_ROOT / "configs/detector_profiles/maintained_original_homr.json"
CURRENT_PYPROJECT = PROJECT_ROOT / "pyproject.toml"
RUNTIME_DISTRIBUTIONS = (
    "numpy",
    "opencv-python-headless",
    "scipy",
)
REPLAY_SOURCE_FILES = (
    "src/measure_numbering/pipeline.py",
    "src/measure_numbering/numbering.py",
    "src/measure_numbering/builder.py",
    "src/measure_numbering/connector_aware_builder.py",
    "src/measure_numbering/connector_evidence.py",
    "src/measure_numbering/types.py",
)


def runtime_provenance() -> dict[str, Any]:
    packages = {}
    for distribution in (*RUNTIME_DISTRIBUTIONS, "opencv-python"):
        try:
            packages[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            continue
    return {
        "python_executable": sys.executable,
        "python_version": sys.version,
        "python_major_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
        "packages": packages,
    }


def expected_runtime_versions() -> dict[str, str]:
    text = CURRENT_PYPROJECT.read_text(encoding="utf-8")
    versions = {}
    for distribution in RUNTIME_DISTRIBUTIONS:
        marker = f'"{distribution}=='
        start = text.find(marker)
        if start < 0:
            raise ValueError(f"Missing exact runtime dependency in {CURRENT_PYPROJECT}: {distribution}")
        value_start = start + len(marker)
        value_end = text.find('"', value_start)
        if value_end < 0:
            raise ValueError(f"Malformed runtime dependency in {CURRENT_PYPROJECT}: {distribution}")
        versions[distribution] = text[value_start:value_end]
    return versions


def expected_runtime_contract() -> dict[str, Any]:
    return {
        "python_major_minor": "3.11",
        "packages": expected_runtime_versions(),
    }


def runtime_contract_drift(runtime: dict[str, Any]) -> list[dict[str, Any]]:
    expected = expected_runtime_contract()
    drift = []
    actual_python = runtime.get("python_major_minor")
    if actual_python != expected["python_major_minor"]:
        drift.append(
            {
                "component": "python_major_minor",
                "expected": expected["python_major_minor"],
                "actual": actual_python,
            }
        )

    packages = runtime.get("packages") or {}
    for distribution, expected_version in expected["packages"].items():
        actual_version = packages.get(distribution)
        if actual_version != expected_version:
            drift.append(
                {
                    "component": distribution,
                    "expected": expected_version,
                    "actual": actual_version,
                }
            )
    return drift


def git_blob_sha(ref: str, path: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", f"{ref}:{path}"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def replay_source_provenance(retained_checkout: Any) -> dict[str, Any]:
    if not isinstance(retained_checkout, dict) or not retained_checkout.get("head"):
        return {
            "retained_head": None,
            "current_head": git_head(),
            "all_equal": None,
            "files": {},
            "note": "Retained manifest has no checkout.head; source equality was not evaluated.",
        }

    retained_head = str(retained_checkout["head"])
    current_head = git_head()
    files = {}
    comparable = True
    for path in REPLAY_SOURCE_FILES:
        try:
            retained_blob = git_blob_sha(retained_head, path)
            current_blob = git_blob_sha(current_head, path)
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            comparable = False
            stderr = getattr(exc, "stderr", None)
            files[path] = {
                "retained_blob": None,
                "current_blob": None,
                "equal": None,
                "error": stderr.strip() if stderr else str(exc),
            }
            continue
        files[path] = {
            "retained_blob": retained_blob,
            "current_blob": current_blob,
            "equal": retained_blob == current_blob,
        }
    return {
        "retained_head": retained_head,
        "current_head": current_head,
        "all_equal": (
            all(item["equal"] for item in files.values())
            if comparable
            else None
        ),
        "files": files,
    }


def git_head() -> str:
    host_commit = os.environ.get("ISSUE286_SOURCE_COMMIT")
    if host_commit:
        return host_commit

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unavailable"
    return result.stdout.strip()


def retained_project_root(full68_manifest: Path) -> Path:
    """Infer the retained checkout root from an existing manifest under logs/."""
    resolved = full68_manifest.resolve()
    parts = resolved.parts
    if "logs" not in parts:
        raise ValueError(f"Retained manifest is not under a logs tree: {resolved}")
    index = parts.index("logs")
    return Path(*parts[:index])


def resolve_project_path(
    value: str | Path,
    *,
    artifact_roots: tuple[Path, ...] = (),
) -> Path:
    raw = Path(value)
    if raw.is_file():
        return raw.resolve()

    roots = tuple(dict.fromkeys((*artifact_roots, PROJECT_ROOT)))

    if not raw.is_absolute():
        for root in roots:
            candidate = root / raw
            if candidate.is_file():
                return candidate.resolve()

    text = str(raw)
    if "/workspace/" in text:
        suffix = text.split("/workspace/", 1)[1]
        for root in roots:
            candidate = root / suffix
            if candidate.is_file():
                return candidate.resolve()

    parts = raw.parts
    for marker in ("ws_PDFScoreBar", "ws_PDFScoreBar_issue294"):
        if marker in parts:
            index = parts.index(marker)
            for root in roots:
                candidate = root.joinpath(*parts[index + 1 :])
                if candidate.is_file():
                    return candidate.resolve()

    for anchor in ("logs", "data"):
        if anchor in parts:
            index = parts.index(anchor)
            for root in roots:
                candidate = root.joinpath(*parts[index:])
                if candidate.is_file():
                    return candidate.resolve()

    raise FileNotFoundError(raw)


def canonical_keys() -> set[tuple[str, str]]:
    return {(score, page) for score, pages in SCORES.items() for page in pages}


def page_identity(image_value: str | Path) -> tuple[str, str]:
    raw = Path(image_value)
    key = (raw.parent.name, raw.stem)
    if key in canonical_keys():
        return key
    matches = [score for score in SCORES if score in raw.parts]
    if len(matches) == 1 and raw.stem in SCORES[matches[0]]:
        return matches[0], raw.stem
    raise ValueError(f"Cannot map matrix image to canonical full68 page: {raw}")


def current_contract() -> dict[str, Any]:
    config = load_yaml(CURRENT_CONFIG)
    detection = config.get("detection") or {}
    profile = load_json(CURRENT_HOMR_PROFILE)
    return {
        "homr_profile": detection.get("homr_profile"),
        "homr_commit": (profile.get("homr") or {}).get("commit"),
        "detector_route": detection.get("detector_route"),
        "cnn_threshold": detection.get("cnn_threshold"),
        "cnn_model_manifest": detection.get("cnn_model_manifest"),
        "cnn_apply_nms": detection.get("cnn_apply_nms"),
    }


def signature(page_obj: Any) -> dict[str, Any]:
    page = copy.deepcopy(page_obj)
    score = Score()
    score.pages.append(page)
    MeasureNumberer().number_score(score, start_number=1)
    pages = []
    for item in score.pages:
        systems = []
        for system in item.systems:
            measures = list(system.measures)
            systems.append(
                {
                    "staff_count": len(system.staves),
                    "measure_count": len(measures),
                    "measure_numbers": [measure.number for measure in measures],
                    "measure_bboxes": [
                        [
                            measure.bbox.x1,
                            measure.bbox.y1,
                            measure.bbox.x2,
                            measure.bbox.y2,
                        ]
                        for measure in measures
                    ],
                }
            )
        pages.append(
            {
                "page_number": item.page_number,
                "system_count": len(item.systems),
                "systems": systems,
                "total_measures": sum(system["measure_count"] for system in systems),
            }
        )
    return {
        "pages": pages,
        "total_measures": sum(page["total_measures"] for page in pages),
    }


def logical_signature(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "pages": [
            {
                "systems": [
                    {
                        "staff_count": system["staff_count"],
                        "measure_numbers": system["measure_numbers"],
                    }
                    for system in page.get("systems", [])
                    if int(system.get("measure_count", 0)) > 0
                ]
            }
            for page in payload.get("pages", [])
        ]
    }


def geometry_signature(payload: dict[str, Any]) -> list[list[int]]:
    return [
        list(bbox)
        for page in payload.get("pages", [])
        for system in page.get("systems", [])
        for bbox in system.get("measure_bboxes", [])
    ]


def retained_to_current_replay_difference(
    retained: dict[str, Any],
    replay: dict[str, Any],
) -> dict[str, Any]:
    """Describe only fields that differ between retained and current replay signatures."""
    difference: dict[str, Any] = {
        "retained_total_measures": retained.get("total_measures"),
        "current_replay_total_measures": replay.get("total_measures"),
        "page_differences": [],
    }
    retained_pages = retained.get("pages", [])
    replay_pages = replay.get("pages", [])
    page_count = max(len(retained_pages), len(replay_pages))

    for page_index in range(page_count):
        retained_page = retained_pages[page_index] if page_index < len(retained_pages) else None
        replay_page = replay_pages[page_index] if page_index < len(replay_pages) else None
        if retained_page == replay_page:
            continue

        page_difference: dict[str, Any] = {"page_index": page_index}
        if retained_page is None or replay_page is None:
            page_difference["retained_page"] = retained_page
            page_difference["current_replay_page"] = replay_page
            difference["page_differences"].append(page_difference)
            continue

        for field in ("page_number", "system_count", "total_measures"):
            if retained_page.get(field) != replay_page.get(field):
                page_difference[field] = {
                    "retained": retained_page.get(field),
                    "current_replay": replay_page.get(field),
                }

        system_differences = []
        retained_systems = retained_page.get("systems", [])
        replay_systems = replay_page.get("systems", [])
        system_count = max(len(retained_systems), len(replay_systems))
        for system_index in range(system_count):
            retained_system = (
                retained_systems[system_index] if system_index < len(retained_systems) else None
            )
            replay_system = replay_systems[system_index] if system_index < len(replay_systems) else None
            if retained_system == replay_system:
                continue

            system_difference: dict[str, Any] = {"system_index": system_index}
            if retained_system is None or replay_system is None:
                system_difference["retained_system"] = retained_system
                system_difference["current_replay_system"] = replay_system
                system_differences.append(system_difference)
                continue

            for field in (
                "staff_count",
                "measure_count",
                "measure_numbers",
                "measure_bboxes",
            ):
                if retained_system.get(field) != replay_system.get(field):
                    system_difference[field] = {
                        "retained": retained_system.get(field),
                        "current_replay": replay_system.get(field),
                    }
            system_differences.append(system_difference)

        if system_differences:
            page_difference["system_differences"] = system_differences
        difference["page_differences"].append(page_difference)

    return difference


def matrix_pages(
    full68_manifest: Path,
    *,
    artifact_roots: tuple[Path, ...] = (),
) -> dict[tuple[str, str], dict[str, Any]]:
    manifest = load_json(full68_manifest)
    if manifest.get("schema_version") != "issue294.full68_host.v1":
        raise ValueError(f"Unexpected Issue #294 full68 schema: {manifest.get('schema_version')}")
    if manifest.get("status") != "completed" or int(manifest.get("completed_page_count", 0)) != 68:
        raise ValueError("Issue #294 full68 manifest is not completed 68/68")

    pages: dict[tuple[str, str], dict[str, Any]] = {}
    chunks = manifest.get("completed_chunks")
    if not isinstance(chunks, list):
        raise ValueError("Issue #294 full68 manifest lacks completed_chunks")
    for chunk in chunks:
        report_path = resolve_project_path(
            str(chunk["matrix_report"]),
            artifact_roots=artifact_roots,
        )
        report = load_json(report_path)
        if report.get("status") != "completed":
            raise ValueError(f"Incomplete matrix report: {report_path}")
        report_pages = report.get("pages")
        if not isinstance(report_pages, list):
            raise ValueError(f"Matrix report lacks pages: {report_path}")
        for page in report_pages:
            identity = page_identity(str(page["image"]))
            if identity in pages:
                raise ValueError(f"Duplicate matrix page: {identity}")
            pages[identity] = page

    if set(pages) != canonical_keys():
        raise ValueError(
            "Issue #294 matrix reports do not form canonical full68: "
            f"observed={len(pages)} missing={sorted(canonical_keys() - set(pages))}"
        )
    pages[("__manifest__", "__metadata__")] = manifest
    return pages


def make_page(
    matrix_page: dict[str, Any],
    *,
    artifact_roots: tuple[Path, ...] = (),
) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    image_path = resolve_project_path(
        str(matrix_page["image"]),
        artifact_roots=artifact_roots,
    )
    mode = matrix_page["modes"]["candidate_native_geometry"]
    variant = mode["variants"]["C_latest"]
    support_path = resolve_project_path(
        str(matrix_page["fixed_inputs"]["support_result"]),
        artifact_roots=artifact_roots,
    )
    support = load_json(support_path)
    staff_mask = resolve_project_path(
        str(variant["staff_mask"]),
        artifact_roots=artifact_roots,
    )
    connector_symbols = resolve_project_path(
        str(support["connector_symbols"]),
        artifact_roots=artifact_roots,
    )
    connector_brace_dot = resolve_project_path(
        str(support["connector_brace_dot"]),
        artifact_roots=artifact_roots,
    )

    image = load_image(image_path)
    height, width = image.shape[:2]
    final_barlines = [[int(v) for v in box] for box in variant["final_barlines"]]
    page_obj = MeasureNumberingPipeline().process_page(
        final_barlines,
        staff_mask,
        (width, height),
        page_number=1,
        assume_one_staff_per_system=False,
        image=None,
        connector_mask_paths={
            "symbols": connector_symbols,
            "brace_dot": connector_brace_dot,
        },
    )
    return page_obj, variant, {
        "image": str(image_path),
        "staff_mask": str(staff_mask),
        "support_result": str(support_path),
        "connector_symbols": str(connector_symbols),
        "connector_brace_dot": str(connector_brace_dot),
    }


def audit_page(
    identity: tuple[str, str],
    matrix_page: dict[str, Any],
    *,
    artifact_roots: tuple[Path, ...] = (),
) -> dict[str, Any]:
    page_obj, variant, paths = make_page(
        matrix_page,
        artifact_roots=artifact_roots,
    )
    retained = variant["numbering"]
    replay = signature(page_obj)
    retained_logical = logical_signature(retained)
    replay_logical = logical_signature(replay)
    retained_geometry = geometry_signature(retained)
    replay_geometry = geometry_signature(replay)

    selectors = {}
    for name in SELECTORS:
        selected_page, decisions = apply_selector(page_obj, name)
        candidate = signature(selected_page)
        candidate_logical = logical_signature(candidate)
        candidate_geometry = geometry_signature(candidate)
        selectors[name] = {
            "logical_equal_to_current_replay": candidate_logical == replay_logical,
            "geometry_equal_to_current_replay": candidate_geometry == replay_geometry,
            "exact_equal_to_current_replay": candidate == replay,
            "logical_equal_to_retained": candidate_logical == retained_logical,
            "geometry_equal_to_retained": candidate_geometry == retained_geometry,
            "exact_equal_to_retained": candidate == retained,
            "decisions": decisions,
        }

    return {
        "score": identity[0],
        "page": identity[1],
        "paths": paths,
        "retained_final_barline_count": int(variant["final_barline_count"]),
        "retained_to_current_replay": {
            "logical_equal": replay_logical == retained_logical,
            "geometry_equal": replay_geometry == retained_geometry,
            "exact_equal": replay == retained,
            "difference": retained_to_current_replay_difference(retained, replay),
        },
        "equal_x_ties": inventory_ties(page_obj),
        "selectors": selectors,
    }


def summarize(pages: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    tie_pages = [key for key, value in pages.items() if value["equal_x_ties"]]
    retained_replay_logical_mismatch = [
        key
        for key, value in pages.items()
        if not value["retained_to_current_replay"]["logical_equal"]
    ]
    retained_replay_geometry_mismatch = [
        key
        for key, value in pages.items()
        if not value["retained_to_current_replay"]["geometry_equal"]
    ]
    retained_replay_any_mismatch = sorted(
        set(retained_replay_logical_mismatch) | set(retained_replay_geometry_mismatch)
    )

    selectors = {}
    for name in SELECTORS:
        logical_changed_from_replay = [
            key
            for key, value in pages.items()
            if not value["selectors"][name]["logical_equal_to_current_replay"]
        ]
        geometry_changed_from_replay = [
            key
            for key, value in pages.items()
            if not value["selectors"][name]["geometry_equal_to_current_replay"]
        ]
        selectors[name] = {
            "logical_changed_from_current_replay_pages": [
                f"{score}/{page}" for score, page in logical_changed_from_replay
            ],
            "geometry_changed_from_current_replay_pages": [
                f"{score}/{page}" for score, page in geometry_changed_from_replay
            ],
        }

    return {
        "page_count": len(pages),
        "equal_x_tie_page_count": len(tie_pages),
        "equal_x_tie_group_count": sum(len(pages[key]["equal_x_ties"]) for key in tie_pages),
        "equal_x_tie_pages": [f"{score}/{page}" for score, page in tie_pages],
        "retained_to_current_replay_logical_mismatch_pages": [
            f"{score}/{page}" for score, page in retained_replay_logical_mismatch
        ],
        "retained_to_current_replay_geometry_mismatch_pages": [
            f"{score}/{page}" for score, page in retained_replay_geometry_mismatch
        ],
        "retained_to_current_replay_difference_details": {
            f"{score}/{page}": pages[(score, page)]["retained_to_current_replay"]["difference"]
            for score, page in retained_replay_any_mismatch
        },
        "selectors": selectors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full68-manifest", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument(
        "--allow-contract-drift",
        action="store_true",
        help="Allow retained #294 evidence that does not match current C/threshold provenance.",
    )
    parser.add_argument(
        "--allow-runtime-drift",
        action="store_true",
        help=(
            "Allow the audit Python environment to differ from the exact numpy/OpenCV/SciPy "
            "versions pinned by the current project. Diagnostic use only."
        ),
    )
    args = parser.parse_args()

    full68_manifest = args.full68_manifest.resolve()
    retained_root = retained_project_root(full68_manifest)
    artifact_roots = (retained_root,)
    pages_with_metadata = matrix_pages(
        full68_manifest,
        artifact_roots=artifact_roots,
    )
    manifest = pages_with_metadata.pop(("__manifest__", "__metadata__"))
    contract = current_contract()
    runtime = runtime_provenance()
    runtime_drift = runtime_contract_drift(runtime)
    if runtime_drift and not args.allow_runtime_drift:
        raise ValueError(
            "Audit runtime does not match current project runtime pins: "
            f"{runtime_drift}"
        )

    drift = []
    if manifest.get("latest_homr_commit") != contract["homr_commit"]:
        drift.append(
            {
                "field": "latest_homr_commit",
                "retained": manifest.get("latest_homr_commit"),
                "current": contract["homr_commit"],
            }
        )

    pages: dict[tuple[str, str], dict[str, Any]] = {}
    threshold_values = set()
    for score, canonical_pages in SCORES.items():
        for page in canonical_pages:
            identity = (score, page)
            matrix_page = pages_with_metadata[identity]
            threshold_values.add(float(matrix_page["fixed_inputs"]["cnn_threshold"]))
            pages[identity] = audit_page(
                identity,
                matrix_page,
                artifact_roots=artifact_roots,
            )

    current_threshold = float(contract["cnn_threshold"])
    if threshold_values != {current_threshold}:
        drift.append(
            {
                "field": "cnn_threshold",
                "retained": sorted(threshold_values),
                "current": current_threshold,
            }
        )
    if drift and not args.allow_contract_drift:
        raise ValueError(
            "Retained Issue #294 evidence does not match current production provenance: "
            f"{drift}"
        )

    summary = summarize(pages)
    result = {
        "schema_version": "issue286.issue294_retained_equal_x_audit.v2",
        "source_commit": git_head(),
        "runtime_provenance": runtime,
        "runtime_contract_expected": expected_runtime_contract(),
        "runtime_contract_drift": runtime_drift,
        "full68_manifest": str(full68_manifest),
        "retained_project_root": str(retained_root),
        "retained_checkout": manifest.get("checkout"),
        "replay_source_provenance": replay_source_provenance(manifest.get("checkout")),
        "retained_latest_homr_commit": manifest.get("latest_homr_commit"),
        "current_contract": contract,
        "contract_drift": drift,
        "comparison_definitions": {
            "retained_to_current_replay": (
                "Compare the numbering signature saved by Issue #294 with a new numbering "
                "calculation from the same retained barlines/staff/connector artifacts using "
                "the current checkout."
            ),
            "selector_to_current_replay": (
                "Compare a deterministic exact-x representative selector with the unmodified "
                "current replay from the same reconstructed page. This isolates selector-only "
                "effects from retained-vs-current replay differences."
            ),
        },
        "scope": {
            "producer": "Issue #294 C_latest candidate_native_geometry",
            "inference_reexecuted": False,
            "production_numbering_modified": False,
            "selector_is_adoption_decision": False,
        },
        "summary": summary,
        "pages": {
            f"{score}/{page}": pages[(score, page)]
            for score, canonical_pages in SCORES.items()
            for page in canonical_pages
        },
    }
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    # A retained-vs-current replay mismatch is diagnostic only for Issue #286.
    # The selector comparison is defined against the unmodified current replay,
    # so a successful audit returns zero even when the historical retained
    # numbering signature differs.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
