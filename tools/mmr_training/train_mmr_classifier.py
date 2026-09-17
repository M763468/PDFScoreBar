import argparse
import io
import json
import random
import subprocess
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from PIL import Image, ImageDraw, ImageFont
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from torchvision import models, transforms
from torchvision.models import ResNet18_Weights

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.mmr_training.issue332.geometry_training import (
    DEFAULT_DELTAS_PX,
    DEFAULT_EXCLUDED_TAGS,
    DEFAULT_GEOMETRY_AUGMENTATION_PROBABILITY,
    GEOMETRY_FAMILIES,
    SemanticMMRDataset,
    StaffRelativeMMRDataset,
    collate_staff_relative_batch,
    prepare_split_contract,
    samples_for_split,
    sha256_file,
)
from tools.mmr_training.issue332.staff_model import StaffRelativeResNet18
from tools.mmr_training.issue332.staff_view import (
    STAFF_CORE_CENTER_VIEW,
    staff_view_contract,
)


def calculate_metrics(y_true, y_pred):
    y_true = np.asarray(y_true).reshape(-1)
    y_pred = np.asarray(y_pred).reshape(-1)
    tp = int(np.sum((y_true == 1) & (y_pred == 1)))
    tn = int(np.sum((y_true == 0) & (y_pred == 0)))
    fp = int(np.sum((y_true == 0) & (y_pred == 1)))
    fn = int(np.sum((y_true == 1) & (y_pred == 0)))
    acc = (tp + tn) / len(y_true) if len(y_true) else 0.0
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
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
    val_data = combined[split_idx:]
    if not train_data or not val_data:
        raise ValueError("legacy crop split produced an empty partition")
    x_train, y_train = zip(*train_data)
    x_val, y_val = zip(*val_data)
    return list(x_train), list(x_val), list(y_train), list(y_val)


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
        return float(np.count_nonzero(patch)) / float(patch.size) if patch.size else 0.0

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
            pos_type = random.choices(["top", "bottom", "cross"], weights=[0.45, 0.45, 0.10], k=1)[
                0
            ]
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
        try:
            image = Image.open(img_path).convert("RGB")
        except Exception as exc:
            print(f"Error loading {img_path}: {exc}")
            image = Image.new("RGB", (224, 224), (0, 0, 0))

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
    import zipfile

    fonts = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            if name.lower().endswith((".ttf", ".otf")):
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
    font_paths = load_fonts_from_dir(args.text_font_dir) + load_fonts_from_zip(args.text_fonts_zip)
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
    train_dataset.full_corpus_class_counts = {"0": len(paths_0), "1": len(paths_1)}
    val_dataset = MMRDataset(val_paths, val_labels, transform=eval_transform)
    class_counts = {
        "train": {"0": len(y0_train), "1": len(y1_train)},
        "val": {"0": len(y0_val), "1": len(y1_val)},
        "test": {"0": 0, "1": 0},
    }
    return (
        train_dataset,
        val_dataset,
        None,
        train_labels,
        None,
        class_counts,
    )


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
        split_mode=str(split_config.get("mode", "score-grouped")),
    )

    train_samples = samples_for_split(eligible, split_contract, "train")
    val_samples = samples_for_split(eligible, split_contract, "validation")
    test_samples = samples_for_split(eligible, split_contract, "test")
    margin_px = int(config.get("margin_px", 20))
    deltas_px = tuple(int(value) for value in config.get("deltas_px", DEFAULT_DELTAS_PX))
    geometry_probability = (
        getattr(args, "geometry_augmentation_probability", None)
        if getattr(args, "geometry_augmentation_probability", None) is not None
        else float(
            config.get(
                "geometry_augmentation_probability",
                DEFAULT_GEOMETRY_AUGMENTATION_PROBABILITY,
            )
        )
    )
    if args.geometry_augmentation == "none":
        geometry_probability = 0.0
    args.geometry_augmentation_probability = geometry_probability
    configured_families = getattr(args, "geometry_augmentation_families", None)
    geometry_families = tuple(
        configured_families or config.get("geometry_augmentation_families", GEOMETRY_FAMILIES[1:])
    )
    invalid_families = set(geometry_families) - set(GEOMETRY_FAMILIES[1:])
    if not geometry_families or invalid_families:
        raise ValueError(
            "geometry_augmentation_families must contain supported families: "
            f"{sorted(invalid_families)}"
        )
    args.geometry_augmentation_families = list(geometry_families)

    classifier_view = getattr(args, "classifier_view", "full_measure")
    if classifier_view not in {"full_measure", STAFF_CORE_CENTER_VIEW}:
        raise ValueError(f"unsupported classifier view: {classifier_view}")
    dataset_class = (
        StaffRelativeMMRDataset if classifier_view == STAFF_CORE_CENTER_VIEW else SemanticMMRDataset
    )

    train_dataset = dataset_class(
        train_samples,
        manifest_path=manifest_path,
        transform=train_transform,
        geometry_policy=args.geometry_augmentation,
        deltas_px=deltas_px,
        margin_px=margin_px,
        seed=args.seed,
        text_noise=text_noise,
        geometry_augmentation_probability=geometry_probability,
        geometry_families=geometry_families,
    )
    val_dataset = dataset_class(
        val_samples,
        manifest_path=manifest_path,
        transform=eval_transform,
        geometry_policy="none",
        deltas_px=deltas_px,
        margin_px=margin_px,
        seed=args.seed,
        geometry_augmentation_probability=0.0,
        geometry_families=geometry_families,
    )
    test_dataset = dataset_class(
        test_samples,
        manifest_path=manifest_path,
        transform=eval_transform,
        geometry_policy="none",
        deltas_px=deltas_px,
        margin_px=margin_px,
        seed=args.seed,
        geometry_augmentation_probability=0.0,
        geometry_families=geometry_families,
    )
    class_counts = {
        "train": {
            "0": sum(int(sample["label"]) == 0 for sample in train_samples),
            "1": sum(int(sample["label"]) == 1 for sample in train_samples),
        },
        "val": {
            "0": sum(int(sample["label"]) == 0 for sample in val_samples),
            "1": sum(int(sample["label"]) == 1 for sample in val_samples),
        },
        "test": {
            "0": sum(int(sample["label"]) == 0 for sample in test_samples),
            "1": sum(int(sample["label"]) == 1 for sample in test_samples),
        },
    }
    return (
        train_dataset,
        val_dataset,
        test_dataset,
        train_dataset.labels,
        split_contract,
        class_counts,
    )


def _make_loader(dataset, labels, args, *, train):
    loader_options = {
        "num_workers": args.num_workers,
        "pin_memory": torch.cuda.is_available(),
        "persistent_workers": args.num_workers > 0,
    }
    if getattr(dataset, "is_staff_relative", False):
        loader_options["collate_fn"] = collate_staff_relative_batch
    if train and args.use_weighted_sampler:
        positives = sum(int(label) == 1 for label in labels)
        negatives = sum(int(label) == 0 for label in labels)
        if positives == 0 or negatives == 0:
            raise ValueError("training split must contain both classes")
        positive_weight = negatives / positives
        weights = [positive_weight if int(label) == 1 else 1.0 for label in labels]
        sampler = WeightedRandomSampler(weights, num_samples=len(labels), replacement=True)
        return DataLoader(
            dataset,
            batch_size=args.batch_size,
            sampler=sampler,
            **loader_options,
        )
    return DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=train,
        **loader_options,
    )


def _forward_batch(model, batch, device):
    if len(batch) == 3:
        images, staff_mask, labels = batch
        return model(
            images.to(device, non_blocking=device.type == "cuda"),
            staff_mask.to(device, non_blocking=device.type == "cuda"),
        ), labels
    images, labels = batch
    return model(images.to(device, non_blocking=device.type == "cuda")), labels


def _evaluate_loader(model, loader, device):
    probabilities = []
    targets = []
    model.eval()
    with torch.inference_mode():
        for batch in loader:
            outputs, labels = _forward_batch(model, batch, device)
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


def _training_code_commit() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip() or None


def _train_pos_weight(class_counts: dict[str, dict[str, int]]) -> float:
    return _pos_weight_from_counts(class_counts["train"])


def _pos_weight_from_counts(class_counts: dict[str, int]) -> float:
    negatives = int(class_counts["0"])
    positives = int(class_counts["1"])
    if positives == 0 or negatives == 0:
        raise ValueError("training corpus must contain both classes")
    return negatives / positives


def _build_model(classifier_view: str):
    if classifier_view == STAFF_CORE_CENTER_VIEW:
        return StaffRelativeResNet18()
    if classifier_view != "full_measure":
        raise ValueError(f"unsupported classifier view: {classifier_view}")
    model = models.resnet18(weights=ResNet18_Weights.IMAGENET1K_V1)
    model.fc = nn.Linear(model.fc.in_features, 1)
    return model


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
    text_noise = _text_noise(args) if args.training_profile == "current" else None

    if args.manifest:
        (
            train_dataset,
            val_dataset,
            test_dataset,
            train_labels,
            split_contract,
            class_counts,
        ) = _manifest_datasets(args, train_transform, eval_transform, text_noise)
        mode = "semantic-manifest"
    else:
        (
            train_dataset,
            val_dataset,
            test_dataset,
            train_labels,
            split_contract,
            class_counts,
        ) = _legacy_datasets(args, train_transform, eval_transform, text_noise)
        mode = "legacy-crops"

    print(
        f"Data mode={mode} profile={args.training_profile} "
        f"train={len(train_dataset)} validation={len(val_dataset)} "
        f"test={len(test_dataset) if test_dataset is not None else 0}"
    )
    train_loader = _make_loader(train_dataset, train_labels, args, train=True)
    val_loader = _make_loader(val_dataset, [], args, train=False)

    if mode == "semantic-manifest":
        pos_weight_counts = class_counts["train"]
        pos_weight_source = "train_split"
    else:
        pos_weight_counts = train_dataset.full_corpus_class_counts
        pos_weight_source = "full_corpus"
    pos_weight = _pos_weight_from_counts(pos_weight_counts)

    classifier_view = getattr(args, "classifier_view", "full_measure")
    model = _build_model(classifier_view)
    model = model.to(device)

    criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([pos_weight], device=device))
    if args.training_profile == "historical":
        optimizer = optim.Adam(model.parameters(), lr=args.lr)
        scheduler = None
    else:
        optimizer = optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
        scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    output_model_path = Path(args.output_model)
    output_model_path.parent.mkdir(parents=True, exist_ok=True)
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

        for batch in train_iter:
            non_blocking = device.type == "cuda"
            outputs, labels = _forward_batch(model, batch, device)
            labels = labels.unsqueeze(1).to(device, non_blocking=non_blocking)
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            running_loss += loss.item() * labels.size(0)

        val_metrics, _ = _evaluate_loader(model, val_loader, device)
        epoch_loss = running_loss / len(train_dataset)
        lr = optimizer.param_groups[0]["lr"]
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
            torch.save(model.state_dict(), output_model_path)
            print(f"  Saved best model to {output_model_path}")

        if scheduler is not None:
            scheduler.step()

    if writer:
        writer.close()

    result = {
        "mode": mode,
        "training_profile": args.training_profile,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "optimizer": "Adam" if args.training_profile == "historical" else "AdamW",
        "weighted_sampler": bool(args.use_weighted_sampler),
        "text_noise_enabled": text_noise is not None,
        "classifier_view": classifier_view,
        "class_counts": class_counts,
        "pos_weight": float(pos_weight),
        "pos_weight_counts": pos_weight_counts,
        "pos_weight_source": pos_weight_source,
        "geometry_augmentation": args.geometry_augmentation if args.manifest else None,
        "geometry_augmentation_probability": (
            args.geometry_augmentation_probability if args.manifest else None
        ),
        "geometry_augmentation_families": (
            args.geometry_augmentation_families if args.manifest else None
        ),
        "best_epoch": best_epoch,
        "selection_metric": "validation_f1",
        "best_validation_f1": best_f1,
        "output_model": str(output_model_path.resolve()),
        "output_model_sha256": sha256_file(output_model_path),
        "test_used_for_model_selection": False,
        "provenance": {
            "training_code_commit": _training_code_commit(),
            "manifest_sha256": sha256_file(Path(args.manifest)) if args.manifest else None,
            "split_sha256": (
                sha256_file(Path(args.split_manifest))
                if split_contract is not None and Path(args.split_manifest).is_file()
                else None
            ),
            "seed": int(args.seed),
            "profile": args.training_profile,
            "class_counts": class_counts,
            "pos_weight": float(pos_weight),
            "pos_weight_counts": pos_weight_counts,
            "pos_weight_source": pos_weight_source,
            "geometry_augmentation_families": (
                args.geometry_augmentation_families if args.manifest else None
            ),
            "classifier_view": classifier_view,
            "classifier_view_contract": (
                staff_view_contract() if classifier_view == STAFF_CORE_CENTER_VIEW else None
            ),
        },
    }

    if split_contract is not None:
        result["split_contract"] = split_contract
        result["split_manifest"] = str(Path(args.split_manifest).resolve())
        result["split_manifest_sha256"] = sha256_file(Path(args.split_manifest))

    if test_dataset is not None:
        best_state = torch.load(output_model_path, map_location=device, weights_only=True)
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
        "--classifier-view",
        choices=("full_measure", STAFF_CORE_CENTER_VIEW),
        default="full_measure",
        help="Classifier input view; staff-relative view is one item per measure with max aggregation.",
    )
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
    parser.add_argument(
        "--geometry-augmentation-probability",
        type=float,
        default=None,
        help="Probability of source-space perturbation for absolute geometry policy.",
    )
    parser.add_argument(
        "--geometry-augmentation-family",
        dest="geometry_augmentation_families",
        action="append",
        choices=GEOMETRY_FAMILIES[1:],
        default=None,
        help="Restrict absolute geometry sampling to one or more perturbation families.",
    )
    parser.add_argument(
        "--training-profile",
        choices=("historical", "current"),
        default=None,
        help="Defaults to historical for semantic manifests and current for legacy crops.",
    )
    parser.add_argument("--output-model", type=str, default="mmr_classifier_best.pth")
    parser.add_argument("--metrics-output", type=str, default=None)
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--seed", type=int, default=42)
    sampler = parser.add_mutually_exclusive_group()
    sampler.add_argument("--weighted-sampler", dest="use_weighted_sampler", action="store_true")
    sampler.add_argument("--no-weighted-sampler", dest="use_weighted_sampler", action="store_false")
    parser.set_defaults(use_weighted_sampler=None)
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

    if args.training_profile is None:
        args.training_profile = "historical" if args.manifest else "current"
    if args.epochs is None:
        args.epochs = 20 if args.training_profile == "historical" else 10
    if args.batch_size is None:
        args.batch_size = 32 if args.training_profile == "historical" else 64
    if args.use_weighted_sampler is None:
        args.use_weighted_sampler = args.training_profile == "current"

    train_model(args)


if __name__ == "__main__":
    main()
