
import os
import argparse
import random
import json
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms, models
from PIL import Image
from pathlib import Path
import numpy as np

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

class MMRDataset(Dataset):
    def __init__(self, image_paths, labels, transform=None):
        self.image_paths = image_paths
        self.labels = labels
        self.transform = transform

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

        if self.transform:
            image = self.transform(image)
        
        return image, torch.tensor(label, dtype=torch.float32)

def train_model(args):
    set_seed()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    # 1. Prepare Data
    data_root = Path(args.data_root)
    # Assume data structure: data_root/train/0 and data_root/train/1
    # We will split this into train/val manually
    
    paths_0 = list((data_root / "train" / "0").glob("*.jpg"))
    paths_1 = list((data_root / "train" / "1").glob("*.jpg"))
    
    labels_0 = [0] * len(paths_0)
    labels_1 = [1] * len(paths_1)
    
    all_paths = paths_0 + paths_1
    all_labels = labels_0 + labels_1
    
    print(f"Total Data: {len(all_paths)} (Pos: {len(paths_1)}, Neg: {len(paths_0)})")
    
    # Stratified Split (Manual - simple random shuffle, close enough for large dataset)
    # To mimic stratification, we can split pos and neg separately then combine, but simple shuffle is usually fine.
    # Let's do separate split to ensure validation has positives.
    
    paths_0_train, paths_0_val, labels_0_train, labels_0_val = manual_train_test_split(paths_0, labels_0, test_size=0.2)
    paths_1_train, paths_1_val, labels_1_train, labels_1_val = manual_train_test_split(paths_1, labels_1, test_size=0.2)
    
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
    train_transforms = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.RandomHorizontalFlip(p=0.5), # Is flip safe? Yes, mmr is symmetric usually.
        transforms.RandomRotation(5),
        transforms.ColorJitter(brightness=0.2, contrast=0.2),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])
    
    val_transforms = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])
    
    train_dataset = MMRDataset(X_train, y_train, transform=train_transforms)
    val_dataset = MMRDataset(X_val, y_val, transform=val_transforms)
    
    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True, num_workers=4)
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size, shuffle=False, num_workers=4)
    
    # 2. Define Model
    # Use ResNet18 (Pretrained)
    model = models.resnet18(pretrained=True)
    # Modify final layer for binary classification
    # ResNet18 fc in: 512, out: 1000
    model.fc = nn.Linear(model.fc.in_features, 1)
    
    model = model.to(device)
    
    # Weighted Loss?
    # Neg:Pos ratio is ~3500:192 (~18:1).
    # We should use pos_weight in BCEWithLogitsLoss
    pos_weight = torch.tensor([len(paths_0) / len(paths_1)]).to(device)
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    
    optimizer = optim.Adam(model.parameters(), lr=args.lr)
    
    # 3. Training Loop
    best_f1 = 0.0
    
    for epoch in range(args.epochs):
        model.train()
        running_loss = 0.0
        
        for images, labels in train_loader:
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
            for images, labels in val_loader:
                images = images.to(device)
                labels = labels.unsqueeze(1).to(device)
                outputs = model(images)
                preds = torch.sigmoid(outputs) > 0.5
                
                val_preds.extend(preds.cpu().numpy())
                val_targets.extend(labels.cpu().numpy())
                
        val_acc, val_prec, val_rec, val_f1 = calculate_metrics(val_targets, val_preds)
        
        print(f"Epoch {epoch+1}/{args.epochs}: Loss={epoch_loss:.4f} | Val Acc={val_acc:.4f} F1={val_f1:.4f} Prec={val_prec:.4f} Rec={val_rec:.4f}")
        
        if val_f1 > best_f1:
            best_f1 = val_f1
            torch.save(model.state_dict(), args.output_model)
            print(f"  Saved best model to {args.output_model}")
            
    print("Training Complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=str, required=True, help="Path to dataset root (containing train/0, train/1)")
    parser.add_argument("--output-model", type=str, default="mmr_classifier_best.pth")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-4)
    
    args = parser.parse_args()
    train_model(args)
