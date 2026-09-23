#!/usr/bin/env python3
"""Fresh downstream semantic replay for Issue #372.

This runner compares three retained detector accepted sets under ONE current
downstream geometry/MMR contract:

- current_control: current maintained-HOMR production detector output;
- late_raw_x4: Issue #372 late-raw x4 compatibility counterfactual;
- accepted_d27: Issue #296 accepted D27 barline set reconstructed from its
  authoritative acceptance deltas over the retained Issue #274 producer output.

No detector, HOMR, SR, or OMR-DLN inference is run.

For each variant the runner freshly executes:
1. current MeasureNumberingPipeline Phase-A construction using the Issue #43
   retained current staff mask;
2. current MMR support mapping using the Issue #43 retained current-x4 HOMR
   staff mask;
3. current MMR classifier/OCR;
4. final numbering, both page-local (start=1) and score-continuation views.

The primary comparison is late_raw_x4 vs accepted_d27. Exact measure bbox drift
is diagnostic. System structure, per-system physical measure counts, MMR skip
effects, and serialized measure-number sequences are the semantic contract.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cv2
import torch

from experiments.issue372.run_retained_x4_gap_counterfactual import (
    _host_path,
    _load_json,
    _source_worker_result,
    _write_json,
)
from src.measure_numbering.mmr import MMRClassifier, MMROCREngine
from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.measure_numbering.types import Score
from src.pipeline.mmr_support_reuse import build_mmr_support_data
from src.pipeline.steps.numbering import rebase_mmr_overrides_to_page_local, run_mmr_batch
from src.pipeline.utils.io import score_to_dict
from tools.issue120 import eval_full68_from_intermediates as full68_eval

EXPECTED_D27_CLEAN = {
    "pages": 68,
    "gt": 3567,
    "tp": 3565,
    "hard_fp": 1,
    "fn": 2,
    "soft": 44,
}
EXPECTED_D27_PRED = 3610
EXPECTED_D27_PRODUCER_PRED = 3599
EXPECTED_PAGES = 68

Box = tuple[int, int, int, int]


def _norm_box(raw: Sequence[Any]) -> Box:
    return tuple(int(round(float(v))) for v in raw[:4])  # type: ignore[return-value]


def _extract_boxes(payload: Any) -> list[Box]:
    records = payload.get("predictions", []) if isinstance(payload, Mapping) else payload
    if not isinstance(records, list):
        raise ValueError("barline payload must be list-like")
    boxes: list[Box] = []
    for item in records:
        if isinstance(item, Mapping):
            raw = None
            for key in ("bbox", "barline_location", "orig_bbox", "pred_bbox"):
                if key in item:
                    raw = item[key]
                    break
        else:
            raw = item
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)) and len(raw) >= 4:
            boxes.append(_norm_box(raw))
    return boxes


def _find_page_file(root: Path, score: str, page: str, filename: str) -> Path:
    record = full68_eval.PageRecord(score=score, page=page)
    path = full68_eval.find_page_file(root, record, filename)
    if path is None or not path.is_file():
        raise FileNotFoundError(f"{score}/{page}: {filename} under {root}")
    return path


def apply_acceptance_deltas(
    control: Sequence[Box],
    deltas: Sequence[Mapping[str, Any]],
) -> list[Box]:
    """Reconstruct accepted D27 boxes from Issue #274 producer control + deltas."""
    removed = {
        _norm_box(row["bbox"])
        for row in deltas
        if row.get("control_accept") is True
        and row.get("clean_accept") is False
        and isinstance(row.get("bbox"), Sequence)
    }
    result = [box for box in control if box not in removed]
    for row in deltas:
        if row.get("control_accept") is False and row.get("clean_accept") is True:
            raw = row.get("bbox")
            if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)) and len(raw) >= 4:
                result.append(_norm_box(raw))
    # Match the authoritative Issue #296 replay contract: preserve the producer
    # list and apply only the recorded acceptance removals/additions. Do not
    # silently deduplicate detector output here.
    return result


def _d27_deltas_by_page(summary: Mapping[str, Any]) -> dict[tuple[str, str], list[Mapping[str, Any]]]:
    rows = summary.get("acceptance_deltas")
    if not isinstance(rows, list):
        raise ValueError("D27 summary lacks acceptance_deltas")
    result: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        result[(str(row["score"]), str(row["page"]))].append(row)
    return dict(result)


def _d27_producer_final(d27_run_root: Path, score: str, page: str) -> Path:
    path = (
        d27_run_root
        / "runs"
        / score
        / "intermediate"
        / "dense_full_pipeline_route"
        / "dense_candidate_reconstruction"
        / "probe_rescue_candidates"
        / f"eval2_{score}_{page}"
        / "pipeline2_no_peak_filtered_cnn.json"
    )
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _inventory_records(path: Path) -> dict[str, Mapping[str, Any]]:
    payload = _load_json(path)
    if not isinstance(payload, Mapping) or not isinstance(payload.get("records"), list):
        raise ValueError(f"Invalid inventory: {path}")
    result: dict[str, Mapping[str, Any]] = {}
    for row in payload["records"]:
        if not isinstance(row, Mapping):
            raise ValueError(f"Invalid inventory record: {row!r}")
        result[str(row["page"])] = row
    return result


def _staff_mask_from_support_payload(
    payload: Mapping[str, Any],
    *,
    issue43_repo_root: Path,
) -> Path | None:
    """Resolve the current-x4 HOMR staff mask from supported retained schemas."""
    for key in ("current_homr_staff_mask", "staff_mask"):
        raw = payload.get(key)
        if not raw:
            continue
        path = _host_path(str(raw), issue43_repo_root)
        if path.is_file():
            return path
    return None


def _current_homr_staff_mask(
    record: Mapping[str, Any],
    *,
    score: str,
    page: str,
    issue43_repo_root: Path,
) -> Path:
    """Resolve retained current-x4 staff geometry across source-worker schemas.

    The maintained-HOMR adoption commit intentionally kept the top-level
    verified source-page result small: it forwarded current_sr_detection/current_omr
    but did not forward current_homr_staff_mask. The child current-support result
    under sibling current_support/<score>/<page>/result.json retained the full
    connector-semantic bundle, including the staff mask.

    Newer source-page schemas may forward the mask directly, so prefer that when
    present and fall back to the child result. As a final provenance-preserving
    fallback, derive the staff-mask sibling from current_sr_detection; both files
    are emitted by the same current_homr_worker batch directory.
    """
    hybrid_raw = record.get("hybrid_predictions")
    if not hybrid_raw:
        raise ValueError(f"{score}/{page}: inventory lacks hybrid_predictions")
    hybrid = _host_path(str(hybrid_raw), issue43_repo_root)
    if not hybrid.is_file():
        raise FileNotFoundError(hybrid)

    source_result = _source_worker_result(hybrid, score=score, page=page)
    source_payload = _load_json(source_result)
    if not isinstance(source_payload, Mapping):
        raise ValueError(f"{score}/{page}: invalid source-worker result: {source_result}")

    direct = _staff_mask_from_support_payload(
        source_payload,
        issue43_repo_root=issue43_repo_root,
    )
    if direct is not None:
        return direct

    hybrid_root = hybrid.parent.parent
    child_result = hybrid_root / "current_support" / score / page / "result.json"
    if child_result.is_file():
        child_payload = _load_json(child_result)
        if not isinstance(child_payload, Mapping):
            raise ValueError(
                f"{score}/{page}: invalid current-support result: {child_result}"
            )
        if child_payload.get("status") != "completed":
            raise ValueError(
                f"{score}/{page}: incomplete current-support result: {child_result}"
            )
        if child_payload.get("historical_detector_artifact_runtime_input") is not False:
            raise ValueError(
                f"{score}/{page}: current-support result used historical artifacts"
            )
        child_mask = _staff_mask_from_support_payload(
            child_payload,
            issue43_repo_root=issue43_repo_root,
        )
        if child_mask is not None:
            return child_mask

    detection_raw = source_payload.get("current_sr_detection")
    if detection_raw:
        detection = _host_path(str(detection_raw), issue43_repo_root)
        expected = detection.with_name(
            detection.name.replace("_detections.json", "_staff_mask.png")
        )
        if expected != detection and expected.is_file():
            return expected

    raise ValueError(
        f"{score}/{page}: unable to resolve retained current-x4 HOMR staff mask; "
        f"source_result={source_result} child_result={child_result}"
    )


def _score_to_payload(
    pipeline: MeasureNumberingPipeline,
    *,
    boxes: Sequence[Box],
    staff_mask: Path,
    image: Any,
    page_number: int,
    start_number: int,
    overrides: list[dict[str, Any]] | None,
) -> tuple[dict[str, Any], int]:
    h, w = image.shape[:2]
    page_obj = pipeline.process_page(
        [list(box) for box in boxes],
        staff_mask,
        (w, h),
        page_number=page_number,
        assume_one_staff_per_system=False,
        image=image,
    )
    score = Score()
    score.pages.append(page_obj)
    next_number = pipeline.numberer.number_score(
        score,
        start_number=start_number,
        overrides=overrides,
    )
    return score_to_dict(score), int(next_number)


def _logical_signature(payload: Mapping[str, Any]) -> dict[str, Any]:
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 1 or not isinstance(pages[0], Mapping):
        raise ValueError("Expected one-page numbering payload")
    page = pages[0]
    systems = []
    for system in page.get("systems", []):
        if not isinstance(system, Mapping):
            continue
        measures = [m for m in system.get("measures", []) if isinstance(m, Mapping)]
        systems.append(
            {
                "measure_count": len(measures),
                "numbers": [
                    m.get("number", m.get("measure_number"))
                    for m in measures
                ],
            }
        )
    return {
        "system_count": len(systems),
        "empty_system_count": len(page.get("empty_systems", []) or []),
        "systems": systems,
    }


def _geometry_signature(payload: Mapping[str, Any]) -> list[list[Any]]:
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 1 or not isinstance(pages[0], Mapping):
        raise ValueError("Expected one-page numbering payload")
    result: list[list[Any]] = []
    for system in pages[0].get("systems", []):
        if not isinstance(system, Mapping):
            continue
        result.append(
            [
                measure.get("bbox")
                for measure in system.get("measures", [])
                if isinstance(measure, Mapping)
            ]
        )
    return result


def _override_signature(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("measure_overrides", [])
    if not isinstance(rows, list):
        return []
    normalized = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        normalized.append(
            {
                "page": row.get("page"),
                "system": row.get("system"),
                "measure": row.get("measure"),
                "skip": row.get("skip"),
            }
        )
    return normalized


def _comparison(
    left_rows: Mapping[tuple[str, str], Mapping[str, Any]],
    right_rows: Mapping[tuple[str, str], Mapping[str, Any]],
) -> dict[str, Any]:
    keys = sorted(set(left_rows) | set(right_rows))
    logical_changed = []
    geometry_only = []
    mmr_changed = []
    exact = 0
    for key in keys:
        left = left_rows.get(key)
        right = right_rows.get(key)
        if left is None or right is None:
            logical_changed.append(
                {"score": key[0], "page": key[1], "reason": "missing_variant_page"}
            )
            continue
        local_equal = left["local_logical"] == right["local_logical"]
        continued_equal = left["continued_logical"] == right["continued_logical"]
        continuation_state_equal = (
            left["continued_start_number"] == right["continued_start_number"]
            and left["continued_next_number"] == right["continued_next_number"]
        )
        logical_equal = local_equal and continued_equal and continuation_state_equal
        geometry_equal = left["local_geometry"] == right["local_geometry"]
        override_equal = left["mmr_overrides"] == right["mmr_overrides"]
        if not override_equal:
            mmr_changed.append(
                {
                    "score": key[0],
                    "page": key[1],
                    "left": left["mmr_overrides"],
                    "right": right["mmr_overrides"],
                }
            )
        if logical_equal and geometry_equal:
            exact += 1
            continue
        payload = {
            "score": key[0],
            "page": key[1],
            "local_logical_equal": local_equal,
            "continued_logical_equal": continued_equal,
            "continuation_state_equal": continuation_state_equal,
            "geometry_equal": geometry_equal,
            "left": {
                "local": left["local_logical"],
                "continued": left["continued_logical"],
                "start_number": left["continued_start_number"],
                "next_number": left["continued_next_number"],
            },
            "right": {
                "local": right["local_logical"],
                "continued": right["continued_logical"],
                "start_number": right["continued_start_number"],
                "next_number": right["continued_next_number"],
            },
        }
        if logical_equal:
            geometry_only.append(payload)
        else:
            logical_changed.append(payload)
    return {
        "logical_match": not logical_changed,
        "logical_changed_page_count": len(logical_changed),
        "geometry_only_changed_page_count": len(geometry_only),
        "exactly_unchanged_page_count": exact,
        "mmr_override_changed_page_count": len(mmr_changed),
        "logical_changed_pages": logical_changed,
        "geometry_only_changed_pages": geometry_only,
        "mmr_override_changed_pages": mmr_changed,
    }


def _variant_barlines(
    *,
    label: str,
    x4_run_root: Path,
    late_run_root: Path,
    d27_run_root: Path,
    d27_deltas: Mapping[tuple[str, str], Sequence[Mapping[str, Any]]],
) -> tuple[dict[tuple[str, str], list[Box]], int]:
    rows: dict[tuple[str, str], list[Box]] = {}
    total = 0
    if label == "current_control":
        source_root = x4_run_root / "control" / "aggregate_probe_output"
    elif label == "late_raw_x4":
        source_root = (
            late_run_root
            / "late_raw_route"
            / "dense_candidate_reconstruction"
            / "probe_rescue_candidates"
        )
    else:
        source_root = Path()

    for score, pages in full68_eval.SCORES.items():
        for page in pages:
            key = (score, page)
            if label in {"current_control", "late_raw_x4"}:
                path = _find_page_file(
                    source_root,
                    score,
                    page,
                    "pipeline2_no_peak_filtered_cnn.json",
                )
                boxes = _extract_boxes(_load_json(path))
            elif label == "accepted_d27":
                producer = _d27_producer_final(d27_run_root, score, page)
                control = _extract_boxes(_load_json(producer))
                boxes = apply_acceptance_deltas(control, d27_deltas.get(key, []))
            else:
                raise ValueError(label)
            rows[key] = boxes
            total += len(boxes)
    return rows, total


def _prepare_runtime(
    *,
    x4_run_root: Path,
    issue43_repo_root: Path,
    image_root: Path,
) -> dict[tuple[str, str], dict[str, Any]]:
    runtime: dict[tuple[str, str], dict[str, Any]] = {}
    global_index = 0
    for score, pages in full68_eval.SCORES.items():
        inv_path = x4_run_root / "inventories" / "control" / f"{score}.json"
        inventory = _inventory_records(inv_path)
        if set(inventory) != set(pages):
            raise ValueError(f"{score}: inventory pages differ from full68 manifest")
        for score_index, page in enumerate(pages):
            record = inventory[page]
            image = image_root / score / f"{page}.png"
            if not image.is_file():
                raise FileNotFoundError(image)
            staff_mask = _host_path(str(record["staff_mask"]), issue43_repo_root)
            if not staff_mask.is_file():
                raise FileNotFoundError(staff_mask)
            current_mask = _current_homr_staff_mask(
                record,
                score=score,
                page=page,
                issue43_repo_root=issue43_repo_root,
            )
            runtime[(score, page)] = {
                "image": image,
                "staff_mask": staff_mask,
                "current_homr_staff_mask": current_mask,
                "global_index": global_index,
                "score_index": score_index,
            }
            global_index += 1
    if len(runtime) != EXPECTED_PAGES:
        raise RuntimeError(f"Expected {EXPECTED_PAGES} runtime pages, got {len(runtime)}")
    return runtime


def _run_variant_downstream(
    *,
    label: str,
    barlines: Mapping[tuple[str, str], Sequence[Box]],
    runtime: Mapping[tuple[str, str], Mapping[str, Any]],
    output_root: Path,
    model_path: Path,
    device: torch.device,
    classifier: MMRClassifier,
    ocr_engine: MMROCREngine,
    mmr_threshold: float,
    rescue_threshold: float,
) -> dict[tuple[str, str], dict[str, Any]]:
    variant_root = output_root / label
    pipeline = MeasureNumberingPipeline()

    bases: list[dict[str, Any]] = []
    images: list[Path] = []
    supports: list[dict[str, Any]] = []
    override_paths: list[Path] = []
    ordered_keys: list[tuple[str, str]] = []

    for score, pages in full68_eval.SCORES.items():
        for page in pages:
            key = (score, page)
            rt = runtime[key]
            image = cv2.imread(str(rt["image"]), cv2.IMREAD_COLOR)
            if image is None:
                raise FileNotFoundError(rt["image"])
            base, _ = _score_to_payload(
                pipeline,
                boxes=barlines[key],
                staff_mask=Path(str(rt["staff_mask"])),
                image=image,
                page_number=int(rt["score_index"]) + 1,
                start_number=1,
                overrides=None,
            )
            base_path = variant_root / score / page / "numbering_base.json"
            _write_json(base_path, base)
            support = build_mmr_support_data(
                base,
                Path(str(rt["current_homr_staff_mask"])),
            )
            support_path = variant_root / score / page / "mmr_support.json"
            _write_json(support_path, support)
            override_path = variant_root / score / page / "overrides_mmr.json"

            bases.append(base)
            images.append(Path(str(rt["image"])))
            supports.append(support)
            override_paths.append(override_path)
            ordered_keys.append(key)

    run_mmr_batch(
        pages_data=bases,
        image_paths=images,
        output_paths=override_paths,
        model_path=model_path,
        device=device,
        enable_rotation_tta=False,
        threshold=mmr_threshold,
        rescue_threshold=rescue_threshold,
        classifier=classifier,
        ocr_engine=ocr_engine,
        support_data=supports,
        rapidocr_provider="auto",
    )

    rows: dict[tuple[str, str], dict[str, Any]] = {}
    score_numbers: dict[str, int] = {score: 1 for score in full68_eval.SCORES}

    for key, override_path in zip(ordered_keys, override_paths):
        score, page = key
        rt = runtime[key]
        image = cv2.imread(str(rt["image"]), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(rt["image"])
        override_payload = _load_json(override_path)
        if not isinstance(override_payload, Mapping):
            raise ValueError(f"Invalid MMR override payload: {override_path}")
        # MMRProcessor persists override.page from the page payload's
        # page_number, which this replay sets from score_index + 1. Rebase in
        # that same score-local coordinate frame. Using the canonical full68
        # global index silently dropped overrides after the first score.
        score_index = int(rt["score_index"])
        rebased = rebase_mmr_overrides_to_page_local(
            dict(override_payload),
            page_index=score_index,
        )
        # Some MMR runners emit page-local index zero when invoked over isolated
        # payloads. Accept that only if global rebasing selected no rows.
        overrides = (
            list(rebased.get("measure_overrides", []))
            if isinstance(rebased, Mapping)
            else []
        )
        if not overrides:
            raw_rows = override_payload.get("measure_overrides", [])
            if isinstance(raw_rows, list):
                page_zero_rows = [
                    dict(row)
                    for row in raw_rows
                    if isinstance(row, Mapping) and row.get("page") == 0
                ]
                if page_zero_rows:
                    overrides = page_zero_rows

        local_final, local_next = _score_to_payload(
            pipeline,
            boxes=barlines[key],
            staff_mask=Path(str(rt["staff_mask"])),
            image=image,
            page_number=int(rt["score_index"]) + 1,
            start_number=1,
            overrides=overrides,
        )
        continued_start = score_numbers[score]
        continued_final, continued_next = _score_to_payload(
            pipeline,
            boxes=barlines[key],
            staff_mask=Path(str(rt["staff_mask"])),
            image=image,
            page_number=int(rt["score_index"]) + 1,
            start_number=continued_start,
            overrides=overrides,
        )
        score_numbers[score] = continued_next

        _write_json(
            variant_root / score / page / "numbering_final_local.json",
            local_final,
        )
        _write_json(
            variant_root / score / page / "numbering_final_continued.json",
            continued_final,
        )
        rows[key] = {
            "barline_count": len(barlines[key]),
            "mmr_overrides": _override_signature({"measure_overrides": overrides}),
            "local_logical": _logical_signature(local_final),
            "local_geometry": _geometry_signature(local_final),
            "local_next_number": local_next,
            "continued_logical": _logical_signature(continued_final),
            "continued_start_number": continued_start,
            "continued_next_number": continued_next,
        }
    return rows


def run(args: argparse.Namespace) -> dict[str, Any]:
    x4_run_root = args.x4_run_root.resolve()
    late_run_root = args.late_run_root.resolve()
    issue43_repo_root = args.issue43_repo_root.resolve()
    image_root = args.image_root.resolve()
    d27_run_root = args.d27_run_root.resolve()
    d27_summary_path = args.d27_summary.resolve()
    model_path = args.mmr_model.resolve()
    output_root = args.output_root.resolve()

    for required in (
        x4_run_root,
        late_run_root,
        issue43_repo_root,
        image_root,
        d27_run_root,
        d27_summary_path,
        model_path,
    ):
        if not required.exists():
            raise FileNotFoundError(required)
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"Output root must be new/empty: {output_root}")

    d27_summary = _load_json(d27_summary_path)
    if not isinstance(d27_summary, Mapping):
        raise ValueError("D27 summary must be JSON object")
    clean = d27_summary.get("clean")
    if not isinstance(clean, Mapping):
        raise ValueError("D27 summary lacks clean aggregate")
    actual_clean = {key: int(clean[key]) for key in EXPECTED_D27_CLEAN}
    if actual_clean != EXPECTED_D27_CLEAN:
        raise RuntimeError(
            f"D27 clean contract mismatch: expected={EXPECTED_D27_CLEAN} actual={actual_clean}"
        )
    d27_deltas = _d27_deltas_by_page(d27_summary)

    runtime = _prepare_runtime(
        x4_run_root=x4_run_root,
        issue43_repo_root=issue43_repo_root,
        image_root=image_root,
    )

    variants: dict[str, dict[tuple[str, str], list[Box]]] = {}
    totals: dict[str, int] = {}
    for label in ("current_control", "late_raw_x4", "accepted_d27"):
        rows, total = _variant_barlines(
            label=label,
            x4_run_root=x4_run_root,
            late_run_root=late_run_root,
            d27_run_root=d27_run_root,
            d27_deltas=d27_deltas,
        )
        variants[label] = rows
        totals[label] = total

    if totals["current_control"] != 3643:
        raise RuntimeError(f"Unexpected current control pred total: {totals['current_control']}")
    if totals["late_raw_x4"] != 3670:
        raise RuntimeError(f"Unexpected late-raw pred total: {totals['late_raw_x4']}")
    producer_total = sum(
        len(_extract_boxes(_load_json(_d27_producer_final(d27_run_root, score, page))))
        for score, pages in full68_eval.SCORES.items()
        for page in pages
    )
    if producer_total != EXPECTED_D27_PRODUCER_PRED:
        raise RuntimeError(
            f"Unexpected D27 producer pred total: {producer_total} "
            f"!= {EXPECTED_D27_PRODUCER_PRED}"
        )
    if totals["accepted_d27"] != EXPECTED_D27_PRED:
        raise RuntimeError(
            f"Reconstructed D27 pred total mismatch: {totals['accepted_d27']} "
            f"!= {EXPECTED_D27_PRED}"
        )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("Fresh downstream replay requires CUDA for production evidence")
    classifier = MMRClassifier(model_path, device)
    ocr_engine = MMROCREngine(enable_rotation_tta=False)

    output_root.mkdir(parents=True, exist_ok=True)
    downstream: dict[str, dict[tuple[str, str], dict[str, Any]]] = {}
    for label in ("current_control", "late_raw_x4", "accepted_d27"):
        print(f"=== downstream variant: {label} ===", flush=True)
        downstream[label] = _run_variant_downstream(
            label=label,
            barlines=variants[label],
            runtime=runtime,
            output_root=output_root,
            model_path=model_path,
            device=device,
            classifier=classifier,
            ocr_engine=ocr_engine,
            mmr_threshold=float(args.mmr_threshold),
            rescue_threshold=float(args.mmr_rescue_threshold),
        )
        if device.type == "cuda":
            torch.cuda.empty_cache()

    comparisons = {
        "late_vs_control": _comparison(
            downstream["current_control"],
            downstream["late_raw_x4"],
        ),
        "late_vs_d27": _comparison(
            downstream["accepted_d27"],
            downstream["late_raw_x4"],
        ),
        "control_vs_d27": _comparison(
            downstream["accepted_d27"],
            downstream["current_control"],
        ),
    }

    per_variant = {}
    for label, rows in downstream.items():
        per_variant[label] = {
            "barline_count": totals[label],
            "mmr_override_count": sum(len(row["mmr_overrides"]) for row in rows.values()),
            "final_selected_page_count": len(rows),
            "per_page": [
                {
                    "score": score,
                    "page": page,
                    **row,
                }
                for (score, page), row in sorted(rows.items())
            ],
        }

    report = {
        "schema_version": "issue372.fresh_downstream_semantic_replay.v1",
        "contract": {
            "detector_rerun": False,
            "homr_sr_omr_rerun": False,
            "phase_a_numbering_fresh": True,
            "mmr_support": "retained current-x4 HOMR staff mask",
            "mmr_inference_fresh": True,
            "final_numbering_fresh": True,
            "reference": "Issue #296 accepted D27 reconstructed from authoritative acceptance deltas",
            "primary_gate": (
                "late_raw_x4 vs accepted_d27 logical measure topology/count/MMR skip/"
                "number-sequence equivalence; bbox-only geometry drift is diagnostic"
            ),
            "score_continuation_note": (
                "continued view uses the canonical 68-page selected subset order and is a "
                "cross-variant drift detector, not an absolute full-score oracle when source "
                "pages outside the selected subset are absent"
            ),
            "d27_clean": actual_clean,
            "mmr_model": str(model_path),
            "mmr_threshold": float(args.mmr_threshold),
            "mmr_rescue_threshold": float(args.mmr_rescue_threshold),
        },
        "variant_summary": {
            label: {
                "barline_count": payload["barline_count"],
                "mmr_override_count": payload["mmr_override_count"],
                "final_selected_page_count": payload["final_selected_page_count"],
            }
            for label, payload in per_variant.items()
        },
        "comparisons": comparisons,
        "primary_semantic_gate_pass": comparisons["late_vs_d27"]["logical_match"],
        "variants": per_variant,
    }
    report_path = output_root / "fresh_downstream_semantic_replay.json"
    _write_json(report_path, report)

    print("=== Issue #372 fresh downstream semantic replay ===")
    print(f"primary_semantic_gate_pass={report['primary_semantic_gate_pass']}")
    for name, comparison in comparisons.items():
        print(
            f"{name}: logical_match={comparison['logical_match']} "
            f"logical_changed={comparison['logical_changed_page_count']} "
            f"geometry_only={comparison['geometry_only_changed_page_count']} "
            f"mmr_changed={comparison['mmr_override_changed_page_count']}"
        )
    print(f"OUTPUT={report_path}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--x4-run-root", type=Path, required=True)
    parser.add_argument("--late-run-root", type=Path, required=True)
    parser.add_argument("--issue43-repo-root", type=Path, required=True)
    parser.add_argument("--d27-run-root", type=Path, required=True)
    parser.add_argument("--d27-summary", type=Path, required=True)
    parser.add_argument("--image-root", type=Path, required=True)
    parser.add_argument(
        "--mmr-model",
        type=Path,
        default=ROOT / "tools/mmr_training/models/mmr_classifier_best.pth",
    )
    parser.add_argument("--mmr-threshold", type=float, default=0.5)
    parser.add_argument("--mmr-rescue-threshold", type=float, default=0.1)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())