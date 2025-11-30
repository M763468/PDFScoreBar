---
## Project Status
The project goal is to develop an automated bar numbering tool for PDF scores, evaluating and improving two model pipelines: `homr` and `oemer`.

## Last Significant Update (2025-12-XX, Phase 30 Design)
- Action: Completed the design phase for context-based False Positive (FP) reduction. Analyzed the remaining ~35 FPs (mostly note stems) and designed three new heuristics leveraging musical context (notehead proximity, staff span, note group maps).
- Result: A clear, incremental plan has been formulated to implement and test these heuristics, starting with the lowest-risk "notehead proximity rejection" (Heuristic 1).
- Conclusion: The project has a well-defined path forward to address the practical limits of the current geometry-based heuristics. The next phase will involve implementation and testing.

## Current Next Step
Proceed with stem-context based FP reduction. The first step is to prepare for the experiment of Heuristic 1 (notehead proximity rejection). This involves investigating the architecture for passing context (like a notehead mask) to the post-processing stage.

## Blocking Issues
A design is needed for how to pass contextual information (e.g., `notehead_pred` mask) to the `thin_barline_finder` or a subsequent filtering step. An approach where filtering is applied as a post-processing step within the main evaluator script is being considered.
---