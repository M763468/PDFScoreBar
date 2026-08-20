#!/usr/bin/env python3
"""Verify a fresh Issue #274 two-HOMR canonical full68 production run.

Post-hoc only: no HOMR, SR, dense probing, CNN, MMR, or numbering is rerun.
The gate checks source-call ownership, audited detector physical-event coverage,
P3 multi-line coverage, connector/MMR reuse, and downstream numbering topology.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from src.common.barline_evaluation import greedy_barline_match, is_barline_match
from tools.issue120.eval_full68_from_intermediates import SCORES

Box = tuple[int, int, int, int]

DEFAULT_AUDIT = Path(
    "logs/issue274_homr_unification_analysis/evaluation2_gt_near_duplicate_audit_01/"
    "issue274_evaluation2_gt_near_duplicate_audit.json"
)
DEFAULT_CONTROL_ROOT = Path(
    "logs/verification/detector_full68/"
    "issue255_production_restore_full68_top_level_worker_01/production_runs"
)
DEFAULT_GT_ROOT = Path("data/evaluation2/annotations")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def to_workspace(value: str | Path, workspace: Path) -> Path:
    text = str(value)
    if text.startswith("/workspace/"):
        return workspace / text[len("/workspace/") :]
    marker = "/ws_PDFScoreBar/"
    if marker in text:
        return workspace / text.split(marker, 1)[1]
    path = Path(text)
    return path if path.is_absolute() else workspace / path


def canonical_identities() -> set[tuple[str, str]]:
    return {(score, page) for score, pages in SCORES.items() for page in pages}


def norm_box(values: Sequence[Any]) -> Box:
    if len(values) < 4:
        raise ValueError(f"Expected four bbox values, got {values!r}")
    return tuple(int(round(float(value))) for value in values[:4])  # type: ignore[return-value]


def extract_box(item: Any) -> Box | None:
    if isinstance(item, (list, tuple)) and len(item) >= 4:
        return norm_box(item)
    if not isinstance(item, Mapping):
        return None
    for key in ("bbox", "orig_bbox", "pred_bbox", "barline_location", "box"):
        value = item.get(key)
        if isinstance(value, (list, tuple)) and len(value) >= 4:
            return norm_box(value)
    return None


def load_boxes(path: Path) -> list[Box]:
    payload = load_json(path)
    records: Any = payload
    if isinstance(payload, Mapping):
        for key in ("predictions", "boxes", "detections"):
            value = payload.get(key)
            if isinstance(value, list):
                records = value
                break
    if not isinstance(records, list):
        raise ValueError(f"Expected bbox list payload: {path}")
    return [box for box in (extract_box(item) for item in records) if box is not None]


def match_box(pred: Box, gt: Box) -> bool:
    return is_barline_match(
        pred,
        gt,
        rule_name="center_anchor",
        vov_threshold=0.5,
        xdist_threshold=12.0,
    )


def maximum_matching_count(
    predictions: Sequence[Box],
    target_count: int,
    matches_target: Callable[[Box, int], bool],
) -> int:
    adjacency = [
        [index for index in range(target_count) if matches_target(pred, index)]
        for pred in predictions
    ]
    target_owner: dict[int, int] = {}

    def augment(pred_index: int, seen: set[int]) -> bool:
        for target_index in adjacency[pred_index]:
            if target_index in seen:
                continue
            seen.add(target_index)
            owner = target_owner.get(target_index)
            if owner is None or augment(owner, seen):
                target_owner[target_index] = pred_index
                return True
        return False

    return sum(1 for index in range(len(predictions)) if augment(index, set()))


def raw_metrics(predictions: Sequence[Box], gt: Sequence[Box]) -> dict[str, int]:
    greedy = greedy_barline_match(
        predictions,
        gt,
        rule_name="center_anchor",
        vov_threshold=0.5,
        xdist_threshold=12.0,
    )
    maximum_tp = maximum_matching_count(
        predictions,
        len(gt),
        lambda pred, index: match_box(pred, gt[index]),
    )
    return {
        "gt": len(gt),
        "pred": len(predictions),
        "greedy_tp": len(greedy.matches),
        "greedy_fp": len(greedy.false_positive_indices),
        "greedy_fn": len(greedy.false_negative_indices),
        "maximum_tp": maximum_tp,
        "maximum_fp": len(predictions) - maximum_tp,
        "maximum_fn": len(gt) - maximum_tp,
    }


def audit_pages(audit: Mapping[str, Any]) -> dict[tuple[str, str], Mapping[str, Any]]:
    return {
        (str(page["score"]), str(page["page"])): page
        for page in audit.get("pages", [])
        if isinstance(page, Mapping)
    }


def event_groups(
    gt: Sequence[Box], audit_page: Mapping[str, Any]
) -> tuple[list[tuple[int, ...]], list[int], list[int], list[int]]:
    p1_pairs = [
        pair
        for pair in audit_page.get("pairs", [])
        if pair.get("priority") == "P1"
        and pair.get("classification") == "ordinary_same_ink_high_overlap"
    ]
    p1_by_index: dict[int, tuple[int, int]] = {}
    for pair in p1_pairs:
        members = tuple(sorted((int(pair["a"]["index"]), int(pair["b"]["index"]))))
        if members[0] < 0 or members[1] >= len(gt) or members[0] == members[1]:
            raise ValueError(f"Invalid P1 members: {members}")
        for index in members:
            previous = p1_by_index.get(index)
            if previous is not None and previous != members:
                raise ValueError(f"Overlapping P1 groups at GT index {index}")
            p1_by_index[index] = members

    events: list[tuple[int, ...]] = []
    consumed: set[int] = set()
    for index in range(len(gt)):
        if index in consumed:
            continue
        members = p1_by_index.get(index, (index,))
        events.append(members)
        consumed.update(members)

    singleton_events = [index for index, members in enumerate(events) if len(members) == 1]
    p1_events = [index for index, members in enumerate(events) if len(members) > 1]
    p3_members = sorted(
        {
            int(side["index"])
            for pair in audit_page.get("pairs", [])
            if pair.get("priority") == "P3"
            for side in (pair["a"], pair["b"])
        }
    )
    return events, singleton_events, p1_events, p3_members


def event_subset_metrics(
    predictions: Sequence[Box],
    gt: Sequence[Box],
    events: Sequence[tuple[int, ...]],
    event_indices: Sequence[int],
) -> dict[str, int]:
    tp = maximum_matching_count(
        predictions,
        len(event_indices),
        lambda pred, target: any(
            match_box(pred, gt[member]) for member in events[event_indices[target]]
        ),
    )
    return {"event_count": len(event_indices), "tp": tp, "fn": len(event_indices) - tp}


def physical_metrics(
    predictions: Sequence[Box], gt: Sequence[Box], audit_page: Mapping[str, Any]
) -> dict[str, Any]:
    events, singleton_events, p1_events, p3_members = event_groups(gt, audit_page)
    physical = event_subset_metrics(predictions, gt, events, list(range(len(events))))
    singleton = event_subset_metrics(predictions, gt, events, singleton_events)
    p1 = event_subset_metrics(predictions, gt, events, p1_events)
    p3_members = [index for index in p3_members if 0 <= index < len(gt)]
    p3_tp = maximum_matching_count(
        predictions,
        len(p3_members),
        lambda pred, target: match_box(pred, gt[p3_members[target]]),
    )
    return {
        "physical": {**physical, "pred": len(predictions)},
        "singleton": singleton,
        "p1": p1,
        "p3": {
            "physical_line_count": len(p3_members),
            "tp": p3_tp,
            "fn": len(p3_members) - p3_tp,
        },
    }


def control_accepted_path(control_root: Path, score: str, page: str) -> Path:
    return (
        control_root
        / score
        / "intermediate"
        / "dense_full_pipeline_route"
        / "dense_candidate_reconstruction"
        / "probe_rescue_candidates"
        / f"eval2_{score}_{page}"
        / "pipeline2_no_peak_filtered_cnn.json"
    )


def add_counter(total: Counter[str], row: Mapping[str, Any]) -> None:
    for key, value in row.items():
        if isinstance(value, int):
            total[key] += value


def topology_signature(page: Mapping[str, Any]) -> tuple[Any, ...]:
    systems = page.get("systems", [])
    return tuple(
        (
            len(system.get("staves", [])),
            len(system.get("measures", [])),
            tuple(measure.get("number") for measure in system.get("measures", [])),
            tuple(
                (
                    int(measure["bbox"][0]),
                    int(measure["bbox"][2]),
                )
                for measure in system.get("measures", [])
                if isinstance(measure.get("bbox"), list) and len(measure["bbox"]) == 4
            ),
        )
        for system in systems
    )


def numbering_by_page_id(manifest: Mapping[str, Any], path: Path) -> dict[str, Mapping[str, Any]]:
    if not path.is_file():
        return {}
    payload = load_json(path)
    pages = payload.get("pages", []) if isinstance(payload, Mapping) else []
    manifest_pages = manifest.get("pages", [])
    if len(pages) != len(manifest_pages):
        return {}
    return {
        str(meta["page_id"]): page
        for meta, page in zip(manifest_pages, pages, strict=True)
        if isinstance(meta, Mapping) and isinstance(page, Mapping)
    }


def verify(args: argparse.Namespace) -> dict[str, Any]:
    workspace = args.workspace.resolve()
    run_root = to_workspace(args.run_root, workspace)
    audit_path = to_workspace(args.audit, workspace)
    control_root = to_workspace(args.control_root, workspace)
    gt_root = to_workspace(args.gt_root, workspace)
    audit = load_json(audit_path)
    audit_map = audit_pages(audit)
    expected = canonical_identities()

    manifests: dict[str, Mapping[str, Any]] = {}
    fresh_pages: dict[tuple[str, str], Mapping[str, Any]] = {}
    command_strings: list[str] = []
    for score in SCORES:
        path = run_root / "runs" / score / "manifest.json"
        if not path.is_file():
            raise FileNotFoundError(path)
        manifest = load_json(path)
        if not isinstance(manifest, Mapping):
            raise ValueError(f"Manifest must be an object: {path}")
        manifests[score] = manifest
        for page in manifest.get("pages", []):
            identity = (score, str(page["page_id"]))
            if identity in fresh_pages:
                raise ValueError(f"Duplicate fresh page: {identity}")
            fresh_pages[identity] = page
        command_strings.extend(
            " ".join(str(part) for part in entry.get("cmd", []))
            for entry in manifest.get("commands", [])
            if isinstance(entry, Mapping)
        )

    source_results = sorted((run_root / "hybrid").rglob("source_page_workers/*/*/result.json"))
    support_results = sorted((run_root / "hybrid").rglob("current_support/*/*/result.json"))
    source_bad: list[str] = []
    for path in source_results:
        payload = load_json(path)
        detection = to_workspace(str(payload.get("current_sr_detection", "")), workspace)
        if not (
            payload.get("status") == "completed"
            and payload.get("homr_neural_inference_count") == 2
            and payload.get("x4_homr_neural_inference_count") == 1
            and payload.get("x4_detector_support_owner") == "current_x4_support"
            and payload.get("historical_detector_artifact_runtime_input") is False
            and detection.is_file()
        ):
            source_bad.append(str(path))

    support_bad: list[str] = []
    for path in support_results:
        payload = load_json(path)
        detection = to_workspace(str(payload.get("current_sr_detection", "")), workspace)
        if not (
            payload.get("status") == "completed"
            and payload.get("current_homr_executed") is True
            and payload.get("historical_detector_artifact_runtime_input") is False
            and detection.is_file()
        ):
            support_bad.append(str(path))

    command_counts = {
        "source_page_worker": sum(
            "src.pipeline.detection.verified_source_page_worker" in command
            for command in command_strings
        ),
        "pinned_homr_profile": sum(
            "homr_profile_compat.py" in command for command in command_strings
        ),
        "current_support_worker": sum(
            "src.pipeline.detection.current_support_worker" in command
            for command in command_strings
        ),
    }
    architecture_ok = (
        len(source_results) == args.expected_pages
        and len(support_results) == args.expected_pages
        and not source_bad
        and not support_bad
        and all(value == args.expected_pages for value in command_counts.values())
    )

    raw_totals = {"control": Counter(), "fresh": Counter()}
    physical_totals = {
        variant: {key: Counter() for key in ("physical", "singleton", "p1", "p3")}
        for variant in ("control", "fresh")
    }
    detector_pages: list[dict[str, Any]] = []
    changed_physical_pages: list[dict[str, str]] = []
    for score, page in sorted(expected):
        fresh_meta = fresh_pages.get((score, page))
        audit_page = audit_map.get((score, page))
        if fresh_meta is None or audit_page is None:
            raise ValueError(f"Missing fresh/audit page: {score}/{page}")
        gt = load_boxes(gt_root / score / page / "boxes_sorted.json")
        control_path = control_accepted_path(control_root, score, page)
        fresh_path = to_workspace(str(fresh_meta["barlines_json"]), workspace)
        control_boxes = load_boxes(control_path)
        fresh_boxes = load_boxes(fresh_path)
        variants: dict[str, Any] = {}
        for variant, predictions in (("control", control_boxes), ("fresh", fresh_boxes)):
            raw = raw_metrics(predictions, gt)
            physical = physical_metrics(predictions, gt, audit_page)
            variants[variant] = {"raw": raw, **physical}
            add_counter(raw_totals[variant], raw)
            for key in ("physical", "singleton", "p1", "p3"):
                add_counter(physical_totals[variant][key], physical[key])

        coverage_changed = any(
            variants["fresh"][key][field] != variants["control"][key][field]
            for key in ("physical", "singleton", "p3")
            for field in ("tp", "fn")
        )
        if coverage_changed:
            changed_physical_pages.append({"score": score, "page": page})
        detector_pages.append(
            {
                "score": score,
                "page": page,
                "control_path": str(control_path),
                "fresh_path": str(fresh_path),
                "coverage_changed": coverage_changed,
                "variants": variants,
            }
        )

    detector_coverage_ok = not changed_physical_pages

    downstream_bad: list[dict[str, Any]] = []
    fallback_pages: list[dict[str, Any]] = []
    for (score, page), meta in sorted(fresh_pages.items()):
        connector = meta.get("connector_evidence") or {}
        mmr = meta.get("mmr_support") or {}
        if not (
            connector.get("source") == "proxy_symbol_layers"
            and mmr.get("source") == "current_x4_support"
            and mmr.get("original_image_homr") is False
            and mmr.get("second_numbering_rebuild") is False
        ):
            downstream_bad.append({"score": score, "page": page})
        fallback = int(mmr.get("fallback_count") or 0)
        if fallback:
            fallback_pages.append({"score": score, "page": page, "fallback_count": fallback})

    fresh_numbering_count = 0
    topology_changed_pages: list[dict[str, str]] = []
    topology_missing_pages: list[dict[str, str]] = []
    for score in SCORES:
        fresh_manifest = manifests[score]
        fresh_numbering = numbering_by_page_id(
            fresh_manifest,
            run_root / "runs" / score / "outputs" / "numbering_final.json",
        )
        control_manifest_path = control_root / score / "manifest.json"
        control_numbering_path = control_root / score / "outputs" / "numbering_final.json"
        if not control_manifest_path.is_file():
            topology_missing_pages.extend({"score": score, "page": page} for page in SCORES[score])
            continue
        control_manifest = load_json(control_manifest_path)
        control_numbering = numbering_by_page_id(control_manifest, control_numbering_path)
        for page in SCORES[score]:
            fresh_page = fresh_numbering.get(page)
            control_page = control_numbering.get(page)
            if fresh_page is None or control_page is None:
                topology_missing_pages.append({"score": score, "page": page})
                continue
            fresh_numbering_count += 1
            if topology_signature(fresh_page) != topology_signature(control_page):
                topology_changed_pages.append({"score": score, "page": page})

    downstream_contract_ok = (
        set(fresh_pages) == expected
        and not downstream_bad
        and fresh_numbering_count == args.expected_pages
        and not topology_missing_pages
        and not topology_changed_pages
    )

    summary = {
        "schema_version": "issue274.two_homr_full68_fresh_gate.v2",
        "status": "completed",
        "run_root": str(run_root),
        "expected_page_count": args.expected_pages,
        "manifest_page_count": len(fresh_pages),
        "page_identity_ok": set(fresh_pages) == expected,
        "architecture": {
            "source_page_result_count": len(source_results),
            "current_support_result_count": len(support_results),
            "source_bad": source_bad,
            "support_bad": support_bad,
            "command_counts": command_counts,
            "contract_ok": architecture_ok,
        },
        "detector": {
            "raw_legacy": {variant: dict(counter) for variant, counter in raw_totals.items()},
            "audited": {
                variant: {key: dict(counter) for key, counter in groups.items()}
                for variant, groups in physical_totals.items()
            },
            "changed_physical_page_count": len(changed_physical_pages),
            "changed_physical_pages": changed_physical_pages,
            "coverage_ok": detector_coverage_ok,
            "pages": detector_pages,
        },
        "downstream": {
            "contract_bad_pages": downstream_bad,
            "fallback_page_count": len(fallback_pages),
            "fallback_pages": fallback_pages,
            "fresh_numbering_page_count": fresh_numbering_count,
            "topology_missing_page_count": len(topology_missing_pages),
            "topology_missing_pages": topology_missing_pages,
            "topology_changed_page_count": len(topology_changed_pages),
            "topology_changed_pages": topology_changed_pages,
            "contract_ok": downstream_contract_ok,
        },
    }
    summary["gate_pass"] = all(
        (
            summary["page_identity_ok"],
            architecture_ok,
            detector_coverage_ok,
            downstream_contract_ok,
        )
    )
    output = run_root / "two_homr_full68_fresh_summary.json"
    summary["output"] = str(output)
    write_json(output, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--expected-pages", type=int, default=68)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--control-root", type=Path, default=DEFAULT_CONTROL_ROOT)
    parser.add_argument("--gt-root", type=Path, default=DEFAULT_GT_ROOT)
    args = parser.parse_args()
    summary = verify(args)
    compact = {
        "gate_pass": summary["gate_pass"],
        "page_identity_ok": summary["page_identity_ok"],
        "architecture_ok": summary["architecture"]["contract_ok"],
        "detector_coverage_ok": summary["detector"]["coverage_ok"],
        "changed_physical_page_count": summary["detector"]["changed_physical_page_count"],
        "downstream_contract_ok": summary["downstream"]["contract_ok"],
        "topology_changed_page_count": summary["downstream"]["topology_changed_page_count"],
        "fallback_page_count": summary["downstream"]["fallback_page_count"],
        "output": summary["output"],
    }
    print(json.dumps(compact, indent=2, ensure_ascii=False))
    return 0 if summary["gate_pass"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
