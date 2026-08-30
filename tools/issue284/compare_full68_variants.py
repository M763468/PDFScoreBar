"""Compare fresh post-#285 control and Issue #284 candidate full-68 runs.

The comparison separates semantic/topology correctness from raw coordinate
identity. This is required because Issue #286 established that exact-x barline
representative geometry is not a stable raw-JSON oracle even when SR inputs are
byte-identical.

The GT metrics in this comparator are intentionally named ``hybrid_*``: they are
computed from ``hybrid_results/*_hybrid.json`` before dense reconstruction,
probe rescue, and CNN scoring. They are not final Stage E detector metrics.

Retained full68 summaries may contain absolute paths from the canonical Docker
checkout (usually ``/workspace``).  Those paths are provenance, not a requirement
that later readers execute inside the same mount.  This comparator therefore
resolves moved artifacts relative to the supplied variant root before falling
back to the current repository root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.common.barline_evaluation import greedy_barline_match
from tools.issue120.eval_full68_from_intermediates import SCORES

Box = tuple[int, int, int, int]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_retained_path(raw: object, *, variant_root: Path) -> Path:
    """Resolve an artifact path recorded before the retained variant was moved."""
    recorded = Path(str(raw))
    candidates: list[Path] = [recorded]

    # Canonical retained variants are frequently generated under
    # /workspace/logs/.../<variant-name>/... and later inspected on the host or
    # from an archive.  Re-anchor the suffix at the explicit variant root first.
    parts = recorded.parts
    for index, part in enumerate(parts):
        if part == variant_root.name:
            candidates.append(variant_root.joinpath(*parts[index + 1 :]))

    # Also support a host checkout of the same repository when only the Docker
    # project-root prefix changed.
    if recorded.is_absolute():
        for docker_root in (Path("/workspace"),):
            try:
                relative = recorded.relative_to(docker_root)
            except ValueError:
                continue
            candidates.append(PROJECT_ROOT / relative)

    seen: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.resolve(strict=False)
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.exists():
            return candidate

    attempted = ", ".join(str(item) for item in seen)
    raise FileNotFoundError(f"Retained artifact not found; recorded={recorded}; tried={attempted}")


def normalize_box(raw: Sequence[Any]) -> Box:
    if len(raw) < 4:
        raise ValueError(f"Invalid bbox: {raw!r}")
    return tuple(int(round(float(value))) for value in raw[:4])  # type: ignore[return-value]


def boxes_from_payload(payload: Any) -> list[Box]:
    if not isinstance(payload, list):
        raise ValueError("Barline payload must be a list")
    boxes: list[Box] = []
    for item in payload:
        if isinstance(item, dict):
            raw = item.get("bbox") or item.get("box") or item.get("barline_location")
            if raw is not None:
                boxes.append(normalize_box(raw))
        elif isinstance(item, list):
            boxes.append(normalize_box(item))
    return boxes


def gt_boxes(path: Path) -> list[Box]:
    return boxes_from_payload(load_json(path))


def hybrid_metrics(pred: list[Box], gt: list[Box]) -> dict[str, Any]:
    """Evaluate one page's upstream hybrid-consensus boxes against raw GT slots."""
    result = greedy_barline_match(
        pred,
        gt,
        rule_name="center_anchor",
        vov_threshold=0.5,
        xdist_threshold=12.0,
    )
    tp = len(result.matches)
    fp = len(result.false_positive_indices)
    fn = len(result.false_negative_indices)
    return {
        "gt": len(gt),
        "pred": len(pred),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
    }


def aggregate_hybrid(items: Iterable[dict[str, Any]]) -> dict[str, Any]:
    values = list(items)
    totals = {
        key: sum(int(item[key]) for item in values) for key in ("gt", "pred", "tp", "fp", "fn")
    }
    tp = totals["tp"]
    fp = totals["fp"]
    fn = totals["fn"]
    return {
        **totals,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
    }


def numbering_view(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    pages = payload.get("pages", []) if isinstance(payload, dict) else []
    if len(pages) != 1:
        raise ValueError(f"Expected one-page numbering JSON: {path}")
    systems = pages[0].get("systems", [])
    return {
        "topology": [len(system.get("measures", [])) for system in systems],
        "numbers": [
            [measure.get("number") for measure in system.get("measures", [])] for system in systems
        ],
        "bboxes": [
            [measure.get("bbox") for measure in system.get("measures", [])] for system in systems
        ],
        "payload": payload,
    }


def bbox_differences(
    control: dict[str, Any],
    candidate: dict[str, Any],
) -> list[dict[str, Any]]:
    if control["topology"] != candidate["topology"]:
        return []

    differences: list[dict[str, Any]] = []
    for system_index, (control_system, candidate_system) in enumerate(
        zip(control["bboxes"], candidate["bboxes"])
    ):
        for measure_index, (control_bbox, candidate_bbox) in enumerate(
            zip(control_system, candidate_system)
        ):
            if control_bbox == candidate_bbox:
                continue
            if not isinstance(control_bbox, list) or not isinstance(candidate_bbox, list):
                differences.append(
                    {
                        "system": system_index,
                        "measure": measure_index,
                        "control": control_bbox,
                        "candidate": candidate_bbox,
                        "classification": "non_bbox_change",
                    }
                )
                continue
            if len(control_bbox) < 4 or len(candidate_bbox) < 4:
                classification = "invalid_bbox_shape"
                delta = None
            else:
                delta = [
                    int(candidate_bbox[index]) - int(control_bbox[index]) for index in range(4)
                ]
                boundary_only = delta[1] == 0 and delta[3] == 0
                small = max(abs(value) for value in delta) <= 6
                classification = (
                    "small_xy_boundary_only"
                    if boundary_only and small
                    else "coordinate_review_required"
                )
            differences.append(
                {
                    "system": system_index,
                    "measure": measure_index,
                    "control": control_bbox,
                    "candidate": candidate_bbox,
                    "delta": delta,
                    "classification": classification,
                }
            )
    return differences


def normalize_overrides(path: Path) -> list[tuple[int, int, int]]:
    payload = load_json(path)
    if isinstance(payload, dict):
        raw = payload.get("measure_overrides")
        if not isinstance(raw, list):
            raw = payload.get("overrides")
    elif isinstance(payload, list):
        raw = payload
    else:
        raw = []
    if not isinstance(raw, list):
        raw = []

    values: list[tuple[int, int, int]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        values.append(
            (
                int(item["system"]),
                int(item["measure"]),
                int(item.get("skip") or 0),
            )
        )
    return sorted(values)


def support_semantics(path: Path, *, variant_root: Path) -> dict[str, Any]:
    payload = load_json(path)

    def optional_artifact(raw: object) -> Path | None:
        if not raw:
            return None
        try:
            return resolve_retained_path(raw, variant_root=variant_root)
        except FileNotFoundError:
            return None

    symbols = optional_artifact(payload.get("connector_symbols"))
    brace_dot = optional_artifact(payload.get("connector_brace_dot"))
    return {
        "connector_complete": payload.get("connector_complete"),
        "historical_detector_artifact_runtime_input": payload.get(
            "historical_detector_artifact_runtime_input"
        ),
        "sr_sha256": payload.get("sr_sha256"),
        "sr_execution_scope": payload.get("sr_execution_scope"),
        "connector_symbols": str(symbols) if symbols is not None else None,
        "connector_symbols_sha256": sha256(symbols) if symbols is not None else None,
        "connector_brace_dot": str(brace_dot) if brace_dot is not None else None,
        "connector_brace_dot_sha256": sha256(brace_dot) if brace_dot is not None else None,
    }


def score_map(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["score"]): item for item in summary.get("scores", [])}


def page_artifact(
    summary: dict[str, Any],
    variant_root: Path,
    score: str,
    page: str,
    key: str,
) -> Path:
    item = score_map(summary)[score]
    raw = item["page_artifacts"][page][key]
    return resolve_retained_path(raw, variant_root=variant_root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    control_root = args.control.resolve()
    candidate_root = args.candidate.resolve()
    control_summary_path = control_root / "variant_summary.json"
    candidate_summary_path = candidate_root / "variant_summary.json"
    control = load_json(control_summary_path)
    candidate = load_json(candidate_summary_path)
    if control.get("status") != "completed" or candidate.get("status") != "completed":
        raise RuntimeError("Both full68 variants must be completed")
    if control.get("canonical_page_count") != 68 or candidate.get("canonical_page_count") != 68:
        raise RuntimeError("Both full68 variants must contain 68 canonical pages")
    if control.get("config_sha256") != candidate.get("config_sha256"):
        raise RuntimeError("Control/candidate canonical config hashes differ")

    pages: list[dict[str, Any]] = []
    control_hybrid: list[dict[str, Any]] = []
    candidate_hybrid: list[dict[str, Any]] = []

    for score, page_names in SCORES.items():
        for page in page_names:
            control_hybrid_path = page_artifact(control, control_root, score, page, "hybrid")
            candidate_hybrid_path = page_artifact(candidate, candidate_root, score, page, "hybrid")
            control_boxes = boxes_from_payload(load_json(control_hybrid_path))
            candidate_boxes = boxes_from_payload(load_json(candidate_hybrid_path))
            gt_path = (
                PROJECT_ROOT / "data/evaluation2/annotations" / score / page / "boxes_sorted.json"
            )
            ground_truth = gt_boxes(gt_path)
            control_metrics = hybrid_metrics(control_boxes, ground_truth)
            candidate_metrics = hybrid_metrics(candidate_boxes, ground_truth)
            control_hybrid.append(control_metrics)
            candidate_hybrid.append(candidate_metrics)

            intervariant = greedy_barline_match(
                candidate_boxes,
                control_boxes,
                rule_name="center_anchor",
                vov_threshold=0.5,
                xdist_threshold=12.0,
            )
            hybrid_multiset_exact = sorted(candidate_boxes) == sorted(control_boxes)

            base_control = numbering_view(
                page_artifact(control, control_root, score, page, "numbering_base")
            )
            base_candidate = numbering_view(
                page_artifact(candidate, candidate_root, score, page, "numbering_base")
            )
            final_control = numbering_view(
                page_artifact(control, control_root, score, page, "numbering_final")
            )
            final_candidate = numbering_view(
                page_artifact(candidate, candidate_root, score, page, "numbering_final")
            )

            base_bbox_diff = bbox_differences(base_control, base_candidate)
            final_bbox_diff = bbox_differences(final_control, final_candidate)
            mmr_control = normalize_overrides(
                page_artifact(control, control_root, score, page, "overrides_mmr")
            )
            mmr_candidate = normalize_overrides(
                page_artifact(candidate, candidate_root, score, page, "overrides_mmr")
            )
            support_control = support_semantics(
                page_artifact(control, control_root, score, page, "current_support"),
                variant_root=control_root,
            )
            support_candidate = support_semantics(
                page_artifact(candidate, candidate_root, score, page, "current_support"),
                variant_root=candidate_root,
            )

            pages.append(
                {
                    "score": score,
                    "page": page,
                    "hybrid": {
                        "control_count": len(control_boxes),
                        "candidate_count": len(candidate_boxes),
                        "multiset_exact": hybrid_multiset_exact,
                        "matched": len(intervariant.matches),
                        "candidate_unmatched": len(intervariant.false_positive_indices),
                        "control_unmatched": len(intervariant.false_negative_indices),
                    },
                    "hybrid_vs_gt": {
                        "control": control_metrics,
                        "candidate": candidate_metrics,
                        "same_counts": control_metrics == candidate_metrics,
                    },
                    "numbering_base": {
                        "topology_equal": base_control["topology"] == base_candidate["topology"],
                        "numbers_equal": base_control["numbers"] == base_candidate["numbers"],
                        "raw_equal": base_control["payload"] == base_candidate["payload"],
                        "bbox_differences": base_bbox_diff,
                    },
                    "numbering_final": {
                        "topology_equal": final_control["topology"] == final_candidate["topology"],
                        "numbers_equal": final_control["numbers"] == final_candidate["numbers"],
                        "raw_equal": final_control["payload"] == final_candidate["payload"],
                        "bbox_differences": final_bbox_diff,
                    },
                    "mmr": {
                        "semantic_equal": mmr_control == mmr_candidate,
                        "control": mmr_control,
                        "candidate": mmr_candidate,
                    },
                    "support": {
                        "control": support_control,
                        "candidate": support_candidate,
                        "sr_byte_identical": (
                            support_control["sr_sha256"] == support_candidate["sr_sha256"]
                        ),
                        "connector_symbols_byte_identical": (
                            support_control["connector_symbols_sha256"]
                            == support_candidate["connector_symbols_sha256"]
                        ),
                        "connector_brace_dot_byte_identical": (
                            support_control["connector_brace_dot_sha256"]
                            == support_candidate["connector_brace_dot_sha256"]
                        ),
                    },
                }
            )

    control_aggregate = aggregate_hybrid(control_hybrid)
    candidate_aggregate = aggregate_hybrid(candidate_hybrid)

    def count_pages(path: tuple[str, ...], expected: Any = True) -> int:
        count = 0
        for page in pages:
            value: Any = page
            for key in path:
                value = value[key]
            if value == expected:
                count += 1
        return count

    coordinate_review_pages = []
    for page in pages:
        base_review = any(
            item.get("classification") == "coordinate_review_required"
            for item in page["numbering_base"]["bbox_differences"]
        )
        final_review = any(
            item.get("classification") == "coordinate_review_required"
            for item in page["numbering_final"]["bbox_differences"]
        )
        if base_review or final_review or not page["hybrid"]["multiset_exact"]:
            coordinate_review_pages.append(
                {
                    "score": page["score"],
                    "page": page["page"],
                    "hybrid_multiset_exact": page["hybrid"]["multiset_exact"],
                    "base_bbox_differences": page["numbering_base"]["bbox_differences"],
                    "final_bbox_differences": page["numbering_final"]["bbox_differences"],
                }
            )

    summary = {
        "schema_version": "issue284.full68_comparison.v2",
        "control": {
            "root": str(control_root),
            "git_commit": control.get("git_commit"),
            "total_score_e2e_wall_sec": control.get("total_score_e2e_wall_sec"),
            "hybrid_vs_gt": control_aggregate,
        },
        "candidate": {
            "root": str(candidate_root),
            "git_commit": candidate.get("git_commit"),
            "total_score_e2e_wall_sec": candidate.get("total_score_e2e_wall_sec"),
            "hybrid_vs_gt": candidate_aggregate,
        },
        "page_count": len(pages),
        "hybrid_multiset_exact_pages": count_pages(("hybrid", "multiset_exact")),
        "hybrid_metric_exact_pages": count_pages(("hybrid_vs_gt", "same_counts")),
        "base_topology_equal_pages": count_pages(("numbering_base", "topology_equal")),
        "base_numbers_equal_pages": count_pages(("numbering_base", "numbers_equal")),
        "final_topology_equal_pages": count_pages(("numbering_final", "topology_equal")),
        "final_numbers_equal_pages": count_pages(("numbering_final", "numbers_equal")),
        "mmr_semantic_equal_pages": count_pages(("mmr", "semantic_equal")),
        "sr_byte_identical_pages": count_pages(("support", "sr_byte_identical")),
        "connector_symbols_byte_identical_pages": count_pages(
            ("support", "connector_symbols_byte_identical")
        ),
        "connector_brace_dot_byte_identical_pages": count_pages(
            ("support", "connector_brace_dot_byte_identical")
        ),
        "coordinate_review_page_count": len(coordinate_review_pages),
        "coordinate_review_pages": coordinate_review_pages,
        "semantic_gate": {
            "all_68_pages": len(pages) == 68,
            "hybrid_metrics_preserved_per_page": count_pages(("hybrid_vs_gt", "same_counts")) == 68,
            "base_topology_preserved": count_pages(("numbering_base", "topology_equal")) == 68,
            "base_numbers_preserved": count_pages(("numbering_base", "numbers_equal")) == 68,
            "final_topology_preserved": count_pages(("numbering_final", "topology_equal")) == 68,
            "final_numbers_preserved": count_pages(("numbering_final", "numbers_equal")) == 68,
            "mmr_semantics_preserved": count_pages(("mmr", "semantic_equal")) == 68,
            "connector_contract_complete": all(
                page["support"][side]["connector_complete"] is True
                and page["support"][side]["historical_detector_artifact_runtime_input"] is False
                for page in pages
                for side in ("control", "candidate")
            ),
        },
        "pages": pages,
    }
    summary["semantic_gate"]["passed"] = all(summary["semantic_gate"].values())
    summary["coordinate_review_required"] = bool(coordinate_review_pages)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    compact = {
        key: summary[key]
        for key in (
            "page_count",
            "hybrid_multiset_exact_pages",
            "hybrid_metric_exact_pages",
            "base_topology_equal_pages",
            "base_numbers_equal_pages",
            "final_topology_equal_pages",
            "final_numbers_equal_pages",
            "mmr_semantic_equal_pages",
            "sr_byte_identical_pages",
            "connector_symbols_byte_identical_pages",
            "connector_brace_dot_byte_identical_pages",
            "coordinate_review_page_count",
            "semantic_gate",
        )
    }
    compact["control_hybrid_vs_gt"] = control_aggregate
    compact["candidate_hybrid_vs_gt"] = candidate_aggregate
    compact["control_total_score_e2e_wall_sec"] = control.get("total_score_e2e_wall_sec")
    compact["candidate_total_score_e2e_wall_sec"] = candidate.get("total_score_e2e_wall_sec")
    print(json.dumps(compact, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
