---
## Project Status
The project goal is to develop an automated bar numbering tool for PDF scores, evaluating and improving two model pipelines: `homr` and `oemer`.

## Last Significant Update (2025-12-01, Phase 31)
- Action: Standardized the `homr` evaluation log path and executed an evaluation of Heuristic 1 (notehead proximity rejection).
- Result: The Heuristic 1 evaluation resulted in a catastrophic failure, with a massive increase in False Negatives (FN=100) that collapsed the F1 score, even though False Positives (FP) were reduced.
- Conclusion: The current implementation of Heuristic 1 is not viable and has been disabled. The root cause appears to be an overly aggressive notehead mask.

## Current Next Step
The immediate priority is to conduct a root cause analysis of the Heuristic 1 failure. This involves:
- Analyzing why Heuristic 1 (notehead proximity) failed catastrophically.
- Inspecting how the `notehead_pred` / notehead mask is generated, scaled, and aligned with the original image.
- Determining why the mask covers too much area, causing valid barlines to be incorrectly rejected as stems.
- Designing safer, more targeted stem-context heuristics or alternative ways to use contextual information for FP reduction.

## Blocking Issues
- Heuristic 1 is currently disabled due to the unacceptable increase in False Negatives.
- Further progress on context-based FP reduction is blocked until the quality and application of the notehead segmentation mask are understood and improved.

## Evaluation / Reproduction
- To re-run the homr evaluation for page_3, use the `homr_eval_gpu` container and the canonical command (see `docs/ENVIRONMENTS.md`).
- Evaluation outputs are now standardized under `logs/homr_eval/<run_id>/`.
---