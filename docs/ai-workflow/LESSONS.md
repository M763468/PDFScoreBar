# AI Agent Lessons Learned (Feedback Loop)

## Lessons Registry

### General Anti-patterns
- **lesson_003**: Don't rely solely on Codex for visual artifact analysis; its sandbox lacks multi-modal depth compared to Gemini CLI's image-based reasoning.

### Geometric Detection
- **lesson_001**: Don't use \`row_filter\` for \`bypass\` mode TP candidates on \`page_001\` (it causes False Negatives due to ink fragmentation).
- **lesson_002**: Always prefer \`unit_size\` scaling over pixel-based thresholds for cross-resolution consistency.
- **lesson_004**: When debugging OMR False Positives, always generate and inspect overlay images (`debug_outputs/`) before modifying geometric filter logic.
- **lesson_007**: In FN_det analysis, separate "double/end-bar merging" from generic geometric mismatch; mixing them weakens root-cause reproducibility.
- **lesson_008**: Rule-only GT matching changes (IoU/IoA/center) do not change candidate sets, so measure-number KPI may stay unchanged; evaluate detector-side variants separately for KPI inversion checks.
- **lesson_016**: Detector-level FN/FP can overstate measure-count impact. Before changing detector heuristics for double/end-bar one-side FN or close duplicate FP, classify residuals by whether a neighboring matched prediction still preserves the logical measure boundary and run the downstream measure-count KPI.
- **lesson_017**: A stricter detector score threshold can improve downstream measure-count KPI even if detector FN rises slightly. For barline recovery work, compare `measure_delta` / `measure_abs_delta_sum` alongside `TP/FP/FN/FN_cnn/FN_det` before adopting or rejecting threshold and post-processing changes.
- **lesson_018**: In evaluation2 E2E recovery, short high-score candidates around 2.5-2.8 staff units can create internal false barlines that over-count measures. A unit-scaled minimum height sweep can improve downstream count KPI more reliably than max-height or x-distance NMS sweeps.
- **lesson_019**: Numbering-layer width thresholds should be staff-unit scaled, not fixed px. On evaluation2 full 68 pages, adopting `dedup=1.2u`, `implicit_start=4.0u`, and `min_measure_width=1.8u` reduced downstream measure-count abs delta without changing detector outputs.
- **lesson_020**: When a hard unit-height threshold fixes a local FP but creates FN elsewhere, test a score-guarded soft threshold before adopting the hard threshold. In evaluation2 full 68 pages, suppressing only candidates below `2.9u` with `score<0.9` removed a `2.88u` internal FP while preserving high-confidence short true bars.
- **lesson_021**: Low-ratio x-peak probe rescue can recover a local tall-band dilution FN but still increase CNN-surviving FPs at score level. Do not enable it from a single-page smoke; require at least a target-score detection report plus downstream measure-count KPI before adopting.
- **lesson_022**: Before another full Issue120 detector run, replay residuals against existing `probe_scan` artifacts and classify them as `candidate_absent`, `cnn_low_score_or_post_filter`, or `survived_filtered_unmatched_greedy`. Detector rescue should target only the first class; the others need CNN/post-filter, matching, or measure-count analysis.

### Pipeline & Infrastructure
- **lesson_009**: Don't assume the current environment (e.g., `.venv_pdf`) has all ML dependencies. Always check `docs/ENVIRONMENTS.md` and use the specified container (e.g., `sr_eval_gpu`) for integrated runs.
- **lesson_010**: When using `gh pr comment` or other shell commands, be extremely careful with backticks (\`) in the body text. Use single quotes (`'`) for the entire body to prevent the shell from attempting to execute backticked text as commands.
- **lesson_011**: Global state in long-running processes (like `logging` handlers) must be restored in a `finally` block. Failing to do so causes handler accumulation and duplicate logs when `run_pipeline` is called multiple times in a single process (e.g., in notebooks or test suites).
- **lesson_012**: Avoid using subprocesses just for "environment handling" (e.g., `docker exec`). Instead, aim to unify dependencies so that heavy components (like `homr`) can be imported and executed in-process. This simplifies debugging and performance profiling.
- **lesson_013**: Before using specialized tools like `pr-viewer`, verify whether the target ID refers to a Pull Request or an Issue. Using `gh pr view` on an Issue ID will result in a "Could not resolve" error.
- **lesson_014**: When searching for specific execution logic (e.g., "how homr is called") in a refactored codebase, perform a recursive search across the entire module directory (e.g., `src/pipeline/`) rather than assuming it remains in the main entry point, as orchestration is often delegated to sub-modules.
- **lesson_015**: For high-complexity tasks that require architectural changes across multiple environments (like Docker image unification in Issue #7), prioritize creating a "Handoff Document" over immediate implementation. This ensures safety and maintains a clean context for the next focused session.
