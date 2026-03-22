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

### Pipeline & Infrastructure
- **lesson_009**: Don't assume the current environment (e.g., `.venv_pdf`) has all ML dependencies. Always check `docs/ENVIRONMENTS.md` and use the specified container (e.g., `sr_eval_gpu`) for integrated runs.
- **lesson_010**: When using `gh pr comment` or other shell commands, be extremely careful with backticks (\`) in the body text. Use single quotes (`'`) for the entire body to prevent the shell from attempting to execute backticked text as commands.
- **lesson_011**: Global state in long-running processes (like `logging` handlers) must be restored in a `finally` block. Failing to do so causes handler accumulation and duplicate logs when `run_pipeline` is called multiple times in a single process (e.g., in notebooks or test suites).
- **lesson_012**: Avoid using subprocesses just for "environment handling" (e.g., `docker exec`). Instead, aim to unify dependencies so that heavy components (like `homr`) can be imported and executed in-process. This simplifies debugging and performance profiling.
- **lesson_013**: Before using specialized tools like `pr-viewer`, verify whether the target ID refers to a Pull Request or an Issue. Using `gh pr view` on an Issue ID will result in a "Could not resolve" error.
- **lesson_014**: When searching for specific execution logic (e.g., "how homr is called") in a refactored codebase, perform a recursive search across the entire module directory (e.g., `src/pipeline/`) rather than assuming it remains in the main entry point, as orchestration is often delegated to sub-modules.
- **lesson_015**: For high-complexity tasks that require architectural changes across multiple environments (like Docker image unification in Issue #7), prioritize creating a "Handoff Document" over immediate implementation. This ensures safety and maintains a clean context for the next focused session.
- **lesson_016**: When rescaling coordinates between different image resolutions (e.g., SR x2 to 1x), DO NOT cast to `int` until the very last step. Rounding before rescaling causes cumulative precision loss that can shift bounding boxes by several pixels, leading to CNN classifier rejection and False Negatives.
- **lesson_017**: In pipeline orchestration, ensure consistent pattern matching for supplementary files (e.g., staff masks). If the system expects `page_XXX.png` but the directory contains `page_XXX_staff.png`, the silent fallback to heuristics (like row-stats) can cause significant accuracy degradation that is hard to trace without detailed logging.
- **lesson_018**: When processing high-resolution (600dpi) or Super-Resolution (SR x2) images, hard-coded geometric constraints (like a `max_height` of 400px in the barline detector) will silently reject valid, full-page annotations as False Positives before CNN scoring. **Always dynamically scale pixel thresholds by `sr_scale` or `unit_size`** to prevent catastrophic recall regressions across different DPI runs.