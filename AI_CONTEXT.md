---
## Project Status
The project goal is to develop an automated bar numbering tool for PDF scores, evaluating and improving two model pipelines: `homr` and `oemer`.

## Last Significant Update (2025-11-30)
- Action: Implemented FP reduction strategies in `thin_barline_finder`: (1) tightened height thresholds for W=1 candidates, (2) refined cluster guard rescue logic to require H≥20, (3) added light stem-suppression heuristic for single-side-override cases with W=1 and H<20.
- Result: Evaluation completed successfully. New metrics: TP=152, FP=35, FN=0 (Precision=0.813, Recall=1.000, F1=0.897). FP reduced from 62 to 35 (−27, 43.5% improvement). Perfect recall maintained.
- Log directory: `logs/20251130T185351JST/`

## Current Next Step
Analyze the remaining 35 FPs to determine whether further reduction is possible without compromising recall.

## Blocking Issues
None. FP analysis is the immediate priority.
---