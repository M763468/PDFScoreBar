#!/usr/bin/env python3
"""Compare full-only and bounded dual-view classifier-stage cost on the full corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence

import cv2
import torch
import torch.nn as nn

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.mmr_training.issue332.dual_view_fusion import (
    MonotonicLogitFusion,
    _load_encoders,
    _tensor,
    sha256_file,
)
from tools.mmr_training.issue332.staff_view import crop_source_bbox, staff_relative_roi_bboxes
from tools.mmr_training.issue332_geometry_benchmark import crop_measure


def _git_head() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _resolve_image(sample: dict[str, Any], manifest_path: Path) -> Path:
    path = Path(str(sample["image_path"]))
    return path if path.is_absolute() else (manifest_path.parent / path).resolve()


def _load_fusion(path: Path) -> MonotonicLogitFusion:
    payload = torch.load(path, map_location="cpu", weights_only=True)
    model = MonotonicLogitFusion()
    model.load_state_dict(payload["fusion_state_dict"])
    return model.eval()


def _warmup(
    samples: Sequence[dict[str, Any]],
    manifest_path: Path,
    full_model: nn.Module,
    staff_model: nn.Module | None,
    device: torch.device,
    count: int,
) -> None:
    for sample in samples[:count]:
        image = cv2.imread(str(_resolve_image(sample, manifest_path)), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(sample["image_path"])
        full_tensor = _tensor(crop_measure(image, sample["bbox"], margin_px=20)).unsqueeze(0)
        with torch.inference_mode():
            full_model(full_tensor.to(device))
            if staff_model is not None:
                staff_tensors = torch.stack(
                    [
                        _tensor(crop_source_bbox(image, roi))
                        for roi in staff_relative_roi_bboxes(sample)
                    ]
                )
                staff_model(staff_tensors.to(device)).max()
    torch.cuda.synchronize(device)


def _summarize(values: Sequence[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "mean_ms": statistics.fmean(values),
        "median_ms": statistics.median(values),
        "p95_ms": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
        "max_ms": max(values),
    }


def _benchmark_route(
    samples: Sequence[dict[str, Any]],
    manifest_path: Path,
    full_model: nn.Module,
    staff_model: nn.Module | None,
    fusion: MonotonicLogitFusion | None,
    device: torch.device,
    warmup_count: int,
) -> dict[str, Any]:
    _warmup(samples, manifest_path, full_model, staff_model, device, warmup_count)
    torch.cuda.reset_peak_memory_stats(device)
    current_path = None
    image = None
    timings = []
    by_staff_count: dict[int, list[float]] = {}
    probabilities = []
    classifier_started = time.perf_counter()
    page_load_seconds = 0.0
    with torch.inference_mode():
        for index, sample in enumerate(samples):
            image_path = _resolve_image(sample, manifest_path)
            if image_path != current_path:
                load_started = time.perf_counter()
                image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
                page_load_seconds += time.perf_counter() - load_started
                if image is None:
                    raise FileNotFoundError(image_path)
                current_path = image_path
            assert image is not None
            started = time.perf_counter()
            full_tensor = _tensor(crop_measure(image, sample["bbox"], margin_px=20))
            full_logit = full_model(full_tensor.unsqueeze(0).to(device)).reshape(())
            if staff_model is None:
                staff_count = 0
                output = full_logit
            else:
                staff_rois = staff_relative_roi_bboxes(sample)
                staff_count = len(staff_rois)
                staff_tensors = torch.stack(
                    [_tensor(crop_source_bbox(image, roi)) for roi in staff_rois]
                )
                staff_logit = staff_model(staff_tensors.to(device)).reshape(-1).max()
                assert fusion is not None
                features = torch.stack((full_logit, staff_logit)).reshape(1, 2)
                output = fusion(features).reshape(())
            probability = float(torch.sigmoid(output).cpu())
            torch.cuda.synchronize(device)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            timings.append(elapsed_ms)
            by_staff_count.setdefault(staff_count, []).append(elapsed_ms)
            probabilities.append(probability)
            if (index + 1) % 500 == 0:
                print(f"runtime route: {index + 1}/{len(samples)}")
    total_elapsed = time.perf_counter() - classifier_started - page_load_seconds
    parameter_count = sum(parameter.numel() for parameter in full_model.parameters())
    if staff_model is not None:
        parameter_count += sum(parameter.numel() for parameter in staff_model.parameters())
        assert fusion is not None
        parameter_count += sum(parameter.numel() for parameter in fusion.parameters())
    return {
        "semantic_measures": len(samples),
        "classifier_stage_elapsed_seconds_excluding_page_io": total_elapsed,
        "page_load_seconds_excluded": page_load_seconds,
        "timing": _summarize(timings),
        "by_staff_count": {
            str(count): {"samples": len(values), **_summarize(values)}
            for count, values in sorted(by_staff_count.items())
        },
        "peak_cuda_allocated_bytes": torch.cuda.max_memory_allocated(device),
        "peak_cuda_reserved_bytes": torch.cuda.max_memory_reserved(device),
        "parameter_count": parameter_count,
        "parameter_memory_fp32_bytes": parameter_count * 4,
        "probability_checksum_sha256": hashlib.sha256(
            json.dumps(probabilities, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    config = json.loads(args.config.read_text(encoding="utf-8"))
    for key, path in (
        ("manifest_sha256", args.manifest),
        ("full_model_sha256", args.full_model),
        ("staff_model_sha256", args.staff_model),
        ("fusion_model_sha256", args.fusion_model),
    ):
        actual = sha256_file(path)
        if actual != config[key]:
            raise ValueError(f"{key} mismatch: expected {config[key]}, got {actual}")
    samples = json.loads(args.manifest.read_text(encoding="utf-8"))["samples"]
    device = torch.device(args.device)

    full_model, _unused_staff = _load_encoders(args.full_model, args.staff_model, device)
    del _unused_staff
    torch.cuda.empty_cache()
    baseline = _benchmark_route(
        samples, args.manifest, full_model, None, None, device, args.warmup_count
    )
    del full_model
    torch.cuda.empty_cache()

    full_model, staff_wrapper = _load_encoders(args.full_model, args.staff_model, device)
    fusion = _load_fusion(args.fusion_model).to(device)
    dual = _benchmark_route(
        samples,
        args.manifest,
        full_model,
        staff_wrapper.encoder,
        fusion,
        device,
        args.warmup_count,
    )
    output = {
        "provenance": {
            "git_head": _git_head(),
            "config_sha256": sha256_file(args.config),
            "manifest_sha256": sha256_file(args.manifest),
            "full_model_sha256": sha256_file(args.full_model),
            "staff_model_sha256": sha256_file(args.staff_model),
            "fusion_model_sha256": sha256_file(args.fusion_model),
            "device": torch.cuda.get_device_name(device),
            "torch": torch.__version__,
            "python": platform.python_version(),
            "warmup_measures": args.warmup_count,
            "page_io_excluded": True,
            "rapidocr_involved": False,
        },
        "baseline_full_measure": baseline,
        "bounded_dual_view": dual,
        "comparison": {
            "mean_latency_ratio": dual["timing"]["mean_ms"] / baseline["timing"]["mean_ms"],
            "total_classifier_elapsed_ratio": dual[
                "classifier_stage_elapsed_seconds_excluding_page_io"
            ]
            / baseline["classifier_stage_elapsed_seconds_excluding_page_io"],
            "peak_allocated_ratio": dual["peak_cuda_allocated_bytes"]
            / baseline["peak_cuda_allocated_bytes"],
            "peak_reserved_ratio": dual["peak_cuda_reserved_bytes"]
            / baseline["peak_cuda_reserved_bytes"],
            "parameter_memory_ratio": dual["parameter_memory_fp32_bytes"]
            / baseline["parameter_memory_fp32_bytes"],
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--full-model", type=Path, required=True)
    parser.add_argument("--staff-model", type=Path, required=True)
    parser.add_argument("--fusion-model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--warmup-count", type=int, default=20)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    return parser


if __name__ == "__main__":
    print(json.dumps(run(build_parser().parse_args()), indent=2))
