---
## Project Status
The project goal is to develop an automated bar numbering tool for PDF scores, evaluating and improving two model pipelines: `homr` and `oemer`.

## Last Significant Update (2025-11-29)
- Action: Modified the `thin_barline_finder` cluster guard. The logic now checks for nearby existing detections before rejecting a tall, fragmented cluster. This prevents the guard from incorrectly removing valid barlines that span multiple staves.
- Result: The fix has been verified. The original FN case is resolved. New metrics: TP=152, FP=62, FN=0 (Precision=0.710, Recall=1.000, F1=0.831). There was a slight increase of 3 False Positives compared to the previous run (59 to 62).
- Log directory: `logs/eval_2025_11_29_1764397202/`

## Current Next Step
Analyze the 3 newly introduced False Positives from the latest evaluation run to identify their cause.

## Blocking Issues
None. Investigation of new False Positives is the immediate priority.
---