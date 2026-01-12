# CNN Retraining Guide - Phase 1: FP-Based Active Learning

## Dataset Preparation (COMPLETED)

### Extracted FP Samples
- **Source:** Global evaluation results (`logs/global_final_opt`)
- **Extraction criteria:** CNN scores 0.5-0.9 (high-confidence false positives)
- **Samples extracted:** 1534 FP crops
- **Output location:** `datasets/cnn_classifier_v4_fp_augmented/splits/train/fp/`

### Dataset Statistics
- **TP samples:** 20,416 (from `datasets/cnn_classifier_v3_active_learning/splits/train/tp/`)
- **FP samples:** 1534 (newly extracted)
- **Total samples:** ~22,000 (5.5x increase from original 4017)
- **Class balance:** ~93% TP, ~7% FP

## Retraining Procedure

### Step 1: Prepare Dataset Symlinks (if needed)

```bash
# Create symlinks to avoid duplicating 20K+ files
cd datasets/cnn_classifier_v4_fp_augmented/splits/train/tp
ln -s ../../../../cnn_classifier_v3_active_learning/splits/train/tp/*.png .
cd -
```

### Step 2: Train CNN Model

```bash
# Activate virtual environment
source .venv_cnn_classifier/bin/activate

# Run training with recommended parameters
python experiments/cnn_classifier/train.py \
    --tp-dir datasets/cnn_classifier_v4_fp_augmented/splits/train/tp \
    --fp-dir datasets/cnn_classifier_v4_fp_augmented/splits/train/fp \
    --model-name resnet18 \
    --learning-rate 0.001 \
    --batch-size 320 \
    --epochs 50 \
    --output-dir logs/cnn_retrain_v4_fp_augmented
```

**Alternative: Use existing TP directory directly**
```bash
python experiments/cnn_classifier/train.py \
    --tp-dir datasets/cnn_classifier_v3_active_learning/splits/train/tp \
    --fp-dir datasets/cnn_classifier_v4_fp_augmented/splits/train/fp \
    --model-name resnet18 \
    --learning-rate 0.001 \
    --batch-size 32 \
    --epochs 50 \
    --output-dir logs/cnn_retrain_v4_fp_augmented
```

### Step 3: Monitor Training

```bash
# Start TensorBoard (if not already running)
tensorboard --logdir=logs/cnn_retrain_v4_fp_augmented

# Monitor training progress
# Expected training time: 2-3 hours on GPU
```

### Step 4: Evaluate Retrained Model

```bash
# Re-score all candidates with new model
python tools/cnn_classifier/score_candidates_batch.py \
    --logs logs/global_final_opt \
    --model logs/cnn_retrain_v4_fp_augmented/cnn_classifier_best.pth \
    --threshold 0.1

# Re-evaluate global performance
python tools/re_evaluate_global.py \
    --scored-root logs/global_final_opt \
    --gt-root data/evaluation2/annotations \
    --output-csv logs/global_final_opt/global_summary_v4.csv \
    --threshold 0.5

# Check results
python -c "
import csv
with open('logs/global_final_opt/global_summary_v4.csv') as f:
    reader = list(csv.DictReader(f))
    tp = sum(int(r['tp']) for r in reader)
    fp = sum(int(r['fp']) for r in reader)
    fn = sum(int(r['fn_total']) for r in reader)
    gt = sum(int(r['gt_count']) for r in reader)
    print(f'Recall: {tp/gt:.4f}, Precision: {tp/(tp+fp):.4f}')
    print(f'TP: {tp}, FP: {fp}, FN: {fn}')
"
```

## Expected Outcomes

### Conservative Estimate
- **Precision improvement:** 45.9% → 60-70%
- **Recall:** Maintained at 99%+
- **FP reduction:** 3834 → 2000-2500

### Optimistic Estimate
- **Precision improvement:** 45.9% → 70-80%
- **Recall:** Maintained at 99%+
- **FP reduction:** 3834 → 1500-2000

## Iteration Strategy

If precision is still below target (80%):

### Phase 2: Extract More FPs
```bash
# Extract FPs with scores 0.3-0.5 (medium confidence)
python tools/cnn_classifier/extract_fps_by_score_range.py \
    --scored-root logs/global_final_opt \
    --image-root data/evaluation2/images \
    --gt-root data/evaluation2/annotations \
    --output-dir datasets/cnn_classifier_v5_fp_augmented/splits/train/fp \
    --min-score 0.3 \
    --max-score 0.5 \
    --max-samples 2000 \
    --threshold 0.5
```

### Phase 3: Consider Architecture Upgrade
- Try ResNet50 for more capacity
- Try EfficientNet-B0 for better efficiency
- Add data augmentation (rotation, brightness, etc.)

## Training Parameters Explanation

- **learning-rate 0.001:** Standard for fine-tuning pre-trained models
- **batch-size 32:** Balance between memory usage and training stability
- **epochs 50:** Sufficient for convergence with early stopping
- **model-name resnet18:** Proven architecture, good balance of speed/accuracy

## Notes

- Training will use GPU if available (CUDA)
- Model checkpoints saved to `logs/cnn_retrain_v4_fp_augmented/`
- Best model saved as `cnn_classifier_best.pth`
- Training logs available in TensorBoard

## Success Criteria

- **Minimum acceptable:** Precision >70%, Recall >95%
- **Target:** Precision >80%, Recall >98%
- **Stretch goal:** Precision >90%, Recall >98%
