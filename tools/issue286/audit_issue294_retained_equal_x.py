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
import json
import subprocess
from pathlib import Path
from typing import Any

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

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CURRENT_CONFIG = PROJECT_ROOT / "configs/dense_full_pipeline.yaml"
CURRENT_HOMR_PROFILE = PROJECT_ROOT / "configs/detector_profiles/maintained_original_homr.json"


def git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
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

    selectors = {}
    for name in SELECTORS:
        selected_page, decisions = apply_selector(page_obj, name)
        candidate = signature(selected_page)
        selectors[name] = {
            "logical_equal_to_retained": logical_signature(candidate) == retained_logical,
            "geometry_equal_to_retained": geometry_signature(candidate)
            == geometry_signature(retained),
            "exact_equal_to_retained": candidate == retained,
            "decisions": decisions,
        }

    return {
        "score": identity[0],
        "page": identity[1],
        "paths": paths,
        "retained_final_barline_count": int(variant["final_barline_count"]),
        "replay": {
            "logical_equal_to_retained": replay_logical == retained_logical,
            "geometry_equal_to_retained": geometry_signature(replay)
            == geometry_signature(retained),
            "exact_equal_to_retained": replay == retained,
        },
        "equal_x_ties": inventory_ties(page_obj),
        "selectors": selectors,
    }


def summarize(pages: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    tie_pages = [key for key, value in pages.items() if value["equal_x_ties"]]
    replay_logical_mismatch = [
        key for key, value in pages.items() if not value["replay"]["logical_equal_to_retained"]
    ]
    replay_geometry_mismatch = [
        key for key, value in pages.items() if not value["replay"]["geometry_equal_to_retained"]
    ]
    selectors = {}
    for name in SELECTORS:
        logical_changed = [
            key
            for key, value in pages.items()
            if not value["selectors"][name]["logical_equal_to_retained"]
        ]
        geometry_changed = [
            key
            for key, value in pages.items()
            if not value["selectors"][name]["geometry_equal_to_retained"]
        ]
        selectors[name] = {
            "logical_changed_pages": [f"{score}/{page}" for score, page in logical_changed],
            "geometry_changed_pages": [f"{score}/{page}" for score, page in geometry_changed],
        }
    return {
        "page_count": len(pages),
        "equal_x_tie_page_count": len(tie_pages),
        "equal_x_tie_group_count": sum(len(pages[key]["equal_x_ties"]) for key in tie_pages),
        "equal_x_tie_pages": [f"{score}/{page}" for score, page in tie_pages],
        "replay_logical_mismatch_pages": [
            f"{score}/{page}" for score, page in replay_logical_mismatch
        ],
        "replay_geometry_mismatch_pages": [
            f"{score}/{page}" for score, page in replay_geometry_mismatch
        ],
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
        "schema_version": "issue286.issue294_retained_equal_x_audit.v1",
        "source_commit": git_head(),
        "full68_manifest": str(full68_manifest),
        "retained_project_root": str(retained_root),
        "retained_checkout": manifest.get("checkout"),
        "retained_latest_homr_commit": manifest.get("latest_homr_commit"),
        "current_contract": contract,
        "contract_drift": drift,
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

    return 2 if summary["replay_logical_mismatch_pages"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
