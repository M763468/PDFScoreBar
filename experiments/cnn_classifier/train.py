import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms, models
from pathlib import Path
from PIL import Image
import cv2
import glob
import os

# --- Configuration ---
BATCH_SIZE = 16  # Small batch size for limited resources TODO: adjust as needed
LEARNING_RATE = 0.001
NUM_EPOCHS = 10
IMG_SIZE = (256, 128) # H, W - consistent with crop logic TODO: adjust as needed
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
WORK_DIR = Path("logs/cnn_barline_classification/training") # Adjust relative to execution root
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
        img = cv2.imread(str(path))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(img)

        if self.transform:
            img = self.transform(img)

        return img, torch.tensor(label, dtype=torch.float32)

# --- Model ---
def get_model():
    # Use MobileNetV3 Small for lightweight inference TODO: adjust as needed. is this the best choice?
    model = models.mobilenet_v3_small(pretrained=True)
    
    # Modify classifier for binary classification
    # MobileNetV3 classifier structure:
    # (classifier): Sequential(
    #   (0): Linear(...)
    #   (1): Hardswish()
    #   (2): Dropout(...)
    #   (3): Linear(..., out_features=1000)
    # )
    in_features = model.classifier[3].in_features
    model.classifier[3] = nn.Linear(in_features, 1)
    
    return model

# --- Training Loop ---
def train():
    print(f"Using device: {DEVICE}")
    
    # Paths　TODO: データセット再作成：元の画像の解像度の違いから、TP/FPのcrop画像の範囲がずれている可能性あり+ダウンロードしたデータから作った追加データセットへのパス移動
    if (TRAIN_SPLIT_DIR / "tp").exists() and (TRAIN_SPLIT_DIR / "fp").exists():
        train_tp_dir = TRAIN_SPLIT_DIR / "tp"
        train_fp_dir = TRAIN_SPLIT_DIR / "fp"
        val_tp_dir = VAL_SPLIT_DIR / "tp"
        val_fp_dir = VAL_SPLIT_DIR / "fp"
    else:
        train_tp_dir = WORK_DIR / "tp_crops"
        train_fp_dir = WORK_DIR / "fp_crops_enhanced"
        val_tp_dir = None
        val_fp_dir = None
    
    if not train_tp_dir.exists() or not train_fp_dir.exists():
        print("Error: Crop directories not found.")
        print(f"Checked: {train_tp_dir}, {train_fp_dir}")
        return

    # Transforms
    transform = transforms.Compose([
        transforms.Resize(IMG_SIZE),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ]) # TODO: データ拡張を追加検討

    # Data Loaders
    train_dataset = BarlineDataset(train_tp_dir, train_fp_dir, transform=transform)
    if val_tp_dir and val_tp_dir.exists() and val_fp_dir and val_fp_dir.exists():
        val_dataset = BarlineDataset(val_tp_dir, val_fp_dir, transform=transform)
    else:
        val_size = max(1, int(0.2 * len(train_dataset)))
        train_size = len(train_dataset) - val_size
        train_dataset, val_dataset = torch.utils.data.random_split(train_dataset, [train_size, val_size])
    
    train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True, num_workers=2)
    val_loader = DataLoader(val_dataset, batch_size=BATCH_SIZE, shuffle=False, num_workers=2)
    
    print(f"Training samples: {len(train_dataset)}, Validation samples: {len(val_dataset)}")

    # Model, Loss, Optimizer
    model = get_model().to(DEVICE)
    criterion = nn.BCEWithLogitsLoss()
    optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE) # TODO: is this the best optimizer?

    # Loop
    for epoch in range(NUM_EPOCHS):
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
            
        train_acc = correct / total
        print(f"Epoch {epoch+1}/{NUM_EPOCHS}, Loss: {running_loss/len(train_loader):.4f}, Train Acc: {train_acc:.4f}")
        
        # Validation
        model.eval()
        val_correct = 0
        val_total = 0
        with torch.no_grad():
            for inputs, labels in val_loader:
                inputs, labels = inputs.to(DEVICE), labels.to(DEVICE).unsqueeze(1)
                outputs = model(inputs)
                preds = (torch.sigmoid(outputs) > 0.5).float()
                val_correct += (preds == labels).sum().item()
                val_total += labels.size(0)
        
        if val_total > 0:
            print(f"Validation Acc: {val_correct/val_total:.4f}")

    # Save Model
    save_path = WORK_DIR / "cnn_classifier_v1.pth"
    torch.save(model.state_dict(), save_path)
    print(f"Model saved to {save_path}")

if __name__ == "__main__":
    train()
