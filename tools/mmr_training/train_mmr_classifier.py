import argparse
import io
import json
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from PIL import Image, ImageDraw, ImageFont
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from torchvision import models, transforms
from torchvision.models import ResNet18_Weights

from tools.mmr_training.issue332.geometry_training import (
    DEFAULT_DELTAS_PX,
    DEFAULT_EXCLUDED_TAGS,
    SemanticMMRDataset,
    prepare_split_contract,
    samples_for_split,
    sha256_file,
)


def calculate_metrics(y_true, y_pred):
    y_true = np.asarray(y_true).reshape(-1)
    y_pred = np.asarray(y_pred).reshape(-1)

    tp = int(np.sum((y_true == 1) & (y_pred == 1)))
    tn = int(np.sum((y_true == 0) & (y_pred == 0)))
    fp = int(np.sum((y_true == 0) & (y_pred == 1)))
    fn = int(np.sum((y_true == 1) & (y_pred == 0)))

    acc = (tp + tn) / len(y_true) if len(y_true) else 0.0
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return acc, prec, rec, f1


def metrics_payload(y_true, y_pred):
    y_true = np.asarray(y_true).reshape(-1)
    y_pred = np.asarray(y_pred).reshape(-1)
    acc, prec, rec, f1 = calculate_metrics(y_true, y_pred)
    return {
        "accuracy": float(acc),
        "precision": float(prec),
        "recall": float(rec),
        "f1": float(f1),
        "confusion_matrix": {
            "tn": int(np.sum((y_true == 0) & (y_pred == 0))),
            "fp": int(np.sum((y_true == 0) & (y_pred == 1))),
            "fn": int(np.sum((y_true == 1) & (y_pred == 0))),
            "tp": int(np.sum((y_true == 1) & (y_pred == 1))),
        },
        "samples": int(len(y_true)),
        "positives": int(np.sum(y_true == 1)),
        "negatives": int(np.sum(y_true == 0)),
    }


def manual_train_test_split(paths, labels, test_size=0.2, random_state=42):
    combined = list(zip(paths, labels))
    random.Random(random_state).shuffle(combined)
    split_idx = int(len(combined) * (1 - test_size))
    train_data = combined[:split_idx]
    test_data = combined[split_idx:]
    if not train_data or not test_data:
        raise ValueError("legacy crop split produced an empty partition")
    x_train, y_train = zip(*train_data)
    x_test, y_test = zip(*test_data)
    return list(x_train), list(x_test), list(y_train), list(y_test)


def set_seed(seed=42):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


class TextNoiseOverlay:
    def __init__(
        self,
        terms,
        prob=0.7,
        font_path=None,
        font_paths=None,
        font_size_range=(16, 40),
        stroke_width_range=(0, 1),
        max_attempts=15,
    ):
        self.terms = terms
        self.prob = prob
        self.font_path = font_path
        self.font_paths = font_paths or []
        self.font_size_range = font_size_range
        self.stroke_width_range = stroke_width_range
        self.max_attempts = max_attempts

    def _load_font(self, size):
        if self.font_paths:
            font_source = random.choice(self.font_paths)
            if hasattr(font_source, "seek"):
                font_source.seek(0)
            return ImageFont.truetype(font_source, size=size)
        if self.font_path and Path(self.font_path).exists():
            return ImageFont.truetype(self.font_path, size=size)
        return ImageFont.load_default()

    def _estimate_staff_band(self, staff_mask, height):
        if staff_mask is None:
            return int(height * 0.3), int(height * 0.7)
        ys = np.where(staff_mask > 0)[0]
        if ys.size == 0:
            return int(height * 0.3), int(height * 0.7)
        return int(np.min(ys)), int(np.max(ys))

    def _overlap_ratio(self, staff_mask, x1, y1, x2, y2):
        if staff_mask is None:
            return 0.0
        h, w = staff_mask.shape[:2]
        cx1 = max(0, min(w, x1))
        cx2 = max(0, min(w, x2))
        cy1 = max(0, min(h, y1))
        cy2 = max(0, min(h, y2))
        if cx2 <= cx1 or cy2 <= cy1:
            return 0.0
        patch = staff_mask[cy1:cy2, cx1:cx2]
        if patch.size == 0:
            return 0.0
        return float(np.count_nonzero(patch)) / float(patch.size)

    def __call__(self, image, staff_mask=None):
        if random.random() > self.prob:
            return image

        img = image.copy()
        draw = ImageDraw.Draw(img)
        w, h = img.size
        text = random.choice(self.terms)
        font_size = random.randint(*self.font_size_range)
        font = self._load_font(font_size)
        stroke_width = random.randint(*self.stroke_width_range)
        text_bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
        text_w = text_bbox[2] - text_bbox[0]
        text_h = text_bbox[3] - text_bbox[1]
        staff_top, staff_bottom = self._estimate_staff_band(staff_mask, h)

        for _ in range(self.max_attempts):
            pos_type = random.choices(["top", "bottom", "cross"], weights=[0.45, 0.45, 0.10], k=1)[0]
            if pos_type == "top":
                y = random.randint(-text_h // 2, max(0, h // 3))
            elif pos_type == "bottom":
                y = random.randint(max(0, h * 2 // 3), h + text_h // 2)
            else:
                y = random.randint(-text_h // 2, h + text_h // 2)
            x = random.randint(-text_w // 2, w - text_w // 2)
            x1, y1 = x, y - text_h
            x2, y2 = x + text_w, y
            if y1 >= staff_top and y2 <= staff_bottom:
                continue
            if self._overlap_ratio(staff_mask, x1, y1, x2, y2) > 0.2:
                continue
            draw.text(
                (x, y),
                text,
                fill=(0, 0, 0),
                font=font,
                stroke_width=stroke_width,
                stroke_fill=(0, 0, 0),
            )
            return img
        return img


class MMRDataset(Dataset):
    """Legacy pre-cropped dataset mode retained for compatibility."""

    def __init__(
        self,
        image_paths,
        labels,
        transform=None,
        staff_mask_root=None,
        staff_mask_suffix="_staff",
        staff_mask_ext=".png",
        text_noise=None,
    ):
        self.image_paths = image_paths
        self.labels = labels
        self.transform = transform
        self.staff_mask_root = Path(staff_mask_root) if staff_mask_root else None
        self.staff_mask_suffix = staff_mask_suffix
        self.staff_mask_ext = staff_mask_ext
        self.text_noise = text_noise

    def __len__(self):
        return len(self.image_paths)

    def __getitem__(self, idx):
        img_path = self.image_paths[idx]
        label = self.labels[idx]
        image = Image.open(img_path).convert("RGB")

        staff_mask = None
        if self.staff_mask_root:
            mask_path = (
                self.staff_mask_root
                / f"{Path(img_path).stem}{self.staff_mask_suffix}{self.staff_mask_ext}"
            )
            if mask_path.exists():
                staff_mask = np.array(Image.open(mask_path).convert("L"))

        if label == 1 and self.text_noise is not None:
            image = self.text_noise(image, staff_mask)
        if self.transform:
            image = self.transform(image)
        return image, torch.tensor(label, dtype=torch.float32)


def load_fonts_from_zip(zip_path):
    if not zip_path:
        return []
    zip_path = Path(zip_path)
    if not zip_path.exists():
        return []
    fonts = []
    import zipfile

    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            if not name.lower().endswith((".ttf", ".otf")):
                continue
            fonts.append(io.BytesIO(zf.read(name)))
    return fonts


def load_fonts_from_dir(dir_path):
    if not dir_path:
        return []
    dir_path = Path(dir_path)
    if not dir_path.exists():
        return []
    return [str(path) for path in dir_path.rglob("*") if path.suffix.lower() in {".ttf", ".otf"}]


def _get_progress_bar():
    try:
        from tqdm import tqdm

        return tqdm
    except Exception:
        return None


def _transforms():
    train_transform = transforms.Compose(
        [
            transforms.Resize((224, 224)),
            transforms.RandomHorizontalFlip(p=0.5),
            transforms.RandomRotation(5),
            transforms.ColorJitter(brightness=0.2, contrast=0.2),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]
    )
    eval_transform = transforms.Compose(
        [
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]
    )
    return train_transform, eval_transform


def _text_noise(args):
    terms = [
        "pizz.", "arco", "div.", "unis.", "solo", "tutti", "a 2", "cresc.", "dim.",
        "espress.", "dolce", "sempre", "sim.", "f", "p", "mf", "mp", "ff", "pp",
        "sfz", "Allegro", "Andante", "Largo", "Presto", "Moderato", "Tempo I",
        "Cadenza", "G.P.", "V.S.", "attacca", "rit.", "rall.", "accel.", "a tempo",
        "cant.", "marc.", "legg.", "stacc.", "ten.", "con sord.", "senza sord.",
        "sul G", "sul D",
    ]
    font_paths = []
    font_paths.extend(load_fonts_from_dir(args.text_font_dir))
    font_paths.extend(load_fonts_from_zip(args.text_fonts_zip))
    return TextNoiseOverlay(
        terms=terms,
        prob=args.text_noise_prob,
        font_path=args.text_font,
        font_paths=font_paths,
        font_size_range=(args.text_font_min_size, args.text_font_max_size),
        stroke_width_range=(args.text_stroke_min, args.text_stroke_max),
    )


def _load_geometry_config(path):
    if path is None:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("geometry config must be a JSON object")
    return payload


def _legacy_datasets(args, train_transform, eval_transform, text_noise):
    data_root = Path(args.data_root)
    paths_0 = list((data_root / "train" / "0").glob("*.jpg"))
    paths_1 = list((data_root / "train" / "1").glob("*.jpg"))
    labels_0 = [0] * len(paths_0)
    labels_1 = [1] * len(paths_1)

    p0_train, p0_val, y0_train, y0_val = manual_train_test_split(
        paths_0, labels_0, test_size=0.2, random_state=args.seed
    )
    p1_train, p1_val, y1_train, y1_val = manual_train_test_split(
        paths_1, labels_1, test_size=0.2, random_state=args.seed
    )
    train_paths = p0_train + p1_train
    train_labels = y0_train + y1_train
    val_paths = p0_val + p1_val
    val_labels = y0_val + y1_val

    train_dataset = MMRDataset(
        train_paths,
        train_labels,
        transform=train_transform,
        staff_mask_root=args.staff_mask_root,
        staff_mask_suffix=args.staff_mask_suffix,
        staff_mask_ext=args.staff_mask_ext,
        text_noise=text_noise,
    )
    val_dataset = MMRDataset(val_paths, val_labels, transform=eval_transform)
    return train_dataset, val_dataset, None, train_labels, None


def _manifest_datasets(args, train_transform, eval_transform, text_noise):
    manifest_path = Path(args.manifest)
    split_path = Path(args.split_manifest)
    config = _load_geometry_config(args.geometry_config)
    split_config = config.get("split", {})
    excluded_tags = config.get("acceptance_excluded_tags", list(DEFAULT_EXCLUDED_TAGS))

    eligible, split_contract = prepare_split_contract(
        manifest_path=manifest_path,
        split_path=split_path,
        acceptance_manifest_path=Path(args.acceptance_manifest)
        if args.acceptance_manifest
        else None,
        excluded_tags=excluded_tags,
        seed=int(split_config.get("seed", args.seed)),
        validation_ratio=float(split_config.get("validation_ratio", 0.2)),
        test_ratio=float(split_config.get("test_ratio", 0.2)),
        group_level=str(split_config.get("group_level", "score")),
        fallback_group_level=split_config.get("fallback_group_level", "page"),
    )

    train_samples = samples_for_split(eligible, split_contract, "train")
    val_samples = samples_for_split(eligible, split_contract, "validation")
    test_samples = samples_for_split(eligible, split_contract, "test")
    margin_px = int(config.get("margin_px", 20))
    deltas_px = tuple(int(value) for value in config.get("deltas_px", DEFAULT_DELTAS_PX))

    train_dataset = SemanticMMRDataset(
        train_samples,
        manifest_path=manifest_path,
        transform=train_transform,
        geometry_policy=args.geometry_augmentation,
        deltas_px=deltas_px,
        margin_px=margin_px,
        seed=args.seed,
        text_noise=text_noise,
    )
    val_dataset = SemanticMMRDataset(
        val_samples,
        manifest_path=manifest_path,
        transform=eval_transform,
        geometry_policy="none",
        deltas_px=deltas_px,
        margin_px=margin_px,
        seed=args.seed,
    )
    test_dataset = SemanticMMRDataset(
        test_samples,
        manifest_path=manifest_path,
        transform=eval_transform,
        geometry_policy="none",
        deltas_px=deltas_px,
        margin_px=margin_px,
        seed=args.seed,
    )
    return train_dataset, val_dataset, test_dataset, train_dataset.labels, split_contract


def _make_loader(dataset, labels, args, *, train):
    if train and args.use_weighted_sampler:
        positives = sum(int(label) == 1 for label in labels)
        negatives = sum(int(label) == 0 for label in labels)
        if positives == 0 or negatives == 0:
            raise ValueError("training split must contain both classes")
        positive_sample_weight = negatives / positives
        weights = [positive_sample_weight if int(label) == 1 else 1.0 for label in labels]
        sampler = WeightedRandomSampler(weights, num_samples=len(labels), replacement=True)
        return DataLoader(
            dataset,
            batch_size=args.batch_size,
            sampler=sampler,
            num_workers=args.num_workers,
        )
    return DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=train,
        num_workers=args.num_workers,
    )


def _evaluate_loader(model, loader, device):
    probabilities = []
    targets = []
    model.eval()
    with torch.no_grad():
        for images, labels in loader:
            images = images.to(device)
            outputs = model(images)
            probabilities.extend(torch.sigmoid(outputs).reshape(-1).cpu().tolist())
            targets.extend(labels.reshape(-1).cpu().tolist())
    predictions = [1 if probability >= 0.5 else 0 for probability in probabilities]
    return metrics_payload(targets, predictions), probabilities


def _per_score_metrics(dataset, probabilities):
    if not hasattr(dataset, "samples"):
        return None
    grouped = {}
    for sample, probability in zip(dataset.samples, probabilities):
        item = grouped.setdefault(sample["score_id"], {"y_true": [], "y_pred": []})
        item["y_true"].append(int(sample["label"]))
        item["y_pred"].append(1 if float(probability) >= 0.5 else 0)
    return {
        score_id: metrics_payload(item["y_true"], item["y_pred"])
        for score_id, item in sorted(grouped.items())
    }


def train_model(args):
    set_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    writer = None
    if args.log_dir:
        try:
            from torch.utils.tensorboard import SummaryWriter

            writer = SummaryWriter(log_dir=args.log_dir)
        except Exception as exc:
            print(f"[Warn] TensorBoard not available: {exc}")

    train_transform, eval_transform = _transforms()
    text_noise = _text_noise(args)

    if args.manifest:
        train_dataset, val_dataset, test_dataset, train_labels, split_contract = _manifest_datasets(
            args, train_transform, eval_transform, text_noise
        )
        mode = "semantic-manifest"
    else:
        train_dataset, val_dataset, test_dataset, train_labels, split_contract = _legacy_datasets(
            args, train_transform, eval_transform, text_noise
        )
        mode = "legacy-crops"

    print(
        f"Data mode={mode} train={len(train_dataset)} validation={len(val_dataset)} "
        f"test={len(test_dataset) if test_dataset is not None else 0}"
    )
    train_loader = _make_loader(train_dataset, train_labels, args, train=True)
    val_loader = _make_loader(val_dataset, [], args, train=False)

    positives = sum(int(label) == 1 for label in train_labels)
    negatives = sum(int(label) == 0 for label in train_labels)
    if positives == 0:
        raise ValueError("training split contains no positive samples")

    model = models.resnet18(weights=ResNet18_Weights.IMAGENET1K_V1)
    model.fc = nn.Linear(model.fc.in_features, 1)
    model = model.to(device)

    criterion = nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor([negatives / positives], device=device)
    )
    optimizer = optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    best_f1 = -1.0
    best_epoch = None
    tqdm = _get_progress_bar()

    for epoch in range(args.epochs):
        if hasattr(train_dataset, "set_epoch"):
            train_dataset.set_epoch(epoch)

        model.train()
        running_loss = 0.0
        train_iter = train_loader
        if tqdm:
            train_iter = tqdm(train_loader, desc=f"Train {epoch + 1}/{args.epochs}", leave=False)

        for images, labels in train_iter:
            images = images.to(device)
            labels = labels.unsqueeze(1).to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            running_loss += loss.item() * images.size(0)

        val_metrics, _ = _evaluate_loader(model, val_loader, device)
        epoch_loss = running_loss / len(train_dataset)
        lr = scheduler.get_last_lr()[0]
        print(
            f"Epoch {epoch + 1}/{args.epochs}: Loss={epoch_loss:.4f} | "
            f"Val Acc={val_metrics['accuracy']:.4f} "
            f"F1={val_metrics['f1']:.4f} "
            f"Prec={val_metrics['precision']:.4f} "
            f"Rec={val_metrics['recall']:.4f} LR={lr:.6f}"
        )

        if writer:
            writer.add_scalar("loss/train", epoch_loss, epoch + 1)
            for key in ("accuracy", "precision", "recall", "f1"):
                writer.add_scalar(f"val/{key}", val_metrics[key], epoch + 1)

        if val_metrics["f1"] > best_f1:
            best_f1 = val_metrics["f1"]
            best_epoch = epoch + 1
            torch.save(model.state_dict(), args.output_model)
            print(f"  Saved best model to {args.output_model}")

        scheduler.step()

    if writer:
        writer.close()

    result = {
        "mode": mode,
        "geometry_augmentation": args.geometry_augmentation if args.manifest else None,
        "best_epoch": best_epoch,
        "selection_metric": "validation_f1",
        "best_validation_f1": best_f1,
        "output_model": str(Path(args.output_model).resolve()),
        "output_model_sha256": sha256_file(Path(args.output_model)),
        "test_used_for_model_selection": False,
    }

    if split_contract is not None:
        result["split_contract"] = split_contract
        result["split_manifest"] = str(Path(args.split_manifest).resolve())
        result["split_manifest_sha256"] = sha256_file(Path(args.split_manifest))

    if test_dataset is not None:
        best_state = torch.load(args.output_model, map_location=device, weights_only=True)
        model.load_state_dict(best_state)
        test_loader = _make_loader(test_dataset, [], args, train=False)
        test_metrics, probabilities = _evaluate_loader(model, test_loader, device)
        result["test_native"] = test_metrics
        result["test_per_score"] = _per_score_metrics(test_dataset, probabilities)

    if args.metrics_output:
        metrics_path = Path(args.metrics_output)
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        metrics_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        print(f"wrote {metrics_path}")

    print("Training Complete.")
    return result


def build_parser():
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--data-root",
        type=str,
        help="Legacy pre-cropped dataset root containing train/0 and train/1.",
    )
    source.add_argument(
        "--manifest",
        type=str,
        help="Semantic source manifest with score/page/image/bbox/label identity.",
    )
    parser.add_argument("--acceptance-manifest", type=str, default=None)
    parser.add_argument("--split-manifest", type=str, default=None)
    parser.add_argument(
        "--geometry-config",
        type=str,
        default="tools/mmr_training/issue332/geometry_augmentation_config.json",
    )
    parser.add_argument(
        "--geometry-augmentation",
        choices=("none", "absolute"),
        default="none",
    )
    parser.add_argument("--output-model", type=str, default="mmr_classifier_best.pth")
    parser.add_argument("--metrics-output", type=str, default=None)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-weighted-sampler", dest="use_weighted_sampler", action="store_false")
    parser.set_defaults(use_weighted_sampler=True)
    parser.add_argument("--staff-mask-root", type=str, default=None)
    parser.add_argument("--staff-mask-suffix", type=str, default="_staff")
    parser.add_argument("--staff-mask-ext", type=str, default=".png")
    parser.add_argument("--text-noise-prob", type=float, default=0.7)
    parser.add_argument("--text-font", type=str, default=None)
    parser.add_argument("--text-font-dir", type=str, default=None)
    parser.add_argument("--text-fonts-zip", type=str, default=None)
    parser.add_argument("--text-font-min-size", type=int, default=16)
    parser.add_argument("--text-font-max-size", type=int, default=40)
    parser.add_argument("--text-stroke-min", type=int, default=0)
    parser.add_argument("--text-stroke-max", type=int, default=1)
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--log-dir", type=str, default=None)
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.manifest and not args.split_manifest:
        parser.error("--split-manifest is required with --manifest")
    if not args.manifest and args.geometry_augmentation != "none":
        parser.error("--geometry-augmentation requires --manifest")
    train_model(args)


if __name__ == "__main__":
    main()
