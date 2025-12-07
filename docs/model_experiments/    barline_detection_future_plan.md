# Barline Detection – Future Strategy and Model Evaluation Summary
This document summarizes the current status, limitations, and future directions for improving barline detection and measure numbering in digitized sheet music. It complements the PDF report *“Barline Detection & Measure Numbering – Models Comparison.pdf”* and should be kept alongside it.

---

## 1. Current Status of the Project
### ✔ Achievements
- Built a robust evaluation pipeline for **HOMR** and **Oemer**.
- Implemented a **Safe Filter** (Heuristic 1) that reduced false positives from 35 → 30 without introducing any false negatives.
- Exhaustively explored local heuristics:
  - Staff-crossing  
  - Notehead proximity  
  - Cluster-resolution  
  - Tight-duplicate merging  
  - Measure-gap filtering  
- **All heuristics beyond the Safe Filter failed** due to causing unacceptable false negative rates.

### ❗ Key Conclusion
The remaining false positives (≈30) are *geometrically indistinguishable* from fragmented true barlines in page_3.  
Further heuristic optimization is no longer productive.

---

## 2. Motivation for Exploring New Models
We reached the structural limit of HOMR/Oemer:

- They do **not** have a class specifically trained for barlines.
- They cannot distinguish:
  - **thin stems**  
  - **broken/fragmented barlines**
- All FP reduction requires heuristic fixes, which have reached their practical limit.
- Improving performance requires **model-level redesign** or using **alternative OMR architectures** with explicit barline modeling.

Thus, the next phase shifts from heuristic engineering → model exploration.

---

## 3. Summary of External Model Investigation
Research shows five major model classes relevant to barline detection:

### 3.1 Oemer / HOMR (Baseline)
- High recall but poor precision due to stem confusion.
- Barline detection occurs *implicitly* via segmentation.
- Requires heavy post-processing.
- **Already explored to its limit in this project.**

---

### 3.2 YOLO-based Object Detectors (Recommended for Short-Term Success)
**Why promising:**
- Detects barlines directly as their own class.
- Stems can be cleanly separated by labeling.
- Very fast (real-time) and easy to fine-tune.
- Works well on imperfect scans or degraded print.
- Can be hybridized with the existing pipeline.

**Caveats:**
- Ultralytics YOLO is GPL-licensed → need ONNX export for commercial use.
- Requires bounding-box annotations.

**Overall: Best trade-off of accuracy, implementation cost, and training data size.**

---

### 3.3 Mask R-CNN (High-Accuracy Option)
**Strengths**
- Pixel-level segmentation of each barline.
- Handles broken or partially occluded barlines.
- Can explicitly separate stems from barlines.

**Weaknesses**
- Model is heavy; training requires more GPU time.
- Annotation (pixel masks) is more expensive.

**Use case:**
When accuracy is more important than training speed.

---

### 3.4 DETR + Relation Learning (Long-Term Potential)
**Advantages**
- Learns *relationships*:
  - stems attach to noteheads  
  - barlines stand independently  
- Reduces FP by learning semantics, not just geometry.

**Disadvantages**
- High implementation complexity.
- Requires datasets such as MUSCIMA++ with relationship labels.

**Use case:**
For advanced research or production systems requiring very high consistency across many pages.

---

### 3.5 End-to-End OMR (MusicXML Generation)
**Advantages**
- Learns musical grammar → avoids impossible bar patterns.
- Eliminates FP by predicting barline tokens directly.

**Disadvantages**
- Requires very large datasets.
- Overkill for the current goal of improving barline detection only.

**Use case:**
Long-term strategy if moving toward full OMR capability.

---

## 4. Recommended Multi-Phase Future Plan
### **Phase A — Documentation & Codebase Clean-up (Immediate)**
- Finalize development logs.
- Consolidate heuristic experiments and results in dedicated docs.
- Organize branches and experimental scripts.

### **Phase B — Build a GUI-Assisted FP Cleanup Tool**
Purpose:
- Accelerate GT creation.
- Quickly inspect FP/T P cases.
- Optional manual correction before training new models.

This can be simple (Python + Qt/Gradio) and created quickly.

### **Phase C — Explore New Detection Models (Parallel Tracks)**

#### Track C1 — YOLO Prototype (High Priority)
1. Create small barline/stem dataset.
2. Train YOLOv8/YOLO-NAS on barline detection.
3. Integrate with existing evaluator.
4. Compare FP, FN, and runtime against HOMR/Oemer.

#### Track C2 — Mask R-CNN Prototype
1. Use polygons/masks to train barline segmentation.
2. Evaluate robustness to broken barlines.

#### Track C3 — Hybrid Pipeline
- Combine HOMR notehead/stem predictions with YOLO barlines.
- Cross-validate predictions for higher precision.

#### Track C4 — Research Track (DETR or End-to-End)
- Optional long-term investment.
- Useful if project expands beyond simple measure numbering.

---

## 5. Future Considerations Beyond Detection
Even with perfect barline detection, measure numbering must handle:
- Repeats (start/end)
- Multiple staves per system
- Multi-measure rests
- Pickup measures (anacrusis)
- Segno/Coda jumps
- Section or movement boundaries

Later phases should include:
- **Topological measure graph construction**
- **Rule-based or ML-based measure indexing**
- **Verification against time signature** (optional)

---

## 6. Final Recommendation
Based on all results so far:

### **Short-Term (Practical):**
→ Implement a **YOLO barline detector** and integrate into current pipeline.

### **Medium-Term (Accurate):**
→ Explore **Mask R-CNN segmentation** with small curated dataset.

### **Long-Term (Advanced):**
→ Consider DETR or end-to-end OMR architectures for semantic reasoning.

---

## 7. File Connections
This document is intended to be stored side-by-side with:

- `Barline Detection & Measure Numbering – Models Comparison.pdf`
- Development logs from the heuristic project
- Future dataset planning documents
- GUI and training pipeline specifications

---

*Prepared for ongoing research and development toward reliable barline detection and automated measure numbering.*
