import argparse
import io
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


# Implement simple metrics manually to avoid sklearn dependency
def calculate_metrics(y_true, y_pred):
    # y_true, y_pred are lists or numpy arrays
    y_true = np.array(y_true)
    y_pred = np.array(y_pred)

    tp = np.sum((y_true == 1) & (y_pred == 1))
    tn = np.sum((y_true == 0) & (y_pred == 0))
    fp = np.sum((y_true == 0) & (y_pred == 1))
    fn = np.sum((y_true == 1) & (y_pred == 0))

    acc = (tp + tn) / len(y_true) if len(y_true) > 0 else 0
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0

    return acc, prec, rec, f1


def manual_train_test_split(paths, labels, test_size=0.2, random_state=42):
    combined = list(zip(paths, labels))
    random.seed(random_state)
    random.shuffle(combined)

    split_idx = int(len(combined) * (1 - test_size))
    train_data = combined[:split_idx]
    test_data = combined[split_idx:]

    X_train, y_train = zip(*train_data)
    X_test, y_test = zip(*test_data)

    return list(X_train), list(X_test), list(y_train), list(y_test)


# Reproducibility
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

        pos_types = ["top", "bottom", "cross"]
        pos_weights = [0.45, 0.45, 0.10]

        for _ in range(self.max_attempts):
            pos_type = random.choices(pos_types, weights=pos_weights, k=1)[0]

            if pos_type == "top":
                y = random.randint(-text_h // 2, max(0, h // 3))
            elif pos_type == "bottom":
                y = random.randint(max(0, h * 2 // 3), h + text_h // 2)
            else:
                y = random.randint(-text_h // 2, h + text_h // 2)

            x = random.randint(-text_w // 2, w - text_w // 2)

            x1, y1 = x, y - text_h
            x2, y2 = x + text_w, y

            # Avoid fully-inside staff placement.
            if y1 >= staff_top and y2 <= staff_bottom:
                continue

            overlap = self._overlap_ratio(staff_mask, x1, y1, x2, y2)
            if overlap > 0.2:
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

        # Load Image (Convert to RGB for ResNet compatibility)
        try:
            image = Image.open(img_path).convert("RGB")
        except Exception as e:
            print(f"Error loading {img_path}: {e}")
            # Return a dummy black image
            image = Image.new("RGB", (224, 224), (0, 0, 0))

        staff_mask = None
        if self.staff_mask_root:
            mask_path = (
                self.staff_mask_root
                / f"{Path(img_path).stem}{self.staff_mask_suffix}{self.staff_mask_ext}"
            )
            if mask_path.exists():
                mask_img = Image.open(mask_path).convert("L")
                staff_mask = np.array(mask_img)

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
            data = zf.read(name)
            try:
                fonts.append(io.BytesIO(data))
            except Exception:
                pass
    return fonts


def load_fonts_from_dir(dir_path):
    if not dir_path:
        return []
    dir_path = Path(dir_path)
    if not dir_path.exists():
        return []
    return [str(p) for p in dir_path.rglob("*") if p.suffix.lower() in {".ttf", ".otf"}]


def _get_progress_bar():
    try:
        from tqdm import tqdm

        return tqdm
    except Exception:
        return None


def train_model(args):
    set_seed()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    writer = None
    if args.log_dir:
        try:
            from torch.utils.tensorboard import SummaryWriter

            writer = SummaryWriter(log_dir=args.log_dir)
            print(f"TensorBoard logging enabled: {args.log_dir}")
        except Exception as e:
            print(f"[Warn] TensorBoard not available: {e}")

    # 1. Prepare Data
    data_root = Path(args.data_root)
    # Assume data structure: data_root/train/0 and data_root/train/1
    # We will split this into train/val manually

    paths_0 = list((data_root / "train" / "0").glob("*.jpg"))
    paths_1 = list((data_root / "train" / "1").glob("*.jpg"))

    labels_0 = [0] * len(paths_0)
    labels_1 = [1] * len(paths_1)

    all_paths = paths_0 + paths_1
    labels_0 + labels_1

    print(f"Total Data: {len(all_paths)} (Pos: {len(paths_1)}, Neg: {len(paths_0)})")

    # Stratified Split (Manual - simple random shuffle, close enough for large dataset)
    # To mimic stratification, we can split pos and neg separately then combine, but simple shuffle is usually fine.
    # Let's do separate split to ensure validation has positives.

    paths_0_train, paths_0_val, labels_0_train, labels_0_val = manual_train_test_split(
        paths_0, labels_0, test_size=0.2
    )
    paths_1_train, paths_1_val, labels_1_train, labels_1_val = manual_train_test_split(
        paths_1, labels_1, test_size=0.2
    )

    X_train = paths_0_train + paths_1_train
    y_train = labels_0_train + labels_1_train

    X_val = paths_0_val + paths_1_val
    y_val = labels_0_val + labels_1_val

    # Transforms
    # ResNet expects 224x224 usually, but our measures are wide rectangles.
    # Warping to square might distort features (H-bar vs Beam).
    # But pre-trained models require fixed input?
    # Actually ResNet is fully convolutional until the GAP, so input size can vary,
    # but the fine-tuning usually sticks to standard sizes.
    # Let's try simple resize first.
    train_transforms = transforms.Compose(
        [
            transforms.Resize((224, 224)),
            transforms.RandomHorizontalFlip(p=0.5),  # Is flip safe? Yes, mmr is symmetric usually.
            transforms.RandomRotation(5),
            transforms.ColorJitter(brightness=0.2, contrast=0.2),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]
    )

    val_transforms = transforms.Compose(
        [
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]
    )

    terms = [
        "pizz.",
        "arco",
        "div.",
        "unis.",
        "solo",
        "tutti",
        "a 2",
        "cresc.",
        "dim.",
        "espress.",
        "dolce",
        "sempre",
        "sim.",
        "f",
        "p",
        "mf",
        "mp",
        "ff",
        "pp",
        "sfz",
        "Allegro",
        "Andante",
        "Largo",
        "Presto",
        "Moderato",
        "Tempo I",
        "Cadenza",
        "G.P.",
        "V.S.",
        "attacca",
        "rit.",
        "rall.",
        "accel.",
        "a tempo",
        "cant.",
        "marc.",
        "legg.",
        "stacc.",
        "ten.",
        "con sord.",
        "senza sord.",
        "sul G",
        "sul D",
    ]

    font_paths = []
    font_paths.extend(load_fonts_from_dir(args.text_font_dir))
    font_paths.extend(load_fonts_from_zip(args.text_fonts_zip))
    if font_paths:
        print(f"Loaded {len(font_paths)} fonts for text noise.")

    text_noise = TextNoiseOverlay(
        terms=terms,
        prob=args.text_noise_prob,
        font_path=args.text_font,
        font_paths=font_paths,
        font_size_range=(args.text_font_min_size, args.text_font_max_size),
        stroke_width_range=(args.text_stroke_min, args.text_stroke_max),
    )

    train_dataset = MMRDataset(
        X_train,
        y_train,
        transform=train_transforms,
        staff_mask_root=args.staff_mask_root,
        staff_mask_suffix=args.staff_mask_suffix,
        staff_mask_ext=args.staff_mask_ext,
        text_noise=text_noise,
    )
    val_dataset = MMRDataset(X_val, y_val, transform=val_transforms)

    if args.use_weighted_sampler:
        pos_weight_val = len(paths_0) / max(1, len(paths_1))
        sample_weights = [pos_weight_val if y == 1 else 1.0 for y in y_train]
        sampler = WeightedRandomSampler(
            sample_weights, num_samples=len(sample_weights), replacement=True
        )
        train_loader = DataLoader(
            train_dataset, batch_size=args.batch_size, sampler=sampler, num_workers=args.num_workers
        )
    else:
        train_loader = DataLoader(
            train_dataset, batch_size=args.batch_size, shuffle=True, num_workers=args.num_workers
        )

    val_loader = DataLoader(
        val_dataset, batch_size=args.batch_size, shuffle=False, num_workers=args.num_workers
    )

    # 2. Define Model
    # Use ResNet18 (Pretrained)
    model = models.resnet18(weights=ResNet18_Weights.IMAGENET1K_V1)
    # Modify final layer for binary classification
    # ResNet18 fc in: 512, out: 1000
    model.fc = nn.Linear(model.fc.in_features, 1)

    model = model.to(device)

    # Weighted Loss?
    # Neg:Pos ratio is ~3500:192 (~18:1).
    # We should use pos_weight in BCEWithLogitsLoss
    pos_weight = torch.tensor([len(paths_0) / len(paths_1)]).to(device)
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

    optimizer = optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    # 3. Training Loop
    best_f1 = 0.0

    tqdm = _get_progress_bar()

    for epoch in range(args.epochs):
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

        epoch_loss = running_loss / len(train_dataset)

        # Validation
        model.eval()
        val_preds = []
        val_targets = []

        with torch.no_grad():
            val_iter = val_loader
            if tqdm:
                val_iter = tqdm(val_loader, desc=f"Val {epoch + 1}/{args.epochs}", leave=False)

            for images, labels in val_iter:
                images = images.to(device)
                labels = labels.unsqueeze(1).to(device)
                outputs = model(images)
                preds = torch.sigmoid(outputs) > 0.5

                val_preds.extend(preds.cpu().numpy())
                val_targets.extend(labels.cpu().numpy())

        val_acc, val_prec, val_rec, val_f1 = calculate_metrics(val_targets, val_preds)

        lr = scheduler.get_last_lr()[0]
        print(
            f"Epoch {epoch + 1}/{args.epochs}: Loss={epoch_loss:.4f} | Val Acc={val_acc:.4f} F1={val_f1:.4f} Prec={val_prec:.4f} Rec={val_rec:.4f} LR={lr:.6f}"
        )

        if writer:
            writer.add_scalar("loss/train", epoch_loss, epoch + 1)
            writer.add_scalar("val/acc", val_acc, epoch + 1)
            writer.add_scalar("val/prec", val_prec, epoch + 1)
            writer.add_scalar("val/rec", val_rec, epoch + 1)
            writer.add_scalar("val/f1", val_f1, epoch + 1)
            writer.add_scalar("lr", lr, epoch + 1)

        if val_f1 > best_f1:
            best_f1 = val_f1
            torch.save(model.state_dict(), args.output_model)
            print(f"  Saved best model to {args.output_model}")

        scheduler.step()

    print("Training Complete.")
    if writer:
        writer.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-root",
        type=str,
        required=True,
        help="Path to dataset root (containing train/0, train/1)",
    )
    parser.add_argument("--output-model", type=str, default="mmr_classifier_best.pth")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--no-weighted-sampler", dest="use_weighted_sampler", action="store_false")
    parser.set_defaults(use_weighted_sampler=True)
    parser.add_argument("--staff-mask-root", type=str, default=None)
    parser.add_argument("--staff-mask-suffix", type=str, default="_staff")
    parser.add_argument("--staff-mask-ext", type=str, default=".png")
    parser.add_argument("--text-noise-prob", type=float, default=0.7)
    parser.add_argument(
        "--text-font",
        type=str,
        default=None,
        help="Path to a music text font (e.g. Bravura/Finale).",
    )
    parser.add_argument(
        "--text-font-dir",
        type=str,
        default=None,
        help="Directory with .ttf/.otf fonts for random sampling.",
    )
    parser.add_argument(
        "--text-fonts-zip",
        type=str,
        default=None,
        help="Zip file containing .ttf/.otf fonts for random sampling.",
    )
    parser.add_argument("--text-font-min-size", type=int, default=16)
    parser.add_argument("--text-font-max-size", type=int, default=40)
    parser.add_argument("--text-stroke-min", type=int, default=0)
    parser.add_argument("--text-stroke-max", type=int, default=1)
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--log-dir", type=str, default=None, help="Enable TensorBoard logging.")

    args = parser.parse_args()
    train_model(args)
