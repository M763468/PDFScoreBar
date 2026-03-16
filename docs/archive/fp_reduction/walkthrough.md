# Heuristic Optimization Project Summary

> [!NOTE]
> This document summarizes the heuristic experiments for FP reduction (Dec 2025).
> For the full project context and history, see [docs/DEVELOPMENT_LOG.md](../DEVELOPMENT_LOG.md).
> **Repo Restructure (Dec 2025)**: Experimental scripts moved to `experiments/fp_reduction/`.

## Objective
Reduce False Positives (FPs) in barline detection on `page_3` without introducing False Negatives (FNs).
**Baseline**: ~35 FPs.

## Journey & Results

### 1. Heuristic 1: Safe Filter (SUCCESS)
- **Logic**: Reject if `Dist_to_Notehead < 5` AND `Height < 24` AND `Width < 4` AND `Overlap >= 5`.
- **Result**: **-5 FPs**. 0 FNs.
- **Status**: **ENABLED**.
- **Current Metrics**: 152 TP, 30 FP, 0 FN.

### 2. Heuristic 2: Staff Crossing (FAILURE)
- **Logic**: Reject if `Staff_Crossings < 3` AND `Overlap < 5`.
- **Result**: Removed 5 FPs, but **18 FNs**.
- **Root Cause**: Many TPs are short fragments (crossing 0-2 lines).
- **Status**: **Reverted**.

### 3. Heuristic 3: Cluster Resolution (FAILURE)
- **Logic**: Keep strongest candidate in local cluster (<15px).
- **Result**: Removed 16 FPs, but **57 FNs**.
- **Root Cause**: TPs are often "weaker" (more fragmented) than nearby artifacts.
- **Status**: **Abandoned**.

### 4. Heuristic 4: Tight Duplicate Merging (FAILURE)
- **Logic**: Merge heavily overlapping candidates within 3px.
- **Result**: Removed 3 TPs. 0 FPs/Softs removed.
- **Root Cause**: Valid "Tight Double Barlines" exist at <3px spacing.
- **Status**: **Abandoned**.

### 5. Heuristic 5: Measure Grid Consistency (FAILURE)
- **Logic**: Global DP to find optimal rhythmic grid dimensions.
- **Result**: **68% of TPs** have gaps < 4px. Indistinguishable from FPs (80% < 4px).
- **Status**: **Abandoned**.

## Conclusion
We have reached the "Safety Limit" for heuristic filtering on this dataset. The remaining 30 FPs are geometrically identical to the valid but fragmented TPs. Further improvements require upstream changes (better Neural Network segmentation) or semantic music theory context (time signature awareness) which was outside the scope of this visual heuristic project.

**Final Recommendation**: Keep Heuristic 1 enabled. Do not enable Heuristics 2-5.
