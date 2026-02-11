# GT Preparation Policy for Barline Detection

This document defines the policies for creating Ground Truth (GT) data for barline detection, specifically focusing on complex cases like double barlines and final barlines.

## 1. Classification & Labeling Policy

To ensure high-quality detection and maintain compatibility with existing datasets (like DeepScores) while allowing for future functional expansion, we adopt a **multi-label, single-event** approach.

### 1.1 Labels used in `gt_relabel_gui`
The following labels should be used strictly according to their musical function:
- **`barline`**: Normal single vertical barline.
- **`double_barline`**: Two vertical lines indicating a section change or key/time change.
- **`end_barline`**: A thin line followed by a thick line indicating the end of a movement or piece.
- **`repeat`**: Barlines with dots indicating a repeat section.

### 1.2 Bounding Box (BBox) Strategy
- **Unit of Labeling**: Each "Barline Event" (including double or final bars) should be treated as a **single logical entity**.
- **Coverage**: The BBox must encompass **all constituent lines** and the space between them.
  - *Reasoning*: This simplifies the mapping to "Measure" objects in the logical numbering layer and prevents double-counting measures.

## 2. Machine Learning (CNN) Integration

### 2.1 Training Strategy
- **Binary Phase (Current)**: For the initial re-training of the binary classifier (Barline vs. Non-Barline), all labels (`barline`, `double_barline`, `end_barline`, `repeat`) will be mapped to **Label 1 (Positive)**.
- **Multi-class Phase (Future)**: The detailed labels will be used to train a classifier capable of distinguishing line types.

### 2.2 DeepScores Consistency
- DeepScores "Label 3" (Barline) contains various types of barlines without detailed subclasses in its basic metadata.
- **Strategy**: 
  - DeepScores data will be treated as the primary source for `thin_barline` samples.
  - Custom GT will provide the high-quality samples for `double` and `end` barlines.
  - For future multi-class training, DeepScores samples can be "pseudo-labeled" based on their width (pixel count) to separate thin and thick lines.

## 3. Logical Layer (Measure Numbering)

### 3.1 Resolution of Multi-line Candidates
- CNN may detect individual lines within a double/final barline.
- **Deduplication**: The logical layer (`MeasureNumberer`) must merge candidates that fall within a threshold of **1.2 * unit_size** (where `unit_size` is the staff line spacing).
- **Scale Invariance**: Using `unit_size` instead of fixed pixel counts ensures the system works across different resolutions and score sizes.

## 4. Workflow for Issue #36

1. **Pick Subset**: Select 3-5 pages containing various double and final barlines.
2. **Apply GUI**: Use `tools/gt_relabel_gui` to label them using the specific types defined above.
3. **Validate**: Ensure the resulting JSON correctly represents the logical "Barline Event".
4. **Iterate**: Once validated on the subset, proceed to full-scale GT preparation.
