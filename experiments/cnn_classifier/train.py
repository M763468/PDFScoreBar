import argparse
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from torch.utils.tensorboard import SummaryWriter
from torchvision import transforms, models
from pathlib import Path
from PIL import Image
import glob
import os
import yaml

# --- Configuration ---
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
DEFAULT_WORK_DIR = Path("logs/cnn_barline_classification/training")
DATASET_ROOT = Path(os.getenv("CNN_DATASET_ROOT", "/mnt/d/datasets/cnn_classifier_v1"))
TRAIN_SPLIT_DIR = DATASET_ROOT / "splits" / "train"
VAL_SPLIT_DIR = DATASET_ROOT / "splits" / "val"

# --- Dataset ---
class BarlineDataset(Dataset):
    def __init__(self, tp_dir, fp_dir, transform=None):
        self.tp_paths = sorted(list(tp_dir.glob("*.png")))
        self.fp_paths = sorted(list(fp_dir.glob("*.png")))
        self.all_paths = self.tp_paths + self.fp_paths
        self.labels = [1] * len(self.tp_paths) + [0] * len(self.fp_paths)
        self.transform = transform

    def __len__(self):
        return len(self.all_paths)

    def __getitem__(self, idx):
        path = self.all_paths[idx]
        label = self.labels[idx]

        # Load image
        img = Image.open(path).convert("RGB")

        if self.transform:
            img = self.transform(img)

        return img, torch.tensor(label, dtype=torch.float32)

# --- Model ---
def get_model(model_name='mobilenet_v3_small'):
    if model_name == 'mobilenet_v3_small':
        model = models.mobilenet_v3_small(pretrained=True)
        in_features = model.classifier[3].in_features
        model.classifier[3] = nn.Linear(in_features, 1)
    else:
        raise ValueError(f"Model {model_name} not supported.")

    return model

# --- Training Loop ---
def get_args():
    parser = argparse.ArgumentParser(description="Train a CNN for barline classification.")
    parser.add_argument("--config", type=str, default=None, help="Path to a config file.")
    parser.add_argument("--work-dir", type=str, help="Working directory for logs and models.")
    parser.add_argument("--tp-dir", type=str, help="Directory of true positive crops. Overrides work-dir.")
    parser.add_argument("--fp-dir", type=str, help="Directory of false positive crops. Overrides work-dir.")
    parser.add_argument("--epochs", type=int, help="Number of training epochs.")
    parser.add_argument("--batch-size", type=int, help="Batch size for training and validation.")
    parser.add_argument("--learning-rate", type=float, help="Learning rate for the optimizer.")
    parser.add_argument("--img-size", type=int, nargs=2, help="Image size (height, width).")
    parser.add_argument("--seed", type=int, help="Random seed for reproducibility.")
    parser.add_argument("--log-dir", type=str, help="Directory for TensorBoard logs.")
    parser.add_argument("--model-name", type=str, help="Name of the model to use.")
    parser.add_argument("--train-val-split", type=float, help="Train/validation split ratio.")

    args = parser.parse_args()

    if args.config:
        with open(args.config, 'r') as f:
            config_args = yaml.safe_load(f)

        # Create a new namespace to avoid conflicts
        config_ns = argparse.Namespace(**config_args)

        # Get the defaults from the parser
        defaults = parser.parse_args([])

        # Update args with config values only if they were not specified on the command line
        for key, value in vars(config_ns).items():
            if getattr(args, key) is None:
                setattr(args, key, value)

    return args

def train(args):
    if args.seed is not None:
        torch.manual_seed(args.seed)

    print(f"Using device: {DEVICE}")

    # TensorBoard
    if args.log_dir:
        writer = SummaryWriter(log_dir=args.log_dir)
    else:
        writer = None

    # Paths
    work_dir = Path(args.work_dir) if args.work_dir else DEFAULT_WORK_DIR
    use_explicit_dirs = args.tp_dir or args.fp_dir

    if use_explicit_dirs:
        tp_dir = Path(args.tp_dir) if args.tp_dir else work_dir / "tp_crops"
        fp_dir = Path(args.fp_dir) if args.fp_dir else work_dir / "fp_crops_enhanced"
        val_tp_dir = None
        val_fp_dir = None
    elif (TRAIN_SPLIT_DIR / "tp").exists() and (TRAIN_SPLIT_DIR / "fp").exists():
        tp_dir = TRAIN_SPLIT_DIR / "tp"
        fp_dir = TRAIN_SPLIT_DIR / "fp"
        val_tp_dir = VAL_SPLIT_DIR / "tp"
        val_fp_dir = VAL_SPLIT_DIR / "fp"
    else:
        tp_dir = work_dir / "tp_crops"
        fp_dir = work_dir / "fp_crops_enhanced"
        val_tp_dir = None
        val_fp_dir = None

    if not tp_dir.exists() or not fp_dir.exists():
        print("Error: Crop directories not found.")
        print(f"Checked: {tp_dir}, {fp_dir}")
        if writer:
            writer.close()
        return

    # Transforms
    transform = transforms.Compose([
        transforms.Resize(tuple(args.img_size)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])

    # Data Loaders
    if val_tp_dir and val_tp_dir.exists() and val_fp_dir and val_fp_dir.exists():
        train_dataset = BarlineDataset(tp_dir, fp_dir, transform=transform)
        val_dataset = BarlineDataset(val_tp_dir, val_fp_dir, transform=transform)
    else:
        dataset = BarlineDataset(tp_dir, fp_dir, transform=transform)
        split_ratio = args.train_val_split if args.train_val_split is not None else 0.8
        train_size = int(split_ratio * len(dataset))
        val_size = len(dataset) - train_size
        if train_size == 0 and len(dataset) > 0:
            train_size = 1
            val_size = len(dataset) - train_size
        generator = torch.Generator().manual_seed(args.seed) if args.seed is not None else None
        train_dataset, val_dataset = torch.utils.data.random_split(
            dataset,
            [train_size, val_size],
            generator=generator
        )

    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True, num_workers=2)
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size, shuffle=False, num_workers=2)
    print(f"Training samples: {len(train_dataset)}, Validation samples: {len(val_dataset)}")

    # Model, Loss, Optimizer
    model = get_model(args.model_name).to(DEVICE)
    criterion = nn.BCEWithLogitsLoss()
    optimizer = optim.Adam(model.parameters(), lr=args.learning_rate)

    # Loop
    for epoch in range(args.epochs):
        model.train()
        running_loss = 0.0
        correct = 0
        total = 0

        for inputs, labels in train_loader:
            inputs, labels = inputs.to(DEVICE), labels.to(DEVICE).unsqueeze(1)

            optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()

            running_loss += loss.item()
            preds = (torch.sigmoid(outputs) > 0.5).float()
            correct += (preds == labels).sum().item()
            total += labels.size(0)

        train_loss = running_loss / len(train_loader)
        train_acc = correct / total
        print(f"Epoch {epoch+1}/{args.epochs}, Loss: {train_loss:.4f}, Train Acc: {train_acc:.4f}")

        # Validation
        model.eval()
        val_correct = 0
        val_total = 0
        val_loss = 0
        with torch.no_grad():
            for inputs, labels in val_loader:
                inputs, labels = inputs.to(DEVICE), labels.to(DEVICE).unsqueeze(1)
                outputs = model(inputs)
                loss = criterion(outputs, labels)
                val_loss += loss.item()
                preds = (torch.sigmoid(outputs) > 0.5).float()
                val_correct += (preds == labels).sum().item()
                val_total += labels.size(0)

        if val_total > 0:
            val_acc = val_correct / val_total
            val_loss /= len(val_loader)
            print(f"Validation Acc: {val_acc:.4f}, Validation Loss: {val_loss:.4f}")
            if writer:
                writer.add_scalar('Loss/train', train_loss, epoch)
                writer.add_scalar('Accuracy/train', train_acc, epoch)
                writer.add_scalar('Loss/validation', val_loss, epoch)
                writer.add_scalar('Accuracy/validation', val_acc, epoch)

    if writer:
        writer.close()

    # Save Model
    save_path = work_dir / "cnn_classifier_v1.pth"
    torch.save(model.state_dict(), save_path)
    print(f"Model saved to {save_path}")

if __name__ == "__main__":
    args = get_args()
    train(args)
