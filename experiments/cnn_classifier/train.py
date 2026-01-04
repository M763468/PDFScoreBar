import argparse
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader, WeightedRandomSampler
from torch.utils.tensorboard import SummaryWriter
from torchvision import transforms, models
from pathlib import Path
from PIL import Image, ImageFilter
import glob
import os
import yaml
import numpy as np
import random
from tqdm import tqdm

# --- Configuration ---
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
DEFAULT_WORK_DIR = Path("logs/cnn_barline_classification/training")
DATASET_ROOT = Path(os.getenv("CNN_DATASET_ROOT", "/mnt/s/dev/datasets/cnn_classifier_v1"))
TRAIN_SPLIT_DIR = DATASET_ROOT / "splits" / "train"
VAL_SPLIT_DIR = DATASET_ROOT / "splits" / "val"

# --- Augmentation Helpers ---
class AddSaltPepperNoise(object):
    def __init__(self, density=0.01, p=0.5):
        self.density = density
        self.p = p

    def __call__(self, img):
        if random.random() < self.p:
            img_np = np.array(img)
            # Salt
            s_mask = np.random.rand(*img_np.shape[:2]) < (self.density / 2)
            img_np[s_mask] = 255
            # Pepper
            p_mask = np.random.rand(*img_np.shape[:2]) < (self.density / 2)
            img_np[p_mask] = 0
            return Image.fromarray(img_np)
        return img

    def __repr__(self):
        return f'{self.__class__.__name__}(density={self.density}, p={self.p})'

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
        return f'{self.__class__.__name__}(radius_range=({self.radius_min}, {self.radius_max}), p={self.p})'

def get_transforms(img_size, split='train'):
    if split == 'train':
        return transforms.Compose([
            # Structural/Geometry
            transforms.RandomAffine(
                degrees=2, # Very slight rotation
                translate=(0.0, 0.1), # Vertical shift ONLY (max 10%)
                scale=(0.95, 1.05), # Slight scale
                fill=255 # White background
            ),
            # Texture/Degradation
            GaussianBlur(radius_range=(0.5, 1.5), p=0.3),
            AddSaltPepperNoise(density=0.02, p=0.3),
            transforms.ColorJitter(brightness=0.3, contrast=0.3),
            
            # Common
            transforms.Resize(tuple(img_size)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])
    else:
        return transforms.Compose([
            transforms.Resize(tuple(img_size)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])

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
            # Return a dummy image (black) to avoid crash, but log it
            img = Image.new('RGB', (128, 256), (0, 0, 0))

        if self.transform:
            img = self.transform(img)

        return img, torch.tensor(label, dtype=torch.float32)

# --- Model ---
def get_model(model_name='mobilenet_v3_small', pretrained=True):
    # Use weights if pretrained is True
    weights = 'DEFAULT' if pretrained else None

    if model_name == 'mobilenet_v3_small':
        model = models.mobilenet_v3_small(weights=weights)
        in_features = model.classifier[3].in_features
        model.classifier[3] = nn.Linear(in_features, 1)
    elif model_name == 'resnet18':
        model = models.resnet18(weights=weights)
        in_features = model.fc.in_features
        model.fc = nn.Linear(in_features, 1)
    else:
        raise ValueError(f"Model {model_name} not supported.")

    return model

# --- Metrics ---
def calculate_metrics(outputs, labels):
    probs = torch.sigmoid(outputs)
    preds = (probs > 0.5).float()
    
    tp = ((preds == 1) & (labels == 1)).sum().item()
    fp = ((preds == 1) & (labels == 0)).sum().item()
    fn = ((preds == 0) & (labels == 1)).sum().item()
    tn = ((preds == 0) & (labels == 0)).sum().item()
    
    return tp, fp, fn, tn

# --- Training Loop ---
def get_args():
    parser = argparse.ArgumentParser(description="Train a CNN for barline classification.")
    parser.add_argument("--config", type=str, default=None, help="Path to a config file.")
    parser.add_argument("--work-dir", type=str, help="Working directory for logs and models.")
    parser.add_argument("--tp-dir", type=str, help="Directory of true positive crops. Overrides work-dir.")
    parser.add_argument("--fp-dir", type=str, help="Directory of false positive crops. Overrides work-dir.")
    parser.add_argument("--epochs", type=int, default=20, help="Number of training epochs.")
    parser.add_argument("--batch-size", type=int, default=32, help="Batch size for training and validation.")
    parser.add_argument("--learning-rate", type=float, default=1e-4, help="Learning rate for the optimizer.")
    parser.add_argument("--img-size", type=int, nargs=2, default=[256, 128], help="Image size (height, width).")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility.")
    parser.add_argument("--log-dir", type=str, help="Directory for TensorBoard logs.")
    parser.add_argument("--model-name", type=str, default='mobilenet_v3_small', help="Name of the model to use (mobilenet_v3_small, resnet18).")
    parser.add_argument("--train-val-split", type=float, help="Train/validation split ratio.")
    parser.add_argument("--no-augment", action='store_true', help="Disable data augmentation.")

    args = parser.parse_args()

    if args.config:
        with open(args.config, 'r') as f:
            config_args = yaml.safe_load(f)
        config_ns = argparse.Namespace(**config_args)
        for key, value in vars(config_ns).items():
            if getattr(args, key) is None:
                setattr(args, key, value)

    return args

def train(args):
    if args.seed is not None:
        torch.manual_seed(args.seed)
        np.random.seed(args.seed)
        random.seed(args.seed)

    print(f"Using device: {DEVICE}")

    # TensorBoard
    if args.log_dir:
        writer = SummaryWriter(log_dir=args.log_dir)
    else:
        writer = None

    # Paths
    work_dir = Path(args.work_dir) if args.work_dir else DEFAULT_WORK_DIR
    work_dir.mkdir(parents=True, exist_ok=True)
    
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
        print(f"Checked: {tp_dir}, {fp_dir}")
        if writer:
            writer.close()
        return

    # Transforms
    train_transform = get_transforms(args.img_size, 'train' if not args.no_augment else 'val')
    val_transform = get_transforms(args.img_size, 'val')

    # Data Loaders
    if val_tp_dir and val_tp_dir.exists() and val_fp_dir and val_fp_dir.exists():
        train_dataset = BarlineDataset(tp_dir, fp_dir, transform=train_transform)
        val_dataset = BarlineDataset(val_tp_dir, val_fp_dir, transform=val_transform)
    else:
        dataset = BarlineDataset(tp_dir, fp_dir, transform=train_transform)
        # Re-use dataset for validation but with different transform? 
        # Ideally we split files first. Since BarlineDataset reads dir, we accept this.
        # But if we split randomly here, we need separate dataset objects to apply different transforms.
        # This is a bit complex with random_split. 
        # Simplified: Use same dataset, check transform in getitem? No.
        # Clean way: Subset.
        split_ratio = args.train_val_split if args.train_val_split is not None else 0.8
        train_size = int(split_ratio * len(dataset))
        val_size = len(dataset) - train_size
        if train_size == 0 and len(dataset) > 0: # Handle tiny datasets
            train_size = 1
            val_size = len(dataset) - train_size
            
        generator = torch.Generator().manual_seed(args.seed) if args.seed is not None else None
        train_indices, val_indices = torch.utils.data.random_split(
            range(len(dataset)), [train_size, val_size], generator=generator
        )
        
        # Create separate datasets with correct transforms
        from torch.utils.data import Subset
        train_dataset = Subset(BarlineDataset(tp_dir, fp_dir, transform=train_transform), train_indices.indices)
        val_dataset = Subset(BarlineDataset(tp_dir, fp_dir, transform=val_transform), val_indices.indices)

    # Class Weighting for Sampler (Only for Training)
    # Recover original dataset from Subset if needed
    if isinstance(train_dataset, torch.utils.data.Subset):
        # We need to access underlying dataset labels to compute weights
        # Indices are available.
        base_ds = train_dataset.dataset
        labels = [base_ds.labels[i] for i in train_dataset.indices]
    else:
        labels = train_dataset.labels

    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    
    print(f"Training Data: Pos={n_pos}, Neg={n_neg}, Total={len(labels)}")
    
    if n_pos > 0 and n_neg > 0:
        weight_pos = 1.0 / n_pos
        weight_neg = 1.0 / n_neg
        samples_weight = torch.tensor([weight_pos if l == 1 else weight_neg for l in labels], dtype=torch.float)
        sampler = WeightedRandomSampler(samples_weight, len(samples_weight))
        shuffle = False # Sampler implies shuffle
    else:
        print("Warning: Single class present in training set. Disabling WeightedRandomSampler.")
        sampler = None
        shuffle = True

    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=shuffle, sampler=sampler, num_workers=8, pin_memory=True)
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size, shuffle=False, num_workers=8, pin_memory=True)
    
    print(f"Training samples: {len(train_dataset)}, Validation samples: {len(val_dataset)}")

    # Model, Loss, Optimizer
    model = get_model(args.model_name).to(DEVICE)
    # Optional: pos_weight in loss (alternative to sampler, but sampler is better for batch stability)
    criterion = nn.BCEWithLogitsLoss() 
    optimizer = optim.Adam(model.parameters(), lr=args.learning_rate)

    best_val_f1 = 0.0

    # Loop
    for epoch in range(args.epochs):
        model.train()
        running_loss = 0.0
        train_tp, train_fp, train_fn, train_tn = 0, 0, 0, 0
        
        pbar = tqdm(train_loader, desc=f"Epoch {epoch+1}/{args.epochs} [Train]")
        for inputs, labels in pbar:
            inputs, labels = inputs.to(DEVICE), labels.to(DEVICE).unsqueeze(1)

            optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()

            running_loss += loss.item()
            pbar.set_postfix({'loss': f"{loss.item():.4f}"})
            
            # Metrics
            tp, fp, fn, tn = calculate_metrics(outputs, labels)
            train_tp += tp
            train_fp += fp
            train_fn += fn
            train_tn += tn

        train_loss = running_loss / len(train_loader) if len(train_loader) > 0 else 0
        train_precision = train_tp / (train_tp + train_fp + 1e-8)
        train_recall = train_tp / (train_tp + train_fn + 1e-8)
        train_f1 = 2 * train_precision * train_recall / (train_precision + train_recall + 1e-8)
        train_acc = (train_tp + train_tn) / (train_tp + train_tn + train_fp + train_fn + 1e-8)

        print(f"Epoch {epoch+1}/{args.epochs} [Train] Loss: {train_loss:.4f}, Acc: {train_acc:.4f}, P: {train_precision:.4f}, R: {train_recall:.4f}, F1: {train_f1:.4f}")

        # Validation
        model.eval()
        val_loss = 0.0
        val_tp, val_fp, val_fn, val_tn = 0, 0, 0, 0
        
        with torch.no_grad():
            for inputs, labels in tqdm(val_loader, desc=f"Epoch {epoch+1}/{args.epochs} [Val]", leave=False):
                inputs, labels = inputs.to(DEVICE), labels.to(DEVICE).unsqueeze(1)
                outputs = model(inputs)
                loss = criterion(outputs, labels)
                val_loss += loss.item()
                
                tp, fp, fn, tn = calculate_metrics(outputs, labels)
                val_tp += tp
                val_fp += fp
                val_fn += fn
                val_tn += tn

        if len(val_loader) > 0:
            val_loss /= len(val_loader)
            val_precision = val_tp / (val_tp + val_fp + 1e-8)
            val_recall = val_tp / (val_tp + val_fn + 1e-8)
            val_f1 = 2 * val_precision * val_recall / (val_precision + val_recall + 1e-8)
            val_acc = (val_tp + val_tn) / (val_tp + val_tn + val_fp + val_fn + 1e-8)
            
            print(f"Epoch {epoch+1}/{args.epochs} [Val]   Loss: {val_loss:.4f}, Acc: {val_acc:.4f}, P: {val_precision:.4f}, R: {val_recall:.4f}, F1: {val_f1:.4f}")
            
            if writer:
                writer.add_scalar('Loss/train', train_loss, epoch)
                writer.add_scalar('Acc/train', train_acc, epoch)
                writer.add_scalar('F1/train', train_f1, epoch)
                
                writer.add_scalar('Loss/val', val_loss, epoch)
                writer.add_scalar('Acc/val', val_acc, epoch)
                writer.add_scalar('F1/val', val_f1, epoch)
                
            # Save best model
            if val_f1 > best_val_f1:
                best_val_f1 = val_f1
                save_path = work_dir / "cnn_classifier_best.pth"
                torch.save(model.state_dict(), save_path)
                print(f"New best model saved to {save_path}")

    if writer:
        writer.close()

    # Save Last Model
    save_path = work_dir / "cnn_classifier_last.pth"
    torch.save(model.state_dict(), save_path)
    print(f"Last model saved to {save_path}")

if __name__ == "__main__":
    args = get_args()
    train(args)
