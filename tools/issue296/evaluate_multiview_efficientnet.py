#!/usr/bin/env python3
"""Validate and full68-audit the Issue #296 multi-view EfficientNet candidate."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image
from torch.utils.data import DataLoader
from torchvision import transforms

import experiments.cnn_classifier.train as trainer
import tools.issue296.evaluate_clean_full68 as full68
from tools.issue296.multiview_model import load_multiview_checkpoint, parameter_count
from tools.issue296.train_multiview_efficientnet import MultiViewDataset, THRESHOLDS, metrics_from_probs

TIGHT_SCALE = 3.0
TIGHT_ASPECT = 0.5
CONTEXT_ASPECT = 1.0
MIN_H = 48
MAX_H = 256
TIGHT_MIN_W = 16
TIGHT_MAX_W = 128
CONTEXT_MIN_W = 48
CONTEXT_MAX_W = 256


def validation_calibration(checkpoint: Path, dataset: Path, batch_size: int) -> dict:
    device = trainer.DEVICE
    model = load_multiview_checkpoint(checkpoint, device)
    ds = MultiViewDataset(dataset / "metadata/samples.csv", "val", False)
    loader = DataLoader(
        ds,
        batch_size=batch_size,
        shuffle=False,
        num_workers=4,
        pin_memory=True,
        persistent_workers=True,
        prefetch_factor=2,
    )
    gpu_val = trainer.get_gpu_transforms("val").to(device)
    gpu_val.eval()
    probs = []
    labels = []
    with torch.no_grad():
        for tight, context, batch_labels in loader:
            tight = gpu_val(tight.to(device, non_blocking=True))
            context = gpu_val(context.to(device, non_blocking=True))
            with torch.amp.autocast("cuda", enabled=device.type == "cuda"):
                logits = model(tight, context)
            probs.append(torch.sigmoid(logits).cpu())
            labels.append(batch_labels.unsqueeze(1))
    result = metrics_from_probs(torch.cat(probs), torch.cat(labels))
    result["val_count"] = len(ds)
    result["selection_policy"] = "maximize validation F1; tie-break toward higher threshold; no full68/x580 tuning"
    return result


def _candidate_views(image: np.ndarray, boxes: list[tuple[int, int, int, int]]):
    tight_tensors = []
    context_tensors = []
    to_tensor = transforms.ToTensor()
    for box in boxes:
        x1, y1, x2, y2 = box
        cx = int(round((x1 + x2) / 2))
        cy = int(round((y1 + y2) / 2))
        tight_w, tight_h = full68.crop_size_from_bbox(
            box,
            scale=TIGHT_SCALE,
            aspect_ratio=TIGHT_ASPECT,
            min_h=MIN_H,
            max_h=MAX_H,
            min_w=TIGHT_MIN_W,
            max_w=TIGHT_MAX_W,
        )
        context_w, context_h = full68.crop_size_from_bbox(
            box,
            scale=TIGHT_SCALE,
            aspect_ratio=CONTEXT_ASPECT,
            min_h=MIN_H,
            max_h=MAX_H,
            min_w=CONTEXT_MIN_W,
            max_w=CONTEXT_MAX_W,
        )
        tight_crop = full68.center_crop(image, cx, cy, tight_w, tight_h)
        context_crop = full68.center_crop(image, cx, cy, context_w, context_h)
        tight_pil = Image.fromarray(cv2.cvtColor(tight_crop, cv2.COLOR_BGR2RGB)).resize((128, 256), Image.BILINEAR)
        context_pil = Image.fromarray(cv2.cvtColor(context_crop, cv2.COLOR_BGR2RGB)).resize((256, 256), Image.BILINEAR)
        tight_tensors.append(to_tensor(tight_pil))
        context_tensors.append(to_tensor(context_pil))
    return tight_tensors, context_tensors


def score_boxes_multiview(image, boxes, model, _ignored_gpu_norm):
    if not boxes:
        return []
    device = trainer.DEVICE
    gpu_val = trainer.get_gpu_transforms("val").to(device)
    gpu_val.eval()
    tight_tensors, context_tensors = _candidate_views(image, boxes)
    scores = []
    for start in range(0, len(boxes), 32):
        tight = torch.stack(tight_tensors[start : start + 32]).to(device)
        context = torch.stack(context_tensors[start : start + 32]).to(device)
        tight = gpu_val(tight)
        context = gpu_val(context)
        with torch.no_grad(), torch.amp.autocast("cuda", enabled=device.type == "cuda"):
            chunk = torch.sigmoid(model(tight, context)).cpu().numpy().reshape(-1)
        scores.extend(float(value) for value in chunk)
    return scores


def run_full68(checkpoint: Path, threshold: float, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    full68.CLEAN_CKPT = checkpoint
    full68.OUT = out
    full68.THRESHOLD = float(threshold)
    full68.get_model = lambda path, _name="resnet18": load_multiview_checkpoint(path, full68.DEVICE)
    full68.score_boxes = score_boxes_multiview
    rc = full68.main()
    if rc not in (0, None):
        raise RuntimeError(f"full68 evaluator returned {rc}")
    payload = json.loads((out / "clean_full68_summary.json").read_text(encoding="utf-8"))
    clean = payload["clean"]
    target = payload.get("target_x580_acceptance_delta")
    p3 = payload["p3"]
    gate = (
        payload.get("control_reproduces_canonical_contract") is True
        and target is not None
        and target.get("clean_accept") is False
        and clean["tp"] >= 3565
        and clean["hard_fp"] <= 2
        and clean["fn"] <= 2
        and p3["pair_count"] == 51
        and p3["clean_complete_pairs"] == 51
    )
    return {
        "threshold": float(threshold),
        "control": payload["control"],
        "clean": clean,
        "delta_vs_control": payload["delta_vs_control"],
        "target_x580_acceptance_delta": target,
        "p007_known_fp_acceptance_deltas": payload.get("p007_known_fp_acceptance_deltas"),
        "acceptance_delta_count": payload.get("acceptance_delta_count"),
        "p3": p3,
        "residuals": payload.get("residuals", []),
        "detector_gate_pass": gate,
    }


def benchmark(checkpoint: Path, batch_size: int = 32) -> dict:
    device = trainer.DEVICE
    model = load_multiview_checkpoint(checkpoint, device)
    tight = torch.rand(batch_size, 3, 256, 128, device=device)
    context = torch.rand(batch_size, 3, 256, 256, device=device)
    with torch.no_grad():
        for _ in range(8):
            _ = model(tight, context)
        if device.type == "cuda":
            torch.cuda.synchronize()
        timings = []
        for _ in range(20):
            start = time.perf_counter()
            _ = model(tight, context)
            if device.type == "cuda":
                torch.cuda.synchronize()
            timings.append(time.perf_counter() - start)
    median = float(np.median(timings))
    return {
        "device": str(device),
        "parameter_count": parameter_count(model),
        "batch_size": batch_size,
        "median_batch_seconds": median,
        "median_candidates_per_second": batch_size / median,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    calibration = validation_calibration(args.checkpoint, args.dataset, 128)
    selected_threshold = float(calibration["best"]["threshold"])
    fixed = run_full68(args.checkpoint, 0.1, args.output / "full68_threshold_0p1")
    selected = fixed if abs(selected_threshold - 0.1) < 1e-12 else run_full68(
        args.checkpoint,
        selected_threshold,
        args.output / "full68_validation_selected",
    )
    report = {
        "schema_version": "issue296.multiview_efficientnet_eval.v1",
        "checkpoint": str(args.checkpoint),
        "dataset": str(args.dataset),
        "design": {
            "backbone": "shared EfficientNet-B0",
            "tight_view": "256x128 current crop contract",
            "context_view": "256x256 same vertical FOV, 2x horizontal FOV",
            "fusion": "concatenated pooled features then dropout + linear binary head",
            "initialization": "torchvision ImageNet only",
            "production_checkpoint_used_for_inference": False,
            "deepscores_context": "neutral white-padded tight fallback because original page coordinates are absent",
        },
        "threshold_grid": THRESHOLDS,
        "validation_calibration": calibration,
        "benchmark": benchmark(args.checkpoint),
        "full68_fixed_0p1": fixed,
        "full68_validation_selected": selected,
        "any_detector_gate_pass": fixed["detector_gate_pass"] or selected["detector_gate_pass"],
    }
    out = args.output / "multiview_efficientnet_summary.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"RESULT={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
