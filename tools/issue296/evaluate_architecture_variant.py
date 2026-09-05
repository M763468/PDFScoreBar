#!/usr/bin/env python3
"""Evaluate one clean Issue #296 architecture on validation and full68.

Diagnostic-only. The production checkpoint is never used for inference here;
retained production artifacts are only the control side of the existing full68
regression evaluator.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

import experiments.cnn_classifier.train as trainer
import tools.issue296.evaluate_clean_full68 as full68
from tools.issue296.architecture_model_factory import load_checkpoint, parameter_count

ROOT = Path(__file__).resolve().parents[2]


def calibrate_threshold(
    checkpoint: Path,
    model_name: str,
    dataset_root: Path,
    batch_size: int,
) -> dict:
    device = trainer.DEVICE
    model = load_checkpoint(checkpoint, model_name, device)
    val_dataset = trainer.BarlineDataset(
        dataset_root / "splits/val/tp",
        dataset_root / "splits/val/fp",
        transform=trainer.get_cpu_transforms([256, 128], "val"),
    )
    loader = DataLoader(
        val_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=4,
        pin_memory=True,
        persistent_workers=True,
        prefetch_factor=2,
    )
    gpu_norm = trainer.get_gpu_transforms("val").to(device)
    probs = []
    labels = []
    with torch.no_grad():
        for inputs, batch_labels in loader:
            inputs = inputs.to(device)
            batch_labels = batch_labels.to(device).unsqueeze(1)
            inputs = gpu_norm(inputs)
            with torch.amp.autocast("cuda", enabled=(device.type == "cuda")):
                outputs = model(inputs)
            probs.append(torch.sigmoid(outputs).cpu())
            labels.append(batch_labels.cpu())
    probs_t = torch.cat(probs)
    labels_t = torch.cat(labels)

    rows = []
    best = None
    for threshold in np.arange(0.10, 0.95, 0.05):
        preds = (probs_t > float(threshold)).float()
        tp = int(((preds == 1) & (labels_t == 1)).sum().item())
        fp = int(((preds == 1) & (labels_t == 0)).sum().item())
        fn = int(((preds == 0) & (labels_t == 1)).sum().item())
        tn = int(((preds == 0) & (labels_t == 0)).sum().item())
        precision = tp / (tp + fp + 1e-12)
        recall = tp / (tp + fn + 1e-12)
        f1 = 2 * precision * recall / (precision + recall + 1e-12)
        row = {
            "threshold": round(float(threshold), 10),
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }
        rows.append(row)
        if best is None or f1 > best["f1"]:
            best = row
    assert best is not None
    return {"best": best, "rows": rows, "val_count": len(val_dataset)}


def benchmark(checkpoint: Path, model_name: str, batch_size: int = 64) -> dict:
    device = trainer.DEVICE
    model = load_checkpoint(checkpoint, model_name, device)
    params = parameter_count(model)
    inputs = torch.rand(batch_size, 3, 256, 128, device=device)
    if device.type == "cuda":
        torch.cuda.synchronize()
    with torch.no_grad():
        for _ in range(10):
            _ = model(inputs)
        if device.type == "cuda":
            torch.cuda.synchronize()
        samples = []
        for _ in range(30):
            start = time.perf_counter()
            _ = model(inputs)
            if device.type == "cuda":
                torch.cuda.synchronize()
            samples.append(time.perf_counter() - start)
    median = float(np.median(samples))
    return {
        "device": str(device),
        "parameter_count": params,
        "batch_size": batch_size,
        "median_batch_seconds": median,
        "median_candidates_per_second": batch_size / median if median > 0 else None,
    }


def run_full68(checkpoint: Path, model_name: str, threshold: float, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    full68.CLEAN_CKPT = checkpoint
    full68.OUT = out
    full68.THRESHOLD = float(threshold)

    def _loader(path, _ignored_model_name="resnet18"):
        return load_checkpoint(path, model_name, full68.DEVICE)

    full68.get_model = _loader
    rc = full68.main()
    if rc not in (0, None):
        raise RuntimeError(f"full68 evaluator returned {rc}")
    result = json.loads((out / "clean_full68_summary.json").read_text(encoding="utf-8"))
    p3 = result["p3"]
    target = result.get("target_x580_acceptance_delta")
    clean = result["clean"]
    gate = (
        result.get("control_reproduces_canonical_contract") is True
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
        "control": result["control"],
        "clean": clean,
        "delta_vs_control": result["delta_vs_control"],
        "target_x580_acceptance_delta": target,
        "p007_known_fp_acceptance_deltas": result.get("p007_known_fp_acceptance_deltas"),
        "acceptance_delta_count": result.get("acceptance_delta_count"),
        "p3": p3,
        "residuals": result.get("residuals", []),
        "detector_gate_pass": gate,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=256)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    calibration = calibrate_threshold(
        args.checkpoint, args.model_name, args.dataset_root, args.batch_size
    )
    val_threshold = float(calibration["best"]["threshold"])
    fixed = run_full68(
        args.checkpoint,
        args.model_name,
        0.1,
        args.output / "full68_threshold_0p1",
    )
    calibrated = (
        fixed
        if abs(val_threshold - 0.1) < 1e-12
        else run_full68(
            args.checkpoint,
            args.model_name,
            val_threshold,
            args.output / "full68_val_threshold",
        )
    )
    payload = {
        "schema_version": "issue296.clean_architecture_variant.v1",
        "model_name": args.model_name,
        "checkpoint": str(args.checkpoint),
        "dataset_root": str(args.dataset_root),
        "training_label_policy": "corrected current canonical labels only",
        "production_checkpoint_used_for_inference": False,
        "validation_calibration": calibration,
        "benchmark": benchmark(args.checkpoint, args.model_name),
        "full68_fixed_0p1": fixed,
        "full68_val_calibrated": calibrated,
        "any_detector_gate_pass": (
            fixed["detector_gate_pass"] or calibrated["detector_gate_pass"]
        ),
    }
    out = args.output / "architecture_variant_summary.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"RESULT={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
