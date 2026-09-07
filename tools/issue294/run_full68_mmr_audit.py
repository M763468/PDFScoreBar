#!/usr/bin/env python3
"""Audit Issue #294 full68 candidates with the production batched MMR stack.

The input is a completed ``issue294.full68_host.v1`` manifest.  Candidate
barlines/staff geometry come from the full68 downstream matrix, while the current
HOMR MMR support mask remains fixed from each page's fixed-support producer.
Both candidate-native and frozen-A geometry are evaluated for B and C.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import cv2
import torch

from src.measure_numbering.mmr import MMRClassifier, MMROCREngine, MMRProcessor
from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.measure_numbering.rapidocr_provider import (
    collect_rapidocr_providers,
    create_mmr_rapidocr,
    providers_include_cuda,
)
from src.measure_numbering.serialization import score_to_dict
from src.pipeline.mmr_support_reuse import build_mmr_support_data
from tools.issue264.run_phase_c_mmr_regression import (
    PAGE_033_ONE_BAR_KEY,
    build_page_specs,
    normalise_overrides,
    score_overrides,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = PROJECT_ROOT / "tools/mmr_training/models/mmr_classifier_best.pth"
MODES = ("candidate_native_geometry", "frozen_A_geometry")
LABELS = ("B_b377", "C_latest")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _compact(payload: Any) -> list[dict[str, int]]:
    compact = [
        {key: int(item[key]) for key in ("page", "system", "measure", "skip")}
        for item in normalise_overrides(payload)
    ]
    return sorted(
        compact,
        key=lambda item: (item["page"], item["system"], item["measure"], item["skip"]),
    )


def _report_page_key(page: dict[str, Any]) -> tuple[str, str]:
    image = Path(str(page["image"]))
    return image.parent.name, image.stem


def _load_matrix_pages(manifest: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    pages: dict[tuple[str, str], dict[str, Any]] = {}
    chunks = manifest.get("completed_chunks")
    if not isinstance(chunks, list):
        raise ValueError("Full68 manifest lacks completed_chunks")
    for chunk in chunks:
        if not isinstance(chunk, dict):
            raise ValueError("Malformed completed chunk")
        report_path = Path(str(chunk["matrix_report"]))
        report = _load_json(report_path)
        report_pages = report.get("pages") if isinstance(report, dict) else None
        if not isinstance(report_pages, list):
            raise ValueError(f"Matrix report lacks pages: {report_path}")
        for page in report_pages:
            if not isinstance(page, dict):
                raise ValueError(f"Malformed page in matrix report: {report_path}")
            key = _report_page_key(page)
            if key in pages:
                raise RuntimeError(f"Duplicate full68 matrix page: {key}")
            pages[key] = page
    if len(pages) != 68:
        raise RuntimeError(f"Expected 68 full68 matrix pages, got {len(pages)}")
    return pages


def _numbering_base(
    page: dict[str, Any],
    *,
    mode: str,
    label: str,
    page_number: int,
) -> dict[str, Any]:
    variant = page["modes"][mode]["variants"][label]
    image_path = Path(str(page["image"]))
    staff_mask = Path(str(variant["staff_mask"]))
    fixed_support = _load_json(Path(str(page["fixed_inputs"]["support_result"])))
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(image_path)
    height, width = image.shape[:2]
    score = MeasureNumberingPipeline().run_sequential(
        [
            {
                "barlines": variant["final_barlines"],
                "staff_mask": str(staff_mask),
                "image_size": (width, height),
                "page_number": page_number,
                "connector_mask_paths": {
                    "symbols": str(fixed_support["connector_symbols"]),
                    "brace_dot": str(fixed_support["connector_brace_dot"]),
                },
            }
        ]
    )
    return score_to_dict(score)


def _expected_for_spec(spec: Any) -> dict[str, Any]:
    fixture = spec.expected_fixture
    if fixture is None:
        return {"overrides": []}
    return _load_json(Path(fixture))


def _row_start_semantic_equal(expected: Any, actual: Any) -> bool:
    expected_items = {
        (int(item["page"]), int(item["system"]), int(item["measure"])): int(item["skip"])
        for item in normalise_overrides(expected)
        if int(item["measure"]) == 0
    }
    actual_items = {
        (int(item["page"]), int(item["system"]), int(item["measure"])): int(item["skip"])
        for item in normalise_overrides(actual)
        if int(item["measure"]) == 0
    }
    return actual_items == expected_items


def _score_condition(
    specs: list[Any],
    bases: list[dict[str, Any]],
    actual: list[dict[str, Any]],
) -> dict[str, Any]:
    if len(specs) != 68 or len(bases) != 68 or len(actual) != 68:
        raise RuntimeError("MMR full68 condition does not contain 68 pages")
    totals = {
        "pages": 68,
        "base_measures": 0,
        "expected": 0,
        "detected": 0,
        "matched_tp": 0,
        "missed_fn": 0,
        "skip_mismatch": 0,
        "unexpected_fp": 0,
        "zero_expected_pages": 0,
    }
    pages: list[dict[str, Any]] = []
    row_start_equal = True
    page_042_exact = False
    page_033_veto = True

    for spec, base, detected in zip(specs, bases, actual):
        expected = _expected_for_spec(spec)
        scoring = score_overrides(expected, detected)
        counts = scoring["counts"]
        systems = base["pages"][0]["systems"]
        total_measures = sum(len(system["measures"]) for system in systems)
        totals["base_measures"] += total_measures
        if counts["expected"] == 0:
            totals["zero_expected_pages"] += 1
        for key in ("expected", "detected", "matched_tp", "missed_fn", "skip_mismatch", "unexpected_fp"):
            totals[key] += int(counts[key])

        expected_compact = _compact(expected)
        actual_compact = _compact(detected)
        row_equal = _row_start_semantic_equal(expected, detected)
        row_start_equal = row_start_equal and row_equal
        if spec.page_id == "page_042":
            page_042_exact = expected_compact == actual_compact and len(expected_compact) == 5
        if spec.page_id == "page_033":
            page_033_veto = not any(
                (item["page"], item["system"], item["measure"]) == PAGE_033_ONE_BAR_KEY
                for item in actual_compact
            )
        pages.append(
            {
                "page_id": spec.page_id,
                "score": spec.score,
                "page_name": spec.page_name,
                "total_measures": total_measures,
                "system_staff_counts": [len(system["staves"]) for system in systems],
                "system_measure_counts": [len(system["measures"]) for system in systems],
                "expected": expected_compact,
                "actual": actual_compact,
                "scoring": scoring,
                "row_start_semantic_equal": row_equal,
            }
        )

    gates = {
        "page_count_68": totals["pages"] == 68,
        "expected_fixture_total_182": totals["expected"] == 182,
        "zero_expected_pages_scored": totals["zero_expected_pages"] == 16,
        "unexpected_fp_zero": totals["unexpected_fp"] == 0,
        "missed_fn_not_above_3": totals["missed_fn"] <= 3,
        "skip_mismatch_not_above_6": totals["skip_mismatch"] <= 6,
        "row_start_semantics": row_start_equal,
        "page_033_one_bar_veto": page_033_veto,
        "page_042_five_overrides": page_042_exact,
    }
    return {"totals": totals, "gates": gates, "pages": pages}


def _build_condition_inputs(
    *,
    specs: list[Any],
    matrix_pages: dict[tuple[str, str], dict[str, Any]],
    mode: str,
    label: str,
) -> tuple[list[dict[str, Any]], list[Path], list[dict[str, Any]]]:
    bases: list[dict[str, Any]] = []
    images: list[Path] = []
    support: list[dict[str, Any]] = []
    for spec in specs:
        key = (str(spec.score), str(spec.page_name))
        page = matrix_pages.get(key)
        if page is None:
            raise RuntimeError(f"Full68 matrix lacks canonical page {spec.page_id}: {key}")
        base = _numbering_base(
            page,
            mode=mode,
            label=label,
            page_number=int(spec.global_index) + 1,
        )
        fixed_support = _load_json(Path(str(page["fixed_inputs"]["support_result"])))
        support_mask = Path(str(fixed_support["current_homr_staff_mask"]))
        bases.append(base)
        images.append(Path(str(page["image"])))
        support.append(build_mmr_support_data(base, support_mask))
    return bases, images, support


def run(manifest_path: Path, model_path: Path) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    if not isinstance(manifest, dict) or manifest.get("status") != "completed":
        raise ValueError(f"Full68 manifest is not completed: {manifest_path}")
    if manifest.get("schema_version") != "issue294.full68_host.v1":
        raise ValueError(f"Unexpected full68 manifest schema: {manifest.get('schema_version')}")
    matrix_pages = _load_matrix_pages(manifest)
    specs = build_page_specs()
    if len(specs) != 68:
        raise RuntimeError(f"Expected 68 canonical specs, got {len(specs)}")
    if not model_path.is_file():
        raise FileNotFoundError(model_path)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("Issue #294 full68 MMR audit requires CUDA")
    classifier = MMRClassifier(model_path, device)
    provider = create_mmr_rapidocr("cuda")
    providers = collect_rapidocr_providers(provider)
    if not providers_include_cuda(providers):
        raise RuntimeError(f"RapidOCR did not activate CUDA: {providers}")
    ocr_engine = MMROCREngine(ocr_engine=provider)

    conditions: dict[str, Any] = {}
    actual_by_mode_label: dict[tuple[str, str], list[dict[str, Any]]] = {}
    started_all = time.perf_counter()
    for mode in MODES:
        for label in LABELS:
            bases, images, support = _build_condition_inputs(
                specs=specs,
                matrix_pages=matrix_pages,
                mode=mode,
                label=label,
            )
            processor = MMRProcessor(
                model_path=model_path,
                device=device,
                classifier=classifier,
                ocr_engine=ocr_engine,
            )
            started = time.perf_counter()
            actual = processor.process_pages(bases, images, support_data=support)
            elapsed = time.perf_counter() - started
            key = (mode, label)
            actual_by_mode_label[key] = actual
            scored = _score_condition(specs, bases, actual)
            conditions[f"{mode}:{label}"] = {
                **scored,
                "elapsed_sec": elapsed,
                "support_stats": dict(processor.support_stats),
            }

    comparisons: dict[str, Any] = {}
    for mode in MODES:
        b = actual_by_mode_label[(mode, "B_b377")]
        c = actual_by_mode_label[(mode, "C_latest")]
        per_page = [_compact(left) == _compact(right) for left, right in zip(b, c)]
        comparisons[f"{mode}:B_vs_C"] = {
            "all_pages_exact": all(per_page),
            "different_pages": [
                specs[index].page_id for index, equal in enumerate(per_page) if not equal
            ],
        }

    overall_gates = {
        "all_condition_acceptance_gates": all(
            all(condition["gates"].values()) for condition in conditions.values()
        ),
        "B_C_candidate_native_mmr_exact": comparisons[
            "candidate_native_geometry:B_vs_C"
        ]["all_pages_exact"],
        "B_C_frozen_A_mmr_exact": comparisons["frozen_A_geometry:B_vs_C"][
            "all_pages_exact"
        ],
    }
    return {
        "schema_version": "issue294.full68_mmr_audit.v1",
        "status": "completed",
        "full68_manifest": str(manifest_path.resolve()),
        "model": str(model_path.resolve()),
        "runtime": {
            "device": str(device),
            "rapidocr_providers": providers,
            "elapsed_sec": time.perf_counter() - started_all,
        },
        "conditions": conditions,
        "comparisons": comparisons,
        "gates": overall_gates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full68-manifest", type=Path, required=True)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = run(args.full68_manifest, args.model)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps({"status": payload["status"], "gates": payload["gates"]}, ensure_ascii=False))
    return 0 if all(payload["gates"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
