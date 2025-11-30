---
## Project Status
The project goal is to develop an automated bar numbering tool for PDF scores, evaluating and improving two model pipelines: `homr` and `oemer`.

## Last Significant Update (2025-11-30, Phase B)
- Action: Completed detailed analysis of remaining 35 FPs from the 2025-11-30 evaluation. Classified FPs into 3 groups: 1 removable (edge case), 2 borderline (risky), 32 unavoidable (stems/note-adjacent elements requiring advanced methods).
- Result: Determined that FP=35 represents the practical limit of heuristic-based reduction. Current metrics (Precision=0.813, Recall=1.000, F1=0.897) are near-optimal for rule-based approach. Remaining FPs are mostly true stems that geometrically resemble barlines.
- Conclusion: Further reduction requires ML-based classification or context-aware filtering (notehead-stem pairing, staff structure analysis).
- Log directory: `logs/20251130T185351JST/`

## Current Next Step
Port `thin_barline_finder` logic to oemer pipeline and evaluate impact. Explore design-phase work for context-based FP filtering (notehead-stem pairing).

## Blocking Issues
None. oemer integration and context-based filtering exploration are next priorities.
---