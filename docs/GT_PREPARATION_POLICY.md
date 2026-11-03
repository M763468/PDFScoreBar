# GT Preparation Policy for Barline Detection

[日本語](GT_PREPARATION_POLICY.ja.md)

This document defines the policies for creating Ground Truth (GT) data for barline detection, specifically focusing on complex cases like double barlines and final barlines.

## 1. Classification & Labeling Policy

To ensure high-quality detection and maintain compatibility with existing datasets (like DeepScores) while allowing for future functional expansion, we adopt a **multi-label, single-event** approach.

### 1.1 Labels used in `gt_relabel_gui`
The following labels (saved as each box's `barline_type`; `barline` is the default) should be used strictly according to their musical function:
- **`barline`**: Normal single vertical barline.
- **`double_barline`**: Two vertical lines indicating a section change or key/time change.
- **`end_barline`**: A thin line followed by a thick line indicating the end of a movement or piece.
- **`repeat`**: Barlines with dots indicating a repeat section.

### 1.2 Bounding Box (BBox) Strategy
- **Unit of Labeling**: Each vertical line is treated as the minimum unit. Lines forming a double barline or final barline must be registered as **independent BBoxes**.
- **Coverage**: Each BBox must accurately encompass a single vertical line.
- **Labeling**: All BBoxes constituting a double barline must be labeled as `double_barline` (likewise for `end_barline`).
  - *Reasoning*: This ensures consistency with CNN training (which detects single lines) and allows the logical layer to merge them using the label and distance (`unit_size`).

## 2. Machine Learning (CNN) Integration

### 2.1 Training Strategy
- **Binary classification (current)**: The production CNN is a binary barline classifier (Barline vs. Non-Barline). Under this policy, all labels (`barline`, `double_barline`, `end_barline`, `repeat`) are treated as **Label 1 (Positive)** for binary training data. The selected model and threshold are defined by the [model artifact contract](contracts/MODEL_ARTIFACT_CONTRACT.md) and `configs/dense_full_pipeline.yaml`, not by this policy.
- **Multi-class Phase (Future)**: The detailed labels may later be used to train a classifier capable of distinguishing line types. No multi-class classifier is currently part of production.

### 2.2 DeepScores Consistency
- DeepScores "Label 3" (Barline) contains various types of barlines without detailed subclasses in its basic metadata.
- **Strategy**: 
  - DeepScores data will be treated as the primary source for thin (single) barline samples.
  - Custom GT will provide the high-quality samples for `double` and `end` barlines.
  - For future multi-class training, DeepScores samples can be "pseudo-labeled" based on their width (pixel count) to separate thin and thick lines.

## 3. Logical Layer (Measure Numbering)

### 3.1 Resolution of Multi-line Candidates
- CNN may detect individual lines within a double/final barline.
- **Deduplication**: The logical layer (`MeasureNumberer` in `src/measure_numbering/numbering.py`) merges candidates that fall within a threshold of **1.2 * unit_size** (`DEDUPLICATION_THRESHOLD_UNITS`, where `unit_size` is the staff line spacing).
- **Scale Invariance**: Using `unit_size` instead of fixed pixel counts ensures the system works across different resolutions and score sizes.

## 4. Workflow for a New Labeling Subset

This workflow was first applied when double/final barline labels were introduced; reuse it when adding a new subset.

1. **Pick Subset**: Select 3-5 pages containing various double and final barlines.
2. **Apply GUI**: Use `tools/gt_relabel_gui` to label them using the specific types defined above.
3. **Validate**: Ensure the resulting JSON correctly represents the logical "Barline Event".
4. **Iterate**: Once validated on the subset, proceed to full-scale GT preparation.
