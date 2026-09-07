#!/usr/bin/env python3
"""Run the Issue #294 canonical full-68 downstream correctness gate in chunks.

This is experiment-only orchestration.  It resolves the retained canonical global
page index, groups consecutive pages by score, delegates each chunk to the
existing same-original/downstream matrix host, and writes a small resumable
manifest under logs/issue294/<run-tag>/.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.issue294 import run_downstream_candidate_matrix_global_host as global_host
from tools.issue294 import run_downstream_candidate_matrix_host as matrix_host
from tools.issue294 import run_same_original_ab_host as base

DEFAULT_LATEST_COMMIT = "457e7c6518a10ba755db2e60883419e56c4d7369"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return slug or "score"


def _canonical_mappings() -> list[dict[str, Any]]:
    mappings = [
        global_host._resolve_global_page(f"page_{index:03d}") for index in range(1, 69)
    ]
    ids = [str(item["global_page_id"]) for item in mappings]
    if ids != [f"page_{index:03d}" for index in range(1, 69)]:
        raise RuntimeError("Canonical Issue #294 full68 mapping is not page_001..page_068")
    if len({(str(item["score"]), str(item["page_name"])) for item in mappings}) != 68:
        raise RuntimeError("Canonical Issue #294 full68 mapping contains duplicate score/page pairs")
    return mappings


def _chunk_mappings(
    mappings: list[dict[str, Any]], chunk_size: int
) -> list[list[dict[str, Any]]]:
    if chunk_size < 1:
        raise ValueError("chunk_size must be >= 1")
    by_score: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for mapping in mappings:
        by_score.setdefault(str(mapping["score"]), []).append(mapping)

    chunks: list[list[dict[str, Any]]] = []
    for score_mappings in by_score.values():
        for offset in range(0, len(score_mappings), chunk_size):
            chunks.append(score_mappings[offset : offset + chunk_size])
    flattened = [str(item["global_page_id"]) for chunk in chunks for item in chunk]
    expected = [str(item["global_page_id"]) for item in mappings]
    if flattened != expected:
        raise RuntimeError("Full68 chunking changed canonical global-page order")
    return chunks


def _report_page_key(page: dict[str, Any]) -> tuple[str, str]:
    image = Path(str(page["image"]))
    return image.parent.name, image.stem


def _mapping_key(mapping: dict[str, Any]) -> tuple[str, str]:
    return str(mapping["score"]), str(mapping["page_name"])


def _mode_summary(mode: dict[str, Any]) -> dict[str, Any]:
    comparisons = mode["comparisons_to_A"]
    variants = mode["variants"]
    b = variants["B_b377"]
    c = variants["C_latest"]
    return {
        "B_vs_A": comparisons["B_b377"],
        "C_vs_A": comparisons["C_latest"],
        "B_C_final_barlines_exact": b["final_barlines"] == c["final_barlines"],
        "B_C_numbering_exact": b["numbering"] == c["numbering"],
        "A_final_barline_count": int(variants["A_pinned"]["final_barline_count"]),
        "B_final_barline_count": int(b["final_barline_count"]),
        "C_final_barline_count": int(c["final_barline_count"]),
        "A_total_measures": int(variants["A_pinned"]["numbering"]["total_measures"]),
        "B_total_measures": int(b["numbering"]["total_measures"]),
        "C_total_measures": int(c["numbering"]["total_measures"]),
    }


def _page_summary(mapping: dict[str, Any], page: dict[str, Any]) -> dict[str, Any]:
    fidelity = page["B_full_vs_detector_material"]
    return {
        "global_page_id": str(mapping["global_page_id"]),
        "score": str(mapping["score"]),
        "page_name": str(mapping["page_name"]),
        "image": str(page["image"]),
        "B_full_vs_detector_material": fidelity,
        "frozen_A_geometry": _mode_summary(page["modes"]["frozen_A_geometry"]),
        "candidate_native_geometry": _mode_summary(
            page["modes"]["candidate_native_geometry"]
        ),
    }


def _aggregate_gates(page_summaries: list[dict[str, Any]]) -> dict[str, bool]:
    def candidate_pass(page: dict[str, Any], label: str) -> bool:
        comparison = page["candidate_native_geometry"][f"{label}_vs_A"]
        return bool(comparison["count_topology_numbering_pass"])

    return {
        "B_b377": all(candidate_pass(page, "B") for page in page_summaries),
        "C_latest": all(candidate_pass(page, "C") for page in page_summaries),
        "B_detector_material_matches_full_B_all_pages": all(
            int(page["B_full_vs_detector_material"]["full_count"])
            == int(page["B_full_vs_detector_material"]["detector_material_count"])
            and bool(page["B_full_vs_detector_material"]["boxes_exact"])
            for page in page_summaries
        ),
        "B_C_native_final_barlines_identical_all_pages": all(
            bool(page["candidate_native_geometry"]["B_C_final_barlines_exact"])
            for page in page_summaries
        ),
        "B_C_native_numbering_identical_all_pages": all(
            bool(page["candidate_native_geometry"]["B_C_numbering_exact"])
            for page in page_summaries
        ),
    }


def _write_manifest(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run(
    *,
    run_tag: str,
    latest_commit: str,
    chunk_size: int,
) -> dict[str, Any]:
    checkout = matrix_host._require_issue294_checkout()
    base.require_container()
    resolved_latest = matrix_host._resolve_latest_commit(latest_commit)
    mappings = _canonical_mappings()
    chunks = _chunk_mappings(mappings, chunk_size)

    output_root = PROJECT_ROOT / "logs/issue294" / run_tag
    manifest_path = output_root / "full68_host.json"
    existing: dict[str, Any] | None = None
    if manifest_path.is_file():
        raw = _load_json(manifest_path)
        if not isinstance(raw, dict):
            raise ValueError(f"Invalid existing full68 manifest: {manifest_path}")
        if raw.get("latest_homr_commit") != resolved_latest:
            raise RuntimeError(
                "Existing full68 manifest uses a different latest candidate: "
                f"{raw.get('latest_homr_commit')} != {resolved_latest}"
            )
        if raw.get("status") == "completed":
            return raw
        existing = raw
    elif output_root.exists():
        raise RuntimeError(
            f"Full68 parent run directory exists without a manifest: {output_root}. "
            "Use a fresh --run-tag; do not overwrite retained artifacts."
        )

    completed_chunks: list[dict[str, Any]] = []
    page_summaries: list[dict[str, Any]] = []
    if existing is not None:
        completed_chunks = list(existing.get("completed_chunks", []))
        page_summaries = list(existing.get("pages", []))

    completed_tags = {str(item["child_run_tag"]) for item in completed_chunks}
    completed_page_ids = {str(item["global_page_id"]) for item in page_summaries}

    for chunk_index, chunk in enumerate(chunks, start=1):
        score = str(chunk[0]["score"])
        if any(str(item["score"]) != score for item in chunk):
            raise RuntimeError("Full68 chunk crossed score boundary")
        physical_pages = [str(item["physical_page"]) for item in chunk]
        first_global = str(chunk[0]["global_page_id"])
        last_global = str(chunk[-1]["global_page_id"])
        child_tag = (
            f"{run_tag}__{chunk_index:02d}_{_slug(score)}_"
            f"{first_global.removeprefix('page_')}-{last_global.removeprefix('page_')}"
        )

        if child_tag not in completed_tags:
            previous_score = base.SCORE
            previous_allowed = base.ALLOWED_PAGES
            base.SCORE = score
            base.ALLOWED_PAGES = set(physical_pages)
            try:
                result = matrix_host.run(child_tag, physical_pages, resolved_latest)
            finally:
                base.SCORE = previous_score
                base.ALLOWED_PAGES = previous_allowed

            report_path = Path(str(result["matrix_report"]))
            report = _load_json(report_path)
            if not isinstance(report, dict) or report.get("status") != "completed":
                raise ValueError(f"Incomplete child matrix report: {report_path}")
            report_pages = report.get("pages")
            if not isinstance(report_pages, list):
                raise ValueError(f"Child matrix report has no pages: {report_path}")
            by_key = {
                _report_page_key(page): page for page in report_pages if isinstance(page, dict)
            }
            if len(by_key) != len(chunk):
                raise RuntimeError(
                    f"Child report page count mismatch: expected={len(chunk)} actual={len(by_key)}"
                )
            for mapping in chunk:
                key = _mapping_key(mapping)
                if key not in by_key:
                    raise RuntimeError(f"Child report missing canonical page {key}: {report_path}")
                page_id = str(mapping["global_page_id"])
                if page_id in completed_page_ids:
                    raise RuntimeError(f"Duplicate full68 page summary: {page_id}")
                page_summaries.append(_page_summary(mapping, by_key[key]))
                completed_page_ids.add(page_id)

            completed_chunks.append(
                {
                    "child_run_tag": child_tag,
                    "score": score,
                    "global_pages": [str(item["global_page_id"]) for item in chunk],
                    "physical_pages": physical_pages,
                    "matrix_report": str(report_path.resolve()),
                    "provenance": str(result["provenance"]),
                }
            )
            completed_tags.add(child_tag)

            checkpoint = {
                "schema_version": "issue294.full68_host.v1",
                "status": "in_progress",
                "run_tag": run_tag,
                "checkout": checkout,
                "latest_homr_commit": resolved_latest,
                "chunk_size": chunk_size,
                "completed_chunks": completed_chunks,
                "pages": page_summaries,
                "completed_page_count": len(page_summaries),
            }
            _write_manifest(manifest_path, checkpoint)

    expected_ids = [f"page_{index:03d}" for index in range(1, 69)]
    actual_ids = [str(item["global_page_id"]) for item in page_summaries]
    if actual_ids != expected_ids:
        raise RuntimeError(
            "Full68 completed page order mismatch: "
            f"expected={expected_ids} actual={actual_ids}"
        )

    payload = {
        "schema_version": "issue294.full68_host.v1",
        "status": "completed",
        "run_tag": run_tag,
        "checkout": checkout,
        "latest_homr_commit": resolved_latest,
        "chunk_size": chunk_size,
        "completed_chunks": completed_chunks,
        "pages": page_summaries,
        "completed_page_count": len(page_summaries),
        "gates": _aggregate_gates(page_summaries),
    }
    _write_manifest(manifest_path, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-tag", required=True)
    parser.add_argument("--latest-homr-commit", default=DEFAULT_LATEST_COMMIT)
    parser.add_argument("--chunk-size", type=int, default=6)
    args = parser.parse_args()
    try:
        payload = run(
            run_tag=args.run_tag,
            latest_commit=args.latest_homr_commit,
            chunk_size=args.chunk_size,
        )
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "status": payload["status"],
                "run_tag": payload["run_tag"],
                "completed_page_count": payload["completed_page_count"],
                "gates": payload.get("gates"),
            },
            ensure_ascii=False,
        )
    )
    return 0 if all(payload.get("gates", {}).values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
