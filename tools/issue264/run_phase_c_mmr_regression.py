#!/usr/bin/env python3
"""Run Issue #264 Phase C MMR regression from retained detector artifacts.

This is the current-production acceptance runner for the detector/counting scope.
It deliberately does not rerun detector inference.  The legacy Issue #94 page index
is used only to preserve the established global page-to-score mapping used by the
expected MMR fixtures; its historical ``numbering_base`` paths are never consumed.

Execution path:

retained canonical detector barlines + retained canonical numbering staff geometry
    -> current Phase A physical-measure construction
    -> fresh current-runtime HOMR staff geometry for MMR only (Phase B handoff)
    -> current batched MMR CNN/OCR
    -> current per-page override application
    -> full-68 MMR scoring, including pages with zero expected MMR overrides

Cross-page measure-number continuation and PDF label placement are intentionally out
of scope for this runner (tracked separately from Issue #264 counting correctness).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import sys
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import torch

from src.measure_numbering.rapidocr_provider import (
    collect_rapidocr_providers,
    providers_include_cuda,
)
from src.pipeline.core.config import load_yaml
from src.pipeline.mmr_geometry_handoff import build_mmr_page_context
from src.pipeline.orchestrator import PipelineOrchestrator
from src.pipeline.utils.io import load_json, write_json

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_RUN = "issue255_production_restore_full68_top_level_worker_01"
CANONICAL_CONFIG = PROJECT_ROOT / "configs/dense_full_pipeline.yaml"
LEGACY_PAGE_INDEX = PROJECT_ROOT / "logs/issue94_mmr_current_state/page_inputs.json"
MODEL_PATH = PROJECT_ROOT / "tools/mmr_training/models/mmr_classifier_best.pth"
FIXTURE_ROOT = PROJECT_ROOT / "tests/fixtures"

HISTORICAL_BASELINE = {
    "pages": 68,
    "base_measures": 3325,
    "expected": 182,
    "detected": 179,
    "matched_tp": 173,
    "missed_fn": 3,
    "skip_mismatch": 6,
    "unexpected_fp": 0,
    "precision": 0.9664804469,
    "recall": 0.9505494505,
    "f1": 0.9584487535,
    "note": (
        "Historical #221 score used legacy numbering geometry and did not count "
        "unexpected detections on pages without an expected fixture."
    ),
}

ACCEPTED_DETECTOR = {
    "GT": 3567,
    "Pred": 3599,
    "TP": 3565,
    "FP": 3,
    "FN": 2,
    "FN_det": 0,
    "FN_cnn": 2,
    "candidate_count": 29774,
}

FOCUSED_PHYSICAL = {
    # Shostakovich-Sym5-Va/page_013
    "page_021": [6, 6, 5, 5, 5],
    # Shostakovich-Sym5-Va/page_014
    "page_022": [4, 5, 5, 5, 5],
    # Va_Prokofiev_Symphony1/page_001 (Issue #244 / Phase B acceptance)
    "page_042": [5, 5, 5, 7, 7, 8, 5, 7, 10, 8, 5, 6],
    # Va_Prokofiev_Symphony1/page_004
    "page_045": [5, 5, 8, 6, 6, 11, 10, 11, 9, 10, 10, 10],
}

PHASE_B_PAGE_ID = "page_042"
PAGE_033_ONE_BAR_KEY = (32, 0, 0)
IMAGE_STEM_RE = re.compile(r"^(?P<score>.+)_page_(?P<page>\d{3})$")


@dataclass(frozen=True)
class PageSpec:
    page_id: str
    global_index: int
    score: str
    page_name: str
    image_stem: str
    image: Path
    barlines: Path
    staff_mask: Path
    expected_fixture: Path | None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def describe_file(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def parse_eval_image_stem(stem: str) -> tuple[str, str]:
    match = IMAGE_STEM_RE.fullmatch(stem)
    if match is None:
        raise ValueError(f"Unexpected evaluation image stem: {stem}")
    return match.group("score"), f"page_{match.group('page')}"


def _canonical_paths(score: str, page_name: str, image_stem: str) -> tuple[Path, Path, Path]:
    image = PROJECT_ROOT / "data/evaluation2/images" / score / f"{page_name}.png"
    barlines = (
        PROJECT_ROOT
        / "logs/verification/detector_full68"
        / CANONICAL_RUN
        / "production_runs"
        / score
        / "intermediate/dense_full_pipeline_route/dense_candidate_reconstruction"
        / "probe_rescue_candidates"
        / f"eval2_{image_stem}"
        / "pipeline2_no_peak_filtered_cnn.json"
    )
    staff_mask = (
        PROJECT_ROOT
        / "logs/full_pipeline_runs/dense_full_pipeline/hybrid_output"
        / f"{CANONICAL_RUN}__{score}"
        / "sr/batch"
        / page_name
        / f"{page_name}_proxy_debug_3_staff.png"
    )
    return image, barlines, staff_mask


def build_page_specs(page_index_path: Path = LEGACY_PAGE_INDEX) -> list[PageSpec]:
    payload = load_json(page_index_path)
    raw_pages = payload.get("pages")
    if not isinstance(raw_pages, list):
        raise ValueError(f"Page index lacks pages list: {page_index_path}")

    specs: list[PageSpec] = []
    for position, raw in enumerate(raw_pages, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"Malformed page entry at position {position}")
        page_id = str(raw.get("page_id", ""))
        expected_page_id = f"page_{position:03d}"
        if page_id != expected_page_id:
            raise ValueError(
                f"Global page mapping changed at position {position}: "
                f"expected {expected_page_id}, got {page_id}"
            )

        # Only the basename/stem from the legacy index is used.  Historical
        # numbering_base and historical image bytes are not production inputs.
        image_stem = Path(str(raw.get("image", ""))).stem
        score, page_name = parse_eval_image_stem(image_stem)
        image, barlines, staff_mask = _canonical_paths(score, page_name, image_stem)
        fixture = FIXTURE_ROOT / f"expected_overrides_{page_id}.json"
        specs.append(
            PageSpec(
                page_id=page_id,
                global_index=position - 1,
                score=score,
                page_name=page_name,
                image_stem=image_stem,
                image=image,
                barlines=barlines,
                staff_mask=staff_mask,
                expected_fixture=fixture if fixture.is_file() else None,
            )
        )
    return specs


def validate_page_specs(specs: list[PageSpec]) -> None:
    if len(specs) != 68:
        raise ValueError(f"Expected 68 evaluation pages, got {len(specs)}")
    missing: list[str] = []
    for spec in specs:
        for label, path in (
            ("image", spec.image),
            ("barlines", spec.barlines),
            ("staff_mask", spec.staff_mask),
        ):
            if not path.is_file():
                missing.append(f"{spec.page_id} {label}: {path}")
    if not MODEL_PATH.is_file():
        missing.append(f"MMR model: {MODEL_PATH}")
    if not CANONICAL_CONFIG.is_file():
        missing.append(f"canonical config: {CANONICAL_CONFIG}")
    if missing:
        raise FileNotFoundError("Missing Phase C inputs:\n" + "\n".join(f"- {x}" for x in missing))


def normalise_overrides(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("measure_overrides", "overrides"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def override_key(item: dict[str, Any]) -> tuple[int, int, int]:
    return int(item["page"]), int(item["system"]), int(item["measure"])


def override_skip(item: dict[str, Any]) -> int:
    return int(item.get("skip") or 0)


def index_overrides(items: Iterable[dict[str, Any]]) -> dict[tuple[int, int, int], dict[str, Any]]:
    indexed: dict[tuple[int, int, int], dict[str, Any]] = {}
    for item in items:
        indexed[override_key(item)] = item
    return indexed


def score_overrides(
    expected_payload: Any,
    detected_payload: Any,
) -> dict[str, Any]:
    """Score one page, treating an absent fixture as an explicit zero-positive page."""
    expected = normalise_overrides(expected_payload)
    detected = normalise_overrides(detected_payload)
    expected_by_key = index_overrides(expected)
    detected_by_key = index_overrides(detected)

    matched: list[dict[str, Any]] = []
    missed: list[dict[str, Any]] = []
    mismatch: list[dict[str, Any]] = []
    unexpected: list[dict[str, Any]] = []

    for key, expected_item in expected_by_key.items():
        detected_item = detected_by_key.get(key)
        if detected_item is None:
            missed.append({"key": list(key), "expected_skip": override_skip(expected_item)})
            continue
        if override_skip(expected_item) == override_skip(detected_item):
            matched.append({"key": list(key), "skip": override_skip(detected_item)})
        else:
            mismatch.append(
                {
                    "key": list(key),
                    "expected_skip": override_skip(expected_item),
                    "detected_skip": override_skip(detected_item),
                    "detected_comment": detected_item.get("comment"),
                }
            )

    # Unlike the legacy Issue #94 accounting, this always runs.  Therefore a
    # page with no fixture is an explicit expected-empty page and any detection
    # is counted as FP.
    for key, detected_item in detected_by_key.items():
        if key not in expected_by_key:
            unexpected.append(
                {
                    "key": list(key),
                    "detected_skip": override_skip(detected_item),
                    "detected_comment": detected_item.get("comment"),
                }
            )

    return {
        "counts": {
            "expected": len(expected),
            "detected": len(detected),
            "matched_tp": len(matched),
            "missed_fn": len(missed),
            "skip_mismatch": len(mismatch),
            "unexpected_fp": len(unexpected),
        },
        "matched": matched,
        "missed": missed,
        "skip_mismatch": mismatch,
        "unexpected": unexpected,
    }


def physical_counts(numbering_payload: dict[str, Any]) -> list[int]:
    pages = numbering_payload.get("pages", [])
    if len(pages) != 1:
        raise ValueError(f"Expected one-page numbering payload, got {len(pages)} pages")
    return [len(system.get("measures", [])) for system in pages[0].get("systems", [])]


def _load_expected(spec: PageSpec) -> dict[str, Any]:
    if spec.expected_fixture is None:
        return {"overrides": []}
    return load_json(spec.expected_fixture)


def _runtime_provenance(orchestrator: PipelineOrchestrator) -> dict[str, Any]:
    providers: dict[str, list[str]] = {}
    provider_mode: str | None = None
    ocr_engine = orchestrator._mmr_persistence.get(("ocr_engine", False))  # noqa: SLF001
    if ocr_engine is not None:
        provider_mode = getattr(ocr_engine, "_rapidocr_provider_mode", None)
        provider_impl = getattr(ocr_engine, "ocr_engine", None)
        if provider_impl is not None:
            providers = collect_rapidocr_providers(provider_impl)

    try:
        ort_version = importlib.metadata.version("onnxruntime-gpu")
    except importlib.metadata.PackageNotFoundError:
        try:
            ort_version = importlib.metadata.version("onnxruntime")
        except importlib.metadata.PackageNotFoundError:
            ort_version = None
    try:
        rapidocr_version = importlib.metadata.version("rapidocr-onnxruntime")
    except importlib.metadata.PackageNotFoundError:
        rapidocr_version = None

    try:
        import onnxruntime as ort

        ort_providers = ort.get_available_providers()
    except Exception:  # noqa: BLE001
        ort_providers = []

    return {
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "torch_version": torch.__version__,
        "torch_cuda_available": torch.cuda.is_available(),
        "torch_cuda_version": torch.version.cuda,
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "onnxruntime_version": ort_version,
        "onnxruntime_available_providers": ort_providers,
        "rapidocr_version": rapidocr_version,
        "rapidocr_provider_mode": provider_mode,
        "rapidocr_component_providers": providers,
        "rapidocr_cuda_confirmed": providers_include_cuda(providers),
        "container_name": os.environ.get("ISSUE264_CONTAINER_NAME"),
        "container_image_id": os.environ.get("ISSUE264_CONTAINER_IMAGE_ID"),
        "container_hostname": platform.node(),
        "dockerenv": Path("/.dockerenv").exists(),
    }


def _detector_provenance() -> dict[str, Any]:
    eval_root = PROJECT_ROOT / "logs/verification/detector_full68" / CANONICAL_RUN / "eval_detector"
    files = {}
    for name in (
        "manifest.json",
        "evaluation_contract.json",
        "detector_metrics.json",
        "detector_page_metrics.csv",
    ):
        path = eval_root / name
        if path.is_file():
            files[name] = describe_file(path)
    return {
        "run_id": CANONICAL_RUN,
        "detector_reexecuted": False,
        "accepted_metrics": ACCEPTED_DETECTOR,
        "artifacts": files,
    }


def _artifact_hashes(specs: list[PageSpec], run_dir: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for spec in specs:
        page_intermediate = run_dir / "intermediate" / spec.page_id
        page_outputs = run_dir / "outputs" / spec.page_id
        row: dict[str, Any] = {"page_id": spec.page_id}
        for label, path in (
            ("numbering_base", page_intermediate / "numbering_base.json"),
            ("numbering_mmr_geometry", page_intermediate / "numbering_mmr_geometry.json"),
            ("overrides_mmr", page_intermediate / "overrides_mmr.json"),
            ("numbering_final", page_outputs / "numbering_final.json"),
        ):
            row[label] = describe_file(path) if path.is_file() else None
        items.append(row)
    return items


def run(run_dir: Path, *, resume: bool = False) -> Path:
    specs = build_page_specs()
    validate_page_specs(specs)
    run_dir.mkdir(parents=True, exist_ok=True)

    config = deepcopy(load_yaml(CANONICAL_CONFIG))
    config.setdefault("steps", {})["detection"] = False
    config["steps"]["overlay"] = False
    config.setdefault("outputs", {}).pop("review", None)

    page_ids = [spec.page_id for spec in specs]
    images = [spec.image for spec in specs]
    resolved = [
        {
            "page_id": spec.page_id,
            "page_run": spec.image_stem,
            "barlines_json": str(spec.barlines),
            "staff_mask": str(spec.staff_mask),
        }
        for spec in specs
    ]

    orchestrator = PipelineOrchestrator(
        config=config,
        run_id=run_dir.name,
        run_dir=run_dir,
        skip_existing=resume,
        debug=False,
    )
    excluded: set[str] = set()

    phase_a = orchestrator.run_base_numbering_and_barline_correction(
        page_ids,
        images,
        resolved,
        excluded,
    )
    page_ctx = phase_a["page_ctx"]

    mmr_page_ctx = build_mmr_page_context(orchestrator, page_ids, excluded, page_ctx)
    orchestrator.run_mmr_batch_detection(page_ids, excluded, mmr_page_ctx)
    # Exercise the current #257 application boundary as part of the real-artifact
    # replay.  The resulting page-local numbers are not interpreted as a
    # cross-page presentation contract here.
    final_paths = orchestrator.run_final_numbering_and_overlays(page_ids, excluded, page_ctx, None)

    page_reports: list[dict[str, Any]] = []
    totals = {
        "pages": len(specs),
        "base_measures": 0,
        "mmr_geometry_measures": 0,
        "expected": 0,
        "detected": 0,
        "matched_tp": 0,
        "missed_fn": 0,
        "skip_mismatch": 0,
        "unexpected_fp": 0,
        "zero_expected_pages": 0,
    }
    focused_checks: dict[str, Any] = {}
    all_fresh_geometry = True

    for spec in specs:
        page_intermediate = run_dir / "intermediate" / spec.page_id
        base_payload = load_json(page_intermediate / "numbering_base.json")
        mmr_geometry_payload = load_json(page_intermediate / "numbering_mmr_geometry.json")
        detected_payload = load_json(page_intermediate / "overrides_mmr.json")
        expected_payload = _load_expected(spec)
        score = score_overrides(expected_payload, detected_payload)

        base_physical = physical_counts(base_payload)
        mmr_physical = physical_counts(mmr_geometry_payload)
        totals["base_measures"] += sum(base_physical)
        totals["mmr_geometry_measures"] += sum(mmr_physical)
        if score["counts"]["expected"] == 0:
            totals["zero_expected_pages"] += 1
        for key in (
            "expected",
            "detected",
            "matched_tp",
            "missed_fn",
            "skip_mismatch",
            "unexpected_fp",
        ):
            totals[key] += score["counts"][key]

        geometry_provenance = page_ctx[spec.page_id]["resolved"].get("mmr_staff_geometry", {})
        fresh_geometry = (
            geometry_provenance.get("historical_detector_artifact_runtime_input") is False
        )
        all_fresh_geometry = all_fresh_geometry and fresh_geometry

        if spec.page_id in FOCUSED_PHYSICAL:
            focused_checks[f"{spec.page_id}_base_physical"] = {
                "actual": base_physical,
                "expected": FOCUSED_PHYSICAL[spec.page_id],
                "passed": base_physical == FOCUSED_PHYSICAL[spec.page_id],
            }
        if spec.page_id == PHASE_B_PAGE_ID:
            focused_checks["page_042_mmr_geometry_physical"] = {
                "actual": mmr_physical,
                "expected": FOCUSED_PHYSICAL[PHASE_B_PAGE_ID],
                "passed": mmr_physical == FOCUSED_PHYSICAL[PHASE_B_PAGE_ID],
            }
            expected_index = index_overrides(normalise_overrides(expected_payload))
            detected_index = index_overrides(normalise_overrides(detected_payload))
            focused_checks["page_042_five_mmr_overrides"] = {
                "expected": [
                    [key[1], key[2], override_skip(item)]
                    for key, item in sorted(expected_index.items())
                ],
                "actual": [
                    [key[1], key[2], override_skip(item)]
                    for key, item in sorted(detected_index.items())
                ],
                "passed": expected_index.keys() == detected_index.keys()
                and all(
                    override_skip(expected_index[key]) == override_skip(detected_index[key])
                    for key in expected_index
                ),
            }

        page_reports.append(
            {
                "page_id": spec.page_id,
                "global_index": spec.global_index,
                "score": spec.score,
                "score_page": spec.page_name,
                "image": str(spec.image),
                "base_physical": base_physical,
                "mmr_geometry_physical": mmr_physical,
                "expected_fixture": str(spec.expected_fixture) if spec.expected_fixture else None,
                "scoring": score,
                "fresh_mmr_geometry": fresh_geometry,
                "mmr_geometry_provenance": geometry_provenance,
            }
        )

    detected_page_033 = load_json(run_dir / "intermediate" / "page_033" / "overrides_mmr.json")
    one_bar_present = PAGE_033_ONE_BAR_KEY in index_overrides(
        normalise_overrides(detected_page_033)
    )
    focused_checks["page_033_one_bar_veto"] = {
        "key": list(PAGE_033_ONE_BAR_KEY),
        "passed": not one_bar_present,
    }

    precision = totals["matched_tp"] / totals["detected"] if totals["detected"] else 0.0
    recall = totals["matched_tp"] / totals["expected"] if totals["expected"] else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    totals.update({"precision": precision, "recall": recall, "f1": f1})

    gates = {
        "page_count_68": totals["pages"] == 68,
        "expected_fixture_total_182": totals["expected"] == 182,
        "zero_expected_pages_scored": totals["zero_expected_pages"] == 16,
        "unexpected_fp_zero": totals["unexpected_fp"] == 0,
        "missed_fn_not_above_3": totals["missed_fn"] <= 3,
        "skip_mismatch_not_above_6": totals["skip_mismatch"] <= 6,
        "page_033_one_bar_veto": focused_checks["page_033_one_bar_veto"]["passed"],
        "fresh_current_homr_mmr_geometry_all_pages": all_fresh_geometry,
        "focused_physical": all(
            value["passed"] for key, value in focused_checks.items() if key.endswith("_physical")
        ),
        "phase_b_page_042_five_overrides": focused_checks["page_042_five_mmr_overrides"]["passed"],
        "final_numbering_files_68": len(final_paths) == 68
        and all(path.is_file() for path in final_paths),
    }

    report = {
        "schema": "issue264.phase_c_mmr_regression.v1",
        "status": "passed" if all(gates.values()) else "failed",
        "scope": {
            "included": [
                "physical measure construction",
                "Multi-Measure Rest detection/OCR",
                "MMR skip application",
                "page-local final numbering application contract",
            ],
            "excluded": [
                "cross-page number continuation",
                "PDF/final label placement",
            ],
        },
        "repository": {
            "git_head": git_head(),
            "canonical_config": describe_file(CANONICAL_CONFIG),
            "mmr_model": describe_file(MODEL_PATH),
        },
        "evaluation_inputs": {
            "page_index": {
                "path": str(LEGACY_PAGE_INDEX),
                "sha256": sha256_file(LEGACY_PAGE_INDEX),
                "usage": "page-id to canonical score/page mapping only",
                "historical_numbering_base_consumed": False,
                "historical_image_bytes_consumed": False,
            },
            "input_images": [
                {
                    "page_id": spec.page_id,
                    "score": spec.score,
                    "score_page": spec.page_name,
                    **describe_file(spec.image),
                }
                for spec in specs
            ],
        },
        "detector": _detector_provenance(),
        "runtime": _runtime_provenance(orchestrator),
        "historical_baseline": HISTORICAL_BASELINE,
        "current": totals,
        "gates": gates,
        "focused_checks": focused_checks,
        "pages": page_reports,
        "generated_artifacts": _artifact_hashes(specs, run_dir),
    }
    report_path = run_dir / "phase_c_mmr_regression_report.json"
    write_json(report_path, report)

    print(json.dumps({"status": report["status"], "current": totals, "gates": gates}, indent=2))
    print(f"report: {report_path}")
    return report_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT / "logs/issue264_phase_c_mmr_regression",
    )
    parser.add_argument("--run-id", default="current_production_full68")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse complete Phase A/MMR artifacts under the selected run directory.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_path = run(args.output_root / args.run_id, resume=args.resume)
    report = load_json(report_path)
    return 0 if report.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
