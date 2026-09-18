#!/usr/bin/env python3
"""Evaluate Issue #332 classifiers on retained Issue #294 candidate-native geometry."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

FOCUSED_PAGE_IDS = {
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
}
RISK_PAGE_IDS = {"page_002", "page_022", "page_034", "page_042"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_head() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _route(probability: float) -> str:
    if probability <= 0.1:
        return "below_rescue"
    if probability <= 0.5:
        return "rescue"
    return "main"


def _correct(expected_skip: int | None, final_skip: int | None) -> bool:
    return expected_skip == final_skip


def summarize_rows(rows: Sequence[Mapping[str, Any]], model_name: str) -> dict[str, Any]:
    expected_positive = sum(row["expected_skip"] is not None for row in rows)
    classifier_tp = classifier_fp = classifier_fn = classifier_tn = 0
    false_override = lost_override = wrong_number = correct = 0
    for row in rows:
        probability = float(row["models"][model_name]["probability"])
        predicted = probability > 0.5
        label = row["expected_skip"] is not None
        classifier_tp += int(predicted and label)
        classifier_fp += int(predicted and not label)
        classifier_fn += int(not predicted and label)
        classifier_tn += int(not predicted and not label)
        final_skip = row["models"][model_name]["final_skip"]
        expected_skip = row["expected_skip"]
        correct += int(_correct(expected_skip, final_skip))
        false_override += int(expected_skip is None and final_skip is not None)
        lost_override += int(expected_skip is not None and final_skip is None)
        wrong_number += int(
            expected_skip is not None and final_skip is not None and expected_skip != final_skip
        )
    precision = (
        classifier_tp / (classifier_tp + classifier_fp) if classifier_tp + classifier_fp else 0
    )
    recall = classifier_tp / (classifier_tp + classifier_fn) if classifier_tp + classifier_fn else 0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
    return {
        "samples": len(rows),
        "expected_positive": expected_positive,
        "classifier": {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "confusion_matrix": {
                "tn": classifier_tn,
                "fp": classifier_fp,
                "fn": classifier_fn,
                "tp": classifier_tp,
            },
            "routes": dict(Counter(row["models"][model_name]["route"] for row in rows)),
        },
        "final": {
            "correct": correct,
            "error": len(rows) - correct,
            "false_override": false_override,
            "lost_override": lost_override,
            "wrong_number": wrong_number,
        },
    }


def compare_models(
    rows: Sequence[Mapping[str, Any]], baseline_name: str, candidate_name: str
) -> dict[str, Any]:
    route_changes = []
    new_regressions = []
    improvements = []
    final_changes = []
    for row in rows:
        baseline = row["models"][baseline_name]
        candidate = row["models"][candidate_name]
        identity = {
            key: row[key]
            for key in ("page_id", "score_id", "page_name", "system_index", "measure_index")
        }
        if baseline["route"] != candidate["route"]:
            route_changes.append(
                {
                    **identity,
                    "expected_skip": row["expected_skip"],
                    "baseline_probability": baseline["probability"],
                    "candidate_probability": candidate["probability"],
                    "baseline_route": baseline["route"],
                    "candidate_route": candidate["route"],
                }
            )
        if baseline["final_skip"] != candidate["final_skip"]:
            final_changes.append(
                {
                    **identity,
                    "expected_skip": row["expected_skip"],
                    "baseline_final_skip": baseline["final_skip"],
                    "candidate_final_skip": candidate["final_skip"],
                }
            )
        baseline_correct = _correct(row["expected_skip"], baseline["final_skip"])
        candidate_correct = _correct(row["expected_skip"], candidate["final_skip"])
        if baseline_correct and not candidate_correct:
            new_regressions.append({**identity, "expected_skip": row["expected_skip"]})
        if not baseline_correct and candidate_correct:
            improvements.append({**identity, "expected_skip": row["expected_skip"]})
    return {
        "route_change_count": len(route_changes),
        "route_changes": route_changes,
        "final_change_count": len(final_changes),
        "final_changes": final_changes,
        "new_final_regression_count": len(new_regressions),
        "new_final_regressions": new_regressions,
        "final_improvement_count": len(improvements),
        "final_improvements": improvements,
    }


def _batched_logits(
    model: Any, tensors: Sequence[Any], device: Any, batch_size: int
) -> list[float]:
    import torch

    values = []
    with torch.inference_mode():
        for start in range(0, len(tensors), batch_size):
            batch = torch.stack(tensors[start : start + batch_size]).to(device)
            values.extend(float(value) for value in model(batch).reshape(-1).cpu())
    return values


def run(args: argparse.Namespace) -> dict[str, Any]:
    import cv2
    import torch
    from tools.issue294._mapping_guarded_candidate_mmr_rescore import (
        _accepted_rebase_pages,
        _rebase_accepted_expected_to_candidate,
    )
    from tools.issue294.evaluate_mapping_guarded_connector_positive_candidate import (
        MappingGuardedConnectorPositivePipeline,
    )
    from tools.issue294.rescore_full68_mmr_audit import _load_matrix_pages
    from tools.issue294.run_post277_mapping_guarded_mmr import _build_variant_inputs

    from src.measure_numbering.mmr import MMRClassifier, MMROCREngine, MMRProcessor
    from src.measure_numbering.rapidocr_provider import (
        collect_rapidocr_providers,
        create_mmr_rapidocr,
        providers_include_cuda,
    )
    from tools.issue264.run_phase_c_mmr_regression import build_page_specs
    from tools.mmr_training.issue332.dual_view_fusion import (
        MonotonicLogitFusion,
        _load_encoders,
        _tensor,
        fuse_logits,
    )
    from tools.mmr_training.issue332.production_replay_validation import CachedRapidOCR
    from tools.mmr_training.issue332.staff_view import (
        crop_source_bbox,
        staff_relative_roi_bboxes,
    )
    from tools.mmr_training.issue332_geometry_benchmark import crop_measure

    hashes = {
        "manifest": _sha256(args.full68_manifest),
        "accepted_rebase": _sha256(args.accepted_rebase_report),
        "production_model": _sha256(args.production_model),
        "full_model": _sha256(args.full_model),
        "staff_model": _sha256(args.staff_model),
        "fusion_model": _sha256(args.fusion_model),
    }
    expected = {
        "production_model": "f163fa2a7679d12c0f4fe6fc2fadc7ed1f144035779a18b83a303bfa6d35903a",
        "full_model": "92f52a27a68a54d8ab49f5e6f6f2156e4f3d7e1634774c69baff5e031a697a46",
        "staff_model": "882c0613036d49d3cf9f21f226d1e057af76a44be1bf02cad5221c23fcced4fc",
        "fusion_model": "a639a0582e3b27e86a323c81701cdd2dbfe91310eb28275222abf840ed0077a2",
    }
    for key, value in expected.items():
        if hashes[key] != value:
            raise ValueError(f"{key} SHA mismatch: expected {value}, got {hashes[key]}")

    manifest = json.loads(args.full68_manifest.read_text(encoding="utf-8"))
    if manifest.get("status") != "completed" or int(manifest.get("completed_page_count", 0)) != 68:
        raise ValueError("Issue #294 full68 manifest is not completed")
    gates = manifest.get("gates", {})
    if not gates.get("B_C_native_final_barlines_identical_all_pages"):
        raise ValueError(
            "Issue #294 provenance gate failed: B_C_native_final_barlines_identical_all_pages"
        )

    specs = build_page_specs()
    if not args.full68:
        specs = [spec for spec in specs if str(spec.page_id) in FOCUSED_PAGE_IDS]
    matrix_pages = _load_matrix_pages(manifest)
    bases, images, supports, mapping_modes = _build_variant_inputs(
        specs=specs,
        matrix_pages=matrix_pages,
        label="C_latest",
        pipeline_factory=MappingGuardedConnectorPositivePipeline,
    )
    accepted_pages, accepted_provenance = _accepted_rebase_pages(args.accepted_rebase_report)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("actual candidate-native gate requires CUDA")
    production_classifier = MMRClassifier(args.production_model, device)
    full_model, staff_model = _load_encoders(args.full_model, args.staff_model, device)
    fusion = MonotonicLogitFusion()
    fusion_bundle = torch.load(args.fusion_model, map_location="cpu", weights_only=True)
    fusion.load_state_dict(fusion_bundle["fusion_state_dict"])
    fusion.eval()
    weights = [float(value) for value in fusion.effective_weights().detach()]
    bias = float(fusion.bias.item())

    rows = []
    probability_lists = {name: [] for name in ("production_full", "retrained_full", "dual_view")}
    geometry_digest = hashlib.sha256()
    feature_started = time.perf_counter()
    for page_index, (spec, base, image_path, support, mapping_mode) in enumerate(
        zip(specs, bases, images, supports, mapping_modes)
    ):
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(image_path)
        primary_page = support["views"]["primary"]["pages"][0]
        full_tensors = []
        staff_tensors = []
        staff_slices = []
        identities = []
        for system_index, system in enumerate(primary_page["systems"]):
            staff_bboxes = [stave["bbox"] for stave in system.get("staves", [])]
            for measure_index, measure in enumerate(system.get("measures", [])):
                bbox = measure["bbox"]
                full_tensors.append(_tensor(crop_measure(image, bbox, margin_px=20)))
                sample = {"bbox": bbox, "_staff_bboxes": staff_bboxes}
                start = len(staff_tensors)
                staff_tensors.extend(
                    _tensor(crop_source_bbox(image, roi))
                    for roi in staff_relative_roi_bboxes(sample)
                )
                staff_slices.append((start, len(staff_tensors)))
                identities.append((system_index, measure_index, bbox, staff_bboxes))
                geometry_digest.update(
                    json.dumps(
                        [str(spec.page_id), system_index, measure_index, bbox, staff_bboxes],
                        separators=(",", ":"),
                    ).encode()
                )

        production_logits = _batched_logits(
            production_classifier.model, full_tensors, device, args.batch_size
        )
        full_logits = _batched_logits(full_model, full_tensors, device, args.batch_size)
        raw_staff_logits = _batched_logits(
            staff_model.encoder, staff_tensors, device, args.batch_size
        )
        expected_payload, _mappings = _rebase_accepted_expected_to_candidate(
            accepted_pages[str(spec.page_id)],
            base,
            global_page_index=int(spec.global_index),
        )
        expected_by_key = {
            (int(item["system"]), int(item["measure"])): int(item["skip"])
            for item in expected_payload.get("overrides", [])
        }
        for local_index, (system_index, measure_index, bbox, staff_bboxes) in enumerate(identities):
            staff_start, staff_end = staff_slices[local_index]
            staff_logit = max(raw_staff_logits[staff_start:staff_end])
            fused_logit = float(
                fuse_logits(
                    torch.tensor(full_logits[local_index]),
                    torch.tensor(staff_logit),
                    weights=weights,
                    bias=bias,
                )
            )
            probabilities = {
                "production_full": float(
                    torch.sigmoid(torch.tensor(production_logits[local_index]))
                ),
                "retrained_full": float(torch.sigmoid(torch.tensor(full_logits[local_index]))),
                "dual_view": float(torch.sigmoid(torch.tensor(fused_logit))),
            }
            row = {
                "page_id": str(spec.page_id),
                "global_page_index": int(spec.global_index),
                "score_id": str(spec.score),
                "page_name": str(spec.page_name),
                "system_index": system_index,
                "measure_index": measure_index,
                "measure_bbox": list(bbox),
                "staff_bboxes": [list(value) for value in staff_bboxes],
                "mapping_mode": mapping_mode,
                "expected_skip": expected_by_key.get((system_index, measure_index)),
                "features": {
                    "production_full_logit": production_logits[local_index],
                    "retrained_full_logit": full_logits[local_index],
                    "staff_logit": staff_logit,
                    "fusion_logit": fused_logit,
                },
                "models": {},
            }
            for name, probability in probabilities.items():
                row["models"][name] = {"probability": probability, "route": _route(probability)}
                probability_lists[name].append(probability)
            rows.append(row)
        print(f"candidate-native features: {page_index + 1}/{len(specs)}", flush=True)
    feature_seconds = time.perf_counter() - feature_started

    class SequenceClassifier:
        def __init__(self, probabilities: Sequence[float]):
            self.probabilities = probabilities
            self.cursor = -1

        def predict(self, _crop: Any) -> float:
            self.cursor += 1
            return float(self.probabilities[self.cursor])

    rapidocr = create_mmr_rapidocr("cuda")
    providers = collect_rapidocr_providers(rapidocr)
    if not providers_include_cuda(providers):
        raise RuntimeError(f"RapidOCR CUDA provider unavailable: {providers}")
    cached_rapidocr = CachedRapidOCR(rapidocr)
    ocr_engine = MMROCREngine(ocr_engine=cached_rapidocr)
    model_elapsed = {}
    for model_name, probabilities in probability_lists.items():
        classifier = SequenceClassifier(probabilities)

        class TraceProcessor(MMRProcessor):
            def __init__(self, *processor_args: Any, **processor_kwargs: Any):
                super().__init__(*processor_args, **processor_kwargs)
                self.ocr_calls: dict[int, list[dict[str, Any]]] = {}

            def _detect_number_with_evidence(
                self,
                image: Any,
                system: Any,
                x1: Any,
                y1: Any,
                x2: Any,
                y2: Any,
                prob: Any,
                w_img: Any,
                h_img: Any,
            ):
                result = super()._detect_number_with_evidence(
                    image, system, x1, y1, x2, y2, prob, w_img, h_img
                )
                self.ocr_calls.setdefault(classifier.cursor, []).append(
                    {
                        "bbox": [int(x1), int(y1), int(x2), int(y2)],
                        "number": result[0],
                        "score": float(result[1]),
                        "debug": result[2],
                        "one_bar_evidence": int(result[3]),
                    }
                )
                return result

        processor = TraceProcessor(
            model_path=args.production_model,
            device=device,
            classifier=classifier,
            ocr_engine=ocr_engine,
            threshold=0.5,
            rescue_threshold=0.1,
        )
        started = time.perf_counter()
        actual = processor.process_pages(bases, images, support_data=supports)
        model_elapsed[model_name] = time.perf_counter() - started
        if classifier.cursor + 1 != len(rows):
            raise RuntimeError(
                f"{model_name} classifier traversal mismatch: {classifier.cursor + 1} != {len(rows)}"
            )
        final_by_key = {}
        for page_result in actual:
            for override in page_result["measure_overrides"]:
                final_by_key[
                    (int(override["page"]), int(override["system"]), int(override["measure"]))
                ] = override
        for index, row in enumerate(rows):
            key = (
                int(row["global_page_index"]),
                int(row["system_index"]),
                int(row["measure_index"]),
            )
            override = final_by_key.get(key)
            row["models"][model_name].update(
                {
                    "ocr_calls": processor.ocr_calls.get(index, []),
                    "final_skip": int(override["skip"]) if override is not None else None,
                    "final_number": int(override["skip"]) + 1 if override is not None else None,
                    "final_correct": _correct(
                        row["expected_skip"],
                        int(override["skip"]) if override is not None else None,
                    ),
                }
            )

    scopes = {
        "all": rows,
        "focused": [row for row in rows if row["page_id"] in FOCUSED_PAGE_IDS],
        "risk": [row for row in rows if row["page_id"] in RISK_PAGE_IDS],
    }
    summaries = {}
    comparisons = {}
    for scope_name, scope_rows in scopes.items():
        summaries[scope_name] = {
            model_name: summarize_rows(scope_rows, model_name) for model_name in probability_lists
        }
        comparisons[scope_name] = {
            "production_full_vs_dual_view": compare_models(
                scope_rows, "production_full", "dual_view"
            ),
            "retrained_full_vs_dual_view": compare_models(
                scope_rows, "retrained_full", "dual_view"
            ),
        }

    payload = {
        "schema_version": "issue332.actual_candidate_geometry_validation.v1",
        "provenance": {
            "git_head": _git_head(),
            "hashes": hashes,
            "accepted_rebase": accepted_provenance,
            "issue294_manifest_checkout": manifest.get("checkout"),
            "issue294_latest_homr_commit": manifest.get("latest_homr_commit"),
            "issue294_manifest_gates": gates,
            "candidate_label": "C_latest",
            "candidate_geometry_sha256": geometry_digest.hexdigest(),
            "runtime": {
                "python": platform.python_version(),
                "torch": torch.__version__,
                "opencv": cv2.__version__,
                "device": str(device),
                "rapidocr_providers": providers,
            },
        },
        "contract": {
            "historical_A_runtime_signal": False,
            "thresholds": {"main": 0.5, "rescue": 0.1},
            "rapidocr_policy_changed": False,
            "page_count": len(specs),
            "semantic_measure_count": len(rows),
            "focused_page_ids": sorted(FOCUSED_PAGE_IDS),
            "risk_page_ids": sorted(RISK_PAGE_IDS),
            "fusion": {"weights": weights, "bias": bias},
        },
        "timing": {
            "feature_seconds": feature_seconds,
            "production_mmr_seconds": model_elapsed,
        },
        "rapidocr_cache": {
            "engine_calls": cached_rapidocr.calls,
            "content_cache_hits": cached_rapidocr.cache_hits,
        },
        "summaries": summaries,
        "comparisons": comparisons,
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full68-manifest", type=Path, required=True)
    parser.add_argument("--accepted-rebase-report", type=Path, required=True)
    parser.add_argument("--production-model", type=Path, required=True)
    parser.add_argument("--full-model", type=Path, required=True)
    parser.add_argument("--staff-model", type=Path, required=True)
    parser.add_argument("--fusion-model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--full68", action="store_true")
    return parser


if __name__ == "__main__":
    result = run(build_parser().parse_args())
    print(
        json.dumps(
            {
                "summaries": result["summaries"],
                "comparisons": result["comparisons"],
                "timing": result["timing"],
                "rapidocr_cache": result["rapidocr_cache"],
            },
            indent=2,
        )
    )
