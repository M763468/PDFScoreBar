---
## Project Status
The project goal is to develop an automated bar numbering tool for PDF scores, evaluating and improving two model pipelines: `homr` and `oemer`.

## Last Significant Update (2025-11-30, oemer Evaluation)
- Action: Validated Phase 28 `thin_barline_finder` improvements on oemer pipeline. Ran evaluation on same test score as homr to compare FP reduction effectiveness across both pipelines.
- Result: 
  - **homr**: TP=152, FP=35, FN=0, Precision=0.813, Recall=1.000, F1=0.897
  - **oemer**: TP=151, FP=34, FN=1, Precision=0.816, Recall=0.993, F1=0.896
  - FP counts nearly identical (34 vs 35), F1 scores nearly identical (0.896 vs 0.897)
  - oemer's 1 FN is due to ML model limitations, not heuristic regression
- Conclusion: Phase 28 FP reduction improvements are confirmed as shared improvements for both pipelines. Heuristic-based FP reduction has reached practical limit in both homr and oemer. Remaining FPs (32-35) are mostly stems requiring context-aware filtering.
- Log directories: `logs/20251130T185351JST/` (homr), `logs/oemer_eval/20251130_fp_reduction_test/` (oemer)

## Current Next Step
Explore context-based FP filtering approaches (notehead-stem pairing, staff structure analysis). Design and experiment with stem-context heuristics to address remaining 32-35 FPs that are geometrically similar to barlines.

## Blocking Issues
None. Context-based FP filtering and stem-context experiments are next priorities.
---