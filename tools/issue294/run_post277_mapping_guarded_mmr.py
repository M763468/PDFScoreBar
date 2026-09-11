#!/usr/bin/env python3
"""Re-evaluate Issue #294 mapping-guarded candidates with merged #277 MMR.

The focused mode is intentionally retained-artifact-first: detector/HOMR/SR/OMR/CNN
outputs from a completed Issue #294 full68 manifest are reused, numbering is
reconstructed with either the production pipeline (A) or the experiment-only
mapping-guarded grouping candidate (B/C), and only current MMR CNN/OCR inference is
rerun. Expected MMR events are spatially rebased from the accepted Issue #264
physical-GT report onto each reconstructed geometry before scoring.

Use ``--full68 --expect-production-reference --require-manifest-head`` after a fresh
post-#277 full68 run. That mode verifies that the production A control reproduces the
merged #277 reference and then requires B/C to be no worse on semantic MMR metrics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping

import torch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.measure_numbering.mmr import MMRClassifier, MMROCREngine, MMRProcessor
from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.measure_numbering.rapidocr_provider import (
    collect_rapidocr_providers,
    create_mmr_rapidocr,
    providers_include_cuda,
)
from src.measure_numbering.serialization import score_to_dict
from src.pipeline.mmr_support_reuse import build_mmr_support_data
from tools.issue264.run_phase_c_mmr_regression import build_page_specs
from tools.issue294._mapping_guarded_candidate_mmr_rescore import (
    _accepted_rebase_pages,
    _rebase_accepted_expected_to_candidate,
    _run_numbering_score,
)
from tools.issue294.evaluate_mapping_guarded_connector_positive_candidate import (
    MappingGuardedConnectorPositivePipeline,
)
from tools.issue294.rescore_full68_mmr_audit import (
    PAGE_033_ONE_BAR_KEY,
    _compact,
    _load_json,
    _load_matrix_pages,
    _resolve_project_path,
    _row_start_equal,
    _score_overrides,
)

REQUIRED_DEVELOP_COMMIT = "edc17ee08de6694827c67d4ab8b30c2adc1f05e3"
DEFAULT_MODEL = PROJECT_ROOT / "tools/mmr_training/models/mmr_classifier_best.pth"
DEFAULT_MANIFEST = PROJECT_ROOT / "logs/issue294/issue294_full68_refresh_02/full68_host.json"
DEFAULT_ACCEPTED_REBASE = Path(
    "/home/masaki_muramatsu/issue264_phase_c_rescore/"
    "phase_c_mmr_geometry_rebased_score_report.json"
)
FOCUSED_PAGE_IDS = (
    "page_001",
    "page_002",
    "page_012",
    "page_013",
    "page_022",
    "page_025",
    "page_033",
    "page_034",
    "page_035",
    "page_042",
    "page_045",
    "page_052",
    "page_055",
    "page_066",
    "page_067",
)
PRODUCTION_REFERENCE = {
    "expected": 177,
    "detected": 175,
    "matched_tp": 171,
    "missed_fn": 2,
    "skip_mismatch": 4,
    "unexpected_fp": 0,
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _capture(command: list[str]) -> str:
    return subprocess.check_output(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        stderr=subprocess.PIPE,
    ).strip()


def _git_provenance() -> dict[str, str]:
    head = _capture(["git", "rev-parse", "HEAD"])
    branch = _capture(["git", "branch", "--show-current"])
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", REQUIRED_DEVELOP_COMMIT, head],
        cwd=PROJECT_ROOT,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Execution HEAD {head} does not contain merged develop {REQUIRED_DEVELOP_COMMIT}"
        )
    return {
        "head": head,
        "branch": branch or "<detached>",
        "required_develop_commit": REQUIRED_DEVELOP_COMMIT,
    }


def focused_page_ids() -> tuple[str, ...]:
    return FOCUSED_PAGE_IDS


def _semantic_shape(numbering: Mapping[str, Any]) -> dict[str, Any]:
    pages = numbering.get("pages")
    if not isinstance(pages, list) or len(pages) != 1:
        raise ValueError("Numbering payload must contain exactly one page")
    systems = pages[0].get("systems")
    if not isinstance(systems, list):
        raise ValueError("Numbering payload lacks systems")
    return {
        "total_measures": sum(len(system.get("measures", [])) for system in systems),
        "system_staff_counts": [len(system.get("staves", [])) for system in systems],
        "system_measure_counts": [len(system.get("measures", [])) for system in systems],
        "measure_numbers": [
            [int(measure.get("number", 0)) for measure in system.get("measures", [])]
            for system in systems
        ],
    }


def _manifest_checkout_head(manifest: Mapping[str, Any]) -> str | None:
    checkout = manifest.get("checkout")
    if isinstance(checkout, Mapping) and isinstance(checkout.get("head"), str):
        return str(checkout["head"])
    return None


def _page_error_count(page: Mapping[str, Any]) -> int:
    counts = page["scoring"]["counts"]
    return int(counts["missed_fn"]) + int(counts["skip_mismatch"]) + int(
        counts["unexpected_fp"]
    )


def candidate_not_worse(
    baseline_page: Mapping[str, Any], candidate_page: Mapping[str, Any]
) -> bool:
    baseline_counts = baseline_page["scoring"]["counts"]
    candidate_counts = candidate_page["scoring"]["counts"]
    return bool(
        int(candidate_counts["unexpected_fp"]) <= int(baseline_counts["unexpected_fp"])
        and _page_error_count(candidate_page) <= _page_error_count(baseline_page)
        and int(candidate_counts["matched_tp"]) >= int(baseline_counts["matched_tp"])
    )


def production_reference_gates(totals: Mapping[str, Any]) -> dict[str, bool]:
    return {
        key: int(totals.get(key, -1)) == expected
        for key, expected in PRODUCTION_REFERENCE.items()
    }


def _build_variant_inputs(
    *,
    specs: list[Any],
    matrix_pages: Mapping[tuple[str, str], Mapping[str, Any]],
    label: str,
    pipeline_factory: Callable[[], Any],
) -> tuple[list[dict[str, Any]], list[Path], list[dict[str, Any]], list[str]]:
    bases: list[dict[str, Any]] = []
    images: list[Path] = []
    supports: list[dict[str, Any]] = []
    mapping_modes: list[str] = []

    for spec in specs:
        key = (str(spec.score), str(spec.page_name))
        matrix_page = matrix_pages.get(key)
        if matrix_page is None:
            raise RuntimeError(f"Full68 matrix lacks {spec.page_id}: {key}")
        pipeline = pipeline_factory()
        score = _run_numbering_score(
            matrix_page,
            mode="candidate_native_geometry",
            label=label,
            page_number=int(spec.global_index) + 1,
            pipeline=pipeline,
        )
        base = score_to_dict(score)
        fixed_support = _load_json(
            _resolve_project_path(str(matrix_page["fixed_inputs"]["support_result"]))
        )
        support_mask = _resolve_project_path(str(fixed_support["current_homr_staff_mask"]))
        image = _resolve_project_path(str(matrix_page["image"]))
        bases.append(base)
        images.append(image)
        supports.append(build_mmr_support_data(base, support_mask))
        mapping_modes.append(str(getattr(pipeline, "last_evidence_geometry_mode", "production")))
    return bases, images, supports, mapping_modes


def _score_variant(
    *,
    name: str,
    specs: list[Any],
    bases: list[dict[str, Any]],
    actual: list[dict[str, Any]],
    mapping_modes: list[str],
    accepted_pages: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    totals = {
        "pages": len(specs),
        "accepted_source_fixture_items": 0,
        "expected": 0,
        "detected": 0,
        "matched_tp": 0,
        "missed_fn": 0,
        "skip_mismatch": 0,
        "unexpected_fp": 0,
        "zero_expected_pages": 0,
        "zero_expected_page_detections": 0,
    }
    pages: list[dict[str, Any]] = []
    row_start_equal = True
    page_033_veto = True
    page_042_exact = True

    for spec, base, detected, mapping_mode in zip(specs, bases, actual, mapping_modes):
        page_id = str(spec.page_id)
        global_index = int(spec.global_index)
        accepted_page = accepted_pages.get(page_id)
        if accepted_page is None:
            raise ValueError(f"Accepted Issue #264 report lacks {page_id}")
        expected, expected_mappings = _rebase_accepted_expected_to_candidate(
            accepted_page,
            base,
            global_page_index=global_index,
        )
        scoring = _score_overrides(expected, detected)
        counts = scoring["counts"]
        totals["accepted_source_fixture_items"] += len(expected_mappings)
        for key in (
            "expected",
            "detected",
            "matched_tp",
            "missed_fn",
            "skip_mismatch",
            "unexpected_fp",
        ):
            totals[key] += int(counts[key])
        if int(counts["expected"]) == 0:
            totals["zero_expected_pages"] += 1
            totals["zero_expected_page_detections"] += int(counts["detected"])

        expected_compact = _compact(expected)
        actual_compact = _compact(detected)
        row_equal = _row_start_equal(expected, detected)
        row_start_equal = row_start_equal and row_equal
        if page_id == "page_033":
            page_033_veto = not any(
                (item["page"], item["system"], item["measure"]) == PAGE_033_ONE_BAR_KEY
                for item in actual_compact
            )
        if page_id == "page_042":
            page_042_exact = expected_compact == actual_compact and len(expected_compact) == 5

        pages.append(
            {
                "page_id": page_id,
                "score": str(spec.score),
                "page_name": str(spec.page_name),
                "mapping_mode": mapping_mode,
                "numbering_shape": _semantic_shape(base),
                "expected": expected_compact,
                "actual": actual_compact,
                "scoring": scoring,
                "row_start_semantic_equal": row_equal,
            }
        )

    return {
        "name": name,
        "totals": totals,
        "pages": pages,
        "gates": {
            "row_start_semantics": row_start_equal,
            "page_033_one_bar_veto": page_033_veto,
            "page_042_five_overrides": page_042_exact,
            "unexpected_fp_zero": int(totals["unexpected_fp"]) == 0,
            "zero_expected_page_detections_zero": int(totals["zero_expected_page_detections"])
            == 0,
        },
    }


def _by_page(variant: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(page["page_id"]): page for page in variant["pages"]}


def _candidate_gates(
    baseline: Mapping[str, Any], candidate: Mapping[str, Any], *, full68: bool
) -> dict[str, bool]:
    baseline_pages = _by_page(baseline)
    candidate_pages = _by_page(candidate)
    not_worse = all(
        candidate_not_worse(baseline_pages[page_id], candidate_pages[page_id])
        for page_id in baseline_pages
    )
    gates = {
        "all_pages_not_worse_than_production": not_worse,
        "unexpected_fp_not_above_production": int(candidate["totals"]["unexpected_fp"])
        <= int(baseline["totals"]["unexpected_fp"]),
        "missed_fn_not_above_production": int(candidate["totals"]["missed_fn"])
        <= int(baseline["totals"]["missed_fn"]),
        "skip_mismatch_not_above_production": int(candidate["totals"]["skip_mismatch"])
        <= int(baseline["totals"]["skip_mismatch"]),
        "matched_tp_not_below_production": int(candidate["totals"]["matched_tp"])
        >= int(baseline["totals"]["matched_tp"]),
        **{f"candidate_{key}": bool(value) for key, value in candidate["gates"].items()},
    }
    if full68:
        gates.update(
            {
                "expected_177": int(candidate["totals"]["expected"]) == 177,
                "zero_expected_pages_16": int(candidate["totals"]["zero_expected_pages"])
                == 16,
            }
        )
    return gates


def run(
    *,
    manifest_path: Path,
    accepted_rebase_report: Path,
    model_path: Path,
    page_ids: list[str] | None,
    full68: bool,
    expect_production_reference: bool,
    require_manifest_head: bool,
) -> dict[str, Any]:
    git = _git_provenance()
    manifest = _load_json(manifest_path)
    if not isinstance(manifest, Mapping) or manifest.get("status") != "completed":
        raise ValueError(f"Full68 manifest is not completed: {manifest_path}")
    if int(manifest.get("completed_page_count", 0)) != 68:
        raise ValueError("Full68 manifest does not contain 68 completed pages")
    if require_manifest_head and _manifest_checkout_head(manifest) != git["head"]:
        raise RuntimeError(
            "Fresh full68 manifest HEAD does not match execution HEAD: "
            f"manifest={_manifest_checkout_head(manifest)} execution={git['head']}"
        )
    if not model_path.is_file():
        raise FileNotFoundError(model_path)

    matrix_pages = _load_matrix_pages(manifest)
    accepted_pages, accepted_provenance = _accepted_rebase_pages(accepted_rebase_report)
    all_specs = build_page_specs()
    by_id = {str(spec.page_id): spec for spec in all_specs}
    if set(by_id) != {f"page_{index:03d}" for index in range(1, 69)}:
        raise RuntimeError("Canonical page specs are not page_001..page_068")
    selected_ids = (
        [f"page_{index:03d}" for index in range(1, 69)]
        if full68
        else list(page_ids or FOCUSED_PAGE_IDS)
    )
    missing = [page_id for page_id in selected_ids if page_id not in by_id]
    if missing:
        raise ValueError(f"Unknown page IDs: {missing}")
    specs = [by_id[page_id] for page_id in selected_ids]

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("Post-#277 MMR gate requires CUDA")
    classifier = MMRClassifier(model_path, device)
    rapidocr = create_mmr_rapidocr("cuda")
    providers = collect_rapidocr_providers(rapidocr)
    if not providers_include_cuda(providers):
        raise RuntimeError(f"RapidOCR did not activate CUDA: {providers}")
    ocr_engine = MMROCREngine(ocr_engine=rapidocr)

    variants: dict[str, Any] = {}
    raw_actual: dict[str, list[dict[str, Any]]] = {}
    variant_specs = (
        ("A_production", "A_pinned", MeasureNumberingPipeline),
        ("B_b377_mapping_guarded", "B_b377", MappingGuardedConnectorPositivePipeline),
        ("C_latest_mapping_guarded", "C_latest", MappingGuardedConnectorPositivePipeline),
    )
    started_all = time.perf_counter()
    for name, label, factory in variant_specs:
        bases, images, supports, mapping_modes = _build_variant_inputs(
            specs=specs,
            matrix_pages=matrix_pages,
            label=label,
            pipeline_factory=factory,
        )
        processor = MMRProcessor(
            model_path=model_path,
            device=device,
            classifier=classifier,
            ocr_engine=ocr_engine,
        )
        started = time.perf_counter()
        actual = processor.process_pages(bases, images, support_data=supports)
        elapsed = time.perf_counter() - started
        scored = _score_variant(
            name=name,
            specs=specs,
            bases=bases,
            actual=actual,
            mapping_modes=mapping_modes,
            accepted_pages=accepted_pages,
        )
        scored["elapsed_sec"] = elapsed
        scored["support_stats"] = dict(processor.support_stats)
        variants[name] = scored
        raw_actual[name] = actual

    baseline = variants["A_production"]
    b = variants["B_b377_mapping_guarded"]
    c = variants["C_latest_mapping_guarded"]
    b_pages = _by_page(b)
    c_pages = _by_page(c)
    b_c_actual_exact = all(
        b_pages[page_id]["actual"] == c_pages[page_id]["actual"] for page_id in selected_ids
    )
    b_c_shape_exact = all(
        b_pages[page_id]["numbering_shape"] == c_pages[page_id]["numbering_shape"]
        for page_id in selected_ids
    )

    gates: dict[str, bool] = {
        "B_C_actual_exact_selected_pages": b_c_actual_exact,
        "B_C_numbering_shape_exact_selected_pages": b_c_shape_exact,
        **{
            f"B_{key}": value
            for key, value in _candidate_gates(baseline, b, full68=full68).items()
        },
        **{
            f"C_{key}": value
            for key, value in _candidate_gates(baseline, c, full68=full68).items()
        },
    }
    if "page_052" in selected_ids:
        gates["page_052_B_C_shape_exact"] = (
            b_pages["page_052"]["numbering_shape"]
            == c_pages["page_052"]["numbering_shape"]
        )
    if "page_067" in selected_ids:
        gates["page_067_B_C_shape_exact"] = (
            b_pages["page_067"]["numbering_shape"]
            == c_pages["page_067"]["numbering_shape"]
        )
    if expect_production_reference:
        for key, value in production_reference_gates(baseline["totals"]).items():
            gates[f"A_production_reference_{key}"] = value

    payload = {
        "schema_version": "issue294.post277_mapping_guarded_mmr.v1",
        "status": "completed",
        "mode": "full68" if full68 else "focused",
        "execution_contract": {
            "retained_or_fresh_upstream_manifest": str(manifest_path.resolve()),
            "detector_reexecuted_by_this_gate": False,
            "homr_reexecuted_by_this_gate": False,
            "sr_reexecuted_by_this_gate": False,
            "omr_reexecuted_by_this_gate": False,
            "cnn_reexecuted_by_this_gate": False,
            "numbering_reconstructed": True,
            "mapping_guarded_grouping_for_B_C": True,
            "production_grouping_for_A": True,
            "mmr_cnn_ocr_reexecuted": True,
            "frozen_A_geometry_used_as_production_signal": False,
            "page_specific_correction": False,
            "threshold_tuning": False,
        },
        "git": git,
        "manifest": {
            "path": str(manifest_path.resolve()),
            "sha256": _sha256(manifest_path),
            "checkout_head": _manifest_checkout_head(manifest),
            "require_manifest_head": require_manifest_head,
        },
        "accepted_issue264_rebase": accepted_provenance,
        "model": str(model_path.resolve()),
        "runtime": {
            "device": str(device),
            "rapidocr_providers": providers,
            "elapsed_sec": time.perf_counter() - started_all,
        },
        "selected_pages": selected_ids,
        "production_reference_expected": (
            PRODUCTION_REFERENCE if expect_production_reference else None
        ),
        "variants": variants,
        "gates": gates,
        "all_gates_pass": all(gates.values()),
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full68-manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--accepted-rebase-report", type=Path, default=DEFAULT_ACCEPTED_REBASE)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--page", action="append", dest="pages")
    parser.add_argument("--full68", action="store_true")
    parser.add_argument("--expect-production-reference", action="store_true")
    parser.add_argument("--require-manifest-head", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = run(
            manifest_path=args.full68_manifest,
            accepted_rebase_report=args.accepted_rebase_report,
            model_path=args.model,
            page_ids=args.pages,
            full68=args.full68,
            expect_production_reference=args.expect_production_reference,
            require_manifest_head=args.require_manifest_head,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
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
                "mode": payload["mode"],
                "selected_page_count": len(payload["selected_pages"]),
                "all_gates_pass": payload["all_gates_pass"],
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0 if payload["all_gates_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
