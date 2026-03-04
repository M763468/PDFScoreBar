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

### Collaboration Successes
- **lesson_005**: Using Gemini for "Macro-Reasoning/Vision" and Codex for "Micro-Implementation/Type-Safety" significantly reduces regression risks and implementation time.
- **lesson_006**: For Codex-to-Gemini consultation, start with network-enabled execution and a longer timeout (e.g., `timeout 180s gemini -p "<prompt>"`), then keep prompts concise and split if needed.