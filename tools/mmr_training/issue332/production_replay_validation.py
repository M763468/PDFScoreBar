#!/usr/bin/env python3
"""Replay Issue #332 joint crossings through the unchanged production OCR policy."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np
import torch

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.mmr_training.issue332.dual_view_diagnosis import _staff_bbox_variants
from tools.mmr_training.issue332.dual_view_fusion import sha256_file
from tools.mmr_training.issue332.staff_view import source_staff_bboxes
from tools.mmr_training.issue332_geometry_benchmark import (
    _scale_page_and_bbox,
    generate_geometry_variants,
)


def _git_head() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


class CachedRapidOCR:
    """Content-addressed cache around the production RapidOCR callable."""

    def __init__(self, engine: Any):
        self.engine = engine
        self.cache: dict[str, Any] = {}
        self.calls = 0
        self.cache_hits = 0

    def __call__(self, image: np.ndarray):
        contiguous = np.ascontiguousarray(image)
        digest = hashlib.sha256()
        digest.update(str(contiguous.shape).encode())
        digest.update(str(contiguous.dtype).encode())
        digest.update(contiguous.tobytes())
        key = digest.hexdigest()
        if key in self.cache:
            self.cache_hits += 1
            return deepcopy(self.cache[key])
        result = self.engine(contiguous)
        self.cache[key] = deepcopy(result)
        self.calls += 1
        return result


def _variant_parts(name: str) -> tuple[str, str]:
    match = re.fullmatch(r"measure=(.+)\|staff=(.+)", name)
    if not match:
        raise ValueError(f"invalid joint variant: {name}")
    return match.group(1), match.group(2)


def baseline_joint_summary(
    full_geometry: dict[str, Any],
    *,
    staff_variant_names: Sequence[str],
) -> dict[str, Any]:
    """Expand full-only rows across the identical staff-variant evaluation space."""
    by_sample: dict[str, list[dict[str, Any]]] = {}
    for row in full_geometry["rows"]:
        if float(row.get("dpi_scale", 1.0)) != 1.0 or row.get("resize_mode") != "direct":
            continue
        by_sample.setdefault(str(row["sample_id"]), []).append(row)
    samples = []
    crossings = {"main": [], "rescue": []}
    crossing_variant_counts = {"main": 0, "rescue": 0}
    for sample_id, rows in sorted(by_sample.items()):
        native = next(row for row in rows if row["variant"] == "native")
        probabilities = [float(row["probability"]) for row in rows]
        item = {
            "sample_id": sample_id,
            "label": int(native["label"]),
            "native_probability": float(native["probability"]),
            "probability_min": min(probabilities),
            "probability_max": max(probabilities),
            "probability_range": max(probabilities) - min(probabilities),
            "max_abs_delta_from_native": max(
                abs(probability - float(native["probability"])) for probability in probabilities
            ),
        }
        for threshold_name, threshold in (("main", 0.5), ("rescue", 0.1)):
            native_decision = float(native["probability"]) >= threshold
            crossing_rows = [
                row for row in rows if (float(row["probability"]) >= threshold) != native_decision
            ]
            expanded = [
                {
                    "variant": f"measure={row['variant']}|staff={staff_name}",
                    "probability": float(row["probability"]),
                }
                for row in crossing_rows
                for staff_name in staff_variant_names
            ]
            item[f"{threshold_name}_crossing_variants"] = expanded
            if expanded:
                crossings[threshold_name].append(
                    {
                        "sample_id": sample_id,
                        "direction": (
                            "positive_to_negative" if native_decision else "negative_to_positive"
                        ),
                    }
                )
                crossing_variant_counts[threshold_name] += len(expanded)
        samples.append(item)
    return {
        "sample_count": len(samples),
        "staff_variants_repeated": len(staff_variant_names),
        "joint_variants_per_sample": len(next(iter(by_sample.values()))) * len(staff_variant_names),
        "main": {
            "unique_crossing_count": len(crossings["main"]),
            "crossings": crossings["main"],
            "crossing_variant_count": crossing_variant_counts["main"],
        },
        "rescue": {
            "unique_crossing_count": len(crossings["rescue"]),
            "crossings": crossings["rescue"],
            "crossing_variant_count": crossing_variant_counts["rescue"],
        },
        "samples": samples,
    }


def _expected_rest_count(sample: dict[str, Any], numbering: dict[str, Any]) -> int | None:
    if int(sample["label"]) == 0:
        return None
    rest_gt_path = sample.get("provenance", {}).get("rest_gt_path")
    if not rest_gt_path:
        raise ValueError(f"positive sample lacks rest_gt provenance: {sample['sample_id']}")
    rest_gt = json.loads(Path(rest_gt_path).read_text(encoding="utf-8"))
    global_index = sample.get("global_measure_index")
    if global_index is None:
        global_index = 0
        target_system = int(sample["system_index"])
        target_measure = int(sample["measure_index"])
        systems = numbering["pages"][0]["systems"]
        for system_index, system in enumerate(systems):
            for measure_index, _measure in enumerate(system.get("measures", [])):
                if system_index == target_system and measure_index == target_measure:
                    break
                global_index += 1
            else:
                continue
            break
    matches = [
        item
        for item in rest_gt.get("overrides", [])
        if int(item["measure_index"]) == int(global_index)
    ]
    if len(matches) != 1:
        raise ValueError(
            f"expected one GT override for {sample['sample_id']} at {global_index}, got {matches}"
        )
    return int(matches[0]["rest_count"])


def _route(probability: float) -> str:
    if probability <= 0.1:
        return "below_rescue"
    if probability <= 0.5:
        return "rescue"
    if probability < 0.6:
        return "main_veto_sensitive"
    return "main"


class ProductionReplay:
    def __init__(self, processor: Any, deltas: Sequence[int]):
        self.processor = processor
        self.deltas = tuple(int(value) for value in deltas)
        self.images: dict[str, np.ndarray] = {}
        self.numbering: dict[str, dict[str, Any]] = {}
        self.decision_cache: dict[tuple[Any, ...], dict[str, Any]] = {}

    def _inputs(self, sample: dict[str, Any]):
        sample_id = str(sample["sample_id"])
        if sample_id not in self.images:
            image = cv2.imread(str(sample["image_path"]), cv2.IMREAD_COLOR)
            if image is None:
                raise FileNotFoundError(sample["image_path"])
            self.images[sample_id] = image
            self.numbering[sample_id] = json.loads(
                Path(sample["provenance"]["numbering_path"]).read_text(encoding="utf-8")
            )
        return self.images[sample_id], self.numbering[sample_id]

    def _decision(
        self,
        sample: dict[str, Any],
        variant_name: str,
        probability: float,
        image: np.ndarray,
        numbering: dict[str, Any],
        measure_bbox: Sequence[float],
        staff_bboxes: Sequence[Sequence[float]],
    ) -> dict[str, Any]:
        expected = _expected_rest_count(sample, numbering)
        route = _route(probability)
        cache_key = (
            sample["sample_id"],
            tuple(int(value) for value in image.shape),
            tuple(float(value) for value in measure_bbox),
            tuple(tuple(float(value) for value in bbox) for bbox in staff_bboxes),
            route,
        )
        if cache_key in self.decision_cache:
            cached = deepcopy(self.decision_cache[cache_key])
            cached["decision_cache_hit"] = True
            cached["probability"] = probability
            cached["variant"] = variant_name
            return cached

        result = {
            "sample_id": sample["sample_id"],
            "score_id": sample["score_id"],
            "label": int(sample["label"]),
            "expected_rest_count": expected,
            "variant": variant_name,
            "probability": probability,
            "route": route,
            "ocr_called": False,
            "found_number": None,
            "final_score": 0.0,
            "ocr_debug": "",
            "one_bar_evidence_count": 0,
            "one_bar_veto": False,
            "status": "below_rescue",
            "final_override_rest_count": None,
            "decision_cache_hit": False,
        }
        if probability > self.processor.rescue_threshold:
            system_index = int(sample["system_index"])
            system = deepcopy(numbering["pages"][0]["systems"][system_index])
            for stave, bbox in zip(system.get("staves", []), staff_bboxes):
                stave["bbox"] = list(bbox)
            x1, y1, x2, y2 = measure_bbox
            height, width = image.shape[:2]
            found, score, debug, evidence = self.processor._detect_number_with_evidence(
                image, system, x1, y1, x2, y2, probability, width, height
            )
            valid, status, vetoed = self.processor._valid_status(
                found, probability, score, evidence
            )
            result.update(
                {
                    "ocr_called": True,
                    "found_number": found,
                    "final_score": float(score),
                    "ocr_debug": debug,
                    "one_bar_evidence_count": int(evidence),
                    "one_bar_veto": bool(vetoed),
                    "status": status or "ocr_no_override",
                    "final_override_rest_count": int(found) if valid else None,
                }
            )
        self.decision_cache[cache_key] = deepcopy(result)
        return result

    def replay(
        self, sample: dict[str, Any], variant_name: str, probability: float
    ) -> dict[str, Any]:
        image, numbering = self._inputs(sample)
        measure_name, staff_name = _variant_parts(variant_name)
        measure_variants = {
            variant.name: variant.bbox
            for variant in generate_geometry_variants(sample["bbox"], self.deltas)
        }
        staff_variants = dict(_staff_bbox_variants(source_staff_bboxes(sample), self.deltas))
        return self._decision(
            sample,
            variant_name,
            probability,
            image,
            numbering,
            measure_variants[measure_name],
            staff_variants[staff_name],
        )

    def replay_dpi(
        self, sample: dict[str, Any], scale: float, probability: float
    ) -> dict[str, Any]:
        image, numbering = self._inputs(sample)
        scaled_image, scaled_bbox = _scale_page_and_bbox(
            image, tuple(float(value) for value in sample["bbox"]), scale
        )
        scaled_staff_bboxes = [
            [float(value) * scale for value in bbox] for bbox in source_staff_bboxes(sample)
        ]
        return self._decision(
            sample,
            f"dpi_{scale:g}",
            probability,
            scaled_image,
            numbering,
            scaled_bbox,
            scaled_staff_bboxes,
        )


def _crossing_requests(
    validation: dict[str, Any],
    samples: dict[str, dict[str, Any]],
    scope: str,
) -> list[dict[str, Any]]:
    requests = []
    for item in validation["joint_geometry"][scope]["samples"]:
        sample = samples[item["sample_id"]]
        crossing_by_variant: dict[str, dict[str, Any]] = {}
        for threshold_name in ("main", "rescue"):
            for crossing in item[f"{threshold_name}_crossing_variants"]:
                entry = crossing_by_variant.setdefault(
                    crossing["variant"],
                    {
                        "sample": sample,
                        "variant": crossing["variant"],
                        "probability": float(crossing["probability"]),
                        "threshold_crossings": [],
                    },
                )
                entry["threshold_crossings"].append(threshold_name)
        requests.extend(crossing_by_variant.values())
    return requests


def _dpi_requests(
    validation: dict[str, Any],
    samples: dict[str, dict[str, Any]],
    scope: str,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    by_sample: dict[str, list[dict[str, Any]]] = {}
    for row in validation["coherent_dpi"][scope]["rows"]:
        by_sample.setdefault(str(row["sample_id"]), []).append(row)
    native_by_sample = {}
    requests = []
    for sample_id, rows in sorted(by_sample.items()):
        native_row = next(row for row in rows if float(row["dpi_scale"]) == 1.0)
        native_probability = float(native_row["probability"])
        native_by_sample[sample_id] = {
            "sample": samples[sample_id],
            "scale": 1.0,
            "probability": native_probability,
        }
        for row in rows:
            scale = float(row["dpi_scale"])
            if scale == 1.0:
                continue
            probability = float(row["probability"])
            threshold_crossings = [
                name
                for name, threshold in (("main", 0.5), ("rescue", 0.1))
                if (native_probability > threshold) != (probability > threshold)
            ]
            requests.append(
                {
                    "sample": samples[sample_id],
                    "scale": scale,
                    "variant": str(row["variant"]),
                    "probability": probability,
                    "threshold_crossings": threshold_crossings,
                }
            )
    return requests, native_by_sample


def _summarize_replay(
    requests: Sequence[dict[str, Any]],
    native_by_sample: dict[str, dict[str, Any]],
    replay_rows: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    counters = {
        "variants": len(replay_rows),
        "native_vs_perturbed_final_override_equal": 0,
        "false_positive_override": 0,
        "lost_correct_override": 0,
        "wrong_override_value": 0,
        "wrong_skip": 0,
        "new_error_vs_native": 0,
        "main_to_rescue_same_final": 0,
        "rescue_crossing_same_final": 0,
        "ocr_called": 0,
        "one_bar_veto": 0,
    }
    failures = []
    for request, row in zip(requests, replay_rows):
        native = native_by_sample[row["sample_id"]]
        expected = row["expected_rest_count"]
        final_value = row["final_override_rest_count"]
        native_value = native["final_override_rest_count"]
        equal = final_value == native_value
        counters["native_vs_perturbed_final_override_equal"] += int(equal)
        counters["ocr_called"] += int(row["ocr_called"])
        counters["one_bar_veto"] += int(row["one_bar_veto"])
        wrong = final_value != expected
        native_wrong = native_value != expected
        false_positive = expected is None and final_value is not None
        lost = expected is not None and native_value == expected and final_value != expected
        counters["false_positive_override"] += int(false_positive)
        counters["lost_correct_override"] += int(lost)
        counters["wrong_override_value"] += int(
            expected is not None and final_value is not None and final_value != expected
        )
        counters["wrong_skip"] += int(expected is not None and final_value is None)
        counters["new_error_vs_native"] += int(wrong and not native_wrong)
        if "main" in request["threshold_crossings"] and row["route"] == "rescue" and equal:
            counters["main_to_rescue_same_final"] += 1
        if "rescue" in request["threshold_crossings"] and equal:
            counters["rescue_crossing_same_final"] += 1
        if not equal or wrong:
            failures.append(
                {
                    "sample_id": row["sample_id"],
                    "variant": row["variant"],
                    "threshold_crossings": request["threshold_crossings"],
                    "label": row["label"],
                    "expected_rest_count": expected,
                    "native_final_override": native_value,
                    "perturbed_final_override": final_value,
                    "probability": row["probability"],
                    "route": row["route"],
                    "found_number": row["found_number"],
                    "final_score": row["final_score"],
                    "one_bar_veto": row["one_bar_veto"],
                    "new_error_vs_native": wrong and not native_wrong,
                }
            )
    counters["native_vs_perturbed_final_override_match_rate"] = (
        counters["native_vs_perturbed_final_override_equal"] / len(replay_rows)
        if replay_rows
        else 1.0
    )
    return {"counts": counters, "failures": failures}


def run(args: argparse.Namespace) -> dict[str, Any]:
    from src.measure_numbering.mmr import MMROCREngine, MMRProcessor
    from src.measure_numbering.rapidocr_provider import (
        collect_rapidocr_providers,
        create_mmr_rapidocr,
    )

    config = json.loads(args.config.read_text(encoding="utf-8"))
    expected_hashes = {
        "manifest_sha256": args.manifest,
        "split_sha256": args.split_manifest,
        "acceptance_manifest_sha256": args.acceptance_manifest,
        "full_model_sha256": args.full_model,
        "staff_model_sha256": args.staff_model,
        "fusion_model_sha256": args.fusion_model,
    }
    for key, path in expected_hashes.items():
        actual = sha256_file(path)
        if actual != config[key]:
            raise ValueError(f"{key} mismatch: expected {config[key]}, got {actual}")
    validation = json.loads(args.final_validation.read_text(encoding="utf-8"))
    primary_list = json.loads(args.primary_manifest.read_text(encoding="utf-8"))["samples"]
    control_list = json.loads(args.controls_manifest.read_text(encoding="utf-8"))["samples"]
    samples = {sample["sample_id"]: sample for sample in primary_list + control_list}

    staff_variant_names = [
        name for name, _staves in _staff_bbox_variants(source_staff_bboxes(primary_list[0]))
    ]
    baseline_primary = baseline_joint_summary(
        json.loads(args.full_primary.read_text(encoding="utf-8")),
        staff_variant_names=staff_variant_names,
    )
    baseline_controls = baseline_joint_summary(
        json.loads(args.full_controls.read_text(encoding="utf-8")),
        staff_variant_names=staff_variant_names,
    )

    rapidocr = create_mmr_rapidocr("auto")
    providers = collect_rapidocr_providers(rapidocr)
    cached_rapidocr = CachedRapidOCR(rapidocr)
    ocr = MMROCREngine(enable_rotation_tta=False, ocr_engine=cached_rapidocr)
    processor = MMRProcessor(
        model_path=args.full_model,
        device=torch.device("cpu"),
        threshold=0.5,
        rescue_threshold=0.1,
        classifier=object(),
        ocr_engine=ocr,
    )
    replay = ProductionReplay(processor, config["deltas_px"])
    started = time.perf_counter()
    scope_outputs = {}
    for scope in ("primary", "controls"):
        requests = _crossing_requests(validation, samples, scope)
        crossing_sample_ids = sorted({request["sample"]["sample_id"] for request in requests})
        native_by_sample = {
            sample_id: replay.replay(
                samples[sample_id],
                "measure=native|staff=native",
                next(
                    item["native_probability"]
                    for item in validation["joint_geometry"][scope]["samples"]
                    if item["sample_id"] == sample_id
                ),
            )
            for sample_id in crossing_sample_ids
        }
        rows = []
        for index, request in enumerate(requests):
            row = replay.replay(request["sample"], request["variant"], request["probability"])
            row["threshold_crossings"] = request["threshold_crossings"]
            rows.append(row)
            if (index + 1) % 100 == 0:
                print(f"production replay {scope}: {index + 1}/{len(requests)}", flush=True)
        scope_outputs[scope] = {
            "request_count": len(requests),
            "native": native_by_sample,
            "summary": _summarize_replay(requests, native_by_sample, rows),
            "rows": rows,
        }

    dpi_outputs = {}
    for scope in ("primary", "controls"):
        requests, native_requests = _dpi_requests(validation, samples, scope)
        native_by_sample = {
            sample_id: replay.replay_dpi(item["sample"], item["scale"], item["probability"])
            for sample_id, item in native_requests.items()
        }
        rows = []
        for index, request in enumerate(requests):
            row = replay.replay_dpi(request["sample"], request["scale"], request["probability"])
            row["threshold_crossings"] = request["threshold_crossings"]
            rows.append(row)
            if (index + 1) % 100 == 0:
                print(f"DPI production replay {scope}: {index + 1}/{len(requests)}", flush=True)
        dpi_outputs[scope] = {
            "request_count": len(requests),
            "native": native_by_sample,
            "summary": _summarize_replay(requests, native_by_sample, rows),
            "rows": rows,
        }

    output = {
        "provenance": {
            "git_head": _git_head(),
            "config_sha256": sha256_file(args.config),
            "final_validation_sha256": sha256_file(args.final_validation),
            "full_primary_sha256": sha256_file(args.full_primary),
            "full_controls_sha256": sha256_file(args.full_controls),
            "runtime": {
                "python": platform.python_version(),
                "opencv": cv2.__version__,
                "torch": torch.__version__,
                "rapidocr_provider_mode": "auto",
                "rapidocr_providers": providers,
            },
        },
        "contract": {
            "main_threshold": 0.5,
            "rescue_threshold": 0.1,
            "rotation_tta": False,
            "production_policy_source": "src/measure_numbering/mmr.py::MMRProcessor",
            "joint_measure_variants": 31,
            "joint_staff_variants": 25,
            "joint_variants_per_sample": 775,
        },
        "baseline_joint": {"primary": baseline_primary, "controls": baseline_controls},
        "candidate_joint": {
            "primary": {
                key: validation["joint_geometry"]["primary"][key]
                for key in ("sample_count", "variants_per_sample", "main", "rescue", "samples")
            },
            "controls": {
                key: validation["joint_geometry"]["controls"][key]
                for key in ("sample_count", "variants_per_sample", "main", "rescue", "samples")
            },
        },
        "production_replay": scope_outputs,
        "coherent_dpi_production_replay": dpi_outputs,
        "rapidocr_cache": {
            "engine_calls": cached_rapidocr.calls,
            "content_cache_hits": cached_rapidocr.cache_hits,
            "decision_cache_entries": len(replay.decision_cache),
        },
        "elapsed_seconds": time.perf_counter() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--acceptance-manifest", type=Path, required=True)
    parser.add_argument("--full-model", type=Path, required=True)
    parser.add_argument("--staff-model", type=Path, required=True)
    parser.add_argument("--fusion-model", type=Path, required=True)
    parser.add_argument("--final-validation", type=Path, required=True)
    parser.add_argument("--primary-manifest", type=Path, required=True)
    parser.add_argument("--controls-manifest", type=Path, required=True)
    parser.add_argument("--full-primary", type=Path, required=True)
    parser.add_argument("--full-controls", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


if __name__ == "__main__":
    result = run(build_parser().parse_args())
    print(
        json.dumps(
            {
                "baseline_joint": {
                    scope: {
                        "main": value["main"],
                        "rescue": value["rescue"],
                    }
                    for scope, value in result["baseline_joint"].items()
                },
                "production_replay": {
                    scope: value["summary"] for scope, value in result["production_replay"].items()
                },
                "coherent_dpi_production_replay": {
                    scope: value["summary"]
                    for scope, value in result["coherent_dpi_production_replay"].items()
                },
                "rapidocr_cache": result["rapidocr_cache"],
                "elapsed_seconds": result["elapsed_seconds"],
            },
            indent=2,
        )
    )
