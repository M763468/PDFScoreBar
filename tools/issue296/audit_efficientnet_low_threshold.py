#!/usr/bin/env python3
"""Temporary Issue #296 audit for EfficientNet-B0 calibration below 0.1.

Diagnostic-only; delete before PR preparation.

This does not tune against x=580 or full68.  It chooses one threshold strictly
from the retained clean-v6 validation split, then evaluates that frozen choice
on full68.  The historical production checkpoint is never used for inference;
retained production artifacts are only the control side of the canonical gate.
"""
from __future__ import annotations

import json
from pathlib import Path

import torch
from torch.utils.data import DataLoader

import experiments.cnn_classifier.train as trainer
from tools.issue296.architecture_model_factory import load_checkpoint
from tools.issue296.evaluate_architecture_variant import run_full68

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "datasets/issue296_clean_lineage/v6"
CHECKPOINT = (
    ROOT
    / "logs/cnn_barline_classification/issue296_arch_efficientnet_b0_v6clean/"
    "cnn_classifier_best.pth"
)
OUT = ROOT / "logs/issue296/diagnostic_14_efficientnet_low_threshold"

# Fixed before looking at full68.  The previous screen searched only >=0.1 and
# landed exactly on that lower bound, so this extends calibration downward.
THRESHOLDS = [
    0.001,
    0.002,
    0.005,
    0.01,
    0.02,
    0.03,
    0.05,
    0.075,
    0.10,
    0.15,
    0.20,
]


def score_validation() -> tuple[torch.Tensor, torch.Tensor]:
    device = trainer.DEVICE
    model = load_checkpoint(CHECKPOINT, "efficientnet_b0", device)
    dataset = trainer.BarlineDataset(
        DATASET / "splits/val/tp",
        DATASET / "splits/val/fp",
        transform=trainer.get_cpu_transforms([256, 128], "val"),
    )
    loader = DataLoader(
        dataset,
        batch_size=256,
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
            inputs = gpu_norm(inputs.to(device))
            with torch.amp.autocast("cuda", enabled=(device.type == "cuda")):
                logits = model(inputs)
            probs.append(torch.sigmoid(logits).cpu().reshape(-1))
            labels.append(batch_labels.cpu().reshape(-1))
    return torch.cat(probs), torch.cat(labels)


def metrics(probs: torch.Tensor, labels: torch.Tensor, threshold: float) -> dict:
    preds = probs > float(threshold)
    pos = labels > 0.5
    tp = int((preds & pos).sum().item())
    fp = int((preds & ~pos).sum().item())
    fn = int((~preds & pos).sum().item())
    tn = int((~preds & ~pos).sum().item())
    precision = tp / (tp + fp + 1e-12)
    recall = tp / (tp + fn + 1e-12)
    f1 = 2 * precision * recall / (precision + recall + 1e-12)
    return {
        "threshold": float(threshold),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def main() -> int:
    if not CHECKPOINT.is_file():
        raise FileNotFoundError(CHECKPOINT)
    for split in ("train", "val"):
        for kind in ("tp", "fp"):
            path = DATASET / "splits" / split / kind
            if not path.is_dir():
                raise FileNotFoundError(path)

    OUT.mkdir(parents=True, exist_ok=True)
    probs, labels = score_validation()
    rows = [metrics(probs, labels, threshold) for threshold in THRESHOLDS]

    # Primary key: validation F1.  Conservative tie-breaker: higher threshold,
    # so the full68 target/residuals cannot influence threshold selection.
    best = max(rows, key=lambda row: (row["f1"], row["threshold"]))
    selected = float(best["threshold"])

    full68_result = run_full68(
        CHECKPOINT,
        "efficientnet_b0",
        selected,
        OUT / "full68_selected_threshold",
    )

    payload = {
        "schema_version": "issue296.efficientnet_low_threshold_calibration.v1",
        "checkpoint": str(CHECKPOINT),
        "dataset": str(DATASET),
        "production_checkpoint_used_for_inference": False,
        "selection_policy": (
            "predeclared threshold grid; maximize clean-v6 validation F1; "
            "tie-break toward higher threshold; no x580/full68 tuning"
        ),
        "threshold_grid": THRESHOLDS,
        "validation_rows": rows,
        "validation_selected": best,
        "full68_selected": full68_result,
    }
    out = OUT / "efficientnet_low_threshold_summary.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"RESULT={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
