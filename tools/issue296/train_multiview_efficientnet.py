#!/usr/bin/env python3
"""Train the Issue #296 shared EfficientNet-B0 tight/context classifier.

Uses only the corrected clean-v6 labels and torchvision ImageNet initialization.
No historical PDFScoreBar checkpoint is loaded.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch import nn, optim
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from tqdm import tqdm

import experiments.cnn_classifier.train as trainer
from tools.issue296.multiview_model import build_multiview_model

THRESHOLDS = [0.001, 0.002, 0.005, 0.01, 0.02, 0.03, 0.05, 0.075, 0.1, 0.15, 0.2, 0.3, 0.5, 0.7]
LAZY_NEUTRAL_CONTEXT = "lazy_neutral_padded_tight_no_extra_context"


def neutral_square_pad(image: Image.Image) -> Image.Image:
    """White-pad a tight RGB crop to square without another disk read."""
    width, height = image.size
    side = max(width, height)
    canvas = Image.new("RGB", (side, side), (255, 255, 255))
    canvas.paste(image, ((side - width) // 2, (side - height) // 2))
    return canvas


class MultiViewDataset(Dataset):
    def __init__(self, metadata: Path, split: str, training: bool) -> None:
        with metadata.open(newline="", encoding="utf-8") as handle:
            self.rows = [row for row in csv.DictReader(handle) if row["split"] == split]
        self.labels = [int(row["label"]) for row in self.rows]
        mode = "train" if training else "val"
        self.tight_transform = trainer.get_cpu_transforms([256, 128], mode)
        self.context_transform = trainer.get_cpu_transforms([256, 256], mode)

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int):
        row = self.rows[index]
        with Image.open(row["tight_path"]) as handle:
            tight = handle.convert("RGB")

        if row.get("context_policy") == LAZY_NEUTRAL_CONTEXT:
            context = neutral_square_pad(tight)
        else:
            context_path = row.get("context_path", "")
            if not context_path:
                raise RuntimeError(f"missing context_path for row: {row}")
            with Image.open(context_path) as handle:
                context = handle.convert("RGB")

        return (
            self.tight_transform(tight),
            self.context_transform(context),
            torch.tensor(float(row["label"]), dtype=torch.float32),
        )


def metrics_from_probs(probs: torch.Tensor, labels: torch.Tensor) -> dict:
    best = None
    rows = []
    for threshold in THRESHOLDS:
        preds = (probs > threshold).float()
        tp = int(((preds == 1) & (labels == 1)).sum().item())
        fp = int(((preds == 1) & (labels == 0)).sum().item())
        fn = int(((preds == 0) & (labels == 1)).sum().item())
        tn = int(((preds == 0) & (labels == 0)).sum().item())
        precision = tp / (tp + fp + 1e-12)
        recall = tp / (tp + fn + 1e-12)
        f1 = 2 * precision * recall / (precision + recall + 1e-12)
        row = {
            "threshold": threshold,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }
        rows.append(row)
        if best is None or f1 > best["f1"] or (
            abs(f1 - best["f1"]) < 1e-12 and threshold > best["threshold"]
        ):
            best = row
    assert best is not None
    return {"best": best, "rows": rows}


def evaluate(model, loader, gpu_val, device, amp: bool) -> tuple[float, dict]:
    model.eval()
    gpu_val.eval()
    criterion = nn.BCEWithLogitsLoss()
    loss_sum = 0.0
    probs = []
    labels_all = []
    with torch.no_grad():
        for tight, context, labels in loader:
            tight = gpu_val(tight.to(device, non_blocking=True))
            context = gpu_val(context.to(device, non_blocking=True))
            labels = labels.to(device, non_blocking=True).unsqueeze(1)
            with torch.amp.autocast("cuda", enabled=amp and device.type == "cuda"):
                logits = model(tight, context)
                loss = criterion(logits, labels)
            loss_sum += float(loss.item())
            probs.append(torch.sigmoid(logits).cpu())
            labels_all.append(labels.cpu())
    probability = torch.cat(probs)
    labels = torch.cat(labels_all)
    return loss_sum / max(1, len(loader)), metrics_from_probs(probability, labels)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--seed", type=int, default=44)
    parser.add_argument("--num-workers", type=int, default=8)
    parser.add_argument("--compile", action="store_true")
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    metadata = args.dataset / "metadata/samples.csv"
    if not metadata.is_file():
        raise FileNotFoundError(metadata)
    args.work_dir.mkdir(parents=True, exist_ok=True)

    train_ds = MultiViewDataset(metadata, "train", True)
    val_ds = MultiViewDataset(metadata, "val", False)
    n_pos = sum(train_ds.labels)
    n_neg = len(train_ds.labels) - n_pos
    if not n_pos or not n_neg:
        raise RuntimeError(f"invalid train balance: pos={n_pos} neg={n_neg}")
    weights = torch.tensor(
        [1.0 / n_pos if label == 1 else 1.0 / n_neg for label in train_ds.labels],
        dtype=torch.float,
    )
    sampler = WeightedRandomSampler(weights, len(weights))
    train_loader = DataLoader(
        train_ds,
        batch_size=args.batch_size,
        sampler=sampler,
        num_workers=args.num_workers,
        pin_memory=True,
        persistent_workers=args.num_workers > 0,
        prefetch_factor=2 if args.num_workers > 0 else None,
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
        pin_memory=True,
        persistent_workers=args.num_workers > 0,
        prefetch_factor=2 if args.num_workers > 0 else None,
    )

    device = trainer.DEVICE
    model = build_multiview_model(pretrained=True).to(device)
    if args.compile:
        model = torch.compile(model, mode="reduce-overhead")
    gpu_train = trainer.get_gpu_transforms("train", sp_density=0.02, sp_p=0.3).to(device)
    gpu_val = trainer.get_gpu_transforms("val").to(device)
    criterion = nn.BCEWithLogitsLoss()
    optimizer = optim.AdamW(
        model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay
    )
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")

    best_f1 = -1.0
    history = []
    best_path = args.work_dir / "cnn_classifier_best.pth"
    for epoch in range(args.epochs):
        model.train()
        gpu_train.train()
        loss_sum = 0.0
        for tight, context, labels in tqdm(
            train_loader, desc=f"Epoch {epoch + 1}/{args.epochs} [Train]"
        ):
            tight = gpu_train(tight.to(device, non_blocking=True))
            context = gpu_train(context.to(device, non_blocking=True))
            labels = labels.to(device, non_blocking=True).unsqueeze(1)
            optimizer.zero_grad(set_to_none=True)
            with torch.amp.autocast("cuda", enabled=device.type == "cuda"):
                logits = model(tight, context)
                loss = criterion(logits, labels)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            loss_sum += float(loss.item())

        val_loss, val_metrics = evaluate(
            model, val_loader, gpu_val, device, device.type == "cuda"
        )
        selected = val_metrics["best"]
        row = {
            "epoch": epoch + 1,
            "train_loss": loss_sum / max(1, len(train_loader)),
            "val_loss": val_loss,
            "val_selected": selected,
        }
        history.append(row)
        print(json.dumps(row, ensure_ascii=False))
        if selected["f1"] > best_f1:
            best_f1 = selected["f1"]
            torch.save(model.state_dict(), best_path)
            print(f"saved best checkpoint: {best_path}")
        scheduler.step()

    last_path = args.work_dir / "cnn_classifier_last.pth"
    torch.save(model.state_dict(), last_path)
    summary = {
        "schema_version": "issue296.multiview_training.v2",
        "dataset": str(args.dataset),
        "initialization": "torchvision ImageNet EfficientNet-B0 only",
        "production_checkpoint_used": False,
        "shared_backbone": True,
        "tight_size": [256, 128],
        "context_size": [256, 256],
        "deepscores_context": "lazy neutral white-pad from already-loaded tight image",
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "learning_rate": args.learning_rate,
        "weight_decay": args.weight_decay,
        "seed": args.seed,
        "train_pos": n_pos,
        "train_neg": n_neg,
        "best_val_f1": best_f1,
        "history": history,
        "best_checkpoint": str(best_path),
    }
    (args.work_dir / "training_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (args.work_dir / "TRAIN_COMPLETE").write_text("ok\n", encoding="utf-8")
    print(f"RESULT={args.work_dir / 'training_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
