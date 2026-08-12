#!/usr/bin/env python3
"""Replay production downstream numbering from a retained fresh full-68 detector run.

This verifier deliberately does not execute detection. It resolves the exact barline,
staff-mask, and connector artifacts retained by ``verify_detector_full68.py`` and
replays only Phase A numbering -> batched MMR -> Phase C numbering.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.common.connector_artifacts import describe_connector_artifacts
from src.pipeline.core.config import load_yaml
from src.pipeline.detection import resolve_paths_from_detection
from src.pipeline.orchestrator import PipelineOrchestrator
from src.pipeline.utils.io import load_json, write_json

ROOT = Path(__file__).resolve().parents[2]
CANONICAL_CONFIG = ROOT / "configs/dense_full_pipeline.yaml"
DEFAULT_DETECTOR_REPORT = (
    ROOT
    / "logs/verification/detector_full68"
    / "issue255_production_restore_full68_top_level_worker_01"
    / "detector_full68_verification_report.json"
)
DEFAULT_OUTPUT_ROOT = ROOT / "logs/verification/downstream_full68"

FOCUSED_EXPECTED: dict[str, dict[str, Any]] = {
    "Shostakovich-Sym5-Va/page_013": {
        "global_page_number": 21,
        "membership": [2, 2, 2, 2, 2],
        "physical_measures_per_system": [6, 6, 5, 5, 5],
        "physical_measure_count": 27,
    },
    "Shostakovich-Sym5-Va/page_014": {
        "global_page_number": 22,
        "membership": [2, 2, 2, 2, 2],
        "physical_measure_count": 24,
    },
    "Va_Prokofiev_Symphony1/page_004": {
        "global_page_number": 45,
        "membership": [1, 1, 1, 1, 1, 1, 2, 1, 1, 1, 1, 1],
        "physical_measure_count": 101,
    },
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_artifact_path(raw: str | Path) -> Path:
    path = Path(raw)
    if path.exists():
        return path.resolve()

    if path.is_absolute():
        parts = path.parts
        if "workspace" in parts:
            workspace_index = parts.index("workspace")
            candidate = ROOT.joinpath(*parts[workspace_index + 1 :])
            if candidate.exists():
                return candidate.resolve()
    else:
        candidate = ROOT / path
        if candidate.exists():
            return candidate.resolve()

    raise FileNotFoundError(path)


def _validate_detector_report(report: Mapping[str, Any]) -> None:
    if report.get("status") != "completed":
        raise ValueError("Detector report is not completed")
    if report.get("authoritative_full68") is not True or report.get("page_count") != 68:
        raise ValueError("An authoritative retained full-68 detector report is required")
    if report.get("historical_detector_target_met") is not True:
        raise ValueError("Retained detector report did not meet the accepted detector target")
    if report.get("historical_detector_artifact_runtime_input") is not False:
        raise ValueError("Retained detector report used a historical detector runtime input")

    contract = report.get("detector_input_contract")
    if not isinstance(contract, Mapping):
        raise ValueError("Detector report lacks detector_input_contract")
    if contract.get("mode") != "fresh_upstream":
        raise ValueError(f"Detector report is not fresh_upstream: {contract}")
    if contract.get("fresh_upstream_authoritative") is not True:
        raise ValueError(f"Detector report is not authoritative fresh upstream: {contract}")
    if contract.get("override_keys") != []:
        raise ValueError(f"Detector report contains runtime detector overrides: {contract}")


def _production_runs_by_score(report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    runs = report.get("production_runs")
    if not isinstance(runs, list):
        raise ValueError("Detector report lacks production_runs")
    indexed: dict[str, Mapping[str, Any]] = {}
    for item in runs:
        if not isinstance(item, Mapping) or not isinstance(item.get("score"), str):
            raise ValueError(f"Invalid production run entry: {item!r}")
        score = str(item["score"])
        if score in indexed:
            raise ValueError(f"Duplicate production run for score: {score}")
        indexed[score] = item
    return indexed


def _selected_pages(report: Mapping[str, Any]) -> list[str]:
    pages = report.get("selected_pages")
    if not isinstance(pages, list) or len(pages) != 68 or not all(isinstance(p, str) for p in pages):
        raise ValueError("Detector report does not contain the canonical 68 selected_pages")
    return list(pages)


def _score_selectors(report: Mapping[str, Any], score: str) -> list[str]:
    return [selector for selector in _selected_pages(report) if selector.split("/", 1)[0] == score]


def _images_for_selectors(selectors: Sequence[str]) -> list[Path]:
    images: list[Path] = []
    for selector in selectors:
        score, page_id = selector.split("/", 1)
        image = ROOT / "data/evaluation2/images" / score / f"{page_id}.png"
        if not image.is_file():
            raise FileNotFoundError(image)
        images.append(image)
    return images


def _write_combined(paths: Sequence[Path], destination: Path) -> None:
    pages = [page for path in paths for page in load_json(path).get("pages", [])]
    write_json(destination, {"pages": pages})


def _first_page(payload: Mapping[str, Any], *, source: Path) -> Mapping[str, Any]:
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 1 or not isinstance(pages[0], Mapping):
        raise ValueError(f"Expected one page in {source}")
    return pages[0]


def _row_starts(page: Mapping[str, Any]) -> list[int | None]:
    starts: list[int | None] = []
    systems = page.get("systems", [])
    if not isinstance(systems, list):
        return starts
    for system in systems:
        if not isinstance(system, Mapping):
            starts.append(None)
            continue
        measures = system.get("measures", [])
        if not isinstance(measures, list) or not measures or not isinstance(measures[0], Mapping):
            starts.append(None)
            continue
        number = measures[0].get("number")
        starts.append(int(number) if isinstance(number, int) else None)
    return starts


def _summarize_page(
    *,
    selector: str,
    global_page_number: int,
    score_page_index: int,
    resolved_item: Mapping[str, str],
    base_path: Path,
    final_path: Path,
    mmr_path: Path,
) -> dict[str, Any]:
    base_page = _first_page(load_json(base_path), source=base_path)
    final_page = _first_page(load_json(final_path), source=final_path)
    systems = base_page.get("systems", [])
    if not isinstance(systems, list):
        raise ValueError(f"Invalid systems in {base_path}")

    membership = [
        len(system.get("staves", [])) if isinstance(system, Mapping) else 0 for system in systems
    ]
    physical_per_system = [
        len(system.get("measures", [])) if isinstance(system, Mapping) else 0 for system in systems
    ]

    mmr_payload: Mapping[str, Any] = {}
    if mmr_path.is_file():
        loaded = load_json(mmr_path)
        if isinstance(loaded, Mapping):
            mmr_payload = loaded
    mmr_overrides = mmr_payload.get("measure_overrides", [])
    if not isinstance(mmr_overrides, list):
        mmr_overrides = []
    mmr_pages = sorted(
        {
            int(override["page"])
            for override in mmr_overrides
            if isinstance(override, Mapping) and isinstance(override.get("page"), int)
        }
    )

    barlines = _resolve_artifact_path(resolved_item["barlines_json"])
    staff_mask = _resolve_artifact_path(resolved_item["staff_mask"])
    connector = describe_connector_artifacts(staff_mask)

    return {
        "selector": selector,
        "global_page_number": global_page_number,
        "score_page_index": score_page_index,
        "barlines_json": str(barlines),
        "barlines_sha256": _sha256(barlines),
        "staff_mask": str(staff_mask),
        "staff_mask_sha256": _sha256(staff_mask),
        "connector_evidence": connector,
        "system_count": len(systems),
        "membership": membership,
        "physical_measures_per_system": physical_per_system,
        "physical_measure_count": sum(physical_per_system),
        "mmr_override_count": len(mmr_overrides),
        "mmr_override_pages": mmr_pages,
        "base_row_starts": _row_starts(base_page),
        "final_row_starts": _row_starts(final_page),
        "numbering_base": str(base_path),
        "overrides_mmr": str(mmr_path),
        "numbering_final": str(final_path),
    }


def _focused_contract_mismatches(page_summaries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    actual_by_selector = {str(page["selector"]): page for page in page_summaries}
    mismatches: dict[str, Any] = {}
    for selector, expected in FOCUSED_EXPECTED.items():
        if selector not in actual_by_selector:
            continue
        actual = actual_by_selector[selector]
        page_mismatches: dict[str, Any] = {}
        for field in ("global_page_number", "membership", "physical_measure_count"):
            if actual.get(field) != expected.get(field):
                page_mismatches[field] = {"expected": expected.get(field), "actual": actual.get(field)}
        if "physical_measures_per_system" in expected and (
            actual.get("physical_measures_per_system") != expected["physical_measures_per_system"]
        ):
            page_mismatches["physical_measures_per_system"] = {
                "expected": expected["physical_measures_per_system"],
                "actual": actual.get("physical_measures_per_system"),
            }

        connector = actual.get("connector_evidence")
        if not isinstance(connector, Mapping):
            page_mismatches["connector_evidence"] = {"expected": "mapping", "actual": connector}
        else:
            connector_expected = {
                "source": "proxy_symbol_layers",
                "coordinate_space": "homr_segmentation_mask",
                "include_absent_pairs": True,
            }
            for field, expected_value in connector_expected.items():
                if connector.get(field) != expected_value:
                    page_mismatches[f"connector_evidence.{field}"] = {
                        "expected": expected_value,
                        "actual": connector.get(field),
                    }
        if page_mismatches:
            mismatches[selector] = page_mismatches
    return mismatches


def _run_score(
    *,
    config: Mapping[str, Any],
    detector_report: Mapping[str, Any],
    detector_run: Mapping[str, Any],
    score: str,
    run_tag: str,
    run_root: Path,
    global_page_numbers: Mapping[str, int],
) -> dict[str, Any]:
    selectors = _score_selectors(detector_report, score)
    if not selectors:
        raise ValueError(f"No canonical pages found for score: {score}")
    images = _images_for_selectors(selectors)
    page_ids = [image.stem for image in images]
    probe_root = _resolve_artifact_path(str(detector_run["probe_output_dir"]))
    hybrid_root = _resolve_artifact_path(str(detector_run["hybrid_output_dir"]))
    resolved = resolve_paths_from_detection(
        dict(config), probe_root, hybrid_root, page_ids, images
    )
    for item in resolved:
        _resolve_artifact_path(item["barlines_json"])
        _resolve_artifact_path(item["staff_mask"])

    score_root = run_root / "production_runs" / score
    score_root.mkdir(parents=True, exist_ok=False)
    score_config = copy.deepcopy(dict(config))
    score_config["steps"]["detection"] = False

    orchestrator = PipelineOrchestrator(
        score_config,
        f"{run_tag}__{score}",
        score_root,
        dry_run=False,
        validate_only=False,
        skip_existing=False,
        debug=False,
    )
    excluded: set[str] = set()
    phase_a = orchestrator.run_base_numbering_and_barline_correction(
        page_ids, images, resolved, excluded
    )
    page_ctx = phase_a["page_ctx"]
    orchestrator.run_mmr_batch_detection(page_ids, excluded, page_ctx)
    final_paths = orchestrator.run_final_numbering_and_overlays(
        page_ids, excluded, page_ctx, None
    )

    combined_base = score_root / "intermediate" / "numbering_base.json"
    combined_final = score_root / "outputs" / "numbering_final.json"
    _write_combined(phase_a["numbering_base_paths"], combined_base)
    _write_combined(final_paths, combined_final)

    page_summaries: list[dict[str, Any]] = []
    for score_page_index, (selector, page_id, resolved_item, final_path) in enumerate(
        zip(selectors, page_ids, resolved, final_paths)
    ):
        ctx = page_ctx[page_id]
        page_summaries.append(
            _summarize_page(
                selector=selector,
                global_page_number=global_page_numbers[selector],
                score_page_index=score_page_index,
                resolved_item=resolved_item,
                base_path=Path(ctx["numbering_base"]),
                final_path=Path(final_path),
                mmr_path=Path(ctx["intermediate_dir"]) / "overrides_mmr.json",
            )
        )

    return {
        "score": score,
        "page_count": len(page_ids),
        "source_detector_run_id": detector_run.get("run_id"),
        "source_probe_output_dir": str(probe_root),
        "source_hybrid_output_dir": str(hybrid_root),
        "downstream_run_root": str(score_root),
        "combined_numbering_base": str(combined_base),
        "combined_numbering_final": str(combined_final),
        "physical_measure_count": sum(page["physical_measure_count"] for page in page_summaries),
        "mmr_override_count": sum(page["mmr_override_count"] for page in page_summaries),
        "pages": page_summaries,
    }


def run(args: argparse.Namespace) -> Path:
    config_path = args.config.resolve()
    if config_path != CANONICAL_CONFIG.resolve():
        raise ValueError(f"Canonical config required: {CANONICAL_CONFIG}")
    detector_report_path = args.detector_report.resolve()
    detector_report = json.loads(detector_report_path.read_text(encoding="utf-8"))
    if not isinstance(detector_report, Mapping):
        raise ValueError("Detector report is not a mapping")
    _validate_detector_report(detector_report)

    config = load_yaml(config_path)
    if not isinstance(config, Mapping):
        raise ValueError("Canonical config is not a mapping")
    runs_by_score = _production_runs_by_score(detector_report)
    all_scores = list(runs_by_score)
    requested_scores = list(args.score or all_scores)
    unknown_scores = [score for score in requested_scores if score not in runs_by_score]
    if unknown_scores:
        raise ValueError(f"Score is not present in detector report: {unknown_scores}")
    if len(set(requested_scores)) != len(requested_scores):
        raise ValueError("Duplicate --score values are not allowed")

    run_root = args.output_root.resolve() / args.run_tag
    if run_root.exists():
        raise FileExistsError(run_root)
    run_root.mkdir(parents=True)

    canonical_pages = _selected_pages(detector_report)
    global_page_numbers = {
        selector: index for index, selector in enumerate(canonical_pages, start=1)
    }
    score_reports = [
        _run_score(
            config=config,
            detector_report=detector_report,
            detector_run=runs_by_score[score],
            score=score,
            run_tag=args.run_tag,
            run_root=run_root,
            global_page_numbers=global_page_numbers,
        )
        for score in requested_scores
    ]
    page_summaries = [page for score_report in score_reports for page in score_report["pages"]]
    focused_mismatches = _focused_contract_mismatches(page_summaries)
    focused_present = sorted(
        selector for selector in FOCUSED_EXPECTED if selector in {p["selector"] for p in page_summaries}
    )

    report = {
        "schema_version": "verification.downstream_full68.v1",
        "status": "completed",
        "run_tag": args.run_tag,
        "detector_reexecuted": False,
        "source_detector_report": str(detector_report_path),
        "source_detector_report_sha256": _sha256(detector_report_path),
        "source_detector_run_tag": detector_report.get("run_tag"),
        "source_detector_input_contract": detector_report.get("detector_input_contract"),
        "config": str(config_path),
        "config_sha256": _sha256(config_path),
        "scores": requested_scores,
        "score_count": len(requested_scores),
        "page_count": len(page_summaries),
        "authoritative_full68_downstream": set(requested_scores) == set(all_scores)
        and len(page_summaries) == 68,
        "physical_measure_count": sum(page["physical_measure_count"] for page in page_summaries),
        "mmr_override_count": sum(page["mmr_override_count"] for page in page_summaries),
        "focused_contract_pages": focused_present,
        "focused_contract_mismatches": focused_mismatches,
        "focused_contract_met": not focused_mismatches,
        "production_runs": score_reports,
    }
    report_path = run_root / "downstream_full68_verification_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-tag", required=True)
    parser.add_argument("--detector-report", type=Path, default=DEFAULT_DETECTOR_REPORT)
    parser.add_argument("--config", type=Path, default=CANONICAL_CONFIG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--score",
        action="append",
        help="Replay a complete score from the retained full-68 detector run. Repeat as needed.",
    )
    args = parser.parse_args()
    try:
        report_path = run(args)
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1

    print(json.dumps({"status": "completed", "report": str(report_path)}, ensure_ascii=False))
    if report.get("focused_contract_met") is not True:
        print(
            json.dumps(
                {"status": "failed_contract", "mismatches": report["focused_contract_mismatches"]},
                ensure_ascii=False,
            )
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
