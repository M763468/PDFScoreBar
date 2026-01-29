import argparse
import os
import random
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import yaml
from PIL import Image, ImageFilter
from torch.utils.data import DataLoader, Dataset, Subset, WeightedRandomSampler
from torch.utils.tensorboard import SummaryWriter
from torchvision import models, transforms
from tqdm import tqdm

# --- Configuration ---
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
DEFAULT_WORK_DIR = Path("logs/cnn_barline_classification/training")
DATASET_ROOT = Path(os.getenv("CNN_DATASET_ROOT", "/mnt/s/dev/datasets/cnn_classifier_v1"))
TRAIN_SPLIT_DIR = DATASET_ROOT / "splits" / "train"
VAL_SPLIT_DIR = DATASET_ROOT / "splits" / "val"


# --- GPU Augmentation ---
class GPUSaltPepperNoise(nn.Module):
    def __init__(self, density=0.01, p=0.5):
        super().__init__()
        self.density = density
        self.p = p

    def forward(self, x):
        # x: (B, C, H, W) Tensor
        if self.training and torch.rand(1).item() < self.p:
            noise = torch.rand_like(x)
            # Salt (1.0)
            salt_mask = noise < (self.density / 2)
            x = torch.where(salt_mask, torch.tensor(1.0, device=x.device), x)
            # Pepper (0.0)
            pepper_mask = (noise >= (self.density / 2)) & (noise < self.density)
            x = torch.where(pepper_mask, torch.tensor(0.0, device=x.device), x)
        return x


class GPUNormalize(nn.Module):
    def __init__(self, mean, std):
        super().__init__()
        self.register_buffer("mean", torch.tensor(mean).view(1, 3, 1, 1))
        self.register_buffer("std", torch.tensor(std).view(1, 3, 1, 1))

    def forward(self, x):
        return (x - self.mean) / self.std


# --- CPU Augmentation (Geometric / PIL only) ---
class GaussianBlur(object):
    """Adds fuzzy blur consistent with ink bleed or low res scan."""

    def __init__(self, radius_range=(0.1, 1.0), p=0.5):
        self.radius_min, self.radius_max = radius_range
        self.p = p

    def __call__(self, img):
        if random.random() < self.p:
            radius = random.uniform(self.radius_min, self.radius_max)
            return img.filter(ImageFilter.GaussianBlur(radius))
        return img

    def __repr__(self):
        return f"{self.__class__.__name__}(radius_range=({self.radius_min}, {self.radius_max}), p={self.p})"


def get_cpu_transforms(img_size, split="train"):
    # REMOVED: Normalize, SaltPepper (Moved to GPU)
    if split == "train":
        return transforms.Compose(
            [
                # Structural/Geometry
                transforms.RandomAffine(
                    degrees=2,  # Very slight rotation
                    translate=(0.0, 0.1),  # Vertical shift ONLY (max 10%)
                    scale=(0.95, 1.05),  # Slight scale
                    fill=255,  # White background
                ),
                # Texture/Degradation (PIL based)
                GaussianBlur(radius_range=(0.5, 1.5), p=0.3),
                transforms.ColorJitter(brightness=0.3, contrast=0.3),
                # Common
                transforms.Resize(tuple(img_size)),
                transforms.ToTensor(),  # Converts to [0, 1]
                # No Normalize here
            ]
        )
    else:
        return transforms.Compose(
            [
                transforms.Resize(tuple(img_size)),
                transforms.ToTensor(),
                # No Normalize here
            ]
        )


def get_gpu_transforms(split="train", sp_density=0.02, sp_p=0.3):
    transforms_list = []
    if split == "train":
        transforms_list.append(GPUSaltPepperNoise(density=sp_density, p=sp_p))

    transforms_list.append(GPUNormalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]))
    return nn.Sequential(*transforms_list)


# --- Dataset ---
class BarlineDataset(Dataset):
    def __init__(self, tp_dir, fp_dir, transform=None):
        self.tp_paths = sorted(list(tp_dir.glob("*.png")))
        self.fp_paths = sorted(list(fp_dir.glob("*.png")))
        self.all_paths = self.tp_paths + self.fp_paths
        # Labels: 1 for Barline, 0 for Not Barline
        self.labels = [1] * len(self.tp_paths) + [0] * len(self.fp_paths)
        self.transform = transform

        # Calculate weights for sampler
        self.n_tp = len(self.tp_paths)
        self.n_fp = len(self.fp_paths)

    def __len__(self):
        return len(self.all_paths)

    def __getitem__(self, idx):
        path = self.all_paths[idx]
        label = self.labels[idx]

        # Load image
        try:
            img = Image.open(path).convert("RGB")
        except Exception as e:
            print(f"Error loading {path}: {e}")
            img = Image.new("RGB", (128, 256), (0, 0, 0))

        if self.transform:
            img = self.transform(img)

        return img, torch.tensor(label, dtype=torch.float32)


# --- Model ---
def get_model(model_name="mobilenet_v3_small", pretrained=True):
    weights = "DEFAULT" if pretrained else None

    if model_name == "mobilenet_v3_small":
        model = models.mobilenet_v3_small(weights=weights)
        in_features = model.classifier[3].in_features
        model.classifier[3] = nn.Linear(in_features, 1)
    elif model_name == "resnet18":
        model = models.resnet18(weights=weights)
        in_features = model.fc.in_features
        model.fc = nn.Linear(in_features, 1)
    else:
        raise ValueError(f"Model {model_name} not supported.")

    return model


# --- Metrics ---
def calculate_metrics(outputs, labels, threshold=0.5):
    probs = torch.sigmoid(outputs)
    preds = (probs > threshold).float()

    tp = ((preds == 1) & (labels == 1)).sum().item()
    fp = ((preds == 1) & (labels == 0)).sum().item()
    fn = ((preds == 0) & (labels == 1)).sum().item()
    tn = ((preds == 0) & (labels == 0)).sum().item()

    return tp, fp, fn, tn


def find_optimal_threshold(model, val_loader, device, gpu_transform=None, amp=False):
    model.eval()
    all_probs = []
    all_labels = []

    with torch.no_grad():
        for inputs, labels in val_loader:
            inputs, labels = inputs.to(device), labels.to(device).unsqueeze(1)
            if gpu_transform:
                inputs = gpu_transform(inputs)

            with torch.amp.autocast("cuda", enabled=amp):
                outputs = model(inputs)
            probs = torch.sigmoid(outputs)
            all_probs.append(probs.cpu())
            all_labels.append(labels.cpu())

    all_probs = torch.cat(all_probs)
    all_labels = torch.cat(all_labels)

    best_f1 = 0
    best_thresh = 0.5

    for thresh in np.arange(0.1, 0.95, 0.05):
        preds = (all_probs > thresh).float()
        tp = ((preds == 1) & (all_labels == 1)).sum().item()
        fp = ((preds == 1) & (all_labels == 0)).sum().item()
        fn = ((preds == 0) & (all_labels == 1)).sum().item()

        precision = tp / (tp + fp + 1e-8)
        recall = tp / (tp + fn + 1e-8)
        f1 = 2 * precision * recall / (precision + recall + 1e-8)

        if f1 > best_f1:
            best_f1 = f1
            best_thresh = thresh

    return best_thresh, best_f1


# --- Training Loop ---
def get_args():
    DEFAULTS = {
        "epochs": 20,
        "batch_size": 32,
        "learning_rate": 1e-4,
        "img_size": [256, 128],
        "seed": 42,
        "model_name": "mobilenet_v3_small",
        "train_val_split": 0.8,
        "compile_mode": "reduce-overhead",
        "imbalance": "sampler",
        "freeze_backbone_epochs": 0,
        "sp_p": 0.3,
        "sp_density": 0.02,
        "weight_decay": 1e-2,
        "num_workers": 8,
        "prefetch_factor": 2,
        "save_interval": 0,
    }

    parser = argparse.ArgumentParser(description="Train a CNN for barline classification.")
    parser.add_argument("--config", type=str, default=None, help="Path to a config file.")
    parser.add_argument("--work-dir", type=str, help="Working directory for logs and models.")
    parser.add_argument("--tp-dir", type=str, help="Directory of true positive crops.")
    parser.add_argument("--fp-dir", type=str, help="Directory of false positive crops.")
    parser.add_argument(
        "--epochs",
        type=int,
        default=None,
        help=f"Number of training epochs (default: {DEFAULTS['epochs']}).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help=f"Batch size (default: {DEFAULTS['batch_size']}).",
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=None,
        help=f"Learning rate (default: {DEFAULTS['learning_rate']}).",
    )
    parser.add_argument(
        "--img-size",
        type=int,
        nargs=2,
        default=None,
        help=f"Image size (height, width) (default: {DEFAULTS['img_size']}).",
    )
    parser.add_argument(
        "--seed", type=int, default=None, help=f"Random seed (default: {DEFAULTS['seed']})."
    )
    parser.add_argument("--log-dir", type=str, help="Directory for TensorBoard logs.")
    parser.add_argument(
        "--model-name",
        type=str,
        default=None,
        help=f"Model name (default: {DEFAULTS['model_name']}).",
    )
    parser.add_argument(
        "--train-val-split",
        type=float,
        default=None,
        help=f"Train/validation split ratio (default: {DEFAULTS['train_val_split']}).",
    )
    parser.add_argument("--no-augment", action="store_true", help="Disable augmentation.")

    # New Arguments
    parser.add_argument(
        "--amp", action="store_true", help="Enable Automatic Mixed Precision (AMP)."
    )
    parser.add_argument("--compile", action="store_true", help="Enable torch.compile (PyTorch 2+).")
    parser.add_argument(
        "--compile-mode",
        type=str,
        default=None,
        help=f"torch.compile mode (default: {DEFAULTS['compile_mode']}).",
    )
    parser.add_argument(
        "--channels-last", action="store_true", help="Use Channels Last memory format."
    )
    parser.add_argument(
        "--imbalance",
        type=str,
        choices=["pos_weight", "sampler", "none"],
        default=None,
        help=f"Strategy for class imbalance (default: {DEFAULTS['imbalance']}).",
    )
    parser.add_argument(
        "--optimize-threshold", action="store_true", help="Find optimal threshold on validation."
    )
    parser.add_argument("--timing", action="store_true", help="Enable detailed timing profiling.")
    parser.add_argument(
        "--freeze-backbone-epochs",
        type=int,
        default=None,
        help=f"Freeze backbone for N epochs (default: {DEFAULTS['freeze_backbone_epochs']}).",
    )
    parser.add_argument(
        "--sp-p",
        type=float,
        default=None,
        help=f"Salt&Pepper probability (default: {DEFAULTS['sp_p']}).",
    )
    parser.add_argument(
        "--sp-density",
        type=float,
        default=None,
        help=f"Salt&Pepper density (default: {DEFAULTS['sp_density']}).",
    )

    # Checkpointing
    parser.add_argument(
        "--save-interval",
        type=int,
        default=None,
        help=f"Save model checkpoint every N epochs (default: {DEFAULTS['save_interval']}).",
    )

    # System / Optimizer
    parser.add_argument(
        "--weight-decay",
        type=float,
        default=None,
        help=f"Weight decay for optimizer (default: {DEFAULTS['weight_decay']}).",
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=None,
        help=f"Number of dataloader workers (default: {DEFAULTS['num_workers']}).",
    )
    parser.add_argument(
        "--prefetch-factor",
        type=int,
        default=None,
        help=f"Dataloader prefetch factor (default: {DEFAULTS['prefetch_factor']}).",
    )

    args = parser.parse_args()

    # Priority: CLI > Config > Defaults
    if args.config:
        with open(args.config, "r") as f:
            config_args = yaml.safe_load(f)
        for key, value in config_args.items():
            # Only set if NOT provided via CLI (CLI args are None if not set now)
            if getattr(args, key) is None:
                setattr(args, key, value)

    # Apply defaults for anything still None
    for key, value in DEFAULTS.items():
        if getattr(args, key) is None:
            setattr(args, key, value)

    return args


def train(args):
    if args.seed is not None:
        torch.manual_seed(args.seed)
        np.random.seed(args.seed)
        random.seed(args.seed)

    print(f"Using device: {DEVICE}")

    # Paths
    work_dir = Path(args.work_dir) if args.work_dir else DEFAULT_WORK_DIR
    work_dir.mkdir(parents=True, exist_ok=True)

    # TensorBoard
    if args.log_dir:
        writer = SummaryWriter(log_dir=args.log_dir)
    else:
        # Default to work_dir/runs
        log_dir = work_dir / "runs"
        writer = SummaryWriter(log_dir=log_dir)
        print(f"TensorBoard logging enabled at {log_dir}")

    use_explicit_dirs = args.tp_dir or args.fp_dir

    if use_explicit_dirs:
        tp_dir = Path(args.tp_dir) if args.tp_dir else work_dir / "tp_crops"
        fp_dir = Path(args.fp_dir) if args.fp_dir else work_dir / "fp_crops_enhanced"
        val_tp_dir = None
        val_fp_dir = None
        print(f"Using explicit dirs: TP={tp_dir}, FP={fp_dir}")
    elif (TRAIN_SPLIT_DIR / "tp").exists() and (TRAIN_SPLIT_DIR / "fp").exists():
        tp_dir = TRAIN_SPLIT_DIR / "tp"
        fp_dir = TRAIN_SPLIT_DIR / "fp"
        val_tp_dir = VAL_SPLIT_DIR / "tp"
        val_fp_dir = VAL_SPLIT_DIR / "fp"
        print(f"Using split dirs from {DATASET_ROOT}")
    else:
        tp_dir = work_dir / "tp_crops"
        fp_dir = work_dir / "fp_crops_enhanced"
        val_tp_dir = None
        val_fp_dir = None
        print(f"Fallback to work_dir: TP={tp_dir}, FP={fp_dir}")

    if not tp_dir.exists() or not fp_dir.exists():
        print("Error: Crop directories not found.")
        if writer:
            writer.close()
        return

    # Transforms (CPU)
    train_transform = get_cpu_transforms(args.img_size, "train" if not args.no_augment else "val")
    val_transform = get_cpu_transforms(args.img_size, "val")

    # Transforms (GPU)
    gpu_train_transform = get_gpu_transforms("train", args.sp_density, args.sp_p).to(DEVICE)
    gpu_val_transform = get_gpu_transforms("val").to(DEVICE)

    if args.compile:
        gpu_train_transform = torch.compile(gpu_train_transform)
        gpu_val_transform = torch.compile(gpu_val_transform)

    # Data Loaders
    if val_tp_dir and val_tp_dir.exists() and val_fp_dir and val_fp_dir.exists():
        train_dataset = BarlineDataset(tp_dir, fp_dir, transform=train_transform)
        val_dataset = BarlineDataset(val_tp_dir, val_fp_dir, transform=val_transform)
    else:
        dataset = BarlineDataset(tp_dir, fp_dir, transform=train_transform)
        train_size = int(args.train_val_split * len(dataset))
        val_size = len(dataset) - train_size
        if train_size == 0 and len(dataset) > 0:
            train_size = 1
            val_size = max(0, len(dataset) - 1)

        generator = torch.Generator().manual_seed(args.seed) if args.seed is not None else None
        train_indices, val_indices = torch.utils.data.random_split(
            range(len(dataset)), [train_size, val_size], generator=generator
        )

        train_dataset = Subset(
            BarlineDataset(tp_dir, fp_dir, transform=train_transform), train_indices.indices
        )
        val_dataset = Subset(
            BarlineDataset(tp_dir, fp_dir, transform=val_transform), val_indices.indices
        )

    # Class Weighting
    if isinstance(train_dataset, Subset):
        base_ds = train_dataset.dataset
        labels = [base_ds.labels[i] for i in train_dataset.indices]
    else:
        labels = train_dataset.labels

    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    print(f"Training Data: Pos={n_pos}, Neg={n_neg}, Total={len(labels)}")

    sampler = None
    criterion_weight = None

    if args.imbalance == "sampler" and n_pos > 0 and n_neg > 0:
        weight_pos = 1.0 / n_pos
        weight_neg = 1.0 / n_neg
        samples_weight = torch.tensor(
            [weight_pos if l == 1 else weight_neg for l in labels], dtype=torch.float
        )
        sampler = WeightedRandomSampler(samples_weight, len(samples_weight))
        print("Using WeightedRandomSampler")
    elif args.imbalance == "pos_weight" and n_neg > 0 and n_pos > 0:
        pos_weight_val = n_neg / n_pos
        criterion_weight = torch.tensor([pos_weight_val]).to(DEVICE)
        print(f"Using BCEWithLogitsLoss pos_weight={pos_weight_val:.2f}")

    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=(sampler is None),
        sampler=sampler,
        num_workers=args.num_workers,
        pin_memory=True,
        persistent_workers=True,
        prefetch_factor=args.prefetch_factor,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
        pin_memory=True,
        persistent_workers=True,
        prefetch_factor=args.prefetch_factor,
    )

    # Model
    model = get_model(args.model_name).to(DEVICE)
    if args.channels_last:
        model = model.to(memory_format=torch.channels_last)

    if args.compile:
        print(f"Compiling model with mode={args.compile_mode}...")
        model = torch.compile(model, mode=args.compile_mode)

    criterion = nn.BCEWithLogitsLoss(pos_weight=criterion_weight)

    # Optimizer - Filter frozen parameters if any
    if args.freeze_backbone_epochs > 0:
        print(f"Freezing backbone for first {args.freeze_backbone_epochs} epochs.")
        # Assuming MobilenetV3 or ResNet structure from get_model
        if args.model_name == "mobilenet_v3_small":
            # Freeze everything except classifier
            for param in model.parameters():
                param.requires_grad = False
            for param in model.classifier.parameters():
                param.requires_grad = True
        elif args.model_name == "resnet18":
            for param in model.parameters():
                param.requires_grad = False
            for param in model.fc.parameters():
                param.requires_grad = True

    optimizer = optim.AdamW(
        filter(lambda p: p.requires_grad, model.parameters()),
        lr=args.learning_rate,
        weight_decay=args.weight_decay,
    )

    # Scheduler
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    scaler = torch.amp.GradScaler("cuda", enabled=args.amp)

    best_val_metric = 0.0

    # Training Loop
    for epoch in range(args.epochs):
        # Unfreeze check
        if args.freeze_backbone_epochs > 0 and epoch == args.freeze_backbone_epochs:
            print("Unfreezing backbone...")
            for param in model.parameters():
                param.requires_grad = True
            # Re-create optimizer to include all params (and reset scheduler)
            optimizer = optim.AdamW(
                model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay
            )
            scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs - epoch)

        model.train()
        running_loss = 0.0
        train_tp, train_fp, train_fn, train_tn = 0, 0, 0, 0

        data_time_sum = 0.0
        compute_time_sum = 0.0

        start_time = time.time()

        pbar = tqdm(train_loader, desc=f"Epoch {epoch + 1}/{args.epochs} [Train]")
        for inputs, labels in pbar:
            data_end_time = time.time()
            data_time_sum += data_end_time - start_time

            inputs, labels = inputs.to(DEVICE), labels.to(DEVICE).unsqueeze(1)

            if args.channels_last:
                inputs = inputs.to(memory_format=torch.channels_last)

            # GPU Augmentation
            inputs = gpu_train_transform(inputs)

            optimizer.zero_grad()

            with torch.amp.autocast("cuda", enabled=args.amp):
                outputs = model(inputs)
                loss = criterion(outputs, labels)

            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()

            running_loss += loss.item()

            # Metrics (Detach for speed)
            tp, fp, fn, tn = calculate_metrics(outputs.detach(), labels)
            train_tp += tp
            train_fp += fp
            train_fn += fn
            train_tn += tn

            compute_end_time = time.time()
            compute_time_sum += compute_end_time - data_end_time
            start_time = compute_end_time  # Reset for next batch

            pbar.set_postfix({"loss": f"{loss.item():.4f}"})

        train_loss = running_loss / len(train_loader) if len(train_loader) > 0 else 0
        train_acc = (train_tp + train_tn) / (train_tp + train_tn + train_fp + train_fn + 1e-8)
        train_precision = train_tp / (train_tp + train_fp + 1e-8)
        train_recall = train_tp / (train_tp + train_fn + 1e-8)
        train_f1 = 2 * train_precision * train_recall / (train_precision + train_recall + 1e-8)

        print(
            f"Epoch {epoch + 1}/{args.epochs} [Train] Loss: {train_loss:.4f}, Acc: {train_acc:.4f}, F1: {train_f1:.4f}"
        )

        if args.timing:
            print(f"  Timing: Data={data_time_sum:.2f}s, Compute={compute_time_sum:.2f}s")

        # Validation
        val_thresh = 0.5
        if args.optimize_threshold:
            val_thresh, val_best_f1 = find_optimal_threshold(
                model, val_loader, DEVICE, gpu_val_transform, args.amp
            )
            print(f"  Optimal Threshold: {val_thresh:.2f} (F1: {val_best_f1:.4f})")

        model.eval()
        val_loss = 0.0
        val_tp, val_fp, val_fn, val_tn = 0, 0, 0, 0

        with torch.no_grad():
            for inputs, labels in tqdm(
                val_loader, desc=f"Epoch {epoch + 1}/{args.epochs} [Val]", leave=False
            ):
                inputs, labels = inputs.to(DEVICE), labels.to(DEVICE).unsqueeze(1)
                if args.channels_last:
                    inputs = inputs.to(memory_format=torch.channels_last)
                inputs = gpu_val_transform(inputs)

                with torch.amp.autocast("cuda", enabled=args.amp):
                    outputs = model(inputs)
                    loss = criterion(outputs, labels)

                val_loss += loss.item()
                tp, fp, fn, tn = calculate_metrics(outputs, labels, threshold=val_thresh)
                val_tp += tp
                val_fp += fp
                val_fn += fn
                val_tn += tn

        if len(val_loader) > 0:
            val_loss /= len(val_loader)
            val_acc = (val_tp + val_tn) / (val_tp + val_tn + val_fp + val_fn + 1e-8)
            val_precision = val_tp / (val_tp + val_fp + 1e-8)
            val_recall = val_tp / (val_tp + val_fn + 1e-8)
            val_f1 = 2 * val_precision * val_recall / (val_precision + val_recall + 1e-8)

            print(
                f"Epoch {epoch + 1}/{args.epochs} [Val]   Loss: {val_loss:.4f}, Acc: {val_acc:.4f}, F1: {val_f1:.4f}"
            )

            if writer:
                writer.add_scalar("Loss/train", train_loss, epoch)
                writer.add_scalar("F1/train", train_f1, epoch)
                writer.add_scalar("Loss/val", val_loss, epoch)
                writer.add_scalar("F1/val", val_f1, epoch)
                writer.add_scalar("LR", scheduler.get_last_lr()[0], epoch)

            # Save best model
            if val_f1 > best_val_metric:
                best_val_metric = val_f1
                save_path = work_dir / "cnn_classifier_best.pth"
                torch.save(model.state_dict(), save_path)
                print(f"New best model saved to {save_path}")

        # Regular Checkpoint
        if args.save_interval > 0 and (epoch + 1) % args.save_interval == 0:
            save_path = work_dir / f"cnn_classifier_epoch_{epoch + 1}.pth"
            torch.save(model.state_dict(), save_path)
            print(f"Checkpoint saved to {save_path}")

        scheduler.step()

    if writer:
        writer.close()

    # Save Last Model
    save_path = work_dir / "cnn_classifier_last.pth"
    torch.save(model.state_dict(), save_path)
    print(f"Last model saved to {save_path}")


if __name__ == "__main__":
    args = get_args()
    train(args)
