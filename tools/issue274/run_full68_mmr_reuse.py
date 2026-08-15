#!/usr/bin/env python3
"""Run one full-68 MMR batch from retained Issue #274 artifacts only.

Repository/commit provenance and cross-run attempt history are intentionally
checked outside this runner so the same retained-artifact replay can be reused
from different worktrees, commits, and validation sessions. The historical
direct-index fixture score emitted here is diagnostic only; final acceptance
uses the geometry-rebased rescorer.
"""

from __future__ import annotations

import argparse
import datetime as dt
import time
import traceback
from pathlib import Path
from typing import Any

import torch

from src.measure_numbering.mmr import MMRClassifier, MMROCREngine
from src.measure_numbering.rapidocr_provider import (
    collect_rapidocr_providers,
    create_mmr_rapidocr,
    providers_include_cuda,
)
from src.pipeline.mmr_support_reuse import build_mmr_support
from src.pipeline.steps.numbering import run_mmr_batch
from src.pipeline.utils.io import load_json, write_json
from tools.issue264.run_phase_c_mmr_regression import (
    build_page_specs,
    index_overrides,
    normalise_overrides,
    override_skip,
    score_overrides,
)
from tools.issue274.validate_mmr_support_mapping import _visible_path

EXPECTED_SUPPORT = {
    "pages": 68,
    "staff_slot_count": 677,
    "mapped_count": 677,
    "fallback_count": 0,
    "union_count": 13,
}


def _empty_expected() -> dict[str, list[dict[str, Any]]]:
    return {"overrides": []}


def _semantic(payload: Any) -> dict[tuple[int, int, int], int]:
    return {
        tuple(int(key_part) for key_part in key): override_skip(item)
        for key, item in index_overrides(normalise_overrides(payload)).items()
    }


def _json_semantic(items: dict[tuple[int, int, int], int]) -> list[dict[str, int]]:
    return [
        {"page": key[0], "system": key[1], "measure": key[2], "skip": skip}
        for key, skip in sorted(items.items())
    ]


def _compare_accepted(expected: Any, actual: Any) -> dict[str, Any]:
    before, after = _semantic(expected), _semantic(actual)
    added = {key: value for key, value in after.items() if key not in before}
    removed = {key: value for key, value in before.items() if key not in after}
    changed = {
        key: {"accepted_skip": before[key], "actual_skip": after[key]}
        for key in before.keys() & after.keys()
        if before[key] != after[key]
    }
    return {
        "exact": not added and not removed and not changed,
        "added": _json_semantic(added),
        "removed": _json_semantic(removed),
        "changed_skip": [
            {"page": key[0], "system": key[1], "measure": key[2], **value}
            for key, value in sorted(changed.items())
        ],
    }


def _aggregate_scores(scores: list[dict[str, Any]]) -> dict[str, Any]:
    names = (
        "expected",
        "detected",
        "matched_tp",
        "missed_fn",
        "skip_mismatch",
        "unexpected_fp",
    )
    totals = {name: sum(score["counts"][name] for score in scores) for name in names}
    tp, fp, fn, mismatch = (
        totals["matched_tp"],
        totals["unexpected_fp"],
        totals["missed_fn"],
        totals["skip_mismatch"],
    )
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn + mismatch) if tp + fn + mismatch else 0.0
    return {
        "pages": len(scores),
        **totals,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "zero_expected_pages": sum(score["counts"]["expected"] == 0 for score in scores),
    }


def _retained_performance(path: Path) -> dict[str, Any]:
    report = path / "phase_c_mmr_regression_report.json"
    if not report.is_file():
        return {"before_directly_comparable": False, "evidence": None}
    payload = load_json(report)
    return {
        "before_directly_comparable": False,
        "evidence": {"source": str(report), "runtime": payload.get("runtime")},
    }


def _write_failure_report(
    *,
    output_dir: Path,
    run_label: str,
    started: float,
    error: Exception,
    support_stats: dict[str, int],
    processor_state: dict[str, Any],
) -> None:
    processor = processor_state.get("processor")
    runtime: dict[str, Any] = {"elapsed_sec": time.perf_counter() - started}
    if torch.cuda.is_available():
        runtime.update(
            {
                "torch_cuda_max_memory_allocated": torch.cuda.max_memory_allocated(),
                "torch_cuda_max_memory_reserved": torch.cuda.max_memory_reserved(),
                "total_gpu_peak_measured": False,
            }
        )
    write_json(
        output_dir / "full68_failure.json",
        {
            "schema_version": "issue274.full68_mmr_reuse.failure.v2",
            "run_label": run_label,
            "timestamp": dt.datetime.now().astimezone().isoformat(),
            "exception_type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
            "runtime": runtime,
            "current_page": getattr(processor, "current_page_id", None),
            "last_completed_page": getattr(processor, "last_completed_page_id", None),
            "support_stats": getattr(processor, "support_stats", support_stats),
        },
    )


def _preflight(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    specs = build_page_specs()
    if [spec.page_id for spec in specs] != [f"page_{index:03d}" for index in range(1, 69)]:
        raise RuntimeError("Evaluation page mapping is not the unique page_001..page_068 sequence")
    feasibility = load_json(args.feasibility)
    entries = {entry["page_id"]: entry for entry in feasibility.get("pages", [])}
    if set(entries) != {spec.page_id for spec in specs}:
        raise RuntimeError("Feasibility entries do not resolve the full 68-page mapping")
    previous = list(args.output_dir.glob("intermediate/page_*/overrides_mmr.json"))
    if previous:
        raise RuntimeError(f"Refusing existing output overrides before MMR: {previous[:3]}")

    pages: list[dict[str, Any]] = []
    for spec in specs:
        base = args.retained_root / "intermediate" / spec.page_id / "numbering_base.json"
        accepted = args.retained_root / "intermediate" / spec.page_id / "overrides_mmr.json"
        mask = _visible_path(entries[spec.page_id]["shared_staff_mask"], Path.cwd())
        missing = [
            label
            for label, value in (
                ("numbering_base", base),
                ("image", spec.image),
                ("current_x4_mask", mask),
                ("accepted_overrides", accepted),
            )
            if not value.is_file()
        ]
        if missing:
            raise FileNotFoundError(f"{spec.page_id}: missing {', '.join(missing)}")
        pages.append(
            {
                "page_id": spec.page_id,
                "image": spec.image,
                "numbering_base": base,
                "accepted": accepted,
                "fixture": spec.expected_fixture,
                "mask": mask,
            }
        )
    if not args.model.is_file():
        raise FileNotFoundError(args.model)
    return pages, entries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retained-root", type=Path, required=True)
    parser.add_argument("--feasibility", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--run-label", default="full68")
    args = parser.parse_args()
    started = time.perf_counter()
    support_stats: dict[str, int] = {}
    processor_state: dict[str, Any] = {}
    try:
        pages, _entries = _preflight(args)
        if args.preflight_only:
            print(f"PREFLIGHT OK: {len(pages)} pages, no MMR invoked", flush=True)
            return

        args.output_dir.mkdir(parents=True, exist_ok=True)
        support_data, pages_data, images, outputs = [], [], [], []
        totals = {key: 0 for key in EXPECTED_SUPPORT}
        for item in pages:
            page_dir = args.output_dir / "intermediate" / item["page_id"]
            support = build_mmr_support(
                numbering_base_path=item["numbering_base"],
                current_homr_staff_mask=item["mask"],
                output_path=page_dir / "mmr_support.json",
            )
            provenance = support["provenance"]
            totals["pages"] += 1
            for key in ("staff_slot_count", "mapped_count", "fallback_count", "union_count"):
                totals[key] += provenance[key]
            support_data.append(support)
            pages_data.append(load_json(item["numbering_base"]))
            images.append(item["image"])
            outputs.append(page_dir / "overrides_mmr.json")
        if totals != EXPECTED_SUPPORT:
            raise RuntimeError(f"Support aggregate mismatch before MMR: {totals}")

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        if device.type != "cuda":
            raise RuntimeError("CUDA is required for this full-68 MMR replay")
        classifier = MMRClassifier(args.model, device)
        provider = create_mmr_rapidocr("cuda")
        ocr = MMROCREngine(ocr_engine=provider)
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        print(f"MMR batch start ({args.run_label})", flush=True)
        actual = run_mmr_batch(
            pages_data=pages_data,
            image_paths=images,
            output_paths=outputs,
            model_path=args.model,
            device=device,
            classifier=classifier,
            ocr_engine=ocr,
            rapidocr_provider="cuda",
            support_data=support_data,
            support_stats=support_stats,
            processor_state=processor_state,
        )
        elapsed = time.perf_counter() - started

        scores, comparisons, page_reports = [], [], []
        for item, output in zip(pages, actual):
            fixture = load_json(item["fixture"]) if item["fixture"] else _empty_expected()
            accepted = load_json(item["accepted"])
            score = score_overrides(fixture, output)
            comparison = _compare_accepted(accepted, output)
            scores.append(score)
            comparisons.append(comparison)
            page_reports.append(
                {
                    "page_id": item["page_id"],
                    "direct_index_diagnostic_score": score,
                    "accepted_diff": comparison,
                }
            )
        direct_index_diagnostic_metrics = _aggregate_scores(scores)
        changed_pages = [
            item["page_id"] for item, diff in zip(pages, comparisons) if not diff["exact"]
        ]
        page_042 = next(item for item in page_reports if item["page_id"] == "page_042")
        page_033 = actual[
            next(index for index, item in enumerate(pages) if item["page_id"] == "page_033")
        ]
        page_033_map = _semantic(page_033)
        page_033_gate = {
            "required": {
                "32,2,2": page_033_map.get((32, 2, 2)) == 1,
                "32,2,7": page_033_map.get((32, 2, 7)) == 6,
                "32,5,6": page_033_map.get((32, 5, 6)) == 5,
                "32,0,0_absent": (32, 0, 0) not in page_033_map,
            }
        }
        page_033_gate["passed"] = all(page_033_gate["required"].values())
        providers = collect_rapidocr_providers(provider)
        report = {
            "schema_version": "issue274.full68_mmr_reuse.v2",
            "evaluation_contract": {
                "direct_index_metrics_are_acceptance": False,
                "acceptance_scoring": "run rescore_full68_mmr_reuse_geometry_rebased.py on completed artifacts",
            },
            "scope": {
                "detector_reexecuted": False,
                "homr_reexecuted": False,
                "sr_reexecuted": False,
                "omr_dln_reexecuted": False,
                "original_image_homr_execution": 0,
                "second_numbering_rebuild": 0,
                "full68_mmr_invocations_this_run": 1,
                "run_label": args.run_label,
                "numbering_base_source": str(args.retained_root / "intermediate"),
            },
            "preflight": {"pages": len(pages), "passed": True},
            "support_aggregate": totals,
            "direct_index_diagnostic_metrics": direct_index_diagnostic_metrics,
            "accepted_diff": {
                "exact_pages": 68 - len(changed_pages),
                "changed_pages": changed_pages,
                "pages": page_reports,
            },
            "focused_gates": {
                "page_042_five_overrides_exact": page_042["accepted_diff"]["exact"]
                and len(normalise_overrides(actual[41])) == 5,
                "page_033": page_033_gate,
            },
            "support_stats": support_stats,
            "runtime": {
                "elapsed_sec": elapsed,
                "torch_cuda_max_memory_allocated": torch.cuda.max_memory_allocated(),
                "torch_cuda_max_memory_reserved": torch.cuda.max_memory_reserved(),
                "total_gpu_peak_measured": False,
                "total_gpu_peak_note": "Total GPU peak was not measured; these are PyTorch CUDA allocator peaks only.",
            },
            "rapidocr": {
                "providers": providers,
                "cuda_confirmed": providers_include_cuda(providers),
            },
            "performance": _retained_performance(args.retained_root),
            "final_numbering_semantics_unchanged": len(changed_pages) == 0,
            "final_numbering_semantics_evidence": "retained numbering_base inputs and all accepted overrides are exact"
            if not changed_pages
            else "accepted override differences are listed above",
        }
        write_json(args.output_dir / "issue274_full68_mmr_reuse.json", report)
        print(
            {
                "direct_index_diagnostic_metrics": direct_index_diagnostic_metrics,
                "direct_index_metrics_are_acceptance": False,
                "exact_pages": report["accepted_diff"]["exact_pages"],
                "changed_pages": changed_pages,
                "runtime": report["runtime"],
            },
            flush=True,
        )
    except Exception as error:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        _write_failure_report(
            output_dir=args.output_dir,
            run_label=args.run_label,
            started=started,
            error=error,
            support_stats=support_stats,
            processor_state=processor_state,
        )
        raise


if __name__ == "__main__":
    main()
